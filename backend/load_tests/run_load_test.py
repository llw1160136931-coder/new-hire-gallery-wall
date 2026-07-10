import argparse
import json
import os
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_PASSWORD = 'LoadTest12345'


def setup_django():
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    import django

    django.setup()


def prepare_data(user_count):
    setup_django()
    from django.conf import settings
    from django.contrib.auth.models import User
    from rest_framework_simplejwt.tokens import RefreshToken

    from api.models import Like, TrainingCamp, Vote, Work

    database_name = str(settings.DATABASES['default']['NAME'])
    if 'loadtest' not in Path(database_name).name.lower() and os.environ.get('ALLOW_LOAD_TEST_DATA') != '1':
        raise RuntimeError(
            'Refusing to create load-test data outside a database whose filename contains "loadtest". '
            'Set DJANGO_DB_NAME to an isolated load-test database.'
        )

    camp = TrainingCamp.get_active()
    if not camp:
        raise RuntimeError('Load-test database has no active training camp.')

    users = []
    for index in range(user_count):
        username = f'loaduser{index:03d}'
        user, created = User.objects.get_or_create(username=username)
        if created or not user.has_usable_password():
            user.set_password(DEFAULT_PASSWORD)
            user.save(update_fields=['password'])
        users.append(user)

    target_works = []
    owner = users[0]
    for index in range(20):
        work, _ = Work.objects.update_or_create(
            camp=camp,
            author=owner,
            title=f'Load target {index:02d}',
            defaults={
                'work_type': Work.WorkType.AI,
                'description': 'Approved target used only by the isolated load test.',
                'status': Work.Status.APPROVED,
            },
        )
        target_works.append(work)

    load_work_ids = list(
        Work.objects.filter(camp=camp, title__startswith='Load submission ').values_list('id', flat=True)
    )
    if load_work_ids:
        Work.objects.filter(id__in=load_work_ids).delete()
    Like.objects.filter(user__in=users, work__in=target_works).delete()
    Vote.objects.filter(user__in=users, work__in=target_works).delete()

    return {
        'users': [
            {
                'username': user.username,
                'token': str(RefreshToken.for_user(user).access_token),
            }
            for user in users
        ],
        'target_ids': [work.id for work in target_works],
    }


def request_once(base_url, method, path, token=None, body=None, expected=(200,)):
    headers = {'Accept': 'application/json'}
    data = None
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')

    started = time.perf_counter()
    status = 0
    response_body = ''
    error = ''
    try:
        request = Request(f'{base_url}{path}', data=data, headers=headers, method=method)
        with urlopen(request, timeout=20) as response:
            status = response.status
            response_body = response.read(500).decode('utf-8', errors='replace')
    except HTTPError as exc:
        status = exc.code
        response_body = exc.read(500).decode('utf-8', errors='replace')
    except (URLError, TimeoutError, OSError) as exc:
        error = f'{type(exc).__name__}: {exc}'
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        'path': path.split('?')[0],
        'status': status,
        'expected': status in expected,
        'latency_ms': elapsed_ms,
        'error': error,
        'body': response_body,
    }


def scenario_steps(name, index, user, target_ids, loops):
    token = user['token']
    username = user['username']
    if name == 'login':
        return [
            ('POST', '/api/auth/token/', None, {'username': username, 'password': DEFAULT_PASSWORD}, (200,)),
        ]
    if name == 'public':
        return [
            ('GET', '/api/camps/current/', None, None, (200,)),
            ('GET', '/api/tags/popular/', None, None, (200,)),
        ] * loops
    if name == 'auth-read':
        return [
            ('GET', '/api/me/', token, None, (200,)),
            ('GET', '/api/courses/', token, None, (200,)),
            ('GET', '/api/works/', token, None, (200,)),
            ('GET', '/api/leaderboard/', token, None, (200,)),
            ('GET', '/api/search/?q=AI', token, None, (200,)),
        ] * loops
    if name == 'mixed':
        target_id = target_ids[index % len(target_ids)]
        return [
            ('GET', '/api/works/', token, None, (200,)),
            (
                'POST',
                '/api/works/',
                token,
                {
                    'title': f'Load submission {username}',
                    'work_type': 'ai',
                    'description': 'Concurrent load-test submission with enough content.',
                    'tags': ['并发测试'],
                },
                (201,),
            ),
            ('POST', f'/api/works/{target_id}/like/', token, {}, (201,)),
            ('POST', f'/api/works/{target_id}/vote/', token, {}, (201,)),
        ]
    raise ValueError(f'Unknown scenario: {name}')


def run_user(base_url, barrier, steps):
    barrier.wait()
    return [request_once(base_url, *step) for step in steps]


def percentile(values, percent):
    if not values:
        return 0
    ordered = sorted(values)
    position = min(round((len(ordered) - 1) * percent), len(ordered) - 1)
    return ordered[position]


def summarize(name, user_count, wall_seconds, results):
    latencies = [item['latency_ms'] for item in results]
    statuses = Counter(str(item['status']) if item['status'] else 'network_error' for item in results)
    by_path = defaultdict(lambda: {'requests': 0, 'failures': 0, 'latencies': []})
    for item in results:
        row = by_path[item['path']]
        row['requests'] += 1
        row['failures'] += int(not item['expected'])
        row['latencies'].append(item['latency_ms'])

    failure_samples = []
    for item in results:
        if not item['expected'] and len(failure_samples) < 8:
            failure_samples.append({
                'path': item['path'],
                'status': item['status'],
                'error': item['error'],
                'body': item['body'][:180],
            })

    return {
        'scenario': name,
        'concurrent_users': user_count,
        'requests': len(results),
        'successes': sum(item['expected'] for item in results),
        'failures': sum(not item['expected'] for item in results),
        'error_rate_percent': round(100 * sum(not item['expected'] for item in results) / max(len(results), 1), 2),
        'wall_seconds': round(wall_seconds, 3),
        'throughput_rps': round(len(results) / max(wall_seconds, 0.001), 2),
        'latency_ms': {
            'mean': round(statistics.mean(latencies), 2) if latencies else 0,
            'p50': round(percentile(latencies, 0.50), 2),
            'p95': round(percentile(latencies, 0.95), 2),
            'p99': round(percentile(latencies, 0.99), 2),
            'max': round(max(latencies), 2) if latencies else 0,
        },
        'statuses': dict(statuses),
        'paths': {
            path: {
                'requests': row['requests'],
                'failures': row['failures'],
                'p95_ms': round(percentile(row['latencies'], 0.95), 2),
            }
            for path, row in sorted(by_path.items())
        },
        'failure_samples': failure_samples,
    }


def main():
    parser = argparse.ArgumentParser(description='Run isolated 100-user load scenarios against the training wall API.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8011')
    parser.add_argument('--users', type=int, default=100)
    parser.add_argument('--loops', type=int, default=1)
    parser.add_argument('--scenario', choices=['login', 'public', 'auth-read', 'mixed'], required=True)
    args = parser.parse_args()

    prepared = prepare_data(args.users)
    barrier = threading.Barrier(args.users)
    all_results = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.users) as executor:
        futures = [
            executor.submit(
                run_user,
                args.base_url,
                barrier,
                scenario_steps(args.scenario, index, user, prepared['target_ids'], args.loops),
            )
            for index, user in enumerate(prepared['users'])
        ]
        for future in as_completed(futures):
            all_results.extend(future.result())
    summary = summarize(args.scenario, args.users, time.perf_counter() - started, all_results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
