"""Observe the native co-op integration gate in one background game instance on an isolated save copy.

Read-only by default. --native-clone-weapon or --native-owned-weapon enables one bounded native creation experiment
on the copied profile.
No teleport, host physics writes or original-profile changes are performed.
"""
import argparse
import csv
from collections import Counter
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from coop_native_audit import PROBE_ACTOR, PROBE_TEARDOWN, PROBE_ALLOCATOR, RESOURCE_BIND, RESOURCE_CLEANUP
from build_coop import install_figure

ROOT = Path(__file__).resolve().parents[1]
CONTROL_EVENTS = ((2000, 'LSTICK -32767 0 2000', 'LSTICK -32767 0'),
                  (5000, 'RSTICK 32767 0 1000', 'RSTICK 32767 0'),
                  (7000, 'Y 100', 'Y'), (9000, 'Y 100', 'Y'))
LOCAL_SAMPLE = re.compile(r'world ms (\d+(?:\.\d+)?), generation (\d+), '
                          r'pos (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?), '
                          r'yaw (-?\d+(?:\.\d+)?), action (\d+);')
TIMED_INPUT = re.compile(r'input: script frame \d+ at (\d+(?:\.\d+)?) ms: (.+)$')
VISUAL_SAMPLE = re.compile(r'coop visual sample: world ms (\d+(?:\.\d+)?), generation (\d+), '
                           r'rotation (observed|absent), animation ([A-Za-z0-9_]+), frame (\d+(?:\.\d+)?);')
PLAYER_OBSERVATION = re.compile(r'coop adapter: generation (\d+), player (observed|absent),')
TEARDOWN_CLEANUP = re.compile(r'coop native actor teardown: .*stage cleanup, observed player same, generation (\d+),')
PLAYER_CONTINUITY = re.compile(r'coop native player continuity: generation (\d+), original generation (\d+), '
                               r'actor metadata id same, constructor entries (\d+), limit (\d+);')


def diagnostic_script(timeout, scenario):
    title = ''.join(f'{tick} A 4\n' for tick in range(180, int(timeout * 60) + 180, 180))
    # A timed line makes input.c stop every untimed title confirmation once the world clock starts.
    world = ''.join(f'@{at} {event}\n' for at, event, _ in CONTROL_EVENTS) if scenario == 'controls' else '@0 LSTICK 0 0 1\n'
    return '# Title confirmation ends at world start; timed actions use the copied save only.\n' + title + world


def local_control_summary(lines):
    samples, inputs = [], []
    for line in lines:
        if 'coop native local sample:' in line and (m := LOCAL_SAMPLE.search(line)):
            values = [float(m[i]) for i in (1, 3, 4, 5, 6)]
            if not all(map(math.isfinite, values)):
                continue
            samples.append(dict(world_ms=values[0], generation=int(m[2]), pos=values[1:4], yaw=values[4], action=int(m[7])))
        if m := TIMED_INPUT.search(line):
            if math.isfinite(at := float(m[1])):
                inputs.append(dict(world_ms=at, event=m[2].strip()))
    origins, maximum = {}, 0.0
    for sample in samples:
        origin = origins.setdefault(sample['generation'], sample['pos'])
        maximum = max(maximum, math.dist(origin, sample['pos']))
    next_input = 0
    matched = []
    for at, command, event in CONTROL_EVENTS:
        while next_input < len(inputs):
            item = inputs[next_input]
            next_input += 1
            if item['event'] == event and at <= item['world_ms'] <= at + 500:
                matched.append((item, float(command.split()[-1])))
                break
    # Loading may settle the actor before input. Require horizontal movement within the actual walk
    # interval, with a nearby baseline and no generation change. Total displacement is informational.
    control_maximum = 0.0
    if matched and matched[0][0]['event'] == CONTROL_EVENTS[0][2]:
        walk, duration = matched[0]
        start, end = walk['world_ms'], walk['world_ms'] + duration
        before = [s for s in samples if start - 500 <= s['world_ms'] <= start]
        if before:
            baseline = max(before, key=lambda s: s['world_ms'])
            during = [s for s in samples if start < s['world_ms'] <= end + 250]
            if during and all(s['generation'] == baseline['generation'] for s in during):
                control_maximum = max(math.dist(baseline['pos'][::2], s['pos'][::2]) for s in during)
    return dict(samples=samples, timed_inputs=inputs, max_displacement=round(maximum, 6),
                max_control_displacement=round(control_maximum, 6),
                generations=sorted(origins), scripted_events_applied=len(matched) == len(CONTROL_EVENTS),
                movement_observed=control_maximum >= 0.1, camera_independence_verified=False,
                native_companion_verified=False)


