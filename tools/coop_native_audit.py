"""Map native observations to generated functions and direct callees, without executing guest code.

Input/output are private game-derived artifacts. Output must stay below build/; no C bodies are copied to it.
Function names, offsets and observed callers are evidence for investigation, not an inferred ABI or safe update phase.
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from check_content import GENERATED_MARKER

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = re.compile(r'^void f_([0-9a-fA-F]+)\(Cpu \*c\)\s*\{', re.M)
DIRECT_CALL = re.compile(r'\bf_([0-9a-fA-F]+)\(c\)')
TRACE = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+),.*?host thread (\d+)'
                   r'(?:, generation (\d+), kind ([a-z_]+))?;')
CANDIDATE = re.compile(r'player vtable\+0x200 -> main\+(0x[0-9a-fA-F]+), generation (\d+);')
VTABLE = re.compile(r'player main\+(0x[0-9a-fA-F]+), generation (\d+);')
RESIDENT_COMPONENT = re.compile(r'vtable main\+(0x[0-9a-fA-F]+), list count (\d+);')
RESIDENT_INIT = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                           r'x0 resident same, host thread (\d+);')
CONSTRUCTOR = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), x0 '
                         r'0x[0-9a-fA-F]+, host thread (\d+)(?:, factory caller (0x[0-9a-fA-F]+))?'
                         r'(?:, request caller (0x[0-9a-fA-F]+))?'
                         r'(?:, pipeline caller (0x[0-9a-fA-F]+))?'
                         r'(?:, task descriptor (0x[0-9a-fA-F]+))?, '
                         r'observed player (same|different);')
HOLDER = re.compile(r'target (0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), x0 '
                    r'0x[0-9a-fA-F]+, x1 player same, x2 (\d+), host thread (\d+)'
                    r'(?:, inline task holder (yes|no|unknown))?;')
INITIALIZER = re.compile(r'target (0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                         r'x0 player same, x1 task\+0x18 (yes|no|unknown), host thread (\d+);')


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def audit(generated, diagnostic):
    layout = json.loads((generated / 'layout.json').read_text(encoding='utf-8'))
    main = next(m for m in layout if m['name'] == 'main')
    base, limit = number(main['base']), number(main['base']) + number(main['size'])
    manifest = json.loads((generated / 'main/manifest.json').read_text(encoding='utf-8'))
    text_low, text_high = map(number, manifest['text'])
    if not base <= text_low < text_high <= limit:
        raise ValueError('Main executable text range is outside its module layout')
    report = json.loads(diagnostic.read_text(encoding='utf-8'))
    entries = []
    for line in report.get('native_function_observations', []):
        match = TRACE.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[3]), generation=int(match[4]) if match[4] else None,
                                kind=match[5] or 'legacy_unscoped'))
    for line in report.get('native_constructor_observations', []):
        match = CONSTRUCTOR.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[3]), generation=None,
                                factory_caller=int(match[4], 16) if match[4] else None,
                                request_caller=int(match[5], 16) if match[5] else None,
                                pipeline_caller=int(match[6], 16) if match[6] else None,
                                task_descriptor_observed=bool(match[7] and int(match[7], 16)),
                                kind='constructor_same_actor' if match[8] == 'same' else 'constructor_other_actor'))
    for line in report.get('native_holder_observations', []):
        match = HOLDER.search(line)
        if match:
            address = int(match[1], 16)
            if not text_low <= address < text_high:
                raise ValueError(f'Observed holder target outside executable main text at {address:#x}')
            entries.append(dict(address=address, caller=int(match[2], 16),
                                thread=int(match[4]), generation=None, holder_mode=int(match[3]),
                                inline_task_holder=match[5],
                                kind='holder_same_actor'))
    for line in report.get('native_initializer_observations', []):
        match = INITIALIZER.search(line)
        if match:
            address = int(match[1], 16)
            if not text_low <= address < text_high:
                raise ValueError(f'Observed initializer target outside executable main text at {address:#x}')
            entries.append(dict(address=address, caller=int(match[2], 16),
                                thread=int(match[4]), generation=None, inline_task_context=match[3],
                                kind='initializer_same_actor'))
    for line in report.get('native_resident_init_observations', []):
        match = RESIDENT_INIT.search(line)
        if match:
            address = base + int(match[1], 16)
            if not text_low <= address < text_high:
                raise ValueError(f'Observed resident initializer outside executable main text at {address:#x}')
            entries.append(dict(address=address, caller=int(match[2], 16),
                                thread=int(match[3]), generation=None,
                                kind='resident_init_same_component'))
    candidates = defaultdict(set)
    for line in report.get('native_method_candidates', []):
        match = CANDIDATE.search(line)
        if match:
            candidates[base + int(match[1], 16)].add(int(match[2]))
    vtables = defaultdict(set)
    for line in report.get('native_vtable_observations', []):
        match = VTABLE.search(line)
        if match:
            address = base + int(match[1], 16)
            if not text_high <= address < limit or address & 7:
                raise ValueError(f'Player vtable outside aligned main data at {address:#x}')
            vtables[address].add(int(match[2]))
    resident_component_vtables = set()
    for line in report.get('native_resident_component_observations', []):
        match = RESIDENT_COMPONENT.search(line)
        if match:
            address = base + int(match[1], 16)
            if not text_high <= address < limit or address & 7:
                raise ValueError(f'Resident component vtable outside aligned main data at {address:#x}')
            resident_component_vtables.add(address)
    if not entries and not candidates and not vtables:
        raise ValueError('The diagnostic contains no recognizable native observations or candidates')

    # Index definitions only. Prototypes and function tables are not function bodies.
    locations = {}
    for path in sorted((generated / 'main').glob('*.c')):
        text = path.read_text(encoding='utf-8')
        definitions = list(DEFINITION.finditer(text))
        for i, match in enumerate(definitions):
            address = int(match[1], 16)
            if not text_low <= address < text_high:
                raise ValueError(f'Function definition outside executable text at {address:#x}')
            if address in locations:
                raise ValueError(f'Duplicate function definition at {address:#x}')
            end = definitions[i + 1].start() if i + 1 < len(definitions) else len(text)
            locations[address] = (path, match.start(), end)
    starts = sorted(locations)
    if not starts:
        raise ValueError('No generated main function definitions found')

    def label(address):
        return f'main+{address - base:#x}' if base <= address < limit else f'{address:#x}'

    def containing(return_address):
        # ARM64 LR is the instruction after the call. Resolve the call site, not the next function at a boundary.
        address = return_address - 4
        if not text_low <= address < text_high:
            return None
        index = bisect_right(starts, address) - 1
        return starts[index] if index >= 0 else None

    by_target = defaultdict(list)
    for entry in entries:
        by_target[entry['address']].append(entry)
    for address in candidates:
        by_target[address]   # a vtable observation does not imply that the function was called
    functions = []
    caller_totals = Counter()
    for address, observed in sorted(by_target.items()):
        location = locations.get(address)
        calls = []
        if location:
            path, start, end = location
            body = path.read_text(encoding='utf-8')[start:end]
            calls = sorted({int(m[1], 16) for m in DIRECT_CALL.finditer(body)})
        callers = defaultdict(list)
        factory_callers = defaultdict(int)
        request_callers = defaultdict(int)
        pipeline_callers = defaultdict(int)
        for entry in observed:
            owner = containing(entry['caller'])
            callers[owner].append(entry)
            if owner is not None:
                caller_totals[owner] += 1
            if entry.get('factory_caller'):
                factory_callers[containing(entry['factory_caller'])] += 1
            if entry.get('request_caller'):
                request_callers[containing(entry['request_caller'])] += 1
            if entry.get('pipeline_caller'):
                pipeline_callers[containing(entry['pipeline_caller'])] += 1
        functions.append(dict(function=label(address), definition_found=location is not None,
                              source=location[0].relative_to(generated).as_posix() if location else None,
                              observations=len(observed), kinds=dict(Counter(e['kind'] for e in observed)),
                              holder_modes=sorted({e['holder_mode'] for e in observed if 'holder_mode' in e}),
                              candidate_roles=['player_method_candidate'] if address in candidates else [],
                              candidate_generations=sorted(candidates.get(address, ())),
                              generations=sorted({e['generation'] for e in observed if e['generation'] is not None}),
                              direct_callees=[label(c) for c in calls],
                              observed_callers=[dict(function=label(owner) if owner is not None else None,
                                                     source=locations[owner][0].relative_to(generated).as_posix()
                                                     if owner is not None else None,
                                                     observations=len(group),
                                                     return_sites=sorted({label(e['caller']) for e in group}),
                                                     host_threads=sorted({e['thread'] for e in group}))
                                                for owner, group in sorted(callers.items(),
                                                                           key=lambda item: -1 if item[0] is None else item[0])],
                              factory_callers=[dict(function=label(owner) if owner is not None else None,
                                                    observations=count)
                                               for owner, count in sorted(factory_callers.items(),
                                                                          key=lambda item: -1 if item[0] is None else item[0])],
                              request_callers=[dict(function=label(owner) if owner is not None else None,
                                                    observations=count)
                                               for owner, count in sorted(request_callers.items(),
                                                                          key=lambda item: -1 if item[0] is None else item[0])],
                              pipeline_callers=[dict(function=label(owner) if owner is not None else None,
                                                     observations=count)
                                                for owner, count in sorted(pipeline_callers.items(),
                                                                           key=lambda item: -1 if item[0] is None else item[0])]))
    kinds = Counter(e['kind'] for e in entries)
    return dict(marker=GENERATED_MARKER, schema_version=1, status='observations_only',
                diagnostic_sha256=hashlib.sha256(diagnostic.read_bytes()).hexdigest(),
                executable_sha256=report.get('executable_sha256'),
                playable_actor_observed=report.get('playable_actor_observed', False),
                player_scene_resident_observed=any('player matched;' in line for line in
                                                  report.get('native_scene_resident_observations', [])),
                trace_count=len(entries), trace_kinds=dict(kinds),
                player_vtables=[dict(address=label(address), generations=sorted(generations))
                                for address, generations in sorted(vtables.items())],
                resident_component_vtables=[label(address) for address in sorted(resident_component_vtables)],
                player_method_candidates=len(candidates),
                constructor_same_actor_count=kinds['constructor_same_actor'],
                constructor_task_descriptor_count=sum(bool(e.get('task_descriptor_observed')) for e in entries),
                holder_same_actor_count=kinds['holder_same_actor'],
                holder_inline_task_count=sum(e.get('inline_task_holder') == 'yes' for e in entries),
                initializer_same_actor_count=kinds['initializer_same_actor'],
                initializer_inline_task_count=sum(e.get('inline_task_context') == 'yes' for e in entries),
                resident_init_same_component_count=kinds['resident_init_same_component'],
                player_epoch_trace_count=sum(e['generation'] is not None for e in entries),
                native_actor_creation_verified=False, world_mutation_phase_verified=False,
                functions=functions,
                frequently_observed_callers=[dict(function=label(a), observations=count)
                                             for a, count in caller_totals.most_common()],
                limitations=['Function entry and x0 matching do not establish the full native ABI.',
                             'A matching constructor invocation does not verify scene registration or safe spawning.',
                             'Physical host-thread identity does not establish guest task ownership or a safe phase.',
                             'Direct callees omit indirect dispatch targets and are not a complete call graph.',
                             'No actor creation, guest calls, memory writes or capability changes are performed.'])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gen', type=Path, default=ROOT / 'build/coop-v143/generated')
    ap.add_argument('--diagnostic', required=True, type=Path)
    ap.add_argument('--out', type=Path, default=ROOT / 'build/coop-v143/native-audit.json')
    args = ap.parse_args(argv)
    out = args.out.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()):
        ap.error('--out must stay below the repository build/ directory')
    generated, diagnostic = args.gen.resolve(), args.diagnostic.resolve()
    if out == diagnostic or out.is_relative_to(generated):
        ap.error('--out must not replace the input report or generated source')
    try:
        report = audit(generated, diagnostic)
    except (OSError, ValueError, StopIteration, KeyError) as error:
        ap.error(str(error))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Native audit: {report["trace_count"]} observations, {len(report["functions"])} function entries; {out}')


if __name__ == '__main__':
    main()
