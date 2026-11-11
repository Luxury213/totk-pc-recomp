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
            candidate_data['native_resident_init_observations'] = [
                '[host] coop native resident init: entry main+0x300, caller 0x1000000220, '
                'x0 resident same, host thread 7; observation only']
            candidate_data['native_constructor_observations'] = [
                '[host] coop native constructor: entry main+0x300, caller 0x1000000220, x0 0x1234, '
                'host thread 7, factory caller 0x1000000110, request caller 0x1000000210, '
                'pipeline caller 0x1000000310, task descriptor 0x5678, '
                'observed player same; observation only']
            candidate_data['native_holder_observations'] = [
                '[host] coop native holder: target 0x1000000300, caller 0x1000000210, x0 0x4567, '
                'x1 player same, x2 1, host thread 7, inline task holder yes; observation only']
            candidate_data['native_initializer_observations'] = [
                '[host] coop native initializer: target 0x1000000300, caller 0x1000000210, '
                'x0 player same, x1 task+0x18 yes, host thread 7; observation only']
            trace.write_text(json.dumps(candidate_data))
            candidate_report = native.audit(gen, trace)
            self.assertEqual(candidate_report['player_method_candidates'], 1)
            self.assertEqual(candidate_report['player_vtables'],
                             [dict(address='main+0x500', generations=[4])])
            self.assertEqual(candidate_report['constructor_same_actor_count'], 1)
            self.assertEqual(candidate_report['constructor_task_descriptor_count'], 1)
            self.assertEqual(candidate_report['holder_same_actor_count'], 1)
            self.assertEqual(candidate_report['holder_inline_task_count'], 1)
            self.assertEqual(candidate_report['initializer_same_actor_count'], 1)
            self.assertEqual(candidate_report['initializer_inline_task_count'], 1)
            self.assertTrue(candidate_report['player_scene_resident_observed'])
            self.assertEqual(candidate_report['resident_component_vtables'], ['main+0x500'])
            self.assertEqual(candidate_report['resident_init_same_component_count'], 1)
            ctor = next(f for f in candidate_report['functions'] if f['function'] == 'main+0x300')
            self.assertEqual(ctor['factory_callers'], [dict(function='main+0x100', observations=1)])
            self.assertEqual(ctor['request_callers'], [dict(function='main+0x200', observations=1)])
            self.assertEqual(ctor['pipeline_callers'], [dict(function='main+0x300', observations=1)])
            self.assertEqual(ctor['holder_modes'], [1])
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
