"""Generate deterministic, privacy-safe files for upload load tests.

Images are valid JPEG files padded to the requested size. Video fixtures can
either preserve a real MP4 supplied by the operator or use a minimal MP4-like
container that is sufficient for upload-throughput and signature validation
tests (but is intentionally not advertised as playable media).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image


MIB = 1024 * 1024
MAX_FIXTURE_MIB = 500


def parse_sizes(raw: str) -> list[int]:
    sizes: list[int] = []
    for value in raw.split(','):
        value = value.strip()
        if not value:
            continue
        size = int(value)
        if size < 1 or size > MAX_FIXTURE_MIB:
            raise argparse.ArgumentTypeError(
                f'fixture sizes must be between 1 and {MAX_FIXTURE_MIB} MiB'
            )
        if size not in sizes:
            sizes.append(size)
    if not sizes:
        raise argparse.ArgumentTypeError('at least one fixture size is required')
    return sizes


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(MIB):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_target(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f'{path} already exists; pass --force to replace it')
    path.parent.mkdir(parents=True, exist_ok=True)


def make_jpeg(path: Path, size_mib: int, *, force: bool) -> dict[str, object]:
    ensure_target(path, force=force)
    canvas = Image.new('RGB', (1280, 720), color=(232, 48, 68))
    buffer = BytesIO()
    canvas.save(buffer, format='JPEG', quality=92, optimize=True)
    payload = buffer.getvalue()
    target_size = size_mib * MIB
    if len(payload) > target_size:
        raise ValueError(f'generated JPEG is larger than requested size: {path}')
    with path.open('wb') as output:
        output.write(payload)
        output.truncate(target_size)
    return fixture_record(path, 'image/jpeg', playable=True)


def minimal_mp4_header() -> bytes:
    compatible_brands = b'isomiso2'
    ftyp_payload = b'isom' + struct.pack('>I', 0x200) + compatible_brands
    ftyp = struct.pack('>I4s', 8 + len(ftyp_payload), b'ftyp') + ftyp_payload
    # A zero-sized mdat extends to EOF. It is structurally useful for transfer
    # tests, while a real source file is required for browser playback checks.
    return ftyp + struct.pack('>I4s', 0, b'mdat')


def make_mp4(
    path: Path,
    size_mib: int,
    *,
    source: Path | None,
    force: bool,
) -> dict[str, object]:
    ensure_target(path, force=force)
    target_size = size_mib * MIB
    playable = False
    if source:
        if not source.is_file():
            raise FileNotFoundError(f'video source does not exist: {source}')
        if source.stat().st_size > target_size:
            raise ValueError(
                f'{source} is larger than the requested {size_mib} MiB fixture'
            )
        shutil.copyfile(source, path)
        playable = True
    else:
        path.write_bytes(minimal_mp4_header())
    with path.open('r+b') as output:
        output.truncate(target_size)
    return fixture_record(path, 'video/mp4', playable=playable)


def fixture_record(path: Path, content_type: str, *, playable: bool) -> dict[str, object]:
    return {
        'path': str(path.resolve()),
        'file_name': path.name,
        'content_type': content_type,
        'size_bytes': path.stat().st_size,
        'sha256': sha256_file(path),
        'playable': playable,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).with_name('fixtures'))
    parser.add_argument('--image-mib', type=parse_sizes, default=parse_sizes('2,5'))
    parser.add_argument('--video-mib', type=parse_sizes, default=parse_sizes('50,100'))
    parser.add_argument(
        '--video-source',
        type=Path,
        help='Optional real MP4 to preserve playability; it is padded to each requested size.',
    )
    parser.add_argument('--force', action='store_true', help='Replace existing fixtures.')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for size_mib in args.image_mib:
        records.append(
            make_jpeg(
                args.output_dir / f'loadtest-image-{size_mib}mib.jpg',
                size_mib,
                force=args.force,
            )
        )
    for size_mib in args.video_mib:
        records.append(
            make_mp4(
                args.output_dir / f'loadtest-video-{size_mib}mib.mp4',
                size_mib,
                source=args.video_source,
                force=args.force,
            )
        )
    manifest = args.output_dir / 'manifest.json'
    manifest.write_text(
        json.dumps({'fixtures': records}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    assets_csv = args.output_dir / 'assets.csv'
    with assets_csv.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(
            output,
            fieldnames=['kind', 'path', 'content_type', 'sha256', 'playable'],
        )
        writer.writeheader()
        for record in records:
            writer.writerow({
                'kind': 'image' if str(record['content_type']).startswith('image/') else 'video',
                'path': record['path'],
                'content_type': record['content_type'],
                'sha256': record['sha256'],
                'playable': int(bool(record['playable'])),
            })
    print(
        f'Generated {len(records)} fixtures. '
        f'Manifest: {manifest.resolve()}; Locust CSV: {assets_csv.resolve()}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
