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
            trace.write_text(json.dumps(candidate_data))
            candidate_report = native.audit(gen, trace)
            self.assertEqual(candidate_report['player_method_candidates'], 1)
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