def visual_summary(lines):
    local = {(float(m[1]), int(m[2])) for line in lines
             if 'coop native local sample:' in line and (m := LOCAL_SAMPLE.search(line))}
    samples, latest = [], {}
    advancing = False
    for line in lines:
        if not (m := VISUAL_SAMPLE.search(line)):
            continue
        at, generation, frame = float(m[1]), int(m[2]), float(m[5])
        if (at, generation) not in local or not math.isfinite(frame):
            continue
        name = m[4]
        samples.append(dict(world_ms=at, generation=generation, rotation_observed=m[3] == 'observed',
                            animation=name if name != 'unavailable' else None, frame=frame))
        if name != 'unavailable':
            previous = latest.get((generation, name))
            if previous and at > previous[0] and frame > previous[1]:
                advancing = True
            latest[generation, name] = at, frame
    return dict(samples=samples, animation_names=sorted({name for _, name in latest}),
                rotation_observed=any(s['rotation_observed'] for s in samples),
                animation_advancing=advancing, native_companion_verified=False)


def reload_summary(lines):
    observations = [(int(m[1]), m[2] == 'observed') for line in lines if (m := PLAYER_OBSERVATION.search(line))]
    players = sorted({g for g, present in observations if present})
    cleanups = sorted({int(m[1]) for line in lines if (m := TEARDOWN_CLEANUP.search(line))})
    constructors = sum('coop native constructor:' in line and 'observed player same;' in line for line in lines)
    # A menu press, disappearance or scene-generation change alone does not establish an actor reload.
    reloaded = constructors >= 2 and any(g in players and any(new > g for new in players) for g in cleanups)
    seen_player = seen_loss = returned = False
    for _, present in observations:
        if present:
            returned |= seen_loss
            seen_player = True
        elif seen_player:
            seen_loss = True
    continuity = [dict(generation=int(m[1]), original_generation=int(m[2]),
                       constructor_entries=int(m[3]), constructor_limit=int(m[4]))
                  for line in lines if (m := PLAYER_CONTINUITY.search(line))]
    return dict(player_generations=players, cleanup_generations=cleanups,
                matched_constructor_count=constructors, actor_recreation_observed=reloaded,
                player_return_observed=returned, identity_continuity=continuity,
                native_actor_removal_verified=False, native_companion_verified=False)


