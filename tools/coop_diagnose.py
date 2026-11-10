"""Observe the native co-op integration gate in one background game instance on an isolated save copy.

No native spawning, teleport, physics writes or original-profile changes are performed.
"""
import argparse
import csv
from collections import Counter
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def save_hashes(path):
    return {p.relative_to(path).as_posix(): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir', type=Path, default=ROOT / 'build/coop-v143')
    ap.add_argument('--seed-profile', required=True, type=Path, help='offline profile to copy for this diagnostic only')
    ap.add_argument('--seconds', type=float, default=5, help='game seconds after the save loads')
    ap.add_argument('--timeout', type=float, default=240, help='wall-clock ceiling, including loading')
    ap.add_argument('--input-script', type=Path, help='override the diagnostic\'s repeating title-screen confirmation')
    args = ap.parse_args()
    output, seed = args.build_dir.resolve(), args.seed_profile.resolve()
    if not output.is_relative_to((ROOT / 'build').resolve()):
        ap.error('--build-dir must be below the repository build/ directory')
    if os.name != 'nt':
        ap.error('the diagnostic runner currently targets Windows')
    rows = csv.reader(subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True,
                                     text=True, check=True).stdout.splitlines())
    if any(row and row[0].lower() in ('totk.exe', 'totk-coop.exe') for row in rows):
        raise SystemExit('A game instance is already running. No diagnostic was launched and no process was stopped.')
    if not (seed / 'save').is_dir():
        ap.error('--seed-profile must contain a save directory')
    info = json.loads((output / 'build-info.json').read_text(encoding='utf-8'))
    exe = output / 'game/totk-coop.exe'
    if hashlib.file_digest(exe.open('rb'), 'sha256').hexdigest() != info['executable_sha256']:
        raise SystemExit('The executable differs from the packaged build; repackage before diagnosing')
    folder = output / 'diagnostics' / ('run-' + uuid.uuid4().hex[:10])
    profile = folder / 'profile'
    profile.mkdir(parents=True)
    before = save_hashes(seed / 'save')
    shutil.copytree(seed / 'save', profile / 'save')
    if (seed / 'account.uid').is_file():
        shutil.copy2(seed / 'account.uid', profile / 'account.uid')
    if before != save_hashes(profile / 'save') or before != save_hashes(seed / 'save'):
        raise SystemExit(f'The source save changed during copying; diagnostic not launched. Copy retained at {folder}')
    script = args.input_script.resolve() if args.input_script else folder / 'input.txt'
    if not args.input_script:
        script.write_text('# Diagnostic title navigation; stop after the world-clock run completes.\n' +
                          ''.join(f'{tick} A 4\n' for tick in range(180, int(args.timeout * 60) + 180, 180)),
                          encoding='utf-8')
    env = dict(os.environ, TOTK_COOP_MODE='bot', TOTK_COOP_TRACE_GUEST='1', TOTK_BACKGROUND_WINDOW='1',
               TOTK_ASSUME_FOCUS='1',
               TOTK_INPUT='none', TOTK_INPUT_SCRIPT=str(script),
               TOTK_FPS_LIMIT='30', TOTK_OPERATION_MODE='handheld',
               TOTK_OUTPUT_RES='1280x720', TOTK_WINDOW_SIZE='1280x720', TOTK_DLAA='0')
    # Explicit game assets from the verified build manifest; only the new profile is writable.
    command = [str(exe), '--exefs', info['exefs'], '--romfs', info['romfs'], '--profile', str(profile),
               '--seconds', str(args.seconds), '--shot', str(folder / 'last-frame.png')]
    started = time.monotonic()
    timed_out = False
    log = folder / 'guest.log'
    with log.open('w', encoding='utf-8') as f:
        process = subprocess.Popen(command, cwd=output / 'game', env=env, stdout=f, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            result = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()   # only this runner's own child, never an existing game instance
            result = process.wait()
    lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
    observations = [line for line in lines if 'coop adapter:' in line]
    traces = [line for line in lines if 'coop native trace:' in line]
    candidates = [line for line in lines if 'coop native candidate:' in line]
    vtables = [line for line in lines if 'coop native vtable:' in line]
    constructors = [line for line in lines if 'coop native constructor:' in line]
    constructor_budgets = [line for line in lines if 'coop native constructor budget:' in line]
    scene_resident_observations = [line for line in lines if 'coop native scene resident:' in line]
    kinds = Counter(match[1] for line in traces if (match := re.search(r'kind ([a-z_]+);', line)))
    intact = before == save_hashes(seed / 'save')
    report = dict(executable_sha256=info['executable_sha256'], exit_code=result, timed_out=timed_out,
                  elapsed_seconds=round(time.monotonic() - started, 2), source_save_unchanged=intact,
                  observations=observations, native_function_observations=traces,
                  native_method_candidates=candidates, native_vtable_observations=vtables,
                  native_constructor_observations=constructors,
                  native_constructor_budgets=constructor_budgets,
                  native_scene_resident_observations=scene_resident_observations,
                  native_trace_kinds=dict(kinds),
                  player_epoch_trace_count=sum('generation ' in line for line in traces),
                  playable_actor_observed=any('player observed' in line for line in observations),
                  native_actor_creation_verified=False, world_mutation_phase_verified=False,
                  native_gameplay_enabled=False, log=str(log))
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result == 0 and intact and report['playable_actor_observed'] else 1)


if __name__ == '__main__':
    main()
