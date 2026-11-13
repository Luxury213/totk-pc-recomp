"""Check the private native-audit tool using entirely synthetic C and trace fixtures, without the game."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import coop_native_audit as native


class AuditCheck(unittest.TestCase):
    def test_mapping_and_output_boundary(self):
        parent = ROOT / 'build/tests'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='coop-audit-', dir=parent) as tmp:
            folder = Path(tmp)
            gen = folder / 'generated'
            (gen / 'main').mkdir(parents=True)
            (gen / 'layout.json').write_text(json.dumps([dict(name='main', base='0x1000000000', size='0x1000')]))
            (gen / 'main/manifest.json').write_text(json.dumps(dict(text=['0x1000000000', '0x1000000400'])))
            (gen / 'main/a.c').write_text('''void f_1000000300(Cpu *c);
void f_1000000100(Cpu *c) {
    f_1000000300(c); /* SYNTHETIC_C_BODY_PRIVATE */
}
void f_1000000200(Cpu *c) {
    f_1000000100(c);
}
''')
            (gen / 'main/b.c').write_text('void f_1000000300(Cpu *c) { }\n')
            trace = folder / 'diagnostic.json'
            trace.write_text(json.dumps(dict(playable_actor_observed=True, native_function_observations=[
                '[host] coop native trace: entry main+0x100, caller 0x1000000220, x0 0x1, host thread 7, '
                'generation 4, kind player_method; observation only',
                # LR exactly at the next entry still belongs to the preceding function's call site.
                '[host] coop native trace: entry main+0x100, caller 0x1000000300, x0 0x1, host thread 9, '
                'generation 4, kind player_method; observation only',
                '[host] coop native trace: entry main+0x300, caller 0x1000000050, x0 0x1, host thread 9; '
                'observation only',
                '[host] coop native trace: entry main+0x300, caller 0x1000000800, x0 0x1, host thread 9; '
                'observation only'])))
            report = native.audit(gen, trace)
            self.assertEqual(report['trace_count'], 4)
            self.assertEqual(report['player_epoch_trace_count'], 2)
            self.assertEqual(report['functions'][0]['source'], 'main/a.c')
            self.assertEqual(report['functions'][0]['direct_callees'], ['main+0x300'])
            caller = report['functions'][0]['observed_callers'][0]
            self.assertEqual(caller['function'], 'main+0x200')
            self.assertEqual(caller['observations'], 2)
            self.assertEqual(caller['host_threads'], [7, 9])
            self.assertIsNone(report['functions'][1]['observed_callers'][0]['function'])
            self.assertEqual(report['functions'][1]['observed_callers'][0]['observations'], 2)
            self.assertFalse(report['native_actor_creation_verified'])
            self.assertNotIn('SYNTHETIC_C_BODY_PRIVATE', json.dumps(report))
            candidate_data = json.loads(trace.read_text())
            candidate_data['native_method_candidates'] = [
                '[host] coop native candidate: player vtable+0x200 -> main+0x200, generation 4; observation only']
            candidate_data['native_vtable_observations'] = [
                '[host] coop native vtable: player main+0x500, generation 4; observation only']
            candidate_data['native_scene_resident_observations'] = [
                '[host] coop native scene resident: player matched; observation only']
            candidate_data['native_resident_component_observations'] = [
                '[host] coop native resident component: vtable main+0x500, list count 1; observation only']
            candidate_data['native_resident_record_observations'] = [
                '[host] coop native resident record: vtable main+0x500, '
                'data first word main vtable no; observation only']
            candidate_data['native_resident_init_observations'] = [
                '[host] coop native resident init: entry main+0x300, caller 0x1000000220, '
                'x0 resident same, host thread 7; observation only']
            candidate_data['native_constructor_observations'] = [
                '[host] coop native constructor: entry main+0x300, caller 0x1000000220, x0 0x1234, '
                'host thread 7, factory caller 0x1000000110, request caller 0x1000000210, '
                'pipeline caller 0x1000000310, task descriptor 0x5678, '
                'observed player same; observation only']
            candidate_data['native_actor_request_observations'] = [
                '[host] coop native actor request: entry main+0x300, caller 0x1000000220, '
                'name Player, manager readable yes, create arg readable yes, transform flags 7, '
                'watcher readable yes, watcher group 1, watcher resident slot yes, priority 1, '
                'host thread 7; observation only',
                '[host] coop native actor request: entry main+0x300, caller 0x1000000220, '
                'name Enemy, manager readable yes, create arg readable yes, transform flags 7, '
                'host thread 7; observation only']
            candidate_data['native_player_pipeline_observations'] = [
                '[host] coop native player pipeline: entry main+0x100, caller 0x1000000220, '
                'x0 readable yes, host thread 7; observation only']
            candidate_data['native_request_context_observations'] = [
                '[host] coop native request context: entry main+0x300, caller 0x1000000220, '
                'name Player, constructor task same, host thread 7; observation only',
                '[host] coop native request context: entry main+0x300, caller 0x1000000220, '
                'name PlayerCamera, constructor task different, host thread 7; observation only']
            candidate_data['native_lifecycle_observations'] = [
                '[host] coop native lifecycle: entry main+0x300, caller 0x1000000220, '
                'stage initialize_result, constructor task same, actor same, result 1, host thread 7; observation only',
                '[host] coop native lifecycle: entry main+0x300, caller 0x1000000220, '
                'stage task_free, constructor task same, actor unscoped, result 0, host thread 7; observation only']
            candidate_data['native_ready_reference_observations'] = [
                '[host] coop native ready reference: entry main+0x300, caller 0x1000000220, '
                'name Player, state 3, resident slot yes, value actor same, '
                'value resident data different, host thread 7, publication yes, release no; observation only',
                '[host] coop native ready reference: entry main+0x300, caller 0x1000000220, '
                'name Player, state 3, resident slot yes, value actor same, '
                'value resident data different, host thread 7, publication no, release yes; observation only',
                '[host] coop native reference event: entry main+0x300, caller 0x1000000220, '
                'name PlayerCamera, state 5, resident slot no, value actor unknown, '
                'value resident data unknown, host thread 7, publication no, release yes; observation only',
                '[host] coop native reference event: entry main+0x300, caller 0x1000000220, '
                'name Player, state 3, resident slot yes, value actor same, '
                'value resident data different, host thread 7, publication no, release no, consumption yes; observation only']
            candidate_data['native_resident_bind_observations'] = [
                '[host] coop native resident bind: entry main+0x300, caller 0x1000000220, '
                'target local record same, source actor same, metadata resident data same, host thread 7; observation only']
            candidate_data['native_player_manager_bind_observations'] = [
                '[host] coop native player manager bind: entry main+0x300, caller 0x1000000220, '
                'source actor same, metadata manager data same, host thread 7; observation only']
            candidate_data['native_resident_reference_observations'] = [
                '[host] coop native resident reference: handle present yes, handle readable yes, state 3, '
                'value actor different, value resident data same; observation only']
            candidate_data['native_enqueue_observations'] = [
                '[host] coop native request enqueue: entry main+0x300, caller 0x1000000220, '
                'name Player, priority 1, manager readable yes, handle readable yes, handle state 2, '
                'watcher handle same yes, host thread 7; observation only']
            candidate_data['native_holder_observations'] = [
                '[host] coop native holder: target 0x1000000300, caller 0x1000000210, x0 0x4567, '
                'x1 player same, x2 1, host thread 7, inline task holder yes; observation only']
            candidate_data['native_initializer_observations'] = [
                '[host] coop native initializer: target 0x1000000300, caller 0x1000000210, '
                'x0 player same, x1 task+0x18 yes, host thread 7; observation only']
            candidate_data['native_actor_teardown_observations'] = [
                '[host] coop native actor teardown: entry main+0x300, caller 0x1000000220, '
                'stage request, observed player same, generation 4, reason 2, actor state 0, '
                'removal pending no, host thread 7; observation only',
                '[host] coop native actor teardown: entry main+0x300, caller 0x1000000220, '
                'stage queue, observed player same, generation 4, reason 0, actor state 0, '
                'removal pending yes, host thread 7; observation only',
                '[host] coop native actor teardown: entry main+0x300, caller 0x1000000220, '
                'stage cleanup, observed player same, generation 4, reason 0, actor state 11, '
                'removal pending yes, host thread 9; observation only']
            candidate_data['native_probe_actor_observations'] = [
                '[host] coop native probe actor: entry main+0x300, caller 0x1000000220, probe 7, '
                'name Weapon_Sword_Test, request task same, metadata backlink same, generation 4, '
                'host thread 7; observation only']
            candidate_data['native_probe_teardown_observations'] = [
                '[host] coop native probe teardown: entry main+0x300, caller 0x1000000220, probe 7, '
                'name Weapon_Sword_Test, stage request, metadata identity same, reason 0, actor state 4, '
                'removal pending no, host thread 7; observation only',
                '[host] coop native probe teardown: entry main+0x300, caller 0x1000000220, probe 7, '
                'name Weapon_Sword_Test, stage queue, actor id same, reason 0, actor state 4, '
                'removal pending yes, host thread 7, metadata live yes; observation only',
                '[host] coop native probe teardown: entry main+0x300, caller 0x1000000220, probe 7, '
                'name Weapon_Sword_Test, stage cleanup, actor id same, reason 0, actor state 11, '
                'removal pending yes, host thread 9, metadata live no; observation only']
            candidate_data['native_probe_allocator_observations'] = [
                '[host] coop native probe allocator: entry main+0x300, caller 0x1000000220, probe 7, '
                'name Weapon_Sword_Test, cleanup scope same, actor argument same, host thread 9; observation only']
            candidate_data['native_request_abi_observations'] = [
                '[host] coop native request abi: entry main+0x300, caller 0x1000000220, name Player, '
                'extra registers nonzero mask 0, stack readable yes, stack flag 0, '
                'stack pointers nonzero mask 0, host thread 7; observation only',
                '[host] coop native request abi: entry main+0x300, caller 0x1000000220, name PlayerCamera, '
                'extra registers nonzero mask 0, stack readable no, stack flag 0, '
                'stack pointers nonzero mask 0, host thread 7; observation only']
            candidate_data['native_resource_binding_observations'] = [
                '[host] coop native resource binding: entry main+0x300, caller 0x1000000220, request 10, '
                'name Weapon_Sword_Test, task resource same, actor resource same, actor id same, host thread 7; observation only']
            candidate_data['native_resource_cleanup_observations'] = [
                '[host] coop native resource cleanup: entry main+0x300, caller 0x1000000220, request 10, '
                'name Weapon_Sword_Test, actor id same, actor resource same, host thread 9; observation only']
            candidate_data['native_player_reference_source_observations'] = [
                '[host] coop native player reference source: entry main+0x300, caller 0x1000000220, '
                'source resident record same, actor local same, metadata manager data same, host thread 7; observation only']
            trace.write_text(json.dumps(candidate_data))
            candidate_report = native.audit(gen, trace)
            self.assertEqual(candidate_report['player_method_candidates'], 1)
            self.assertEqual(candidate_report['player_vtables'],
                             [dict(address='main+0x500', generations=[4])])
            self.assertEqual(candidate_report['constructor_same_actor_count'], 1)
            self.assertEqual(candidate_report['actor_request_player_name_count'], 1)
            self.assertEqual(candidate_report['actor_request_exact_player_count'], 1)
            self.assertEqual(candidate_report['player_creation_pipeline_count'], 1)
            self.assertEqual(candidate_report['request_constructor_task_match_count'], 1)
            self.assertEqual(candidate_report['task_lifecycle_stages'], dict(initialize_result=1, task_free=1))
            self.assertEqual(candidate_report['ready_reference_count'], 3)
            self.assertEqual(candidate_report['reference_event_count'], 4)
            self.assertEqual(candidate_report['player_reference_publication_count'], 1)
            self.assertEqual(candidate_report['player_reference_release_count'], 1)
            self.assertEqual(candidate_report['player_reference_consumption_count'], 1)
            self.assertEqual(candidate_report['resident_bind_count'], 1)
            self.assertEqual(candidate_report['resident_bind_metadata_match_count'], 1)
            self.assertEqual(candidate_report['player_manager_bind_count'], 1)
            self.assertEqual(candidate_report['player_manager_bind_metadata_match_count'], 1)
            self.assertEqual(candidate_report['actor_teardown_stages'], dict(request=1, queue=1, cleanup=1))
            self.assertEqual(candidate_report['probe_actor_count'], 1)
            self.assertEqual(candidate_report['probe_allocator_handoff_count'], 1)
            self.assertEqual(candidate_report['request_abi_count'], 2)
            self.assertEqual(candidate_report['resource_binding_count'], 1)
            self.assertEqual(candidate_report['resource_cleanup_count'], 1)
            self.assertEqual(candidate_report['resource_cleanup_same_count'], 1)
            self.assertEqual(candidate_report['player_reference_source_count'], 1)
            self.assertEqual(candidate_report['probe_teardown_stages'], dict(request=1, queue=1, cleanup=1))
            self.assertEqual(candidate_report['resident_references'], [
                dict(handle_present=True, handle_readable=True, state=3, actor_match='different', data_match='same')])
            self.assertEqual(candidate_report['request_enqueue_count'], 1)
            self.assertEqual(candidate_report['constructor_task_descriptor_count'], 1)
            self.assertEqual(candidate_report['holder_same_actor_count'], 1)
            self.assertEqual(candidate_report['holder_inline_task_count'], 1)
            self.assertEqual(candidate_report['initializer_same_actor_count'], 1)
            self.assertEqual(candidate_report['initializer_inline_task_count'], 1)
            self.assertTrue(candidate_report['player_scene_resident_observed'])
            self.assertEqual(candidate_report['resident_component_vtables'], ['main+0x500'])
            self.assertEqual(candidate_report['resident_record_vtables'],
                             [dict(address='main+0x500', data_first_word_main_vtable=False)])
            self.assertEqual(candidate_report['resident_init_same_component_count'], 1)
            ctor = next(f for f in candidate_report['functions'] if f['function'] == 'main+0x300')
            self.assertEqual(ctor['factory_callers'], [dict(function='main+0x100', observations=1)])
            self.assertEqual(ctor['request_callers'], [dict(function='main+0x200', observations=1)])
            self.assertEqual(ctor['pipeline_callers'], [dict(function='main+0x300', observations=1)])
            self.assertEqual(ctor['holder_modes'], [1])
            self.assertEqual(ctor['request_names'], ['Player'])
            self.assertEqual(ctor['request_contexts'], [
                dict(name='Player', constructor_task_match='same'),
                dict(name='PlayerCamera', constructor_task_match='different')])
            self.assertEqual(ctor['task_lifecycle'], [
                dict(stage='initialize_result', actor_match='same', result=1),
                dict(stage='task_free', actor_match='unscoped', result=0)])
            self.assertEqual(ctor['ready_references'], [
                dict(name='Player', state=3, resident_slot='yes', actor_match='same', data_match='different', publication=True, release=False, consumption=None),
                dict(name='Player', state=3, resident_slot='yes', actor_match='same', data_match='different', publication=False, release=True, consumption=None),
                dict(name='PlayerCamera', state=5, resident_slot='no', actor_match='unknown', data_match='unknown', publication=False, release=True, consumption=None),
                dict(name='Player', state=3, resident_slot='yes', actor_match='same', data_match='different', publication=False, release=False, consumption=True)])
            self.assertEqual(ctor['request_enqueues'], [
                dict(name='Player', priority=1, manager_readable=True, handle_readable=True,
                     handle_state=2, watcher_handle_same=True)])
            self.assertEqual(ctor['actor_teardowns'], [
                dict(stage='request', generation=4, reason=2, actor_state=0, removal_pending=False),
                dict(stage='queue', generation=4, reason=0, actor_state=0, removal_pending=True),
                dict(stage='cleanup', generation=4, reason=0, actor_state=11, removal_pending=True)])
            self.assertEqual(ctor['probe_actors'], [dict(probe=7, name='Weapon_Sword_Test', generation=4)])
            self.assertEqual(ctor['probe_allocators'], [dict(probe=7, name='Weapon_Sword_Test')])
            self.assertEqual(ctor['resource_bindings'], [dict(request=10, name='Weapon_Sword_Test')])
            self.assertEqual(ctor['resource_cleanups'], [dict(request=10, name='Weapon_Sword_Test', same=True)])
            self.assertEqual(ctor['player_reference_sources'], [dict(source_resident_record='same', metadata_same=True)])
            self.assertEqual(ctor['request_abi'], [
                dict(name='Player', extra_register_mask=0, stack_readable=True, stack_flag=0, stack_pointer_mask=0),
                dict(name='PlayerCamera', extra_register_mask=0, stack_readable=False, stack_flag=None, stack_pointer_mask=None)])
            self.assertEqual(ctor['probe_teardowns'], [
                dict(probe=7, name='Weapon_Sword_Test', stage='request', reason=0, actor_state=4,
                     removal_pending=False, metadata_live=True),
                dict(probe=7, name='Weapon_Sword_Test', stage='queue', reason=0, actor_state=4,
                     removal_pending=True, metadata_live=True),
                dict(probe=7, name='Weapon_Sword_Test', stage='cleanup', reason=0, actor_state=11,
                     removal_pending=True, metadata_live=False)])
            self.assertEqual(ctor['actor_requests'], [dict(name='Player', caller='main+0x200',
                                                          return_site='main+0x220', manager_readable=True,
                                                          create_arg_readable=True, transform_flags=7,
                                                          watcher_readable=True, watcher_group=1,
                                                          watcher_resident_slot='yes',
                                                          priority=1)])
            candidate = next(f for f in candidate_report['functions'] if f['function']=='main+0x200')
            self.assertEqual(candidate['observations'], 0)
            self.assertEqual(candidate['candidate_roles'], ['player_method_candidate'])
            output = folder / 'audit.json'
            with contextlib.redirect_stdout(io.StringIO()):
                native.main(['--gen', str(gen), '--diagnostic', str(trace), '--out', str(output)])
            self.assertEqual(json.loads(output.read_text())['status'], 'observations_only')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                native.main(['--gen', str(gen), '--diagnostic', str(trace),
                             '--out', str(ROOT / 'docs/forbidden-audit.json')])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((ROOT / 'docs/forbidden-audit.json').exists())
            (gen / 'main/b.c').write_text('void f_1000000100(Cpu *c) { }\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                native.audit(gen, trace)


if __name__ == '__main__':
    unittest.main()
