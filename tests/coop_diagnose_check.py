"""Check diagnostic acceptance using synthetic logs, without game files or Windows processes."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import coop_diagnose as diagnose


def sample(time, generation, x):
    return (f'[host] coop native local sample: world ms {time:.1f}, generation {generation}, '
            f'pos {x:.6f} 0.000000 0.000000, yaw 0.000000, action 0; observation only')


def control_inputs():
    return [f'[host] input: script frame {at // 16} at {at:.1f} ms: {event}'
            for at, _, event in diagnose.CONTROL_EVENTS]


def object_events(probe=0, name='Weapon_Sword_Test', request=None):
    actor = (f'[host] coop native probe actor: entry main+0x300, caller 0x1000000220, probe {probe}, name {name}, '
             'request task same, metadata backlink same, generation 3, host thread 7'
             + (f', request {request}' if request is not None else '') + '; observation only')
    events = [(f'[host] coop native probe teardown: entry main+0x300, caller 0x1000000220, probe {probe}, name {name}, '
               f'stage {stage}, metadata identity same, reason 0, actor state 0, removal pending {pending}, '
               'host thread 7; observation only')
              for stage, pending in [('request', 'no'), ('queue', 'yes'), ('cleanup', 'yes')]]
    return [actor, *events]


def resource_events(request=10, name='Weapon_Sword_Test'):
    return [f'[host] coop native resource binding: entry main+0x300, caller 0x1000000220, request {request}, '
            f'name {name}, task resource same, actor resource same, actor id same, host thread 7; observation only',
            f'[host] coop native resource cleanup: entry main+0x300, caller 0x1000000220, request {request}, '
            f'name {name}, actor id same, actor resource same, host thread 7; observation only']


class DiagnosticChecks(unittest.TestCase):
    def npc_peer_fixture(self):
        lines = ['coop native npc physics: probe 10, request 5, entry main+0x2e27b0, caller 0, '
                 'generation 3, world us 0, host thread 1, phase later-actor-update; owner and metadata matched, observation only',
                 'coop native npc peer binding: session 11, player 22, remote generation 1, local generation 3; diagnostic velocity only']
        samples, pos, previous = [], [0., 3., 0.], [0., 0., 0.]
        for i in range(187):
            t = 1000000+i*50000
            pos = [p+v*.05 for p, v in zip(pos, previous)]
            samples.append(dict(probe=10, request=5, world_us=t, pos=list(pos)))
            if i > 160:
                continue
            reason, vx, vz = ('fresh', 2, 0) if 1250000 <= t < 2250000 else (
                ('expired', 0, 0) if 2250000 <= t < 3050000 else (
                ('fresh', -2, 0) if 3050000 <= t < 4050000 else (
                ('expired', 0, 0) if 4050000 <= t < 4850000 else (
                ('fresh', 1, 1) if 4850000 <= t < 5850000 else ('finished' if i == 160 else 'waiting', 0, 0)))))
            previous = [vx, 0., vz]
            lines.append(f'coop native npc peer velocity: step {i+1}, reason {reason}, generation 3, '
                         f'world us {t}, velocity {vx:.6f} 0.000000 {vz:.6f}; leased native request, original CPU restored')
        return lines, dict(actor_name='Npc_Road_001', acceptance_passed=True,
                           initialized=[dict(probe=10, request=5)], samples=samples)

    def test_peer_motion_requires_displacement_expiry_stops_and_recovery(self):
        lines, spawn = self.npc_peer_fixture()
        result = diagnose.npc_peer_velocity_summary(lines, spawn)
        self.assertTrue(result['acceptance_passed'])
        self.assertFalse(result['human_peer_verified'])
        for change in ('wrong_world', 'wrong_probe', 'missing_finish', 'duplicate_step', 'no_expiry',
                       'moving_during_gap', 'floating_during_gap', 'teleport', 'stationary'):
            with self.subTest(change=change):
                lines, spawn = self.npc_peer_fixture()
                if change == 'wrong_world':
                    lines = [l.replace('generation 3,', 'generation 4,') for l in lines]
                elif change == 'wrong_probe':
                    spawn['initialized'] = [dict(probe=11, request=5)]
                elif change == 'missing_finish':
                    lines = [l for l in lines if 'reason finished,' not in l]
                elif change == 'duplicate_step':
                    lines.append(lines[-1])
                elif change == 'no_expiry':
                    lines = [l.replace('reason expired,', 'reason waiting,') for l in lines]
                elif change in ('moving_during_gap', 'floating_during_gap'):
                    for s in spawn['samples']:
                        if 2250000 <= s['world_us'] < 3050000:
                            s['pos'][0 if change == 'moving_during_gap' else 1] += (s['world_us']-2250000)/1000000
                elif change == 'teleport':
                    spawn['samples'][20]['pos'][0] += 10
                else:
                    for s in spawn['samples']:
                        s['pos'] = [0., 3., 0.]
                self.assertFalse(diagnose.npc_peer_velocity_summary(lines, spawn)['acceptance_passed'])

    def npc_motion_fixture(self):
        lines = ['coop native npc physics: probe 10, request 5, entry main+0x2e27b0, caller 0, '
                 'generation 3, world us 0, host thread 1, phase later-actor-update; owner and metadata matched, observation only']
        for i in range(41):
            phase = 'forward' if i < 20 else 'reverse' if i < 40 else 'stop'
            vx = 2 if i < 20 else -2 if i < 40 else 0
            lines.append(f'coop native npc velocity probe: step {i+1}, phase {phase}, generation 3, '
                         f'world us {2000000+i*50000}, velocity {vx}.000000 0.000000 0.000000; '
                         'native request, original CPU restored')
        samples = []
        for i in range(35):
            t = 1800000+i*100000
            x = max(0, (t-2000000)/500000) if t <= 3000000 else max(0, (4000000-t)/500000)
            samples.append(dict(probe=10, request=5, world_us=t, pos=[x, 3, 0]))
        spawn = dict(actor_name='Npc_Road_001', acceptance_passed=True,
                     initialized=[dict(probe=10, request=5)], samples=samples)
        return lines, spawn

    def test_npc_motion_requires_native_direction_changes_and_later_rest(self):
        lines, spawn = self.npc_motion_fixture()
        report = diagnose.npc_velocity_summary(lines, spawn)
        self.assertTrue(report['acceptance_passed'])
        self.assertEqual(report['forward_distance'], 2)
        self.assertEqual(report['reverse_distance'], 2)
        self.assertFalse(report['remote_control_verified'])
        self.assertFalse(report['native_companion_verified'])
        for row in spawn['samples']:
            row['pos'][0] = 0
        self.assertFalse(diagnose.npc_velocity_summary(lines, spawn)['acceptance_passed'])

    def test_npc_motion_rejects_missing_stop_duplicate_steps_and_wrong_world(self):
        lines, spawn = self.npc_motion_fixture()
        for invalid in (lines[:-1], lines+[lines[-1]], lines[1:],
                        [l.replace('generation 3,', 'generation 4,') if 'step 2,' in l else l for l in lines],
                        lines+['coop native npc velocity probe: aborted; target identity changed'],
                        [lines[0].replace('request 5,', 'request 6,'), *lines[1:]]):
            self.assertFalse(diagnose.npc_velocity_summary(invalid, spawn)['acceptance_passed'])

    def test_npc_motion_rejects_another_actor_a_teleport_or_unsettled_result(self):
        lines, spawn = self.npc_motion_fixture()
        spawn['samples'][8]['pos'][0] += 20
        self.assertFalse(diagnose.npc_velocity_summary(lines, spawn)['acceptance_passed'])

        lines, spawn = self.npc_motion_fixture()
        for sample in spawn['samples']:
            sample['probe'] = 11
        self.assertFalse(diagnose.npc_velocity_summary(lines, spawn)['acceptance_passed'])
        lines, spawn = self.npc_motion_fixture()
        spawn['samples'] = [s for s in spawn['samples'] if s['world_us'] <= 4000000]
        self.assertFalse(diagnose.npc_velocity_summary(lines, spawn)['acceptance_passed'])

    def test_consumer_corrections_require_the_same_world_and_pulse(self):
        lines, spawn = self.npc_motion_fixture()
        motion = diagnose.npc_velocity_summary(lines, spawn)
        corrections = [f'coop native npc velocity consumer reapply: correction {i+1}, generation 3, '
                       f'world us {2000000+i*50000}; same live pending request, original CPU restored' for i in range(40)]
        self.assertTrue(diagnose.npc_consumer_reapply_summary(corrections, motion)['acceptance_passed'])
        for invalid in ([], corrections+[corrections[-1]], corrections[1:],
                        [l.replace('generation 3,', 'generation 4,') for l in corrections],
                        [l.replace('world us 2000000;', 'world us 1999999;') for l in corrections]):
            self.assertFalse(diagnose.npc_consumer_reapply_summary(invalid, motion)['acceptance_passed'])

    def test_game_exit_zero_does_not_hide_failed_diagnostic_gates(self):
        report=dict(exit_code=0, timed_out=False, source_save_unchanged=True, playable_actor_observed=True,
                    object_lifecycle=dict(acceptance_passed=True),
                    native_spawn_experiment=dict(acceptance_passed=True, owned_argument_observed=True,
                                                  retirement_observed=True, fall=dict(acceptance_passed=True)))
        def evaluate():
            return diagnose.diagnostic_acceptance(report, scenario='object', spawning=True, owned=True,
                                                   require_spawn_retirement=True, require_spawn_fall=True)
        self.assertTrue(all(evaluate().values()))
        # A successful game run silently falling back without the requested layer is not validation evidence.
        report['vulkan_validation_requested'] = True
        self.assertFalse(evaluate()['validation'])
        report['vulkan_validation_enabled'] = True
        self.assertTrue(evaluate()['validation'])
        report['vulkan_validation_errors'] = 1
        self.assertFalse(evaluate()['validation'])
        report['vulkan_validation_errors'] = 0
        for gate in ('acceptance_passed', 'owned_argument_observed', 'retirement_observed'):
            report['native_spawn_experiment'][gate]=False
            self.assertFalse(all(evaluate().values()))
            report['native_spawn_experiment'][gate]=True
        report['native_spawn_experiment']['fall']['acceptance_passed']=False
        self.assertFalse(evaluate()['native_fall'])
        report['native_spawn_experiment']['fall']['acceptance_passed']=True
        report['object_lifecycle']['acceptance_passed']=False
        self.assertFalse(evaluate()['object_lifecycle'])
        report['object_lifecycle']['acceptance_passed']=True
        report['timed_out']=True
        self.assertFalse(evaluate()['game_exited'])
        report['timed_out']=False
        report['source_save_unchanged']=False
        self.assertFalse(evaluate()['source_save_unchanged'])

    def test_native_fall_requires_gradual_descent_and_later_rest(self):
        def trajectory(heights):
            return [dict(probe=3, request=10, world_us=10000000+i*120000, pos=[1, y, 3])
                    for i,y in enumerate(heights)]
        samples=trajectory([12,12,11.95,11.8,11.5,11.1,10.7,10.5]+[10.5]*10)
        report=diagnose.spawn_fall_summary(samples, [1,12,3])
        self.assertTrue(report['origin_matched'] and report['descent_observed'] and report['settled_after_descent'])
        self.assertEqual(report['descent_distance'], 1.5)
        self.assertTrue(report['acceptance_passed'])
        for invalid in (trajectory([12,12]+[10.5]*16), trajectory([12]*18),
                        trajectory([12-i*.1 for i in range(18)]), samples[:7],
                        samples[:2]+samples[1:], samples[::-1]):
            self.assertFalse(diagnose.spawn_fall_summary(invalid, [1,12,3])['acceptance_passed'])
        self.assertFalse(diagnose.spawn_fall_summary(samples, [5,12,3])['acceptance_passed'])
        mixed=[dict(s, probe=4) if i==5 else s for i,s in enumerate(samples)]
        self.assertFalse(diagnose.spawn_fall_summary(mixed, [1,12,3])['acceptance_passed'])
        delayed=[dict(s, world_us=s['world_us']+i*500000) for i,s in enumerate(samples)]
        self.assertFalse(diagnose.spawn_fall_summary(delayed, [1,12,3])['acceptance_passed'])

    def test_owned_argument_evidence_is_distinct_from_initialization(self):
        owned='coop native spawn owned: pos 1 12 3, empty blackboard, actor dependencies absent;'
        report=diagnose.native_spawn_summary([owned])
        self.assertTrue(report['owned_argument_observed'])
        self.assertFalse(report['acceptance_passed'] or report['fall']['acceptance_passed'])
        self.assertFalse(diagnose.native_spawn_summary([owned,owned])['owned_argument_observed'])
        for invalid in ('nan', '.', '--1', '1.2.3'):
            self.assertFalse(diagnose.native_spawn_summary([owned.replace('pos 1 ', f'pos {invalid} ')])['owned_argument_observed'])

    def test_npc_creation_evidence_cannot_be_borrowed_from_a_weapon(self):
        actor = object_events(0, 'Npc_Road_001', 10)[0]
        queued = 'coop native spawn probe: queued yes, name Npc_Road_001, original CPU restored;'
        request = 'coop native spawn request: request 10, name Npc_Road_001, watcher absent;'
        lines = [queued, request, actor]
        self.assertTrue(diagnose.native_spawn_summary(lines, 'Npc_Road_001')['acceptance_passed'])
        self.assertFalse(diagnose.native_spawn_summary(lines)['acceptance_passed'])
        self.assertFalse(diagnose.native_spawn_summary(
            [queued.replace('Npc_Road_001', 'Weapon_Sword_101'), request, actor],
            'Npc_Road_001')['acceptance_passed'])

    def test_native_spawn_requires_the_injected_request_not_an_ordinary_drop(self):
        actor=object_events(0, 'Weapon_Sword_101', 10)[0]
        queued='coop native spawn probe: queued yes, name Weapon_Sword_101, original CPU restored;'
        request='coop native spawn request: request 10, name Weapon_Sword_101, watcher absent;'
        self.assertFalse(diagnose.native_spawn_summary([queued,actor])['acceptance_passed'])
        lines=[queued,request,actor]
        report=diagnose.native_spawn_summary(lines)
        self.assertTrue(report['acceptance_passed'])
        self.assertFalse(report['physics_verified'] or report['native_companion_verified'])
        self.assertFalse(diagnose.native_spawn_summary(lines+[queued])['acceptance_passed'])
        self.assertFalse(diagnose.native_spawn_summary([queued,request,actor.replace('request 10','request 11')])['acceptance_passed'])

    def test_native_spawn_retirement_cannot_borrow_the_original_drop_lifecycle(self):
        queued='coop native spawn probe: queued yes, name Weapon_Sword_101, original CPU restored;'
        request='coop native spawn request: request 10, name Weapon_Sword_101, watcher absent;'
        injected=object_events(0, 'Weapon_Sword_101', 10)
        original=object_events(1, 'Weapon_Sword_101', 11)
        allocator=('coop native probe allocator: entry main+0x300, caller 0x1000000220, probe 0, '
                   'name Weapon_Sword_101, cleanup scope same, actor argument same, host thread 7; observation only')
        lines=[queued,request,injected[0],*original,*resource_events(11, 'Weapon_Sword_101')]
        self.assertFalse(diagnose.native_spawn_summary(lines)['retirement_observed'])
        lines += injected[1:] + resource_events(10, 'Weapon_Sword_101')
        self.assertFalse(diagnose.native_spawn_summary(lines)['retirement_observed'])
        self.assertTrue(diagnose.native_spawn_summary(lines+[allocator])['retirement_observed'])
        self.assertFalse(diagnose.native_spawn_summary(lines+[allocator.replace('probe 0','probe 1')])['retirement_observed'])

    def test_visual_capture_requires_correlated_samples_and_frame_progress(self):
        def sample(at, frame, generation=1, name='Synthetic_Walk'):
            return [f'coop native local sample: world ms {at}, generation {generation}, '
                    'pos 10 20 30, yaw 0, action 0; observation only',
                    f'coop visual sample: world ms {at}, generation {generation}, rotation observed, '
                    f'animation {name}, frame {frame}; observation only']
        lines=sample(1000,1)+sample(1250,8)
        result=diagnose.visual_summary(lines)
        self.assertTrue(result['rotation_observed'] and result['animation_advancing'])
        self.assertEqual(result['animation_names'], ['Synthetic_Walk'])
        self.assertFalse(result['native_companion_verified'])
        self.assertFalse(diagnose.visual_summary(sample(1000,8)+sample(1250,8))['animation_advancing'])
        self.assertFalse(diagnose.visual_summary(sample(1000,1)+sample(1250,8,2))['animation_advancing'])
        self.assertFalse(diagnose.visual_summary(sample(1000,1)+sample(1250,8,name='Synthetic_Attack'))['animation_advancing'])
        self.assertFalse(diagnose.visual_summary(lines[1::2])['samples'])
        self.assertFalse(diagnose.visual_summary(sample(1000,1,'1',name='unavailable'))['animation_names'])

    def test_object_lifecycle_requires_one_correlated_actor(self):
        lines = object_events()
        report = diagnose.probe_summary(lines)
        self.assertTrue(report['observed_lifecycle_complete'])
        self.assertFalse(report['native_actor_removal_verified'])
        self.assertFalse(report['native_companion_verified'])
        for missing in range(len(lines)):
            self.assertFalse(diagnose.probe_summary(lines[:missing]+lines[missing+1:])['observed_lifecycle_complete'])
        for index in (1, 2, 3):
            mixed = lines.copy()
            mixed[index] = mixed[index].replace('probe 0,', 'probe 1,')
            self.assertFalse(diagnose.probe_summary(mixed)['observed_lifecycle_complete'])

    def test_object_lifecycle_rejects_reordering_duplicates_and_identity_mismatch(self):
        lines = object_events()
        for invalid in ([lines[0], lines[2], lines[1], lines[3]], lines+[lines[3]],
                        [lines[0], lines[1], lines[2].replace('pending yes', 'pending no'), lines[3]],
                        [lines[0], lines[1], lines[2], lines[3].replace('Weapon_Sword_Test', 'Weapon_Bow_Test')]):
            self.assertFalse(diagnose.probe_summary(invalid)['observed_lifecycle_complete'])

    def test_object_target_cannot_be_satisfied_by_another_weapon(self):
        lines = object_events(0, 'Weapon_Shield_Test') + object_events(1, 'Weapon_Sword_Test')[:1]
        self.assertTrue(diagnose.probe_summary(lines)['observed_lifecycle_complete'])
        self.assertFalse(diagnose.probe_summary(lines, 'Weapon_Sword_Test')['observed_lifecycle_complete'])
        self.assertTrue(diagnose.probe_summary(lines, 'Weapon_Shield_Test')['observed_lifecycle_complete'])

    def test_allocator_handoff_requires_the_same_cleaned_probe(self):
        handoff = ('[host] coop native probe allocator: entry main+0x300, caller 0x1000000220, probe 0, '
                   'name Weapon_Sword_Test, cleanup scope same, actor argument same, host thread 7; observation only')
        lines = object_events()
        self.assertFalse(diagnose.probe_summary(lines)['allocator_handoff_observed'])
        report = diagnose.probe_summary(lines+[handoff])
        self.assertTrue(report['allocator_handoff_observed'])
        self.assertFalse(report['native_actor_removal_verified'])
        for invalid in (lines+[handoff.replace('probe 0,', 'probe 1,')],
                        lines+[handoff.replace('Weapon_Sword_Test', 'Weapon_Bow_Test')],
                        lines+[handoff, handoff], lines[:-1]+[handoff, lines[-1]]):
            self.assertFalse(diagnose.probe_summary(invalid)['allocator_handoff_observed'])

    def test_resource_binding_must_survive_until_the_same_actor_cleanup(self):
        actor = object_events(request=10)
        binding, cleanup = resource_events()
        report = diagnose.probe_summary(actor+[binding, cleanup], require_resource=True)
        self.assertTrue(report['resource_lifetime_observed'])
        self.assertTrue(report['acceptance_passed'])
        self.assertFalse(report['resource_ownership_verified'])
        for events in ([binding], [cleanup], [binding, cleanup.replace('resource same', 'resource different')],
                       [binding, cleanup.replace('request 10,', 'request 11,')],
                       [binding, cleanup.replace('Weapon_Sword_Test', 'Weapon_Shield_Test')],
                       [binding, binding, cleanup], [binding, cleanup, cleanup]):
            self.assertFalse(diagnose.probe_summary(actor+events, require_resource=True)['acceptance_passed'])
        self.assertFalse(diagnose.probe_summary(object_events()+resource_events(), require_resource=True)['acceptance_passed'])

    def test_combined_requirements_cannot_be_split_between_probes(self):
        first = object_events(0, request=10)
        handoff = ('[host] coop native probe allocator: entry main+0x300, caller 0x1000000220, probe 0, '
                   'name Weapon_Sword_Test, cleanup scope same, actor argument same, host thread 7; observation only')
        second = object_events(1, request=11)
        report = diagnose.probe_summary(first+[handoff]+second+resource_events(11), require_allocator=True, require_resource=True)
        self.assertTrue(report['allocator_handoff_observed'])
        self.assertTrue(report['resource_lifetime_observed'])
        self.assertFalse(report['acceptance_passed'])

    def test_applied_inputs_and_native_movement(self):
        report = diagnose.local_control_summary([sample(1750, 1, 0), sample(3000, 1, 1), *control_inputs()])
        self.assertTrue(report['scripted_events_applied'])
        self.assertTrue(report['movement_observed'])
        self.assertEqual(report['max_displacement'], 1)
        self.assertEqual(report['max_control_displacement'], 1)
        self.assertFalse(report['camera_independence_verified'])
        self.assertFalse(report['native_companion_verified'])

    def test_generation_change_is_not_movement(self):
        lines = [sample(1750, 1, 0), sample(2250, 2, 100), *control_inputs()]
        report = diagnose.local_control_summary(lines)
        self.assertEqual(report['max_displacement'], 0)
        self.assertFalse(report['movement_observed'])
        report = diagnose.local_control_summary([*lines, sample(2500, 2, 100.2)])
        self.assertFalse(report['movement_observed'])
        self.assertEqual(report['max_displacement'], 0.2)

    def test_loading_settle_is_not_controlled_movement(self):
        report = diagnose.local_control_summary([sample(0, 1, 0), sample(250, 1, 2),
                                                sample(1750, 1, 2), sample(3000, 1, 2), *control_inputs()])
        self.assertEqual(report['max_displacement'], 2)
        self.assertEqual(report['max_control_displacement'], 0)
        self.assertFalse(report['movement_observed'])

    def test_motion_outside_input_window_is_not_controlled(self):
        report = diagnose.local_control_summary([sample(1750, 1, 0), sample(3000, 1, 0),
                                                sample(6000, 1, 2), *control_inputs()])
        self.assertFalse(report['movement_observed'])

    def test_vertical_settle_does_not_pass_walk_check(self):
        falling = sample(3000, 1, 0).replace('pos 0.000000 0.000000', 'pos 0.000000 2.000000')
        report = diagnose.local_control_summary([sample(1750, 1, 0), falling, *control_inputs()])
        self.assertEqual(report['max_displacement'], 2)
        self.assertFalse(report['movement_observed'])

    def test_late_input_does_not_pass_sequence(self):
        inputs = control_inputs()
        inputs[0] = inputs[0].replace('2000.0 ms', '2600.0 ms')
        self.assertFalse(diagnose.local_control_summary(inputs)['scripted_events_applied'])

    def test_one_button_event_cannot_satisfy_two_phases(self):
        report = diagnose.local_control_summary(control_inputs()[:-1])
        self.assertFalse(report['scripted_events_applied'])
        self.assertFalse(report['movement_observed'])

    def test_malformed_samples_are_ignored(self):
        lines = [sample(0, 1, 0).replace('0.000000 0.000000', 'nan 0.000000', 1),
                 sample(0, 1, 0).replace('pos 0.000000', 'pos 1..0'),
                 sample(1000, 1, 2)]
        report = diagnose.local_control_summary(lines)
        self.assertEqual(len(report['samples']), 1)
        self.assertFalse(report['movement_observed'])

    def test_reload_requires_cleanup_and_a_new_player_construction(self):
        first = '[host] coop adapter: generation 3, player observed, scene observation present;'
        second = first.replace('generation 3', 'generation 5')
        constructor = '[host] coop native constructor: synthetic invocation, observed player same; observation only'
        cleanup = ('[host] coop native actor teardown: entry main+0x300, caller 0x1000000220, '
                   'stage cleanup, observed player same, generation 3, reason 0;')
        lines = [first, constructor, cleanup, second, constructor]
        report = diagnose.reload_summary(lines)
        self.assertTrue(report['actor_recreation_observed'])
        self.assertEqual(report['cleanup_generations'], [3])
        self.assertEqual(report['matched_constructor_count'], 2)
        self.assertFalse(report['native_actor_removal_verified'])
        self.assertFalse(report['native_companion_verified'])
        for missing in (0, 1, 2, 3, 4):
            with self.subTest(missing=missing):
                self.assertFalse(diagnose.reload_summary(lines[:missing] + lines[missing+1:])['actor_recreation_observed'])
        self.assertFalse(diagnose.reload_summary([first, constructor, cleanup, first, constructor])['actor_recreation_observed'])
        self.assertFalse(diagnose.reload_summary([first, constructor, cleanup.replace('generation 3', 'generation 4'),
                                                 second, constructor])['actor_recreation_observed'])

    def test_returning_player_identity_is_not_actor_recreation(self):
        lines = ['[host] coop adapter: generation 3, player observed,',
                 '[host] coop native constructor: synthetic invocation, observed player same;',
                 '[host] coop adapter: generation 4, player absent,',
                 '[host] coop adapter: generation 5, player observed,',
                 '[host] coop native player continuity: generation 5, original generation 3, '
                 'actor metadata id same, constructor entries 1200, limit 16384; observation only']
        report = diagnose.reload_summary(lines)
        self.assertTrue(report['player_return_observed'])
        self.assertFalse(report['actor_recreation_observed'])
        self.assertEqual(report['identity_continuity'], [dict(generation=5, original_generation=3,
                                                            constructor_entries=1200, constructor_limit=16384)])


if __name__ == '__main__':
    unittest.main()
