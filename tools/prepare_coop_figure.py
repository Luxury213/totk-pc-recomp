"""Prepare the visual co-op Link from the user's indexed RomFS. Requires Python 3.14 and McSharp.

All model/texture/animation outputs stay under build/ or generated/. This does not modify the game.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from check_content import GENERATED_MARKER

ROOT = Path(__file__).resolve().parents[1]


def private_output(value):
    path = Path(value).resolve()
    if not any(path.is_relative_to(ROOT / base) and path != ROOT / base for base in ('build', 'generated')):
        raise argparse.ArgumentTypeError('figure output and work paths must be below build/ or generated/')
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--romfs', required=True, type=Path)
    ap.add_argument('--mcsharp', required=True, type=Path)
    ap.add_argument('--out', type=private_output, default=ROOT / 'build/coop-v143/assets/link-figure.bin')
    ap.add_argument('--work', type=private_output, default=ROOT / 'build/coop-v143/figure-work')
    args = ap.parse_args()
    if sys.version_info < (3, 14):
        ap.error('run with .venv-py314/Scripts/python.exe (compression.zstd is required)')
    import link_figure
    args.out.parent.mkdir(parents=True, exist_ok=True)
    romfs = link_figure.RomFS(args.romfs)
    try:
        models = link_figure.prepare(romfs, args.mcsharp.resolve(), args.work)
    finally:
        romfs.rom.close()
    temporary = args.out.with_suffix('.tmp')
    link_figure.main(['link_figure.py', str(models), str(args.romfs), str(temporary)])
    temporary.replace(args.out)
    info = dict(marker=GENERATED_MARKER, upstream_revision='7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c',
                format='LNKF', version=4, bytes=args.out.stat().st_size,
                sha256=hashlib.file_digest(args.out.open('rb'), 'sha256').hexdigest())
    args.out.with_suffix('.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    print('Prepared visual diagnostic asset:', args.out)


if __name__ == '__main__':
    main()
