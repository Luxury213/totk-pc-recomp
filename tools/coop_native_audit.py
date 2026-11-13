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
RESIDENT_RECORD = re.compile(r'vtable main\+(0x[0-9a-fA-F]+), '
                             r'data first word main vtable (yes|no);')
RESIDENT_INIT = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                           r'x0 resident same, host thread (\d+);')
CONSTRUCTOR = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), x0 '
                         r'0x[0-9a-fA-F]+, host thread (\d+)(?:, factory caller (0x[0-9a-fA-F]+))?'
                         r'(?:, request caller (0x[0-9a-fA-F]+))?'
                         r'(?:, pipeline caller (0x[0-9a-fA-F]+))?'
                         r'(?:, task descriptor (0x[0-9a-fA-F]+))?, '
                         r'observed player (same|different);')
ACTOR_REQUEST = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                           r'name ([A-Za-z0-9_]+), manager readable (yes|no), create arg readable (yes|no), '
                           r'transform flags (\d+)(?:, watcher readable (yes|no)'
                           r'(?:, watcher group (\d+))?'
                           r'(?:, watcher resident slot (yes|no|unknown))?, priority (\d+))?, '
                           r'host thread (\d+);')
PLAYER_PIPELINE = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                             r'x0 readable (yes|no), host thread (\d+);')
REQUEST_CONTEXT = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                             r'name ([A-Za-z0-9_]+), constructor task (same|different|unknown), '
                             r'host thread (\d+);')
LIFECYCLE = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                       r'stage (initialize_result|release_140|release_110|release_f0|context_cleanup|task_free|allocator_release), '
                       r'constructor task same, actor (same|different|unscoped), result (\d+), host thread (\d+);')
READY_REFERENCE = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                             r'name ([A-Za-z0-9_]+), state (\d+), resident slot (yes|no|unknown), '
                             r'value actor (same|different|unknown), value resident data (same|different|unknown), '
                             r'host thread (\d+)(?:, publication (yes|no))?(?:, release (yes|no))?'
                             r'(?:, consumption (yes|no))?;')
RESIDENT_BIND = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                           r'target local record same, source actor same, metadata resident data (same|different), '
                           r'host thread (\d+);')
PLAYER_MANAGER_BIND = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                                 r'source actor same, metadata manager data (same|different), host thread (\d+);')
PLAYER_REFERENCE_SOURCE = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                                     r'source resident record (same|different|unknown), actor local same, '
                                     r'metadata manager data (same|different), host thread (\d+);')
ACTOR_TEARDOWN = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                            r'stage (request|queue|cleanup), observed player same, generation (\d+), '
                            r'reason (\d+), actor state (\d+), removal pending (yes|no), host thread (\d+);')
PROBE_ACTOR = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                         r'probe (\d+), name (Weapon[A-Za-z0-9_]*|Npc_Road_001), request task same, metadata backlink same, '
                         r'generation (\d+), host thread (\d+)(?:, request (\d+))?;')
RESOURCE_BIND = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), request (\d+), '
                           r'name ([A-Za-z0-9_]+), task resource same, actor resource same, actor id same, host thread (\d+);')
RESOURCE_CLEANUP = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), request (\d+), '
                              r'name ([A-Za-z0-9_]+), actor id same, actor resource (same|different), host thread (\d+);')
PROBE_TEARDOWN = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                            r'probe (\d+), name (Weapon[A-Za-z0-9_]*), stage (request|queue|cleanup), '
                            r'(?:metadata identity same|actor id same), reason (\d+), actor state (\d+), '
                            r'removal pending (yes|no), host thread (\d+)(?:, metadata live (yes|no))?;')
PROBE_ALLOCATOR = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                             r'probe (\d+), name (Weapon[A-Za-z0-9_]*), cleanup scope same, actor argument same, '
                             r'host thread (\d+);')
REQUEST_ABI = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                         r'name ([A-Za-z0-9_]+), extra registers nonzero mask (\d+), stack readable (yes|no), '
                         r'stack flag (\d+), stack pointers nonzero mask (\d+), host thread (\d+);')
