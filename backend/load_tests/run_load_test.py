"""Deprecated compatibility entry point.

The former ad-hoc load generator used a fixed password and is intentionally
retired. Use run_suite.py and the documented isolated Locust workflow instead.
"""

from pathlib import Path


def main() -> int:
    guide = Path(__file__).with_name('README.md')
    print(
        'This legacy load-test script is disabled. '
        f'Use run_suite.py and follow {guide}.'
    )
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
