"""Check diagnostic acceptance using synthetic logs, without game files or Windows processes."""
from pathlib import Path
import re
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
    def test_native_pose_script_separates_nearby_pose_acceptance_from_long_walk_reproduction(self):
        near=diagnose.diagnostic_script(60,'controls',True)
        far=diagnose.diagnostic_script(60,'controls',True,True)
        self.assertIn('@2000 LSTICK -32767 0 2000',near)
        self.assertIn('@10000 LSTICK -32767 0 300',near)
        self.assertIn('@23000 LSTICK -32767 0 300',near)
        self.assertIn('@10000 LSTICK -32767 0 2000',far)
        self.assertIn('@12500 Y 100',near)
        self.assertNotIn('@10000',diagnose.diagnostic_script(60,'controls'))
    def test_native_original_pose_requires_native_origin_both_actors_and_original_actions(self):
        native=self.reconnect_fixture()
        figures=[c['figure'] for c in diagnose.session_reconnect_summary(native,[0,0])['cycles']]
        poses=[]
        for i,figure in enumerate(figures):
            for k,s in enumerate(figure['samples']):
                poses.append(f'coop native figure pose: sample {s["sample_ns"]}, generation {s["generation"]}, actor id {s["actor_id"]}, '
                             f'changed {int(k>0)}, rotation 1, animation '+('Nml_Move_Run' if k%2 else 'Sword_Blunt_Attack_S1')+
                             '; captured body supplied to mapped skeleton')
        lines=native+poses+['figure: final body pose applied (89 palette entries, 191 bones); presentation only']
        peer='peer: native pose relay completed: published 40, bodies 40, changed 39\n'*2
        summary=diagnose.native_original_pose_summary(lines,peer,figures,[0,0])
        self.assertTrue(summary['acceptance_passed']); self.assertFalse(summary['climbing_physics_verified'])
        for changed in (lines[:-1],native+poses[:-31]+[lines[-1]],lines+[poses[0]],
                        [s.replace('Sword_Blunt_Attack_S1','Nml_Wait') for s in lines],
                        [s.replace('Nml_Move_Run','Nml_Wait') for s in lines],
                        [s.replace('rotation 1, animation','rotation 0, animation') for s in lines],
                        [s.replace('figure pose: sample','figure pose: bad') for s in lines]):
            self.assertFalse(diagnose.native_original_pose_summary(changed,peer,figures,[0,0])['acceptance_passed'])
        self.assertFalse(diagnose.native_original_pose_summary(lines,peer,figures,[0])['acceptance_passed'])
        self.assertFalse(diagnose.native_original_pose_summary(lines,peer.replace('changed 39','changed 0'),figures,[0,0])['acceptance_passed'])
        self.assertFalse(diagnose.native_original_pose_summary(lines,peer,[],[0,0])['acceptance_passed'])

    def reconnect_fixture(self):
        lines=[]
        for i,start in enumerate((6000000,26000000)):
            actor=17+i; probe=10+i; request=5+i; session=11+i
            base,spawn=self.npc_peer_fixture()
            base=[re.sub(r'world us (\d+)',lambda m:f'world us {start+int(m[1])}',s)
                    .replace('probe 10,',f'probe {probe},').replace('request 5,',f'request {request},')
                    .replace('session 11,',f'session {session},') for s in base]
            events=object_events(probe=probe,name='Npc_Road_001',request=request)
            lines.extend([f'coop native npc cycle begin: cycle {i+1}, world us {start}, prior actor id {17 if i else -1}, prior retired {int(i>0)};',
                'coop native spawn owned: pos 1 2 3, empty blackboard, actor dependencies absent;',
                f'coop native spawn request: request {request}, name Npc_Road_001, watcher absent;',
                'coop native spawn probe: queued yes, name Npc_Road_001,',
                f'coop native session creation: session {session}, player 22, local generation 3, remote generation 1, world us {start}, worker 1, queued 1; local actor update, owned stack arguments, original CPU restored',
                events[0],*base,
                f'coop native npc cycle binding: cycle {i+1}, generation 3, actor id {actor}, world us {start+1000000};'])
            for s in spawn['samples']:
                x,y,z=s['pos']
                lines.append(f'coop native spawn motion: probe {probe}, request {request}, world us {start+s["world_us"]}, pos {x:.6f} {y:.6f} {z:.6f},')
            for j in range(40):
                at=start+2000000+j*50000
                ns=(i+1)*1000000000+j
                lines.extend([f'coop native npc velocity consumer reapply: correction {j+1}, generation 3, world us {at}; same live pending request, original CPU restored',
                    f'coop native figure capture: sample {ns}, world us {at}, generation 3, actor id {actor}, pos 1 2 3, body pos 1 2.8 3;',
                    f'coop native figure submitted: sample {ns}, generation 3, actor id {actor}, pos 1 2 3;'])
            lines.extend([f'coop native model visibility: call 1, phase hide, generation 3, actor id {actor}, world us {start+2000000}, before 1, requested 0, after 0, owner matched 1;',
                f'coop native model visibility: call 2, phase restore, generation 3, actor id {actor}, world us {start+8000000}, before 0, requested 1, after 1, owner matched 1;',
                *events[1:],*resource_events(request=request,name='Npc_Road_001'),
                f'coop native probe allocator: entry main+0x100, caller 0x1000000020, probe {probe}, name Npc_Road_001, cleanup scope same, actor argument same, host thread 7;',
                f'coop native npc retirement request: generation 3, actor id {actor}, world us {start+12000000}, result 1, worker 0, rest samples 31, rest us 1000000;',
                f'coop native session retired: cycle {i+1}, session {session}, generation 3, actor id {actor}, world us {start+13000000}; correlated cleanup and allocator handoff'])
        return lines

    def test_reconnect_requires_two_complete_distinct_session_lifetimes_and_one_player(self):
        lines=self.reconnect_fixture()
        summary=diagnose.session_reconnect_summary(lines,[0,0])
        self.assertTrue(summary['acceptance_passed'],summary)
        self.assertTrue(summary['bounded_reconnect_verified']); self.assertTrue(summary['same_player'])
        self.assertFalse(summary['native_request_storage_reused']); self.assertFalse(summary['human_peer_verified'])
        for results in ([],[0],[0,1],[0,0,0]):
            self.assertFalse(diagnose.session_reconnect_summary(lines,results)['acceptance_passed'])
        changes=(('missing_cleanup',lambda s:'coop native session retired: cycle 1,' not in s),
                 ('missing_second_figure',lambda s:not ('figure submitted:' in s and 'actor id 18,' in s)),
                 ('missing_resource',lambda s:not ('resource cleanup:' in s and 'request 6,' in s)),
                 ('missing_retirement',lambda s:not ('retirement request:' in s and 'actor id 18,' in s)))
        for name,keep in changes:
            with self.subTest(name=name):
                self.assertFalse(diagnose.session_reconnect_summary(list(filter(keep,lines)),[0,0])['acceptance_passed'])
        for old,new in (('session 12,','session 11,'),('session 12, player 22,','session 12, player 23,'),
                        ('prior actor id 17,','prior actor id 18,'),('prior retired 1;','prior retired 0;'),
                        ('world us 19000000;','world us 27000000;'),
                        ('actor id 18, world us 38000000, result 1','actor id 18, world us 38000000, result 0')):
            with self.subTest(change=(old,new)):
                self.assertFalse(diagnose.session_reconnect_summary([s.replace(old,new) for s in lines],[0,0])['acceptance_passed'])
        self.assertFalse(diagnose.session_reconnect_summary(lines+[lines[-1]],[0,0])['acceptance_passed'])
        self.assertFalse(diagnose.session_reconnect_summary(lines+['coop native session retired: malformed;'],[0,0])['acceptance_passed'])

    def test_session_creation_requires_owned_spawn_matching_peer_and_retirement_without_drop(self):
        creation=('coop native session creation: session 11, player 22, local generation 3, remote generation 1, '
                  'world us 6000000, worker 1, queued 1; local actor update, owned stack arguments, original CPU restored')
        binding='coop native npc peer binding: session 11, player 22, remote generation 1, local generation 3;'
        spawn=dict(acceptance_passed=True,owned_argument_observed=True)
        retired=dict(acceptance_passed=True,requests=[dict(generation=3,world_us=19000000)])
        summary=diagnose.session_creation_summary([creation,binding],spawn,retired)
        self.assertTrue(summary['acceptance_passed']); self.assertFalse(summary['reconnect_verified'])
        for lines in ([],[creation],[binding],[binding,creation],[creation,creation,binding],
                      [creation,binding,creation.replace('worker 1','worker malformed')],
                      [creation,binding.replace('player 22','player 23')],
                      [creation,binding.replace('generation 1','generation 2')],
                      [creation.replace('queued 1','queued 0'),binding],
                      [creation.replace('6000000','5000000'),binding],
                      [creation,binding,'coop native actor request: caller 0x70020a57d8,']):
            self.assertFalse(diagnose.session_creation_summary(lines,spawn,retired)['acceptance_passed'])
        for bad in (dict(acceptance_passed=False),dict(acceptance_passed=True,requests=[]),
                    dict(acceptance_passed=True,requests=[dict(generation=4,world_us=19000000)]),
                    dict(acceptance_passed=True,requests=[dict(generation=3,world_us=5000000)])):
            self.assertFalse(diagnose.session_creation_summary([creation,binding],spawn,bad)['acceptance_passed'])
        self.assertFalse(diagnose.session_creation_summary([creation,binding],dict(acceptance_passed=True),retired)['acceptance_passed'])

    def test_npc_retirement_requires_correlated_cleanup_resource_and_allocator(self):
        events=object_events(probe=4,name='Npc_Road_001',request=10)
        resources=resource_events(request=10,name='Npc_Road_001')
        allocator='coop native probe allocator: entry main+0x100, caller 0x1000000020, probe 4, name Npc_Road_001, cleanup scope same, actor argument same, host thread 7;'
        request='coop native npc retirement request: generation 3, actor id 17, world us 24000000, result 1, worker 0, rest samples 31, rest us 1000000;'
        lines=[events[0],resources[0],*events[1:],resources[1],allocator,request]
        spawn=dict(acceptance_passed=True,initialized=[dict(probe=4,request=10)])
        figure=dict(acceptance_passed=True,samples=[dict(generation=3,actor_id=17,world_us=22000000)])
        report=diagnose.npc_retirement_summary(lines,spawn,figure)
        self.assertTrue(report['acceptance_passed']); self.assertTrue(report['native_retirement_verified'])
        self.assertFalse(report['reconnect_verified']); self.assertFalse(report['native_request_storage_reused'])
        for index in range(len(lines)):
            self.assertFalse(diagnose.npc_retirement_summary(lines[:index]+lines[index+1:],spawn,figure)['acceptance_passed'])
        for changed in (request.replace('result 1','result 0'),request.replace('actor id 17','actor id 18'),
                        request.replace('generation 3','generation 4'),request.replace('24000000','21000000'),
                        request.replace('samples 31','samples 1'),request.replace('rest us 1000000','rest us 1000')):
            self.assertFalse(diagnose.npc_retirement_summary(lines[:-1]+[changed],spawn,figure)['acceptance_passed'])
        self.assertFalse(diagnose.npc_retirement_summary(lines+[request],spawn,figure)['acceptance_passed'])
        self.assertFalse(diagnose.npc_retirement_summary(lines,dict(acceptance_passed=True,initialized=[dict(probe=5,request=10)]),figure)['acceptance_passed'])

    def test_native_visibility_requires_owned_hide_and_restore_pair(self):
        figure=dict(acceptance_passed=True,samples=[dict(generation=3,actor_id=17,world_us=15000000+n*100000) for n in range(32)])
        hide='coop native model visibility: call 1, phase hide, generation 3, actor id 17, world us 15000000, before 1, requested 0, after 0, owner matched 1;'
        restore='coop native model visibility: call 2, phase restore, generation 3, actor id 17, world us 22000000, before 0, requested 1, after 1, owner matched 1;'
        report=diagnose.native_visibility_summary([hide,restore],figure)
        self.assertTrue(report['acceptance_passed']); self.assertTrue(report['native_flag_control_verified'])
        self.assertFalse(report['visual_replacement_verified']); self.assertFalse(report['native_retirement_verified'])
        self.assertEqual(report['hidden_figure_samples'],32)
        for lines in ([hide], [restore,hide], [hide,restore,restore],
                      [hide,restore.replace('after 1','after 0')],
                      [hide,restore.replace('actor id 17','actor id 18')],
                      [hide,restore.replace('owner matched 1','owner matched 0')],
                      [hide,restore,'coop native model visibility: aborted; changed owner']):
            self.assertFalse(diagnose.native_visibility_summary(lines,figure)['acceptance_passed'])
        self.assertFalse(diagnose.native_visibility_summary([hide,restore],dict(acceptance_passed=False,samples=figure['samples']))['acceptance_passed'])
        self.assertFalse(diagnose.native_visibility_summary([hide,restore.replace('22000000','15100000')],figure)['acceptance_passed'])

    def test_native_figure_requires_exact_copied_actor_origin(self):
        lines=[]
        for n in range(12):
            lines.extend([f'coop native figure capture: sample {1000000000+n}, world us {1000000+n}, generation 3, actor id 17, pos 1 2 3, body pos 1 2.8 3;',
                          f'coop native figure submitted: sample {1000000000+n}, generation 3, actor id 17, pos 1 2 3;'])
        report=diagnose.native_figure_summary(lines)
        self.assertTrue(report['acceptance_passed']); self.assertEqual(report['maximum_origin_error'],0)
        self.assertFalse(report['ground_contact_verified']); self.assertFalse(report['lifecycle_verified'])
        self.assertFalse(report['native_appearance_suppressed'])
        self.assertTrue(diagnose.native_figure_summary(lines[1:2]+lines[:1]+lines[2:])['acceptance_passed'])
        for changed in (lines[:18], lines[::2], [s.replace('submitted: sample 1000000000','submitted: sample 999') for s in lines],
                        [s.replace('pos 1 2 3;','pos 1 2.8 3;') if 'submitted' in s else s for s in lines],
                        [s.replace('actor id 17','actor id 18') if 'submitted' in s else s for s in lines]):
            self.assertFalse(diagnose.native_figure_summary(changed)['acceptance_passed'])

    def test_native_model_matrices_do_not_prove_reference_lifetime_or_ownership(self):
        lines=['coop gear native model: slot 0, actor 0x10000, model 0x20000, depth 1, embedded delta 288;',
               'coop gear references: captured 4;',
               'coop gear reference candidate: generation 3, slot 0, actor 0x10000, metadata id 17, caller 0x30000;',
               'coop gear reference pose: world us 1000000, generation 3, slot 0, candidate 0, first 1.0 2.0 3.0; axes 1 0 0 0 1 0 0 0 1; reference live 0; native model render origin']
        summary=diagnose.gear_graph_summary(lines)
        self.assertEqual(summary['reference_events'],4)
        self.assertEqual(summary['native_models'][0]['embedded_delta'],288)
        self.assertEqual(summary['reference_candidates'][0]['metadata_id'],17)
        self.assertEqual(summary['reference_poses'][0]['render_origin_pos'],[1,2,3])
        self.assertFalse(summary['reference_poses'][0]['reference_live'])
        self.assertFalse(summary['exclusive_ownership_verified'])
        self.assertFalse(summary['native_attachment_binding_verified'])

    def test_malformed_gear_matrices_are_ignored(self):
        graph='coop gear graph pose: world us 1000000, generation 3, candidate 0, slot 0, first 1..2 2 3;'
        reference='coop gear reference pose: world us 1000000, generation 3, slot 0, candidate 0, first 1..2 2 3; axes 1 0 0 0 1 0 0 0 1;'
        summary=diagnose.gear_graph_summary([graph,reference,reference.replace('1..2','1').replace('axes 1 0 0','axes 1 0')])
        self.assertEqual(summary['poses'],[])
        self.assertEqual(summary['reference_poses'],[])

    def test_gear_graph_search_is_not_attachment_ownership(self):
        lines=['coop gear graph: armed, node limit 2048, depth limit 6, per tick 16;',
               'coop gear graph done: generation 3, nodes 2048, candidates 0, capped 1; reachability only']
        summary=diagnose.gear_graph_summary(lines)
        self.assertTrue(summary['search_completed']); self.assertEqual(summary['candidates'],[])
        self.assertFalse(summary['native_attachment_binding_verified'])
        self.assertFalse(summary['exclusive_ownership_verified'])
        self.assertFalse(diagnose.gear_graph_summary(lines[1:])['search_completed'])
        self.assertFalse(diagnose.gear_graph_summary([lines[0],lines[1].replace('2048','9999')])['search_completed'])

    def test_gear_probe_requires_valid_slot_and_exact_model_alias(self):
        manifest=dict(format='LNKA',version=2,actors={'Weapon_Sword_101':'Alias.Blade','Weapon_Shield_005':'Alias.Shield'})
        text=diagnose.gear_probe_mapping(manifest)
        self.assertIn('0\tWeapon_Sword_101\tAlias.Blade\n',text)
        self.assertIn('1\tWeapon_Shield_005\tAlias.Shield\n',text)
        for actors in ({'Weapon_Sword_101':'../bad'}, {'../actor':'Alias.Blade'},
                       {'Weapon_Sword_101':'Alias.Blade','Weapon_Sword_102':'Alias.Blade'}, {}):
            with self.assertRaises(ValueError): diagnose.gear_probe_mapping(dict(format='LNKA',version=2,actors=actors))

    def test_equipment_echo_requires_real_received_items(self):
        text='peer: equipment echo completed: samples 30, equipped 25, changes 1'
        result=diagnose.equipment_echo_summary(text,0)
        self.assertTrue(result['acceptance_passed'])
        self.assertFalse(result['placement_verified'])
        self.assertFalse(result['inventory_replication_verified'])
        for log,code in (('',0),(text,1),(text.replace('equipped 25','equipped 0'),0),
                         (text.replace('equipped 25','equipped 35'),0)):
            self.assertFalse(diagnose.equipment_echo_summary(log,code)['acceptance_passed'])

    def test_pose_echo_waits_for_world_and_requires_live_applied_bones(self):
        self.assertFalse(diagnose.peer_start_ready(True,'boot: first NVN call'))
        self.assertFalse(diagnose.peer_start_ready(True,'coop native npc peer velocity: step 1,'))
        self.assertTrue(diagnose.peer_start_ready(True,'frame step: world clock starts at present 12'))
        self.assertTrue(diagnose.peer_start_ready(False,'coop native npc peer velocity: step 1,'))
        peer='peer: pose echo completed: samples 50, bodies 45, changed 44'
        lines=['figure: final body pose applied (89 palette entries, 100 bones); presentation only']
        self.assertTrue(diagnose.pose_echo_summary(peer,lines,0)['acceptance_passed'])
        for text, log, code in ((peer,[],0), (peer,lines,1), ('',lines,0),
                                (peer.replace('changed 44','changed 0'),lines,0),
                                (peer.replace('bodies 45','bodies 55'),lines,0)):
            self.assertFalse(diagnose.pose_echo_summary(text,log,code)['acceptance_passed'])

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

    def npc_cycles_fixture(self):
        result=[]
        for cycle in (1,2):
            shift=(cycle-1)*10000000; probe=9+cycle; request=4+cycle; actor_id=16+cycle
            result.append(f'coop native npc cycle begin: cycle {cycle}, world us {1000000+shift}, prior actor id {-1 if cycle==1 else 17}, prior retired {cycle-1};')
            result.extend(['coop native spawn owned: pos 0 3 0, empty blackboard, actor dependencies absent;',
                'coop native spawn probe: queued yes, name Npc_Road_001, original CPU restored;',
                f'coop native spawn request: request {request}, name Npc_Road_001, watcher absent;'])
            events=object_events(probe,'Npc_Road_001',request); resources=resource_events(request,'Npc_Road_001')
            result += [events[0],resources[0]]
            result.append(f'coop native npc cycle binding: cycle {cycle}, generation 3, actor id {actor_id}, world us {2000000+shift};')
            motion,spawn=self.npc_motion_fixture()
            motion[0]=motion[0].replace('world us 0,','world us 1500000,')
            for line in motion:
                line=line.replace('probe 10,',f'probe {probe},').replace('request 5,',f'request {request},')
                line=re.sub(r'world us (\d+)',lambda m:'world us '+str(int(m[1])+shift),line)
                result.append(line)
            for point in spawn['samples']:
                x,y,z=point['pos']
                result.append(f'coop native spawn motion: probe {probe}, request {request}, world us {point["world_us"]+shift}, pos {x:.6f} {y:.6f} {z:.6f}, entry main+0x2e27b0;')
            for index,at in enumerate((2000000,2500000,3000000,3500000),1):
                result.append(f'coop native npc velocity consumer reapply: correction {index}, generation 3, world us {at+shift}; same live pending request, original CPU restored')
            result.append(f'coop native npc retirement request: generation 3, actor id {actor_id}, world us {6000000+shift}, result 1, worker 0, rest samples 31, rest us 1000000;')
            result += events[1:]+[resources[1],f'coop native probe allocator: entry main+0x100, caller 0x1000000020, probe {probe}, name Npc_Road_001, cleanup scope same, actor argument same, host thread 7;']
        return result

    def test_two_cycles_require_separate_identities_and_complete_native_evidence(self):
        lines=self.npc_cycles_fixture()
        report=diagnose.npc_cycles_summary(lines)
        self.assertTrue(report['acceptance_passed'] and report['repeated_in_process_verified'])
        self.assertEqual(len(report['cycles']),2)
        self.assertFalse(report['request_storage_reused'] or report['reconnect_verified'] or report['human_peer_verified'])
        for token in ('cycle begin: cycle 2,','cycle binding: cycle 2,','request 6, name Npc_Road_001, watcher',
                      'probe 11, name Npc_Road_001, stage request', 'probe 11, name Npc_Road_001, stage queue',
                      'probe 11, name Npc_Road_001, stage cleanup', 'resource cleanup:', 'probe allocator:',
                      'velocity consumer reapply:','npc physics: probe 11,'):
            with self.subTest(missing=token):
                self.assertFalse(diagnose.npc_cycles_summary([line for line in lines if token not in line])['acceptance_passed'])
        for before,after in (('actor id 18,','actor id 17,'),('prior retired 1;','prior retired 0;'),
                             ('prior actor id 17,','prior actor id 19,'),('rest us 1000000;','rest us 1000;'),
                             ('rest samples 31,','rest samples 1,'),('result 1, worker','result 0, worker'),
                             ('cycle 2, generation 3,','cycle 2, generation 4,'),('request 6,','request 5,')):
            with self.subTest(changed=before):
                self.assertFalse(diagnose.npc_cycles_summary([line.replace(before,after) for line in lines])['acceptance_passed'])
        self.assertFalse(diagnose.npc_cycles_summary(lines+[lines[0]])['acceptance_passed'])
        self.assertFalse(diagnose.npc_cycles_summary(lines[::-1])['acceptance_passed'])
        extra=next(line for line in lines if 'npc retirement request:' in line)
        self.assertFalse(diagnose.npc_cycles_summary(lines+[extra.replace('world us 6000000','world us 0')])['acceptance_passed'])

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