def probe_summary(lines, target_name=None, require_allocator=False, require_resource=False):
    probes, resources = {}, {}
    for line in lines:
        if 'coop native probe actor:' in line and (m := PROBE_ACTOR.search(line)):
            probe = int(m[3])
            if probe not in probes:
                probes[probe] = dict(probe=probe, name=m[4], generation=int(m[5]), stages=[], invalid=False,
                                     request=int(m[7]) if m[7] else None, queue_pending=False, allocator_handoff_observed=False)
            else:
                probes[probe]['invalid'] = True
        elif 'coop native probe teardown:' in line and (m := PROBE_TEARDOWN.search(line)):
            probe = probes.get(int(m[3]))
            if probe is None:
                continue
            if probe['name'] != m[4] or m[5] in probe['stages']:
                probe['invalid'] = True
            probe['stages'].append(m[5])
            if m[5] == 'queue':
                probe['queue_pending'] = m[8] == 'yes'
        elif 'coop native probe allocator:' in line and (m := PROBE_ALLOCATOR.search(line)):
            probe = probes.get(int(m[3]))
            if probe is None:
                continue
            if probe['name'] != m[4] or probe['stages'] != ['request', 'queue', 'cleanup'] or probe['allocator_handoff_observed']:
                probe['invalid'] = True
            probe['allocator_handoff_observed'] = True
        elif 'coop native resource binding:' in line and (m := RESOURCE_BIND.search(line)):
            request = int(m[3])
            if request in resources:
                resources[request]['invalid'] = True
            else:
                resources[request] = dict(name=m[4], invalid=False, cleanup=None)
        elif 'coop native resource cleanup:' in line and (m := RESOURCE_CLEANUP.search(line)):
            resource = resources.get(int(m[3]))
            if resource is not None:
                if resource['name'] != m[4] or resource['cleanup'] is not None:
                    resource['invalid'] = True
                resource['cleanup'] = m[5] == 'same'
    for probe in probes.values():
        probe['observed_lifecycle_complete'] = (not probe['invalid'] and probe['queue_pending'] and
                                                 probe['stages'] == ['request', 'queue', 'cleanup'])
        resource = resources.get(probe['request'])
        probe['resource_lifetime_observed'] = bool(resource and not resource['invalid'] and
                                                   resource['name'] == probe['name'] and resource['cleanup'] is True)
        probe['acceptance_passed'] = (probe['observed_lifecycle_complete'] and
                                      (target_name is None or probe['name'] == target_name) and
                                      (not require_allocator or probe['allocator_handoff_observed']) and
                                      (not require_resource or probe['resource_lifetime_observed']))
    return dict(probes=list(probes.values()),
                target_name=target_name,
                observed_lifecycle_complete=any(p['observed_lifecycle_complete'] and
                                               (target_name is None or p['name'] == target_name) for p in probes.values()),
                allocator_handoff_observed=any(p['observed_lifecycle_complete'] and p['allocator_handoff_observed'] and
                                              (target_name is None or p['name'] == target_name) for p in probes.values()),
                resource_lifetime_observed=any(p['observed_lifecycle_complete'] and p['resource_lifetime_observed'] and
                                              (target_name is None or p['name'] == target_name) for p in probes.values()),
                acceptance_passed=any(p['acceptance_passed'] for p in probes.values()),
                resource_ownership_verified=False,
                native_actor_removal_verified=False, native_companion_verified=False)


def save_hashes(path):
    return {p.relative_to(path).as_posix(): hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file()}


def spawn_fall_summary(samples, origin):
    """Require a correlated start, several downward steps and later rest; a teleport is insufficient."""
    absent = dict(origin_matched=False, descent_observed=False, settled_after_descent=False,
                  descent_distance=0.0, acceptance_passed=False)
    if len(samples) < 8 or any(b['world_us'] <= a['world_us'] for a, b in zip(samples, samples[1:])):
        return absent
    if any((s['probe'], s['request']) != (samples[0]['probe'], samples[0]['request']) for s in samples):
        return absent
    start = next((i for i, s in enumerate(samples) if math.dist(s['pos'], origin) <= .2), None)
    if start is None:
        return absent
    samples = samples[start:]
    steps, distance, descent_at = 0, 0.0, None
    for a, b in zip(samples, samples[1:]):
        dy = a['pos'][1] - b['pos'][1]
        if 0 < b['world_us'] - a['world_us'] <= 350000 and .01 <= dy <= 1.0:
            steps += 1
            distance += dy
            if steps >= 3 and distance >= .5:
                descent_at = b['world_us']
                break
        else:
            steps, distance = 0, 0.0
    settled = False
    if descent_at is not None:
        for i, sample in enumerate(samples):
            if sample['world_us'] < descent_at:
                continue
            window = [s for s in samples[i:] if s['world_us'] - sample['world_us'] <= 850000]
            if len(window) >= 5 and window[-1]['world_us'] - sample['world_us'] >= 500000 and all(
                    max(s['pos'][axis] for s in window) - min(s['pos'][axis] for s in window) <= .03
                    for axis in range(3)):
                settled = True
                break
    return dict(origin_matched=True, descent_observed=descent_at is not None,
                settled_after_descent=settled, descent_distance=round(max(0, origin[1] - min(s['pos'][1] for s in samples)), 6),
                acceptance_passed=descent_at is not None and settled)


