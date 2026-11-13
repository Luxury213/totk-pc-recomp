"""Build the isolated 1.4.3 co-op diagnostic executable and role launchers, without changing an installed game.

    .venv/Scripts/python tools/build_coop.py --game-dir <installed-game-folder> --jobs 6

Native actor/control integration is gated off. A successful build is not a playable multiplayer campaign.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from check_content import GENERATED_MARKER


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def install_figure(source, target):
    """Install a validated immutable figure without duplicating it on the same volume.

    Only figure assets use this path, never writable saves. Atomic replacement preserves existing hardlink
    snapshots when preparation installs a new source. Filesystems without hardlinks use an ordinary copy.
    """
    source, target = Path(source), Path(target)
    if source.name != 'link-figure.bin' or target.name != 'link-figure.bin':
        raise ValueError('only immutable link-figure.bin assets may be shared')
    if target.exists() and os.path.samefile(source, target):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.{uuid.uuid4().hex}.tmp')
    try:
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def run(command, log, env):
    print('Running:', ' '.join(map(str, command)), flush=True)
    with log.open('w', encoding='utf-8') as f:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(log.read_text(encoding='utf-8', errors='replace').splitlines()[-25:]))
        raise SystemExit(f'Failed ({result.returncode}); see {log}')


def package(game, out):
    folder = out / 'game'
    exe = folder / 'totk.exe'
    if not exe.is_file():
        raise SystemExit(f'{exe} does not exist; build first')
    shutil.copy2(exe, folder / 'totk-coop.exe')
    for name in ('totk_xlate.exe', 'totk_xlate.id'):
        source = game / name
        if not source.is_file():
            raise SystemExit(f'{source} missing; build the shader translator before a gameplay test')
        shutil.copy2(source, folder / name)
    (folder / 'licenses').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'runtime/third_party/enet/LICENSE', folder / 'licenses/ENet-LICENSE.txt')
    shutil.copy2(ROOT / 'runtime/third_party/licenses/totk-recomp.txt', folder / 'licenses/totk-recomp-LICENSE.txt')
    figure = out / 'assets/link-figure.bin'
    if figure.is_file():
        manifest = json.loads(figure.with_suffix('.json').read_text(encoding='utf-8'))
        if manifest.get('format') != 'LNKF' or manifest.get('version') != 4 or digest(figure) != manifest.get('sha256'):
            raise SystemExit('The prepared co-op figure does not match its manifest; prepare it again')
    # Deliberately use fresh host/client profiles. An advanced save belongs only to a separate test profile.
    for role in ('host', 'client', 'bot'):
        profile = out / 'profiles' / role
        profile.mkdir(parents=True, exist_ok=True)
        if figure.is_file():
            install_figure(figure, profile / 'link-figure.bin')
        lines = ['@echo off', 'chcp 65001 >nul', f'@rem {GENERATED_MARKER}', 'setlocal',
                 f'set "TOTK_COOP_MODE={role}"', 'set "TOTK_COOP_PORT=7777"']
        if role == 'client':
            lines += ['set "TOTK_COOP_IP="', 'set /p "TOTK_COOP_IP=Host IPv4 address on your private VPN: "']
        lines += [f'cd /d "{folder}"',
                  f'"{folder / "totk-coop.exe"}" --exefs "{game / "exefs"}" --romfs "{game / "romfs"}" '
                  f'--profile "{profile}"', 'if errorlevel 1 pause', 'endlocal']
        (out / f'start-{role}.bat').write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')
    record = dict(marker=GENERATED_MARKER, game_version='1.4.3', protocol=3, native_gameplay_enabled=False,
                  executable_sha256=digest(folder / 'totk-coop.exe'),
                  exefs=str(game / 'exefs'), romfs=str(game / 'romfs'),
                  profiles=str(out / 'profiles'), status='Presence and native integration diagnostics only')
    (out / 'build-info.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    (out / 'README.txt').write_text(
        'Experimental co-op diagnostics, not a playable cooperative campaign.\n'
        'Use start-host.bat / start-client.bat on the private VPN, or start-bot.bat for the visual test.\n'
        'A prepared Link model is a visual diagnostic; missing assets use an overlay silhouette.\n'
        'Session-controlled native companions, world pause and progression remain disabled.\n'
        'Separate copied-profile weapon probes are documented in docs/coop-development.md.\n'
        'Profiles are isolated here. Existing co-op binaries elsewhere have not been replaced.\n'
        'Set TOTK_COOP_TRACE_GUEST=1 before launching to collect bounded native function observations.\n',
        encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game-dir', required=True, type=Path)
    ap.add_argument('--out', type=Path, default=ROOT / 'build/coop-v143')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--package-only', action='store_true', help='package and probe an already built isolated executable')
    args = ap.parse_args()
    game, out = args.game_dir.resolve(), args.out.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()) or out == (ROOT / 'build').resolve():
        ap.error('--out must be a dedicated directory below this repository\'s build/')
    if game == out or out.is_relative_to(game) or game.is_relative_to(out):
        ap.error('the installed game and co-op output must be separate directories')
    expected = json.loads((ROOT / 'tools/data/expected-v1.4.3.json').read_text())['exefs_sha256']
    for name, sha in expected.items():
        source = game / 'exefs' / name
        if not source.is_file() or digest(source) != sha:
            raise SystemExit(f'{source}: not the verified 1.4.3 input')
    if not (game / 'romfs/index.json').is_file() or not (game / 'romfs/romfs.bin').is_file():
        raise SystemExit('The installed RomFS must include index.json and romfs.bin')
    if sys.version_info[:2] != (3, 12):
        raise SystemExit('Run this build with .venv/Scripts/python.exe (Python 3.12)')
    ucrt = Path('C:/msys64/ucrt64/bin')
    for tool in ('clang.exe', 'ninja.exe', 'llvm-ar.exe'):
        if not (ucrt / tool).is_file():
            raise SystemExit(f'{ucrt / tool} missing; restore the MSYS2 toolchain in docs/building.md')
    env = dict(os.environ, PATH=str(ucrt) + os.pathsep + os.environ.get('PATH', ''))
    out.mkdir(parents=True, exist_ok=True)
    if not args.package_only:
        inputs = dict(marker=GENERATED_MARKER, **{name: digest(game / 'exefs' / name) for name in expected})
        inputs['generator'] = hashlib.sha256(b''.join(
            p.relative_to(ROOT).as_posix().encode() + p.read_bytes()
            for p in sorted((ROOT / 'recomp').rglob('*')) if p.suffix in ('.py', '.txt'))).hexdigest()
        stamp = out / 'generation-inputs.json'
        try:
            previous = json.loads(stamp.read_text()) if stamp.is_file() else None
        except (OSError, json.JSONDecodeError):
            previous = None
        if previous != inputs or not (out / 'generated/layout.json').is_file():
            run([sys.executable, ROOT / 'recomp/gen.py', '--exefs', game / 'exefs', '--out', out / 'generated',
                 '--patches', ROOT / 'recomp/patches-v143.txt', '--jobs', args.jobs], out / 'generate.log', env)
            temporary = stamp.with_suffix('.tmp')
            temporary.write_text(json.dumps(inputs, indent=2) + '\n', encoding='utf-8')
            temporary.replace(stamp)
        common = [sys.executable, ROOT / 'tools/build_game.py', '--version', 'v143', '--gen', out / 'generated',
                  '--exefs', game / 'exefs', '--romfs', game / 'romfs',
                  '--profile', out / 'profiles/test', '--jobs', args.jobs]
        run([*common, '--out', out / 'runtime', '--make-runtime-lib'], out / 'runtime-build.log', env)
        run([*common, '--out', out / 'game', '--runtime-lib', out / 'runtime/libtotkrt.a'], out / 'game-build.log', env)
    for probe in ('--selftest', '--probe-cfg'):
        run([out / 'game/totk.exe', probe], out / (probe[2:] + '.log'), env)
    package(game, out)
    print(f'Co-op diagnostic build ready: {out / "game/totk-coop.exe"}')


if __name__ == '__main__':
    main()
