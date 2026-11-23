"""Observe the native co-op integration gate in one background game instance on an isolated save copy.

Read-only by default. Explicit native options enable bounded creation or velocity experiments on the copied profile.
No teleport, direct host physics writes or original-profile changes are performed.
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
import socket
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


def native_spawn_summary(lines, actor_name='Weapon_Sword_101', expected=1):
    number = r'(-?\d+(?:\.\d+)?)'
    requests = [int(m[1]) for line in lines if (m := re.search(
        r'coop native spawn request: request (\d+), name ' + re.escape(actor_name) + r', watcher absent;', line))]
    initialized = [dict(probe=int(m[3]), request=int(m[7])) for line in lines
                   if (m := PROBE_ACTOR.search(line)) and m[4] == actor_name and m[7] and int(m[7]) in requests]
    samples = []
    for line in lines:
        m = re.search(r'coop native spawn motion: probe (\d+), request (\d+), world us (\d+), '
                      r'pos ' + number + ' ' + number + ' ' + number + ',', line)
        if m and dict(probe=int(m[1]), request=int(m[2])) in initialized:
            pos = [float(m[i]) for i in (4, 5, 6)]
            if all(map(math.isfinite, pos)):
                samples.append(dict(probe=int(m[1]), request=int(m[2]), world_us=int(m[3]), pos=pos))
    lifecycle = probe_summary(lines, actor_name, True, True)
    retired = [p for p in lifecycle['probes'] if p['acceptance_passed'] and
               dict(probe=p['probe'], request=p['request']) in initialized]
    owned = [dict(pos=[float(m[i]) for i in (1, 2, 3)]) for line in lines if (m := re.search(
        r'coop native spawn owned: pos ' + number + ' ' + number + ' ' + number +
        ', empty blackboard, actor dependencies absent;', line))]
    owned = [o for o in owned if all(map(math.isfinite, o['pos']))]
    fall = spawn_fall_summary(samples, owned[0]['pos']) if len(owned) == 1 else spawn_fall_summary([], [0, 0, 0])
    queued = sum(f'coop native spawn probe: queued yes, name {actor_name},' in line for line in lines) == expected
    # A changed transform alone does not establish verified gravity or ground contact.
    return dict(queued=queued,
                actor_name=actor_name, requests=requests, initialized=initialized, samples=samples,
                retirement_observed=len(retired) == expected,
                owned_argument_observed=len(owned) == expected, owned_origins=owned,expected_count=expected,
                fall=fall,
                acceptance_passed=expected in (1,2) and len(requests) == len(set(requests)) == expected and
                    len(initialized) == len({p['probe'] for p in initialized}) == expected and queued,
                physics_verified=False, native_companion_verified=False)


def npc_velocity_summary(lines, spawn):
    """Require requested direction changes and corresponding motion of the same initialized native NPC."""
    number = r'(-?\d+(?:\.\d+)?)'
    commands = [dict(step=int(m[1]), phase=m[2], generation=int(m[3]), world_us=int(m[4]),
                     velocity=[float(m[i]) for i in (5, 6, 7)]) for line in lines if (m := re.search(
        r'coop native npc velocity probe: step (\d+), phase (forward|reverse|stop), generation (\d+), world us (\d+), '
        r'velocity ' + number + ' ' + number + ' ' + number + r'; native request, original CPU restored', line))]
    scopes = [dict(probe=int(m[1]), request=int(m[2]), generation=int(m[3])) for line in lines if (m := re.search(
        r'coop native npc physics: probe (\d+), request (\d+), .*generation (\d+), .*phase later-actor-update;', line))]
    aborted = any('coop native npc velocity probe: aborted;' in line for line in lines)
    valid = (spawn.get('actor_name') == 'Npc_Road_001' and spawn['acceptance_passed'] and
             len(scopes) == 1 and {k: scopes[0][k] for k in ('probe', 'request')} in spawn['initialized'] and
             3 <= len(commands) <= 96 and not aborted)
    phases = [c['phase'] for c in commands]
    valid = bool(valid and phases[0] == 'forward' and phases[-1] == 'stop' and phases.count('stop') == 1 and
                 'reverse' in phases and phases == sorted(phases, key=('forward', 'reverse', 'stop').index) and
                 [c['step'] for c in commands] == list(range(1, len(commands) + 1)) and
                 all(c['generation'] == scopes[0]['generation'] and all(map(math.isfinite, c['velocity'])) and
                     c['velocity'][0] == {'forward': 2, 'reverse': -2, 'stop': 0}[c['phase']] and
                     c['velocity'][2] == 0 and abs(c['velocity'][1]) <= 50 for c in commands) and
                 all(30000 <= b['world_us'] - a['world_us'] <= 250000 for a, b in zip(commands, commands[1:])))
    forward = reverse = 0.0
    rest = False
    if valid:
        start = commands[0]['world_us']
        turn = next(c['world_us'] for c in commands if c['phase'] == 'reverse')
        stop = commands[-1]['world_us']
        valid = 1000000 <= turn-start <= 1250000 and 2000000 <= stop-start <= 2250000
        samples = sorted((s for s in spawn['samples'] if s['probe'] == scopes[0]['probe'] and
                          s['request'] == scopes[0]['request']), key=lambda s: s['world_us'])
        before = [s for s in samples if start-500000 <= s['world_us'] <= start]
        advancing = [s for s in samples if start <= s['world_us'] <= turn+200000]
        returning = [s for s in samples if turn+200000 <= s['world_us'] <= stop+200000]
        stopped = [s for s in samples if stop+300000 <= s['world_us'] <= stop+1200000]
        if before and advancing and returning:
            peak = max(s['pos'][0] for s in advancing)
            forward = peak - before[-1]['pos'][0]
            reverse = peak - min(s['pos'][0] for s in returning)
        rest = len(stopped) >= 3 and max(math.dist(a['pos'], b['pos']) for a in stopped for b in stopped) <= .10
        path = [s for s in samples if start-500000 <= s['world_us'] <= stop+1200000]
        valid = bool(valid and all(math.dist(a['pos'], b['pos']) < 1 for a, b in zip(path, path[1:])))
    return dict(commands=commands, aborted=aborted, forward_distance=round(forward, 6),
                reverse_distance=round(reverse, 6), rest_observed=rest,
                acceptance_passed=bool(valid and forward >= .4 and reverse >= .4 and rest),
                remote_control_verified=False, native_companion_verified=False)


def npc_consumer_reapply_summary(lines, motion, limit=96):
    corrections = [dict(correction=int(m[1]), generation=int(m[2]), world_us=int(m[3]))
                   for line in lines if (m := re.search(
                       r'coop native npc velocity consumer reapply: correction (\d+), generation (\d+), world us (\d+); '
                       r'same live pending request, original CPU restored', line))]
    commands = motion['commands']
    valid = bool(commands and 0 < len(corrections) <= limit and
                 [c['correction'] for c in corrections] == list(range(1, len(corrections)+1)) and
                 all(c['generation'] == commands[0]['generation'] and
                     commands[0]['world_us'] <= c['world_us'] <= commands[-1]['world_us'] for c in corrections) and
                 all(a['world_us'] < b['world_us'] for a, b in zip(corrections, corrections[1:])))
    return dict(corrections=corrections, count=len(corrections), acceptance_passed=valid)


def npc_peer_velocity_summary(lines, spawn):
    """Require native displacement, two lease-expiry stops and same-epoch recovery from actual peer commands."""
    number = r'(-?\d+(?:\.\d+)?)'
    commands = [dict(step=int(m[1]), reason=m[2], generation=int(m[3]), world_us=int(m[4]),
                     velocity=[float(m[i]) for i in (5, 6, 7)]) for line in lines if (m := re.search(
        r'coop native npc peer velocity: step (\d+), reason (\w+), generation (\d+), world us (\d+), '
        r'velocity ' + number + ' ' + number + ' ' + number + r'; leased native request, original CPU restored', line))]
    scopes = [dict(probe=int(m[1]), request=int(m[2]), generation=int(m[3])) for line in lines if (m := re.search(
        r'coop native npc physics: probe (\d+), request (\d+), .*generation (\d+), .*phase later-actor-update;', line))]
    bindings = [tuple(map(int, m.groups())) for line in lines if (m := re.search(
        r'coop native npc peer binding: session (\d+), player (\d+), remote generation (\d+), local generation (\d+);', line))]
    valid = bool(spawn.get('actor_name') == 'Npc_Road_001' and spawn['acceptance_passed'] and len(scopes) == 1 and
                 {k: scopes[0][k] for k in ('probe', 'request')} in spawn['initialized'] and
                 3 <= len(commands) <= 256 and len(bindings) == 1 and all(bindings[0]) and
                 bindings[0][3] == scopes[0]['generation'] and
                 [c['step'] for c in commands] == list(range(1, len(commands)+1)) and
                 all(c['generation'] == scopes[0]['generation'] and all(map(math.isfinite, c['velocity'])) and
                     c['velocity'][0]**2+c['velocity'][2]**2 <= 4.001 and abs(c['velocity'][1]) <= 50 for c in commands) and
                 all(30000 <= b['world_us']-a['world_us'] <= 250000 for a, b in zip(commands, commands[1:])) and
                 commands[-1]['reason'] == 'finished' and
                 8000000 <= commands[-1]['world_us']-commands[0]['world_us'] <= 8250000 and
                 all(c['velocity'][0] == c['velocity'][2] == 0 for c in commands if c['reason'] != 'fresh'))
    samples = sorted((s for s in spawn['samples'] if scopes and s['probe'] == scopes[0]['probe'] and
                      s['request'] == scopes[0]['request']), key=lambda s: s['world_us'])
    valid = valid and all(0 < b['world_us']-a['world_us'] <= 350000 and
                         math.hypot(b['pos'][0]-a['pos'][0], b['pos'][2]-a['pos'][2]) <=
                         2.1*(b['world_us']-a['world_us'])/1000000+.1 for a, b in zip(samples, samples[1:]))
    groups = []
    for c in commands:
        x, _, z = c['velocity']
        kind = ('forward' if x == 2 and z == 0 else 'reverse' if x == -2 and z == 0 else
                'diagonal' if x == z == 1 else 'expired' if c['reason'] == 'expired' else 'idle')
        if not groups or groups[-1]['kind'] != kind:
            groups.append(dict(kind=kind, start=c['world_us'], end=c['world_us']))
        groups[-1]['end'] = c['world_us']
    segments = []
    for group in groups:
        points = [s['pos'] for s in samples if group['start']+100000 <= s['world_us'] <= group['end']]
        displacement = [points[-1][i]-points[0][i] for i in range(3)] if len(points) >= 2 else [0., 0., 0.]
        rest = len(points) >= 3 and group['end']-group['start'] >= 300000 and all(
            max(p[i] for p in points)-min(p[i] for p in points) <= .06 for i in range(3))
        segments.append(dict(**group, samples=len(points), displacement=displacement, positional_rest=rest))
    kinds = [s['kind'] for s in segments if s['kind'] != 'idle']
    movement = kinds == ['forward', 'expired', 'reverse', 'expired', 'diagonal']
    for s in segments:
        dx, _, dz = s['displacement']
        movement = movement and dict(forward=dx >= .4, reverse=dx <= -.4, diagonal=dx >= .2 and dz >= .2,
                                     expired=s['positional_rest'], idle=True)[s['kind']]
    stop = commands[-1]['world_us'] if commands else 0
    later = [s for s in samples if stop+200000 <= s['world_us'] <= stop+1200000]
    rest = len(later) >= 4 and later[-1]['world_us']-later[0]['world_us'] >= 400000 and all(
        max(s['pos'][i] for s in later)-min(s['pos'][i] for s in later) <= .06 for i in range(3))
    return dict(commands=commands, bindings=bindings, segments=segments, rest_observed=rest,
                acceptance_passed=bool(valid and movement and rest), human_peer_verified=False,
                native_companion_verified=False)


def diagnostic_acceptance(report, *, scenario, require_animation=False, require_figure=False,
                          spawning=False, owned=False, require_spawn_retirement=False, require_spawn_fall=False,
                          require_npc_motion=False):
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
                native_fall=not require_spawn_fall or spawn['fall']['acceptance_passed'],
                native_npc_motion=not require_npc_motion or report['native_npc_velocity_experiment']['acceptance_passed'])


def peer_start_ready(pose_echo, text):
    # ENet's connect timeout is shorter than title/loading. Start the echo only
    # when the game has an initialized host and the copied world is available.
    marker = 'frame step: world clock starts' if pose_echo else 'coop native npc peer velocity: step 1,'
    return marker in text


def session_creation_summary(lines,spawn,retirement):
    pattern=(r'coop native session creation: session (\d+), player (\d+), local generation (\d+), '
             r'remote generation (\d+), world us (\d+), worker (\d+), queued ([01]); '
             r'local actor update, owned stack arguments, original CPU restored')
    creations=[dict(zip(('session','player','local_generation','remote_generation','world_us','worker','queued'),
                       map(int,m.groups()))) for line in lines if (m:=re.search(pattern,line))]
    bindings=[tuple(map(int,m.groups())) for line in lines if (m:=re.search(
        r'coop native npc peer binding: session (\d+), player (\d+), remote generation (\d+), local generation (\d+);',line))]
    drop=any('coop native actor request:' in line and 'caller 0x70020a57d8,' in line for line in lines)
    valid=False
    if len(creations)==1 and len(bindings)==1 and sum('coop native session creation:' in line for line in lines)==1:
        c=creations[0]
        valid=(c['session']>0 and c['player']>0 and c['local_generation']>0 and c['remote_generation']>0 and
               c['world_us']>=6000000 and c['worker']<3 and c['queued']==1 and
               bindings[0]==(c['session'],c['player'],c['remote_generation'],c['local_generation']))
        requests=retirement.get('requests',[])
        valid=valid and len(requests)==1 and all(r['generation']==c['local_generation'] and r['world_us']>c['world_us']
                                               for r in requests)
        valid=valid and next(i for i,s in enumerate(lines) if 'coop native session creation:' in s)<next(
            i for i,s in enumerate(lines) if 'coop native npc peer binding:' in s)
    passed=bool(valid and not drop and spawn.get('acceptance_passed') and spawn.get('owned_argument_observed') and
                retirement.get('acceptance_passed'))
    return dict(creations=creations,peer_bindings=bindings,inventory_drop_observed=drop,acceptance_passed=passed,
                session_driven_creation_verified=passed,reconnect_verified=False,human_peer_verified=False,
                request_storage_reused=False)


def pose_echo_summary(peer_text, lines, exit_code):
    match=re.search(r'peer: pose echo completed: samples (\d+), bodies (\d+), changed (\d+)',peer_text)
    samples, bodies, changed = tuple(map(int,match.groups())) if match else (0,0,0)
    body_applied=any('figure: final body pose applied' in line for line in lines)
    passed=exit_code==0 and samples>=bodies>=10 and 0<changed<bodies and body_applied
    return dict(peer_exit_code=exit_code, samples=samples, bodies=bodies, changed=changed,
                renderer_body_applied=body_applied, acceptance_passed=passed, native_companion_verified=False)


def equipment_echo_summary(peer_text, exit_code):
    match=re.search(r'peer: equipment echo completed: samples (\d+), equipped (\d+), changes (\d+)',peer_text)
    samples, equipped, changes=tuple(map(int,match.groups())) if match else (0,0,0)
    passed=exit_code==0 and samples>=10 and 0<equipped<=samples and changes<samples
    return dict(samples=samples,equipped_samples=equipped,changes=changes,acceptance_passed=passed,
                placement_verified=False,inventory_replication_verified=False)


def gear_probe_mapping(manifest):
    actors=manifest.get('actors')
    if manifest.get('format')!='LNKA' or manifest.get('version')!=2 or not isinstance(actors,dict):
        raise ValueError('invalid private equipment manifest')
    groups=[[],[],[]]
    for actor,model in actors.items():
        if not isinstance(actor,str) or len(actor)>=48 or not isinstance(model,str) or len(model)>=64 or \
            not re.fullmatch(r'[A-Za-z0-9_]+\.[A-Za-z0-9_]+',model):
            raise ValueError('invalid equipment model mapping')
        if re.fullmatch(r'Weapon_(?:Sword|Lsword|Spear)_[0-9][A-Za-z0-9_]*',actor): slot=0
        elif re.fullmatch(r'Weapon_Shield_[0-9][A-Za-z0-9_]*',actor): slot=1
        elif re.fullmatch(r'Weapon_Bow_[0-9][A-Za-z0-9_]*',actor): slot=2
        else: raise ValueError('invalid equipment actor mapping')
        groups[slot].append((actor,model))
    if any(len(group)>1 for group in groups) or not any(groups):
        raise ValueError('graph diagnostic requires at most one prepared model per equipment slot')
    return 'read-only-gear-graph-v1\n'+''.join(f'{i}\t{actor}\t{model}\n'
        for i,group in enumerate(groups) for actor,model in group)


def gear_graph_summary(lines):
    armed=any('coop gear graph: armed,' in line for line in lines)
    found=[]; poses=[]; done=[]; references=[]; reference_poses=[]; native_models=[]; captured=0
    for line in lines:
        if m:=re.search(r'coop gear native model: slot (\d+), actor (0x[0-9a-f]+), model (0x[0-9a-f]+), depth (\d+), embedded delta (-?\d+);',line):
            native_models.append(dict(slot=int(m[1]),actor=m[2],model=m[3],depth=int(m[4]),embedded_delta=int(m[5])))
        if m:=re.search(r'coop gear references: captured (\d+);',line): captured=max(captured,int(m[1]))
        if m:=re.search(r'coop gear reference candidate: generation (\d+), slot (\d+), actor (0x[0-9a-f]+), metadata id (-?\d+),',line):
            references.append(dict(generation=int(m[1]),slot=int(m[2]),actor=m[3],metadata_id=int(m[4])))
        if m:=re.search(r'coop gear reference pose: world us (\d+), generation (\d+), slot (\d+), candidate (\d+), first ([-0-9.]+) ([-0-9.]+) ([-0-9.]+); axes ([-0-9. ]+);',line):
            try: values=list(map(float,m.group(5,6,7)))+list(map(float,m[8].split()))
            except ValueError: continue
            if len(values)==12 and all(map(math.isfinite,values)):
                reference_poses.append(dict(world_us=int(m[1]),generation=int(m[2]),slot=int(m[3]),candidate=int(m[4]),
                    render_origin_pos=values[:3],render_origin_axes=values[3:],
                    reference_live=bool(int(live[1])) if (live:=re.search(r'reference live ([01]);',line)) else None))
        if m:=re.search(r'coop gear graph candidate: generation (\d+), slot (\d+), path (actor(?:->0x[0-9a-f]+)+),',line):
            found.append(dict(generation=int(m[1]),slot=int(m[2]),path=m[3]))
        if m:=re.search(r'coop gear graph done: generation (\d+), nodes (\d+), candidates (\d+), capped ([01]);',line):
            done.append(dict(generation=int(m[1]),nodes=int(m[2]),candidates=int(m[3]),capped=bool(int(m[4]))))
        if m:=re.search(r'coop gear graph pose: world us (\d+), generation (\d+), candidate (\d+), slot (\d+), first (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+);',line):
            try: p=list(map(float,m.group(5,6,7)))
            except ValueError: continue
            if all(map(math.isfinite,p)):
                poses.append(dict(world_us=int(m[1]),generation=int(m[2]),candidate=int(m[3]),slot=int(m[4]),render_origin_pos=p))
    ran=armed and bool(done) and all(1<=d['nodes']<=2048 and d['candidates']<=24 for d in done)
    return dict(armed=armed,search_completed=ran,searches=done,candidates=found,poses=poses,
                reference_events=captured,reference_candidates=references,reference_poses=reference_poses,native_models=native_models,
                native_attachment_binding_verified=False,exclusive_ownership_verified=False)


def native_figure_summary(lines):
    captured={}; submitted=[]; invalid=0
    number=r'(-?\d+(?:\.\d+)?)'
    for line in lines:
        if m:=re.search(r'coop native figure capture: sample (\d+), world us (\d+), generation (\d+), actor id (-?\d+), pos '+number+' '+number+' '+number+r', body pos '+number+' '+number+' '+number+';',line):
            values=list(map(float,m.group(5,6,7,8,9,10)))
            if all(map(math.isfinite,values)):
                captured[(int(m[1]),int(m[3]),int(m[4]))]=dict(world_us=int(m[2]),pos=values[:3],body_pos=values[3:])
    # Capture and rendering log from different threads; file order need not reflect publication order.
    for line in lines:
        if m:=re.search(r'coop native figure submitted: sample (\d+), generation (\d+), actor id (-?\d+), pos '+number+' '+number+' '+number+';',line):
            key=tuple(map(int,m.group(1,2,3))); pos=list(map(float,m.group(4,5,6)))
            original=captured.get(key)
            if not original or not all(map(math.isfinite,pos)): invalid+=1; continue
            submitted.append(dict(sample_ns=key[0],generation=key[1],actor_id=key[2],world_us=original['world_us'],
                pos=pos,body_pos=original['body_pos'],error=math.dist(pos,original['pos'])))
    keys={(p['generation'],p['actor_id']) for p in submitted}
    ordered=all(b['sample_ns']>a['sample_ns'] for a,b in zip(submitted,submitted[1:]))
    error=max((p['error'] for p in submitted),default=None)
    passed=len(submitted)>=10 and len(keys)==1 and ordered and not invalid and error is not None and error<=.0001
    return dict(acceptance_passed=passed,captured=len(captured),submitted=len(submitted),unmatched=invalid,
        maximum_origin_error=error,samples=submitted,native_appearance_suppressed=False,
        ground_contact_verified=False,lifecycle_verified=False,human_peer_verified=False)


def native_visibility_summary(lines,figure):
    events=[]
    for line in lines:
        if m:=re.search(r'coop native model visibility: call (\d+), phase (hide|restore), generation (\d+), actor id (-?\d+), world us (\d+), before ([01]), requested ([01]), after (\d+), owner matched ([01]);',line):
            events.append(dict(call=int(m[1]),phase=m[2],generation=int(m[3]),actor_id=int(m[4]),world_us=int(m[5]),
                before=int(m[6]),requested=int(m[7]),after=int(m[8]),owner_matched=bool(int(m[9]))))
    owned={(p['generation'],p['actor_id']) for p in figure.get('samples',[])}
    aborted=any('coop native model visibility: aborted;' in line for line in lines)
    pair=len(events)==2 and [e['call'] for e in events]==[1,2] and [e['phase'] for e in events]==['hide','restore']
    matched=pair and all(e['owner_matched'] and (e['generation'],e['actor_id']) in owned for e in events) and len(owned)==1
    applied=matched and [(e['before'],e['requested'],e['after']) for e in events]==[(1,0,0),(0,1,1)]
    ordered=pair and events[0]['world_us']<events[1]['world_us']
    duration=(events[1]['world_us']-events[0]['world_us'])/1e6 if ordered else 0
    covered=sum(events[0]['world_us']<=p.get('world_us',-1)<=events[1]['world_us'] for p in figure.get('samples',[])) if ordered else 0
    return dict(acceptance_passed=bool(figure.get('acceptance_passed') and applied and ordered and not aborted and duration>=2 and covered>=30),
        events=events,aborted=aborted,native_flag_control_verified=bool(applied and ordered and not aborted),
        hidden_world_seconds=duration,hidden_figure_samples=covered,
        visual_replacement_verified=False,native_retirement_verified=False,human_peer_verified=False)


def retirement_requests(lines):
    requests=[]
    for line in lines:
        if m:=re.search(r'coop native npc retirement request: generation (\d+), actor id (-?\d+), world us (\d+), result (\d+), worker ([012]), rest samples (\d+), rest us (\d+);',line):
            requests.append(dict(generation=int(m[1]),actor_id=int(m[2]),world_us=int(m[3]),result=int(m[4]),worker=int(m[5]),
                rest_samples=int(m[6]),rest_us=int(m[7])))
    return requests


def npc_retirement_summary(lines,spawn,figure):
    requests=retirement_requests(lines)
    lifecycle=probe_summary(lines,'Npc_Road_001',True,True)
    initialized=spawn.get('initialized',[])
    owned={(p['generation'],p['actor_id']) for p in figure.get('samples',[])}
    correlated=[p for p in lifecycle['probes'] if p['acceptance_passed'] and len(initialized)==1 and
        (p['probe'],p['request'])==(initialized[0]['probe'],initialized[0]['request'])]
    request=requests[0] if len(requests)==1 else None
    same=bool(request and request['result']==1 and owned=={(request['generation'],request['actor_id'])} and
        len(correlated)==1 and correlated[0]['generation']==request['generation'])
    last=max((p.get('world_us',0) for p in figure.get('samples',[])),default=0)
    passed=bool(same and spawn.get('acceptance_passed') and figure.get('acceptance_passed') and request['world_us']>=last and
        request['rest_samples']>=12 and request['rest_us']>=1000000)
    return dict(acceptance_passed=passed,requests=requests,lifecycle=lifecycle,
        native_retirement_verified=passed,repeated_lifecycle_verified=False,reconnect_verified=False,
        native_request_storage_reused=False)


def npc_cycles_summary(lines):
    begins=[dict(cycle=int(m[1]),world_us=int(m[2]),prior=int(m[3]),retired=int(m[4])) for line in lines
        if (m:=re.search(r'coop native npc cycle begin: cycle (\d+), world us (\d+), prior actor id (-?\d+), prior retired ([01]);',line))]
    bindings=[dict(cycle=int(m[1]),generation=int(m[2]),actor_id=int(m[3]),world_us=int(m[4])) for line in lines
        if (m:=re.search(r'coop native npc cycle binding: cycle (\d+), generation (\d+), actor id (-?\d+), world us (\d+);',line))]
    total=native_spawn_summary(lines,'Npc_Road_001',expected=2)
    requests=total['requests']
    owned=[i for i,line in enumerate(lines) if 'coop native spawn owned: pos ' in line]
    queued=[i for i,line in enumerate(lines) if 'coop native spawn probe: queued yes, name Npc_Road_001,' in line]
    valid=(total['acceptance_passed'] and total['owned_argument_observed'] and
        len(begins)==len(bindings)==len(owned)==len(queued)==2 and
        len(retirement_requests(lines))==2 and all(b['generation']>0 and b['actor_id']>=0 for b in bindings) and
        [b['cycle'] for b in begins]==[1,2] and [b['cycle'] for b in bindings]==[1,2] and
        begins[0]['world_us']<begins[1]['world_us'] and begins[0]['prior']==-1 and not begins[0]['retired'] and
        begins[1]['retired']==1 and begins[1]['prior']==bindings[0]['actor_id'] and
        bindings[0]['actor_id']!=bindings[1]['actor_id'] and bindings[0]['generation']==bindings[1]['generation'])
    cycles=[]
    if valid:
        for i,begin in enumerate(begins):
            initialized=[p for p in total['initialized'] if p['request']==requests[i]]
            if len(initialized)!=1: valid=False; break
            probe=initialized[0]['probe']; scoped=[]
            stop=begins[i+1]['world_us'] if i+1<len(begins) else float('inf')
            for index,line in enumerate(lines):
                if index in owned and index!=owned[i] or index in queued and index!=queued[i]: continue
                if (m:=re.search(r'world us (\d+)',line)) and not begin['world_us']<=int(m[1])<stop: continue
                if (m:=re.search(r'coop native spawn request: request (\d+), name Npc_Road_001,',line)) and int(m[1])!=requests[i]: continue
                if (m:=PROBE_ACTOR.search(line)) and m[4]=='Npc_Road_001' and int(m[3])!=probe: continue
                if 'coop native spawn motion:' in line or 'coop native npc physics:' in line or 'coop native probe teardown:' in line or 'coop native probe allocator:' in line:
                    if (m:=re.search(r'probe (\d+)',line)) and int(m[1])!=probe: continue
                scoped.append(line)
            spawn=native_spawn_summary(scoped,'Npc_Road_001')
            motion=npc_velocity_summary(scoped,spawn)
            consumer=npc_consumer_reapply_summary(scoped,motion)
            retirement=retirement_requests(scoped)
            binding=bindings[i]
            retired=bool(len(retirement)==1 and spawn['retirement_observed'] and
                retirement[0]['result']==1 and retirement[0]['actor_id']==binding['actor_id'] and
                retirement[0]['generation']==binding['generation'] and retirement[0]['rest_samples']>=12 and
                retirement[0]['rest_us']>=1000000 and binding['world_us']>=begin['world_us'] and
                motion['commands'] and retirement[0]['world_us']>=motion['commands'][-1]['world_us']+1000000)
            passed=bool(spawn['acceptance_passed'] and motion['acceptance_passed'] and consumer['acceptance_passed'] and retired)
            cycles.append(dict(cycle=i+1,spawn=spawn,motion=motion,consumer=consumer,retirement=retirement,
                binding=binding,acceptance_passed=passed))
            valid=valid and passed
    passed=bool(valid and len(cycles)==2)
    return dict(acceptance_passed=passed,begins=begins,bindings=bindings,cycles=cycles,
        repeated_in_process_verified=passed,request_storage_reused=False,reconnect_verified=False,human_peer_verified=False)


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
    ap.add_argument('--require-equipment', action='store_true', help='require equipped identities received by the pose echo peer; no gear placement claim')
    ap.add_argument('--equipment-graph', action='store_true', help='bounded read-only search for prepared models reachable from local Link; no attachment binding')
    ap.add_argument('--pose-echo-offset',type=float,help='diagnostic world-X offset in metres; default 3, zero compares both origins; no ground solver')
    ap.add_argument('--require-figure', action='store_true', help='require a loaded model and a diagnostic G-buffer figure submission')
    ap.add_argument('--without-figure', action='store_true', help='omit the optional figure asset for a baseline comparison')
    spawn = ap.add_mutually_exclusive_group()
    spawn.add_argument('--pose-echo', action='store_true',
                       help='round-trip captured body poses through a game-free ENet peer; no native actor')
    spawn.add_argument('--native-clone-weapon', action='store_true',
                    help='create one extra native Weapon_Sword_101 at a verified drop call; copied test profile only')
    spawn.add_argument('--native-owned-weapon', action='store_true',
                       help='create one elevated native weapon with independent arguments and no actor dependencies')
    spawn.add_argument('--native-owned-npc', action='store_true',
                       help='try one Npc_Road_001 request with owned arguments; isolated creation diagnostic only')
    spawn.add_argument('--native-npc-motion', action='store_true',
                       help='create one scoped NPC and test a bounded native forward/reverse/stop velocity pulse')
    spawn.add_argument('--native-npc-consumer-motion', action='store_true',
                       help='test a separate NPC pulse reapplied through the native API at its request-consumer entry')
    spawn.add_argument('--native-npc-peer-motion', action='store_true',
                       help='test bounded ENet loopback velocities, lease-expiry stops and same-session recovery')
    spawn.add_argument('--native-npc-cycles',action='store_true',
                       help='two native pulse/removal cycles with distinct retained request slots; no figure/peer')
    spawn.add_argument('--native-npc-session',action='store_true',
                       help='one connection-driven NPC creation at the local actor update; no inventory drop')
    ap.add_argument('--native-npc-figure',action='store_true',
                    help='use the scoped native NPC origin for the Link figure; requires --native-npc-peer-motion')
    ap.add_argument('--native-npc-visibility',action='store_true',
                    help='one guarded native hide/restore pair; requires --native-npc-figure')
    ap.add_argument('--native-npc-retirement',action='store_true',
                    help='one native NPC retirement after the completed stop/restore sequence; requires --native-npc-visibility')
    ap.add_argument('--require-spawn-retirement', action='store_true',
                    help='require the injected actor itself to retire with its resource and allocator correlation')
    ap.add_argument('--require-spawn-fall', action='store_true',
                    help='require gradual native descent from the owned origin and subsequent positional rest')
    args = ap.parse_args()
    if args.native_npc_session:
        if args.without_figure or args.input_script or args.scenario not in ('idle','controls'):
            ap.error('--native-npc-session requires idle/controls with built-in input and figure asset')
        args.native_npc_peer_motion=args.native_npc_figure=args.native_npc_visibility=args.native_npc_retirement=True
    if args.native_npc_cycles and (not args.without_figure or args.native_npc_figure or args.native_npc_visibility or args.native_npc_retirement):
        ap.error('--native-npc-cycles requires --without-figure and cannot combine appearance/peer experiments')
    if args.native_npc_retirement and not args.native_npc_visibility:
        ap.error('--native-npc-retirement requires the scoped --native-npc-visibility experiment')
    if args.native_npc_visibility and not args.native_npc_figure:
        ap.error('--native-npc-visibility requires --native-npc-figure and its scoped ENet experiment')
    if args.native_npc_figure:
        if not args.native_npc_peer_motion or args.without_figure:
            ap.error('--native-npc-figure requires --native-npc-peer-motion and the figure asset')
        args.require_figure=True
    if args.require_figure and args.without_figure:
        ap.error('--require-figure and --without-figure are mutually exclusive')
    if args.pose_echo and args.without_figure:
        ap.error('--pose-echo requires the figure to verify received-pose application')
    if args.require_equipment and not args.pose_echo:
        ap.error('--require-equipment requires --pose-echo')
    if args.pose_echo_offset is not None and (not args.pose_echo or not math.isfinite(args.pose_echo_offset) or abs(args.pose_echo_offset)>10):
        ap.error('--pose-echo-offset requires --pose-echo and a finite value within ten metres')
    args.pose_echo_offset=3 if args.pose_echo_offset is None else args.pose_echo_offset
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
    motion = args.native_npc_motion or args.native_npc_consumer_motion or args.native_npc_cycles
    npc = args.native_owned_npc or motion or args.native_npc_peer_motion
    spawning = args.native_clone_weapon or args.native_owned_weapon or npc
    if (args.native_clone_weapon or args.native_owned_weapon) and (args.scenario != 'object' or args.probe_name != 'Weapon_Sword_101'):
        ap.error('native weapon experiments require --scenario object --probe-name Weapon_Sword_101')
    minimum = 42 if args.native_npc_cycles else 29 if args.native_npc_retirement else 27 if args.native_npc_peer_motion else 20 if motion else 15
    if npc and ((args.scenario != 'idle' and not args.native_npc_session) or (not args.input_script and not args.native_npc_session) or args.seconds < minimum or
                                  args.require_spawn_retirement or args.require_spawn_fall):
        requirements='built-in idle/controls input' if args.native_npc_session else '--scenario idle and recorded drop input'
        ap.error(f'native NPC experiments require {requirements} and at least '
                 f'{minimum} world seconds; no pickup/fall acceptance')
    if args.equipment_graph and (spawning or args.seconds<12):
        ap.error('--equipment-graph requires at least 12 world seconds and no native mutation experiment')
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
    if args.equipment_graph:
        library=output/'assets/link-gear.bin'
        manifest=json.loads(library.with_suffix('.json').read_text(encoding='utf-8'))
        with library.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=manifest.get('sha256'):
                raise SystemExit('Private equipment library differs from its manifest')
        (profile/'coop-gear-probe.tsv').write_bytes(gear_probe_mapping(manifest).encode('ascii'))
    if spawning:
        marker = ('isolated-npc-session-create-v1\n' if args.native_npc_session else
                  'isolated-npc-two-cycles-v1\n' if args.native_npc_cycles else
                  'isolated-npc-native-retirement-v1\n' if args.native_npc_retirement else
                  'isolated-npc-native-visibility-v1\n' if args.native_npc_visibility else
                  'isolated-npc-body-figure-v1\n' if args.native_npc_figure else
                  'isolated-npc-enet-velocity-v1\n' if args.native_npc_peer_motion else
                  'isolated-npc-consumer-velocity-v1\n' if args.native_npc_consumer_motion else
                  'isolated-npc-velocity-v1\n' if args.native_npc_motion else 'isolated-npc-road-001-v1\n' if npc else
                  'isolated-physics-owned-v1\n' if args.native_owned_weapon else 'isolated-physics-probe-v1\n')
        (profile / 'coop-native-probe.txt').write_bytes(marker.encode('ascii'))
    script = args.input_script.resolve() if args.input_script else folder / 'input.txt'
    if not args.input_script:
        script.write_text(diagnostic_script(args.timeout, args.scenario), encoding='utf-8')
    env = dict(os.environ, TOTK_COOP_MODE='bot', TOTK_COOP_TRACE_GUEST='1', TOTK_BACKGROUND_WINDOW='1',
               TOTK_COOP_NATIVE_PROBE='11' if args.native_npc_session else '10' if args.native_npc_cycles else '9' if args.native_npc_retirement else '8' if args.native_npc_visibility else '7' if args.native_npc_figure else '6' if args.native_npc_peer_motion else '5' if args.native_npc_consumer_motion else '4' if args.native_npc_motion else '3' if npc else '2' if args.native_owned_weapon else '1' if args.native_clone_weapon else '0',
               TOTK_ASSUME_FOCUS='1',
               TOTK_INPUT='none', TOTK_INPUT_SCRIPT=str(script),
               TOTK_FPS_LIMIT='30', TOTK_OPERATION_MODE='handheld',
               TOTK_OUTPUT_RES='1280x720', TOTK_WINDOW_SIZE='1280x720', TOTK_DLAA='0')
    if args.shots is not None:
        env.update(TOTK_SHOTS=f'w0-{args.seconds}:{args.shots}', TOTK_SHOTS_DIR=str(folder / 'frames'))
    peer_command = None
    if args.native_npc_peer_motion or args.pose_echo:
        from build_coop_velocity_peer import build_peer
        peer_exe = build_peer()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        hashes = json.loads((ROOT / 'tools/data/expected-v1.4.3.json').read_text())['exefs_sha256']
        content = hashlib.sha256(''.join(h for name, h in sorted(hashes.items())
                                        if name in ('main', 'sdk', 'subsdk0')).encode('ascii')).hexdigest()
        peer_profile = folder / 'peer-profile'
        peer_profile.mkdir()
        peer_command = [str(peer_exe), str(port), content, str(peer_profile)]
        if args.pose_echo:
            peer_command.extend(['--pose-echo',str(args.pose_echo_offset)])
        env.update(TOTK_COOP_MODE='host', TOTK_COOP_IP='127.0.0.1', TOTK_COOP_PORT=str(port))
    # Explicit game assets from the verified build manifest; only the new profile is writable.
    command = [str(exe), '--exefs', info['exefs'], '--romfs', info['romfs'], '--profile', str(profile),
               '--seconds', str(args.seconds), '--shot', str(folder / 'last-frame.png')]
    started = time.monotonic()
    timed_out = False
    log = folder / 'guest.log'
    peer_process = None
    peer_result = None
    with log.open('w', encoding='utf-8') as f, (folder / 'peer.log').open('w', encoding='utf-8') as peer_log:
        process = subprocess.Popen(command, cwd=output / 'game', env=env, stdout=f, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            if peer_command:
                with log.open('r', encoding='utf-8', errors='replace') as reader:
                    tail = ''
                    while process.poll() is None and time.monotonic()-started < args.timeout:
                        if peer_process is None:
                            chunk = tail + reader.read()
                            if peer_start_ready(args.pose_echo or args.native_npc_session,chunk):
                                peer_process = subprocess.Popen(peer_command, env=dict(env, PATH='C:/msys64/ucrt64/bin'+os.pathsep+env.get('PATH', '')),
                                    stdout=peer_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
                            tail = chunk[-256:]
                        time.sleep(.05)
                result = process.wait(timeout=max(.01, args.timeout-(time.monotonic()-started)))
            else:
                result = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()   # only this runner's own child, never an existing game instance
            result = process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
        finally:
            if peer_process is not None:
                if args.pose_echo and peer_process.poll() is None:
                    try:
                        peer_process.wait(timeout=7)
                    except subprocess.TimeoutExpired:
                        pass
                if peer_process.poll() is None:
                    peer_process.kill()
                peer_result = peer_process.wait()
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
                  native_spawn_experiment=native_spawn_summary(lines, 'Npc_Road_001' if npc else 'Weapon_Sword_101',expected=2 if args.native_npc_cycles else 1),
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
                  native_npc_physics_observations=[line for line in lines if 'coop native npc ' in line],
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
    report['native_npc_velocity_experiment'] = npc_velocity_summary(lines, report['native_spawn_experiment'])
    consumer = npc_consumer_reapply_summary(lines, report['native_npc_velocity_experiment'])
    report['native_npc_velocity_experiment']['consumer_reapply'] = consumer
    report['native_npc_velocity_experiment']['consumer_reapplications'] = consumer['count']
    if args.native_npc_cycles:
        report['native_npc_cycles']=npc_cycles_summary(lines)
        report['native_npc_velocity_experiment']=dict(acceptance_passed=report['native_npc_cycles']['acceptance_passed'],
            per_cycle=[c['motion'] for c in report['native_npc_cycles']['cycles']])
    report['acceptance_checks'] = diagnostic_acceptance(
        report, scenario=args.scenario, require_animation=args.require_animation, require_figure=args.require_figure,
        spawning=spawning, owned=args.native_owned_weapon or npc, require_spawn_retirement=args.require_spawn_retirement,
        require_spawn_fall=args.require_spawn_fall, require_npc_motion=motion)
    if args.native_npc_cycles:
        report['acceptance_checks']['native_npc_cycles']=report['native_npc_cycles']['acceptance_passed']
    if args.native_npc_consumer_motion:
        report['acceptance_checks']['native_consumer_reapply'] = consumer['acceptance_passed']
    if args.native_npc_peer_motion:
        peer_motion = npc_peer_velocity_summary(lines, report['native_spawn_experiment'])
        peer_motion['peer_exit_code'] = peer_result
        peer_motion['consumer_reapply'] = npc_consumer_reapply_summary(lines, peer_motion, limit=256)
        report['native_npc_peer_experiment'] = peer_motion
        report['acceptance_checks']['native_peer_velocity'] = peer_motion['acceptance_passed']
        report['acceptance_checks']['native_peer_consumer'] = peer_motion['consumer_reapply']['acceptance_passed']
        report['acceptance_checks']['native_peer_process'] = peer_result == 0
    if args.pose_echo:
        peer_text=(folder / 'peer.log').read_text(encoding='utf-8',errors='replace')
        report['pose_echo'] = pose_echo_summary(peer_text,lines,peer_result)
        report['pose_echo']['offset_metres']=args.pose_echo_offset
        report['pose_echo']['ground_contact_verified']=False
        report['acceptance_checks']['pose_echo'] = report['pose_echo']['acceptance_passed']
        report['equipment_echo'] = equipment_echo_summary(peer_text,peer_result)
        if args.require_equipment:
            report['acceptance_checks']['equipment_echo'] = report['equipment_echo']['acceptance_passed']
    if args.native_npc_figure:
        report['native_body_figure']=native_figure_summary(lines)
        report['acceptance_checks']['native_figure_origin']=report['native_body_figure']['acceptance_passed']
    if args.native_npc_visibility:
        report['native_body_figure'].pop('native_appearance_suppressed',None)
        report['native_model_visibility']=native_visibility_summary(lines,report['native_body_figure'])
        report['acceptance_checks']['native_model_visibility']=report['native_model_visibility']['acceptance_passed']
    if args.native_npc_retirement:
        report['native_npc_retirement']=npc_retirement_summary(lines,report['native_spawn_experiment'],report['native_body_figure'])
        report['acceptance_checks']['native_npc_retirement']=report['native_npc_retirement']['acceptance_passed']
        report['native_model_visibility']['native_retirement_verified']=report['native_npc_retirement']['native_retirement_verified']
    if args.native_npc_session:
        report['native_session_creation']=session_creation_summary(lines,report['native_spawn_experiment'],report['native_npc_retirement'])
        report['acceptance_checks']['native_session_creation']=report['native_session_creation']['acceptance_passed']
    if args.equipment_graph:
        report['equipment_graph']=gear_graph_summary(lines)
        report['acceptance_checks']['equipment_graph_ran']=report['equipment_graph']['search_completed']
    report['diagnostic_passed'] = all(report['acceptance_checks'].values())
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['diagnostic_passed'] else 1)


if __name__ == '__main__':
    main()