def native_spawn_summary(lines):
    number = r'(-?\d+(?:\.\d+)?)'
    requests = [int(m[1]) for line in lines if (m := re.search(
        r'coop native spawn request: request (\d+), name Weapon_Sword_101, watcher absent;', line))]
    initialized = [dict(probe=int(m[3]), request=int(m[7])) for line in lines
                   if (m := PROBE_ACTOR.search(line)) and m[4] == 'Weapon_Sword_101' and m[7] and int(m[7]) in requests]
    samples = []
    for line in lines:
        m = re.search(r'coop native spawn motion: probe (\d+), request (\d+), world us (\d+), '
                      r'pos ' + number + ' ' + number + ' ' + number + ',', line)
        if m and dict(probe=int(m[1]), request=int(m[2])) in initialized:
            pos = [float(m[i]) for i in (4, 5, 6)]
            if all(map(math.isfinite, pos)):
                samples.append(dict(probe=int(m[1]), request=int(m[2]), world_us=int(m[3]), pos=pos))
    lifecycle = probe_summary(lines, 'Weapon_Sword_101', True, True)
    retired = [p for p in lifecycle['probes'] if p['acceptance_passed'] and
               dict(probe=p['probe'], request=p['request']) in initialized]
    owned = [dict(pos=[float(m[i]) for i in (1, 2, 3)]) for line in lines if (m := re.search(
        r'coop native spawn owned: pos ' + number + ' ' + number + ' ' + number +
        ', empty blackboard, actor dependencies absent;', line))]
    owned = [o for o in owned if all(map(math.isfinite, o['pos']))]
    fall = spawn_fall_summary(samples, owned[0]['pos']) if len(owned) == 1 else spawn_fall_summary([], [0, 0, 0])
    # A changed transform alone does not establish verified gravity or ground contact.
    return dict(queued=sum('coop native spawn probe: queued yes,' in line for line in lines) == 1,
                requests=requests, initialized=initialized, samples=samples,
                retirement_observed=bool(retired),
                owned_argument_observed=len(owned) == 1, owned_origins=owned,
                fall=fall,
                acceptance_passed=len(requests) == 1 and len(initialized) == 1 and
                    sum('coop native spawn probe: queued yes,' in line for line in lines) == 1,
                physics_verified=False, native_companion_verified=False)