RESIDENT_REFERENCE = re.compile(r'(?:handle present (yes|no), )?handle readable (yes|no), state (\d+), value actor (same|different|unknown), '
                                r'value resident data (same|different|unknown);')
ENQUEUE = re.compile(r'entry main\+(0x[0-9a-fA-F]+), caller (0x[0-9a-fA-F]+), '
                     r'name ([A-Za-z0-9_]+), priority (\d+), manager readable (yes|no), '
                     r'handle readable (yes|no), handle state (\d+), watcher handle same (yes|no), host thread (\d+);')
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
    for line in report.get('native_actor_request_observations', []):
        match = ACTOR_REQUEST.search(line)
        if match and match[3].startswith('Player'):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[11]), generation=None,
                                request_name=match[3], manager_readable=match[4] == 'yes',
                                create_arg_readable=match[5] == 'yes', transform_flags=int(match[6]),
                                watcher_readable=match[7] == 'yes' if match[7] else None,
                                watcher_group=int(match[8]) if match[8] else None,
                                watcher_resident_slot=match[9],
                                priority=int(match[10]) if match[10] else None,
                                kind='actor_request_player_name'))
    for line in report.get('native_player_pipeline_observations', []):
        match = PLAYER_PIPELINE.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[4]), generation=None,
                                receiver_readable=match[3] == 'yes', kind='player_creation_pipeline'))
    for line in report.get('native_request_context_observations', []):
        match = REQUEST_CONTEXT.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[5]), generation=None,
                                context_name=match[3], constructor_task_match=match[4],
                                kind='request_context'))
    for line in report.get('native_lifecycle_observations', []):
        match = LIFECYCLE.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[6]), generation=None, stage=match[3],
                                actor_match=match[4], result=int(match[5]), kind='task_lifecycle'))
    for line in report.get('native_ready_reference_observations', []):
        match = READY_REFERENCE.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[8]), generation=None, reference_name=match[3], reference_state=int(match[4]),
                                reference_resident_slot=match[5], reference_actor_match=match[6],
                                reference_data_match=match[7], publication=match[9] == 'yes' if match[9] else None,
                                reference_release=match[10] == 'yes' if match[10] else None,
                                reference_consumption=match[11] == 'yes' if match[11] else None,
                                kind='ready_reference'))
    for line in report.get('native_enqueue_observations', []):
        match = ENQUEUE.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[9]), generation=None, enqueue_name=match[3], priority=int(match[4]),
                                manager_readable=match[5] == 'yes', handle_readable=match[6] == 'yes',
                                handle_state=int(match[7]), watcher_handle_same=match[8] == 'yes', kind='request_enqueue'))
    for line in report.get('native_resident_bind_observations', []):
        match = RESIDENT_BIND.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[4]), generation=None, metadata_resident_match=match[3] == 'same',
                                kind='resident_bind'))
    for line in report.get('native_player_manager_bind_observations', []):
        match = PLAYER_MANAGER_BIND.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[4]), generation=None, metadata_manager_match=match[3] == 'same',
                                kind='player_manager_bind'))
    for line in report.get('native_player_reference_source_observations', []):
        if match := PLAYER_REFERENCE_SOURCE.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[5]), generation=None, kind='player_reference_source',
                                source_resident_record=match[3], source_metadata_match=match[4] == 'same'))
    for line in report.get('native_actor_teardown_observations', []):
        match = ACTOR_TEARDOWN.search(line)
        if match:
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[8]), generation=int(match[4]), kind='actor_teardown',
                                teardown_stage=match[3], removal_reason=int(match[5]),
                                actor_state=int(match[6]), removal_pending=match[7] == 'yes'))
    for line in report.get('native_probe_actor_observations', []):
        if match := PROBE_ACTOR.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[6]), generation=int(match[5]), kind='probe_actor',
                                probe=int(match[3]), probe_name=match[4]))
    for line in report.get('native_probe_teardown_observations', []):
        if match := PROBE_TEARDOWN.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[9]), generation=None, kind='probe_teardown',
                                probe=int(match[3]), probe_name=match[4], probe_teardown_stage=match[5],
                                removal_reason=int(match[6]), actor_state=int(match[7]), removal_pending=match[8] == 'yes',
                                metadata_live=match[10] != 'no'))
    for line in report.get('native_probe_allocator_observations', []):
        if match := PROBE_ALLOCATOR.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[5]), generation=None, kind='probe_allocator',
                                probe=int(match[3]), probe_name=match[4]))
    for line in report.get('native_request_abi_observations', []):
        if match := REQUEST_ABI.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[8]), generation=None, kind='request_abi',
                                abi_name=match[3], extra_register_mask=int(match[4]), stack_readable=match[5] == 'yes',
                                stack_flag=int(match[6]) if match[5] == 'yes' else None,
                                stack_pointer_mask=int(match[7]) if match[5] == 'yes' else None))
    for line in report.get('native_resource_binding_observations', []):
        if match := RESOURCE_BIND.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[5]), generation=None, kind='resource_binding',
                                resource_request=int(match[3]), resource_name=match[4]))
    for line in report.get('native_resource_cleanup_observations', []):
        if match := RESOURCE_CLEANUP.search(line):
            entries.append(dict(address=base + int(match[1], 16), caller=int(match[2], 16),
                                thread=int(match[6]), generation=None, kind='resource_cleanup',
                                resource_request=int(match[3]), resource_name=match[4], resource_same=match[5] == 'same'))
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
    resident_record_vtables = set()
    for line in report.get('native_resident_record_observations', []):
        match = RESIDENT_RECORD.search(line)
        if match:
            address = base + int(match[1], 16)
            if not text_high <= address < limit or address & 7:
                raise ValueError('Resident record vtable outside aligned main data')
            resident_record_vtables.add((address, match[2] == 'yes'))
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
                              request_names=sorted({e['request_name'] for e in observed if 'request_name' in e}),
                              request_contexts=[dict(name=e['context_name'],
                                                     constructor_task_match=e['constructor_task_match'])
                                                for e in observed if 'context_name' in e],
                              task_lifecycle=[dict(stage=e['stage'], actor_match=e['actor_match'], result=e['result'])
                                              for e in observed if 'stage' in e],
                              ready_references=[dict(name=e['reference_name'], resident_slot=e['reference_resident_slot'],
                                                     state=e['reference_state'],
                                                     actor_match=e['reference_actor_match'], data_match=e['reference_data_match'],
                                                     publication=e['publication'], release=e['reference_release'],
                                                     consumption=e['reference_consumption'])
                                                for e in observed if 'reference_name' in e],
                              request_enqueues=[dict(name=e['enqueue_name'], priority=e['priority'],
                                                     manager_readable=e['manager_readable'], handle_readable=e['handle_readable'],
                                                     handle_state=e['handle_state'], watcher_handle_same=e['watcher_handle_same'])
                                                for e in observed if 'enqueue_name' in e],
                              actor_teardowns=[dict(stage=e['teardown_stage'], generation=e['generation'],
                                                    reason=e['removal_reason'], actor_state=e['actor_state'],
                                                    removal_pending=e['removal_pending'])
                                               for e in observed if 'teardown_stage' in e],
                              probe_actors=[dict(probe=e['probe'], name=e['probe_name'], generation=e['generation'])
                                            for e in observed if e['kind'] == 'probe_actor'],
                              probe_teardowns=[dict(probe=e['probe'], name=e['probe_name'], stage=e['probe_teardown_stage'],
                                                    reason=e['removal_reason'], actor_state=e['actor_state'],
                                                    removal_pending=e['removal_pending'], metadata_live=e['metadata_live'])
                                               for e in observed if 'probe_teardown_stage' in e],
                              probe_allocators=[dict(probe=e['probe'], name=e['probe_name'])
                                                for e in observed if e['kind'] == 'probe_allocator'],
                              resource_bindings=[dict(request=e['resource_request'], name=e['resource_name'])
                                                 for e in observed if e['kind'] == 'resource_binding'],
                              player_reference_sources=[dict(source_resident_record=e['source_resident_record'],
                                                             metadata_same=e['source_metadata_match'])
                                                        for e in observed if e['kind'] == 'player_reference_source'],
                              resource_cleanups=[dict(request=e['resource_request'], name=e['resource_name'], same=e['resource_same'])
                                                 for e in observed if e['kind'] == 'resource_cleanup'],
                              request_abi=[dict(name=e['abi_name'], extra_register_mask=e['extra_register_mask'],
                                                stack_readable=e['stack_readable'], stack_flag=e['stack_flag'],
                                                stack_pointer_mask=e['stack_pointer_mask'])
                                           for e in observed if e['kind'] == 'request_abi'],
                              actor_requests=[dict(name=e['request_name'],
                                                   caller=label(containing(e['caller']))
                                                   if containing(e['caller']) is not None else None,
                                                   return_site=label(e['caller']),
                                                   manager_readable=e['manager_readable'],
                                                   create_arg_readable=e['create_arg_readable'],
                                                   transform_flags=e['transform_flags'],
                                                   watcher_readable=e['watcher_readable'],
                                                   watcher_group=e['watcher_group'],
                                                   watcher_resident_slot=e['watcher_resident_slot'],
                                                   priority=e['priority'])
                                              for e in observed if 'request_name' in e],
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
                resident_record_vtables=[dict(address=label(address), data_first_word_main_vtable=is_vtable)
                                         for address, is_vtable in sorted(resident_record_vtables)],
                player_method_candidates=len(candidates),
                constructor_same_actor_count=kinds['constructor_same_actor'],
                actor_request_player_name_count=kinds['actor_request_player_name'],
                actor_request_exact_player_count=sum(e.get('request_name') == 'Player' for e in entries),
                player_creation_pipeline_count=kinds['player_creation_pipeline'],
                request_constructor_task_match_count=sum(e.get('constructor_task_match') == 'same'
                                                         for e in entries),
                task_lifecycle_stages=dict(Counter(e['stage'] for e in entries if 'stage' in e)),
                reference_event_count=kinds['ready_reference'],
                ready_reference_count=sum(e.get('reference_state') == 3 for e in entries),
                player_reference_publication_count=sum(e.get('publication') is True and
                                                      e.get('reference_actor_match') == 'same' and
                                                      e.get('reference_resident_slot') == 'yes' for e in entries),
                player_reference_release_count=sum(e.get('reference_release') is True and
                                                  e.get('reference_actor_match') == 'same' and
                                                  e.get('reference_resident_slot') == 'yes' for e in entries),
                player_reference_consumption_count=sum(e.get('reference_consumption') is True and
                                                      e.get('reference_actor_match') == 'same' and
                                                      e.get('reference_resident_slot') == 'yes' for e in entries),
                resident_bind_count=kinds['resident_bind'],
                resident_bind_metadata_match_count=sum(e.get('metadata_resident_match') is True for e in entries),
                player_manager_bind_count=kinds['player_manager_bind'],
                player_manager_bind_metadata_match_count=sum(e.get('metadata_manager_match') is True for e in entries),
                actor_teardown_stages=dict(Counter(e['teardown_stage'] for e in entries if 'teardown_stage' in e)),
                probe_actor_count=kinds['probe_actor'],
                probe_allocator_handoff_count=kinds['probe_allocator'], request_abi_count=kinds['request_abi'],
                resource_binding_count=kinds['resource_binding'], resource_cleanup_count=kinds['resource_cleanup'],
                player_reference_source_count=kinds['player_reference_source'],
                resource_cleanup_same_count=sum(e.get('resource_same') is True for e in entries),
                probe_teardown_stages=dict(Counter(e['probe_teardown_stage'] for e in entries if 'probe_teardown_stage' in e)),
                request_enqueue_count=kinds['request_enqueue'],
                resident_references=[dict(handle_present=m[1] == 'yes' if m[1] else None,
                                           handle_readable=m[2] == 'yes', state=int(m[3]),
                                           actor_match=m[4], data_match=m[5])
                                     for line in report.get('native_resident_reference_observations', [])
                                     if (m := RESIDENT_REFERENCE.search(line))],
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
                             'A Player-named creation request does not prove which actor was created or that a second Player is safe.',
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