def diagnostic_acceptance(report, *, scenario, require_animation=False, require_figure=False,
                          spawning=False, owned=False, require_spawn_retirement=False, require_spawn_fall=False):
    spawn = report['native_spawn_experiment']
    return dict(game_exited=report['exit_code'] == 0 and not report['timed_out'],
                validation=(not report.get('vulkan_validation_requested', False) or
                            (report.get('vulkan_validation_enabled', False) and
                             not report.get('vulkan_validation_errors', 0))),
                source_save_unchanged=bool(report['source_save_unchanged']),
                local_player_observed=bool(report['playable_actor_observed']),
                controls=scenario != 'controls' or (report['local_controls']['scripted_events_applied'] and
                                                    report['local_controls']['movement_observed']),
                reload=scenario != 'reload' or report['reload']['actor_recreation_observed'],
                object_lifecycle=scenario != 'object' or report['object_lifecycle']['acceptance_passed'],
                visual_state=not require_animation or (report['visual_state']['rotation_observed'] and
                                                       report['visual_state']['animation_advancing']),
                figure=not require_figure or (report['figure_model_loaded'] and report['figure_submission_observed'] and
                                             not report['vulkan_validation_errors']),
                native_creation=not spawning or spawn['acceptance_passed'],
                owned_argument=not owned or spawn['owned_argument_observed'],
                native_retirement=not require_spawn_retirement or spawn['retirement_observed'],
                native_fall=not require_spawn_fall or spawn['fall']['acceptance_passed'])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir', type=Path, default=ROOT / 'build/coop-v143')
    ap.add_argument('--seed-profile', required=True, type=Path, help='offline profile to copy for this diagnostic only')
    ap.add_argument('--seconds', type=float, help='world seconds after loading; defaults: idle 5, controls 15, reload 45, object 24')
    ap.add_argument('--scenario', choices=('idle', 'controls', 'reload', 'object'), default='idle',
                    help='observe loading, exercise local controls, verify player recreation, or follow a normally retired weapon')
    ap.add_argument('--timeout', type=float, default=240, help='wall-clock ceiling, including loading')
    ap.add_argument('--input-script', type=Path, help='override the diagnostic\'s repeating title-screen confirmation')
    ap.add_argument('--shots', type=float, help='capture a frame series at this interval in world seconds (at most 64 frames)')
    ap.add_argument('--probe-name', help='require this exact Weapon_ actor in the object scenario, excluding other sampled weapons')
    ap.add_argument('--require-allocator', action='store_true', help='also require the same probe reaching its native allocator handoff')
    ap.add_argument('--require-resource', action='store_true', help='also require the same probe retaining its queued resource until cleanup')
    ap.add_argument('--require-animation', action='store_true', help='require captured rotation and advancing native animation frames')
    ap.add_argument('--require-figure', action='store_true', help='require a loaded model and a diagnostic G-buffer figure submission')
    ap.add_argument('--without-figure', action='store_true', help='omit the optional figure asset for a baseline comparison')
    spawn = ap.add_mutually_exclusive_group()
    spawn.add_argument('--native-clone-weapon', action='store_true',
                    help='create one extra native Weapon_Sword_101 at a verified drop call; copied test profile only')
    spawn.add_argument('--native-owned-weapon', action='store_true',
                       help='create one elevated native weapon with independent arguments and no actor dependencies')
    ap.add_argument('--require-spawn-retirement', action='store_true',
                    help='require the injected actor itself to retire with its resource and allocator correlation')
    ap.add_argument('--require-spawn-fall', action='store_true',
                    help='require gradual native descent from the owned origin and subsequent positional rest')
    args = ap.parse_args()
    if args.require_figure and args.without_figure:
        ap.error('--require-figure and --without-figure are mutually exclusive')
    args.seconds = args.seconds if args.seconds is not None else {'idle': 5, 'controls': 15, 'reload': 45, 'object': 24}[args.scenario]
    if not math.isfinite(args.seconds) or args.seconds <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        ap.error('--seconds and --timeout must be finite and positive')
    if args.scenario == 'controls' and (args.seconds < 11 or args.input_script):
        ap.error('--scenario controls requires at least 11 world seconds and its built-in input script')
    if args.scenario in ('reload', 'object') and not args.input_script:
        ap.error(f'--scenario {args.scenario} requires --input-script with normal menu navigation for the copied profile')
    if args.probe_name and (args.scenario != 'object' or len(args.probe_name) > 31 or
                            not re.fullmatch(r'Weapon_[A-Za-z0-9_]+', args.probe_name)):
        ap.error('--probe-name requires --scenario object and a Weapon_ actor name of at most 31 characters')
    if args.require_allocator and args.scenario != 'object':
        ap.error('--require-allocator requires --scenario object')
    if args.require_resource and args.scenario != 'object':
        ap.error('--require-resource requires --scenario object')
    spawning = args.native_clone_weapon or args.native_owned_weapon
    if spawning and (args.scenario != 'object' or args.probe_name != 'Weapon_Sword_101'):
        ap.error('native weapon experiments require --scenario object --probe-name Weapon_Sword_101')
    if args.require_spawn_retirement and not spawning:
        ap.error('--require-spawn-retirement requires a native weapon experiment')
    if args.require_spawn_fall and not args.native_owned_weapon:
        ap.error('--require-spawn-fall requires --native-owned-weapon')
    if args.shots is not None and (not math.isfinite(args.shots) or args.shots <= 0 or args.seconds / args.shots > 63):
        ap.error('--shots must be finite and positive, and allow at most 64 frames over --seconds')
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
    figure = output / 'assets/link-figure.bin'
    if args.require_figure and not figure.is_file():
        ap.error('--require-figure needs assets/link-figure.bin; run tools/prepare_coop_figure.py')
    if figure.is_file() and not args.without_figure:
        manifest = json.loads(figure.with_suffix('.json').read_text(encoding='utf-8'))
        if hashlib.file_digest(figure.open('rb'), 'sha256').hexdigest() != manifest.get('sha256'):
            raise SystemExit('Prepared figure differs from its manifest; diagnostic not launched')
        install_figure(figure, profile / 'link-figure.bin')
    before = save_hashes(seed / 'save')
    shutil.copytree(seed / 'save', profile / 'save')
    if (seed / 'account.uid').is_file():
        shutil.copy2(seed / 'account.uid', profile / 'account.uid')
    if before != save_hashes(profile / 'save') or before != save_hashes(seed / 'save'):
        raise SystemExit(f'The source save changed during copying; diagnostic not launched. Copy retained at {folder}')
    if spawning:
        marker = 'isolated-physics-owned-v1\n' if args.native_owned_weapon else 'isolated-physics-probe-v1\n'
        (profile / 'coop-native-probe.txt').write_bytes(marker.encode('ascii'))
    script = args.input_script.resolve() if args.input_script else folder / 'input.txt'
    if not args.input_script:
        script.write_text(diagnostic_script(args.timeout, args.scenario), encoding='utf-8')
    env = dict(os.environ, TOTK_COOP_MODE='bot', TOTK_COOP_TRACE_GUEST='1', TOTK_BACKGROUND_WINDOW='1',
               TOTK_COOP_NATIVE_PROBE='2' if args.native_owned_weapon else '1' if args.native_clone_weapon else '0',
               TOTK_ASSUME_FOCUS='1',
               TOTK_INPUT='none', TOTK_INPUT_SCRIPT=str(script),
               TOTK_FPS_LIMIT='30', TOTK_OPERATION_MODE='handheld',
               TOTK_OUTPUT_RES='1280x720', TOTK_WINDOW_SIZE='1280x720', TOTK_DLAA='0')
    if args.shots is not None:
        env.update(TOTK_SHOTS=f'w0-{args.seconds}:{args.shots}', TOTK_SHOTS_DIR=str(folder / 'frames'))
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
    actor_requests = [line for line in lines if 'coop native actor request:' in line]
    request_contexts = [line for line in lines if 'coop native request context:' in line]
    lifecycle = [line for line in lines if 'coop native lifecycle:' in line]
    ready_references = [line for line in lines if 'coop native ready reference:' in line or 'coop native reference event:' in line]
    resident_references = [line for line in lines if 'coop native resident reference:' in line]
    enqueues = [line for line in lines if 'coop native request enqueue:' in line]
    resident_binds = [line for line in lines if 'coop native resident bind:' in line]
    player_manager_binds = [line for line in lines if 'coop native player manager bind:' in line]
    actor_teardowns = [line for line in lines if 'coop native actor teardown:' in line]
    teardown_scopes = [line for line in lines if 'coop native teardown scope:' in line]
    probe_actors = [line for line in lines if 'coop native probe actor:' in line]
    probe_teardowns = [line for line in lines if 'coop native probe teardown:' in line]
    probe_allocators = [line for line in lines if 'coop native probe allocator:' in line]
    request_abi = [line for line in lines if 'coop native request abi:' in line]
    resource_bindings = [line for line in lines if 'coop native resource binding:' in line]
    resource_cleanups = [line for line in lines if 'coop native resource cleanup:' in line]
    player_reference_sources = [line for line in lines if 'coop native player reference source:' in line]
    actor_request_budgets = [line for line in lines if 'coop native actor request budget:' in line]
    player_pipeline_observations = [line for line in lines if 'coop native player pipeline:' in line]
    holders = [line for line in lines if 'coop native holder:' in line]
    initializers = [line for line in lines if 'coop native initializer:' in line]
    constructor_budgets = [line for line in lines if 'coop native constructor budget:' in line]
    scene_resident_observations = [line for line in lines if 'coop native scene resident:' in line]
    resident_component_observations = [line for line in lines if 'coop native resident component:' in line]
    resident_record_observations = [line for line in lines if 'coop native resident record:' in line]
    resident_init_observations = [line for line in lines if 'coop native resident init:' in line]
    resident_init_budgets = [line for line in lines if 'coop native resident init budget:' in line]
    kinds = Counter(match[1] for line in traces if (match := re.search(r'kind ([a-z_]+);', line)))
    intact = before == save_hashes(seed / 'save')
    controls = local_control_summary(lines)
    reload = reload_summary(lines)
    report = dict(executable_sha256=info['executable_sha256'], exit_code=result, timed_out=timed_out,
                  elapsed_seconds=round(time.monotonic() - started, 2), source_save_unchanged=intact,
                  scenario='custom' if args.input_script and args.scenario == 'idle' else args.scenario,
                  local_controls=controls, reload=reload, visual_state=visual_summary(lines),
                  figure_model_loaded=any('link figure:' in line and 'vertices,' in line for line in lines),
                  figure_submission_observed=any('figure: submitted ' in line and 'no native actor' in line for line in lines),
                  vulkan_validation_errors=sum('vk validation error:' in line for line in lines),
                  vulkan_validation_requested=env.get('TOTK_VK_VALIDATION', '').lower() in ('1', 'true', 'yes', 'on'),
                  vulkan_validation_enabled=any('vk: validation layer enabled (VK_LAYER_KHRONOS_validation)' in line
                                                for line in lines),
                  object_lifecycle=probe_summary(lines, args.probe_name, args.require_allocator, args.require_resource),
                  native_spawn_experiment=native_spawn_summary(lines),
                  frame_series=[str(p) for p in sorted((folder / 'frames').glob('f*.png'))],
                  observations=observations, native_function_observations=traces,
                  native_method_candidates=candidates, native_vtable_observations=vtables,
                  native_constructor_observations=constructors,
                  native_actor_request_observations=actor_requests,
                  native_request_context_observations=request_contexts,
                  native_lifecycle_observations=lifecycle,
                  native_ready_reference_observations=ready_references,
                  native_resident_reference_observations=resident_references,
                  native_enqueue_observations=enqueues,
                  native_resident_bind_observations=resident_binds,
                  native_player_manager_bind_observations=player_manager_binds,
                  native_actor_teardown_observations=actor_teardowns,
                  native_teardown_scope_observations=teardown_scopes,
                  native_probe_actor_observations=probe_actors,
                  native_probe_teardown_observations=probe_teardowns,
                  native_probe_allocator_observations=probe_allocators,
                  native_request_abi_observations=request_abi,
                  native_resource_binding_observations=resource_bindings,
                  native_resource_cleanup_observations=resource_cleanups,
                  native_player_reference_source_observations=player_reference_sources,
                  native_actor_request_budgets=actor_request_budgets,
                  native_player_pipeline_observations=player_pipeline_observations,
                  native_holder_observations=holders,
                  native_initializer_observations=initializers,
                  native_constructor_budgets=constructor_budgets,
                  native_scene_resident_observations=scene_resident_observations,
                  native_resident_component_observations=resident_component_observations,
                  native_resident_record_observations=resident_record_observations,
                  native_resident_init_observations=resident_init_observations,
                  native_resident_init_budgets=resident_init_budgets,
                  native_trace_kinds=dict(kinds),
                  player_epoch_trace_count=sum('generation ' in line for line in traces),
                  playable_actor_observed=any('player observed' in line for line in observations),
                  native_actor_creation_verified=False, world_mutation_phase_verified=False,
                  native_gameplay_enabled=False, log=str(log))
    report['acceptance_checks'] = diagnostic_acceptance(
        report, scenario=args.scenario, require_animation=args.require_animation, require_figure=args.require_figure,
        spawning=spawning, owned=args.native_owned_weapon, require_spawn_retirement=args.require_spawn_retirement,
        require_spawn_fall=args.require_spawn_fall)
    report['diagnostic_passed'] = all(report['acceptance_checks'].values())
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['diagnostic_passed'] else 1)


if __name__ == '__main__':
    main()
