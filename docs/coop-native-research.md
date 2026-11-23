# Co-op native research notes

## Session-driven creation at the local actor update (November 23, 2026)

Mode 11 (`--native-npc-session`, `isolated-npc-session-create-v1`) removes inventory-drop scheduling from
one isolated native lifecycle. `coop_native_probe.c` `session_offer_locked` retains only copied negotiated
session/player/local-world/remote-world identities and fresh sample times. Replayed sender samples cannot
renew the pending creation lease. Cancellation before dispatch clears the candidate; after a request, ownership
changes revoke movement rather than rebind the live actor or reuse creation storage.

The locally inspected `main+0x2f1554` installs its current actor into the worker slot before invoking virtual
`+0x180`, return site `main+0x2f1608`. The local Player and tested NPC share the observed base actor update
`main+0x2e27b0` through vtable `main+0x3633078`. `coop_actor_worker_context`, shared with the earlier retirement
experiment, verifies the installed SDK TLS getter, task kind and current actor/worker equality. The creation
experiment additionally hashes the complete dispatch through the indirect call, the TLS getter, update and
request prologues. `coop_adapter_local_actor` matches the current observed Player, resident metadata backlink/ID,
active generation and finite position; matching the shared vtable alone is insufficient.

`rt_call` still accepts at most eight register arguments and does not marshal stack arguments. The request ABI
has three additional optional arguments. `session_create_locked` reserves 32 aligned bytes below current SP,
requiring a mapped writable Stack region with 64 KiB committed call headroom. AAPCS64 has no red zone. It writes
the three zero optional arguments there, invokes the already inspected request with separately retained
CreateArg/BlackboardInit storage and restores the outgoing area's bytes, complete Cpu and host FP environment.
It does not replace the original caller's existing stack arguments, publish native pointers to the network,
copy Player singleton references or request a watcher. This is a bounded experiment at one native phase,
not a general callable creation API or arbitrary-thread scheduling contract.

The first 30-world-second copied-save run, `run-a507426c10`, passed all requested gates. The request at world
6.013454 s used worker 0; session and peer generation matched the later velocity binding. Actor 885 in generation
3 moved under the game-free ENet peer, published the native-origin Link figure and suppressed/restored its NPC
model for 6.417340 s across 177 figure samples. Retirement was accepted at world 19.504015 s on worker 2 after
30 rest samples over 1.002777 s, with the same actor's native request/queue, resource cleanup and allocator handoff.
Game/peer exits were zero and source saves unchanged. No inventory drop occurred. The inspected image shows
black-haired Link at the right frame edge; a horse occludes the local player and grass obscures the feet.

A second 30-world-second run, `run-a95babe3c7`, passed with the built-in local control sequence. Local horizontal
displacement during its walk was 9.937337 m; walking, camera and attack-button inputs were applied. This does
not establish that every attack input produced a weapon strike or a shared damage outcome. Actor 888/gen3
was requested at world 6.002549 s on worker 1. All 122 native-origin figure submissions matched exactly;
hide/restore lasted 5.956652 s across 121 figure samples. Native retirement at world 19.873683 s on worker 2
followed 23 rest samples over 1.017672 s and correlated resource/allocator cleanup. Both exits were zero and
source saves unchanged. Frame `f01549.png` shows the local Link and black-haired companion together. Grass
still hides their feet; exact capsule/model fit and terrain acceptance remain open. These are separate fresh
processes, not two joins in one running game. No heavy-scene performance or complete camera-independence
acceptance is claimed.

Synthetic checks cover canceled/stale/replayed candidates, mismatched local metadata/world/worker, independent
dispatch/TLS hash refusals, mapped-stack refusal, single-shot creation, ownership revocation, early leave before
figure publication and full CPU/FP/outgoing-area restoration. No native code is called from the observer, render
or network worker. Human control, indefinite lifetime, a second join/reconnect, scene transitions, terrain/model
fit and combat remain unaccepted. Do not combine mode 10's two synthetic lifetimes with this one peer lifetime
to claim two session-driven creations.

## Two retained NPC lifecycles (November 23, 2026)

Mode 10 (`--native-npc-cycles`, `isolated-npc-two-cycles-v1`) permits two separately retained creation
argument/empty-blackboard slots. A second authentic inventory-drop trigger is refused until the first actor
has an accepted native retirement and copied request/queue/cleanup/resource/allocator-handoff evidence.
Neither slot is reused or released. The native allocator observation is still its entry/handoff, not proof
that the allocator call returned. This bounded experiment does not establish a reusable request pool.

`coop_native_probe.c` `cycle_claim` holds the existing try-lock while checking that evidence and resetting
the new cycle's motion state. The same verified inventory producer/ABI/code/stack guards remain in force.
Mode 10 alone permits other bounded ASCII `Weapon_` names at that producer: the first drop changes the
selected inventory slot. The injected name remains exactly `Npc_Road_001`. CPU/FP state and the original
producer's watcher are preserved. Each cycle uses the bounded mode 5 pulse, then the previously verified
native removal path after measured rest. This mode has no figure or peer.

`coop_adapter.c` retains initial/later physics snapshots and motion sample budgets per initialized probe.
The active index is atomic; published slots are never reset. Consumer/backend and lock scopes include the
probe identity so a new creation in the same world cannot inherit a prior TLS scope, even when addresses
are reused. The body getter checks the selected snapshot's probe. The retirement predicate reads copied
host evidence only and rejects incompatible epochs, IDs, partial stages and mismatched resource cleanup.
Synthetic tests cover address reuse with a new metadata ID, unpublished snapshots, stale TLS scopes and
absence of guest reads when consulting retired identities. No native pointer enters a wire message/render
snapshot, and no generated C, lifter or CPU header changed.

The final 45-world-second copied-save diagnostic, `run-16b6eb3cd9`, passed both cycles:

| Cycle | Actor ID / generation | Probe / request | Forward / reverse | Producer / consumer calls | Accepted retirement / measured rest |
| --- | --- | --- | --- | --- | --- |
| 1 | 919 / 3 | 10 / 15 | 1.863586 / 1.930298 m | 59 / 59 | world 19.183969 s; 32 samples over 1.033162 s |
| 2 | 962 / 3 | 21 / 29 | 1.932373 / 1.997864 m | 61 / 61 | world 37.183806 s; 32 samples over 1.020461 s |

The second request began at world 28.050557 s with the first retired identity matched. Each actor's native
request/queue, resource cleanup and allocator handoff correlated separately. Game exit was zero and source
save hashes were unchanged. Inspected images show the first NPC and its absence afterward, then the second
NPC and its later absence; camera framing clips the second actor in some frames. Grass obscures the feet.

The same executable also passed the mode 9 regression `run-90cad6854a`: 32 world seconds, leased ENet
forward/reverse/diagonal motion, both expiry rests/recovery, 160 exact native-origin figure submissions,
native hide/restore for 6.258225 seconds across 159 figure samples, and correlated native retirement.
Game/peer exits were zero and source saves were unchanged. Full-size images show the black-haired Link,
the restored NPC and the later empty position. This remains one peer-driven lifecycle; mode 10's two
synthetic cycles do not automatically establish two peer-driven joins or reconnection.

Earlier runs `run-d30d795716` and `run-1797c033d8` passed before the final observer publication guard.
An authored concurrent-publication fixture exposed a new-index/old-address window in the receiver sampler;
it failed against the preceding guard and passes when the selected probe's ready state and actor address
are checked before any guest read. The final two runs above repeat the relevant gameplay gates after that
correction. This does not constitute a broad multithreaded stress or performance acceptance.

This passes two bounded native lifecycles in one world. It does not pass peer-driven recreation, connection
events as creation triggers, scene load/unload, indefinite storage reuse, human control or a shared campaign.
The authentic inventory drop remains the creation scheduling boundary. Ordinary native capabilities stay
disabled. Before a playable session, bind fresh peer/actor identities and establish creation/retirement at a
verified session-driven native phase while retaining the original camera/input and terrain checks.

## Owned NPC retirement (November 18, 2026)

`runtime/coop_retirement.c` adds a separately armed, one-shot mode 9 experiment. The original caller at
`main+0xe2c924` passes its owner actor and reason zero to `main+0x63baa8`. Inspection of the complete
0x244-byte callee found actor-state/pending checks, native locking and task-context handling, a call to the
queue at `main+0x3d45e0`, then a native virtual notification. It is an asynchronous removal request, not a
destructor or permission for the host to free memory. Its complete code and the queue/update prologues are
hashed before the experiment calls it; no generated body is copied into public source.

The original update dispatcher at `main+0x2f1554` writes its current actor into the selected worker slot
before the virtual update, returning to `main+0x2f1608`. The experiment checks that return, GameActor's
exact vtable/callbacks, SDK `GetTlsValue` import binding and getter code, its inspected TLS slot, native task
type/kind, worker index and current-actor slot. These are guest scheduler identities, not a host thread ID.
An incompatible context issues no call. Ownership/body/metadata/epoch guards are checked again before use.

Mode 9 retains the earlier movement/visibility limits. Once movement finishes and native visibility is
restored, actor/body origins and cached velocity must establish one continuous world second of rest.
At least twelve distinct samples, position drift at most one centimetre, velocity at most 0.05 m/s and
gaps at most 100 ms are required. The first live experiment, `run-ae4482476d`, never called removal: it
incorrectly required a fresh final-stop consumer acknowledgement even after the body had become idle.
Measured rest replaces that dependency; the absence of a consumer event alone is not rest evidence.

An issued request is never retried, even when rejected. Full CPU/host FP state is restored and no guest
memory is read after the call. Figure binding and pending velocity-consumer work are closed. Existing
native observers independently correlate the same initialization with its removal request, pending queue,
resource cleanup and allocator handoff; a request return alone cannot pass the new report gate.

`run-a820c571be` accepted one request at world 25.205635 s, with 30 rest samples spanning 1.017812 s.
The same NPC (actor ID 916, generation 3, probe 8/request 13) reached native request/queue, resource cleanup
and allocator handoff. Full-size images show Link, the restored NPC, then neither remote representation.
Game/peer exits were zero and source saves were unchanged. This run's overall diagnostic failed because
an extra receive-lease expiry split the diagonal movement segment; native retirement itself passed.
That failure is retained and the receive-time lease and movement acceptance were not weakened.

An unchanged-build repeat, `run-29935d2488`, passed the full 32-world-second diagnostic. It retained
227 producer requests, 120 native consumer reapplications, forward/reverse/diagonal displacement, both
scheduled lease-expiry rests and recovery. All 174 captured/submitted figure origins matched exactly.
The native hide/restore pair lasted 5.933282 s across 173 figure samples. One retirement at world
25.151521 s followed 31 rest samples spanning 1.031515 s. Its actor ID 917/generation 3, probe 10/request 15
matched the native request/queue/resource/allocator sequence. Game and peer exited zero; source saves
were unchanged. Inspected frames show the black-haired Link, restored NPC and later empty companion
position. Tall grass still hides the feet, so terrain/feet acceptance remains open.

One retirement does not authorize reuse of process-lifetime creation argument/blackboard storage. Rejection,
cancellation, repeated creation/removal in one world, disconnect/reconnect and load/unload remain separate
requirements. Ordinary native capabilities stay disabled; no human-peer or full Player-controller acceptance.

## Owned NPC model visibility (November 17, 2026)

The original `OneShotSetOnlyModelVisible` action at `main+0x2588c64` obtains its actor through
`main+0x9a89c4`, calls the getter at `main+0x1b9ce0`, then passes the requested boolean to
`main+0x1b87b50`. The getter returns `[actor+0x228]+0x280`. Other original call sites also derive this
receiver from the actor, and controller methods follow +0x18 back to its owner. The setter changes its +0x9c
visibility byte and marks a pending model-controller update; it does not touch the rigid body. These are
locally inspected native paths, not imported offsets from another game version or guessed signatures.

The read-only mode 7 audit found that controller on the owned NPC, with matching owner, initially visible
and vtable `main+0x3673b58`. The adapter now guards that exact type and checks the owner, component slot,
actor/metadata ID, body and local epoch again before returning it to a native hook. Ordinary observer/render
snapshots still contain no such pointer. Getter and full setter hashes are checked independently before use.

Separate mode 8 uses a distinct timed-profile marker. One copied-publication acknowledgement feeds a bounded
slot under the existing native-probe try-lock. The owned actor-update entry consumes it; neither the renderer
nor the network calls the model API. A fresh matching publication may request one hide through the original
setter. Expiry, peer revocation or the bounded experiment's end requests restoration. CPU/FP state is restored
after both calls. At most two calls are allowed, and changed controller identity never triggers a stale restore.
An initially hidden controller is not taken over; a competing changed visible value ends the experiment.

In the controlled copied-save run `run-bca5cca87a`, hide and restore values both matched on the same owned
controller/actor. The hide lasted 6.499937 world seconds covering 195 copied figure samples; 196 figure
submissions matched native positions exactly. Forward/reverse/diagonal movement, expiry rests/recovery and
consumer correlation passed, all processes exited zero and source saves were unchanged. Full-size images
show Link without the NPC mesh while hidden and the NPC restored after peer exit. This proves visual
suppression/restoration in that one scenario while native body movement continued. Grass hides the feet.

This is not native retirement, repeatable creation, a general scheduling/visibility authority contract or
human control. A same-value competing request cannot be detected from the visible byte. General native
capabilities remain disabled. Verify lifecycle and unobstructed feet/terrain before calling this a playable
companion, and preserve the visibility restoration fallback while investigating native retirement.

An additional inspected original caller at `main+0xe2c924` obtains its owner actor and calls the removal
request at `main+0x63baa8` with a zero reason after a model-hide branch. This is a research starting point
for retirement, not authorization to call it externally. Inspect the full callee, task context, asynchronous
cleanup and request-storage lifetime before adding any removal experiment.

## Native actor origin to Link figure (November 17, 2026)

Mode 7 is armed only by `isolated-npc-body-figure-v1` in a timed copied profile. It reuses mode 6's authentic
NPC creation, verified velocity request/consumer path, receive-time lease and call/duration limits. The first
run created the NPC but made no velocity calls because the public update wrapper omitted the new mode. That
run failed; the wrapper now uses the common peer-mode predicate, and a regression test executes mode 7 calls.

`coop_adapter.c` `npc_figure_observe` copies actor +0x2b4, the identified body's +0xa4/+0xb4/+0xc4 translation
and +0xf8 velocity. Existing probe metadata, retirement, component/controller/body links and world-generation
checks run before and after the reads. These read-only observations do not establish a general native locking
contract. `coop.c` `coop_guest_observe` correlates the copy with the bound peer/session and generations;
`native_figure_ready` rejects missing, future or older-than-250-ms copies and title/loading peer samples.
Rendering receives values only. The actor origin is used directly, without assuming a collider-centre offset.

The corrected 28-world-second controlled run passed native forward/reverse/diagonal movement, two lease-expiry
rests and recovery, normal exits, source-save preservation and 194 exact captured/submitted origin matches.
Its forward segment rose approximately 0.427 m and reverse descended approximately 0.437 m. This is native
movement over the tested slope, not a host-computed terrain correction. During these samples actor and body
translation agreed, but that does not prove they always share an origin or that Link's feet fit the NPC collider.

The NPC's original mesh/behavior remains. Link drawing can overlap it; local camera movement put the companion
outside the view for much of the controlled run. No appearance suppression, terrain-wide grounding, native
retirement, reusable creation/reconnect or independently controlled human Link is accepted. Ordinary capabilities
remain presence-only. A verified model/visibility owner relation and native lifecycle are the next requirements.

A second 28-world-second run kept the camera stationary after the normal drop and passed with 189 exact
origin matches, native movement/rest/recovery and unchanged source saves. Full-size images show Link sharing
the NPC origin and overlapping its mesh while connected; after the peer exits, Link presentation disappears
while the NPC remains. Grass hides the feet, so visual terrain-contact acceptance is still open. This is evidence
for native-origin association and presentation cancellation only, not native removal or appearance replacement.

## Original equipment actor/model observations (November 17, 2026)

`runtime/main.c` `fnprof_hit` already observes the 1.4.3 actor-reference setter at `main+0x14f334`.
`runtime/coop_adapter.c` `coop_adapter_actor_bind` now forwards a strictly opt-in, bounded observation to
`coop_gear_probe_reference`. The probe validates actor/metadata backlinks and IDs, exact prepared actor names,
and deduplicates repeated setter events. It invokes no guest function and writes no guest memory. Native hook
threads publish bounded identity records; ModelUnit reads occur later in the guest observer.

The first Player-root graph search exhausted 2,048 nodes without finding the equipment. A second search with
per-component budgets examined 552 nodes and still found none within those limits. These are capped negative
results, not proof that no path exists. Original setter observations initially filled the record budget with
repeated identities; deduplication reduced the run to four distinct matching native actors.

The original weapon, shield and bow actors then supplied three named model candidates and 81 copied first
palette matrices in a 15-world-second copied-save run. Native model discovery starts from each identified
actor's ModelUnit and checks bounded descendants/embedded model-name fields before reading the palette.
The observed model subobjects were embedded at +0xc0 for bow/shield and +0x120 for the weapon relative to their
discovered descendant bases. Do not hardcode these deltas as a general accessor. Names, metadata IDs, model
paths and world/player/equipment identity remain required guards. Matrices are in render-origin coordinates,
not ready-to-apply actor space, and additional bow palette entries were not captured.

Exclusive equipment ownership remains unverified. In the observed caller, `main+0x6769c4`, the containing
routine beginning at `main+0x676910` creates a temporary stack reference before the setter call. The reference
was no longer live during the sampled model poses; it cannot serve as a persistent owner/binding handle.
Current actor identity, nearby position and model-name agreement provide research candidates only. A scan
through readable words can include adjacent objects; object bounds and accessors still need verification.
The report leaves native attachment binding and exclusive ownership false. No candidate enters network IDs,
rendering or an actor-mutation command.

## Visual size and ground-contact audit

The visible Link figure still owns no collider and is separate from the native NPC experiment. In the default
echo diagnostic, adding three metres to X while retaining the source Y can put the figure inside a slope or
above it. The synthetic bot also lacks terrain contact. Actual two-PC presence uses the other original Link's
sampled position, but local collision/body binding remains an independent unmet requirement.

A local audit of the prepared geometry using `link_figure_pose` measured `Nml_Wait` frame zero from
Y=0.000307 to 1.763705 metres (height 1.763398). The tested run/attack first-frame heights were 1.689609 and
1.554329 metres, respectively: pose extents vary with posture. No uniform shrink factor was found in the
figure's CPU/world transformation. These measurements describe the prepared model, not the physical collider
or a confirmed runtime match against the local outfit.

`--pose-echo-offset 0` permits same-origin calibration without inventing a ground height. A 12-world-second
idle echo passed with 291 body poses and unchanged source saves, while ground contact stayed false. A horse
occluded much of that comparison, so exact visual size equivalence remains unaccepted. Native body binding,
feet alignment and terrain tests now precede additional equipment appearance work. No arbitrary scale or Y
correction was introduced and no collision fix is claimed.

## Equipped identity observation (November 17, 2026)

The pinned MIT reference's `runtime/game_flags.c` array readers and `runtime/game_gear.c`
`game_player_gear` supply the pouch layout. Our `coop_equipment_guest.c` is a bounded read-only adaptation,
called only from the validated local-player observer on 1.4.3. It validates the bool-table vtable at
`main+0x39403d0` through the manager slot at `main+0x3ad66b0`, reads the int-array table three 0x60-byte records
after the bool table and the String64-array table seventeen records after it. Int-array entries are 64 bytes
with count/pointer at +0x20/+0x28; String64 entries are 144 bytes with count/pointer at +0x70/+0x78, 0x50-byte
elements with their text at +0x0c. Module bases continue to come only from generated layout data.

For weapon, shield and bow, `Pouch.<kind>.EquipIndex[0]` selects `Pouch.<kind>.Content.Name`. A negative-one
index means unequipped. Other negative/out-of-range indices, unavailable arrays, invalid names or mismatching
second reads remove the optional observation. Each map lookup stops after at most 64 probes. Manager/table
descriptors and all values are rechecked before publishing. No raw pointer crosses the network.

A 15-world-second copied-save run received 394 equipment snapshots through a separate ENet echo peer,
with all three base identities observed, successful process exits and unchanged source saves. Its 394 body
poses also passed the existing application gate. Synthetic checks cover unequipping, changing items,
unavailable observations, malformed names, pointer bounds, map corruption and unstable reads.

This identifies the equipped base actors only. The reference's separate model search scans large heap
ranges and compares nearby render origins modulo ten metres. It has not been adopted as proof of native
attachment ownership. Hand/back selection, cancellation on world/model changes, unique candidate identity,
native attachment palettes, fused additions and bowed-string deformation remain unverified here.
`prepare_coop_gear.py` can prepare a small private LNKA2 library for selected identities; rendering and its
bounded GPU/resource retirement remain a separate gate. A prepared mesh is not a wielded native weapon.

These notes summarize TotK 1.4.3 observations used by `runtime/coop_adapter.c` and the isolated experiments in
`runtime/coop_native_probe.c`. They preserve current findings rather than a chronological run log. Native
companions, direct movement/teleport and shared campaign control remain disabled. See the
[public plan](coop-phase2.md) for the remaining gate and [development guide](coop-development.md) for commands.

## Evidence and attribution

A static call path or readable pointer is a candidate, not proof of ownership or permission to invoke it.
An observed ordinary game call establishes that specific path; the successful weapon experiment adds one
bounded invocation context. Physical host-thread identity does not establish a guest scheduling/locking contract.
Native capability bits remain presence-only until the companion acceptance tests pass.

The pinned MIT arnaldolima1/totk-recomp reference supplies actor-request ABI/layout research, local pose readers,
model conversion/pose evaluation and rendering helpers. Exact source revisions and copied/adapted files are in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). The actor ABI research retains its MacNativeGames credit.
The external MeshCodec decoder is pinned MIT McSharp. Reference checkouts remain read-only; derived assets stay
ignored. GPL/AGPL references were consulted for behavior only, not copied into this implementation.

The [November 14 follow-up and next-session handover](coop-next-session.md#reference-review-on-2026-11-14)
records the unchanged arnaldolima1 revision, its still-unintegrated final body-pose/equipment path, Daurosk's
newly reviewed main and working branches, and LFarhi's early-access announcement. Keep pending body/combat
work and GPL behavior references distinct from verified reusable implementations.

The private audit tool `tools/coop_native_audit.py` maps scoped observations to the local generated functions,
resolves a return address to its call instruction, excludes non-executable data and distinguishes candidates from
invocations. Its output stays below `build/`, carries the generated-content marker and contains offsets/equality
results rather than generated bodies. Live pointers are local diagnostic identities, never network entity IDs.

## Local-player ownership and creation

`runtime/coop_adapter.c` `player_proc`, `resident_player_proc` and `player_manager_link` independently resolve the
local actor and its resident ownership. The PlayerMgr root slot is `main+0x3969918`. Scene component 13 is reached
through the module slot at `main+0x3add238`; the observed component vtable is `main+0x36d8598`.
Resident records are 0x70 bytes: linked data at +0x8, watcher at +0x18, with the linked actor at data +0x40 and ID
at +0x48. The local actor must match by pointer/metadata/ID, not by the name Player alone.

| Operation | 1.4.3 observation |
| --- | --- |
| Creation request | `main+0x599670`; Player helper `main+0xd3174c`, camera helper `main+0xd3105c` |
| Producer dispatch | `main+0xd30cf8`, observed from `main+0x1fe4ea8` via virtual slot +0x110 |
| Context copy | `main+0x59a138` from return site `main+0x599a90`; descriptor +0x18, source watcher +0x10 |
| Queue submission | `main+0x59a380` from return site `main+0x599cc0`; descriptor +0x98 handle has state 2 |
| Factory/construction | `main+0x3d3dd0` -> `main+0x3d40f0` -> `main+0x689894` -> `main+0x6898dc` |
| Initialization | Factory holder and initializer match the actor; result dispatch `main+0x62e910` from `main+0x3d4488`, result 1 |
| Task cleanup | `main+0x3d3edc`; allocator `main+0x85d170` from `main+0x108cad0` is task disposal, not actor destruction |
| Reference publication | `main+0x54cb00` writes handle +0x8 and state 3; observe before its unlock at return site `main+0x54cf00` |
| Reference take | Resident consumer `main+0xea5c80` calls `main+0x50d6bc`, return site `main+0xea5d28` |
| Resident binding | `main+0x14f334`, return site `main+0xea5d70`, binds the actor metadata into its resident record |
| Local-manager selection | `main+0x1b0614` from `main+0x7217e0` in `main+0x7216f0` selects scene component 13's final resident record |

The ordinary Player request's watcher equals its resident record +0x18. PlayerCamera and related Player-prefixed
requests have different watchers. The normal path connects request, task, constructor, state-3 publication, take
and resident binding to the same independently observed player. The manager selection/bind is a scene-owned
operation a companion must avoid claiming; it does not identify every camera/input/save singleton.

`coop_adapter_actor_request`, `coop_adapter_request_context` and `coop_adapter_request_enqueue` associate a request
once by watcher, thread and descriptor. New requests invalidate unfinished associations; handle attribution stops
after consumption. Pooled descriptor/handle reuse must not inherit an earlier actor's identity. Constructor,
initializer, holder and lifecycle traces are bounded. The observer never dereferences a descriptor after its
allocator handoff. Resolution discovery and co-op tracing use separate profiler bits.

## Retirement and resource correlation

`coop_adapter_actor_teardown`, `coop_adapter_dispose_begin` and `coop_adapter_native_dispatch` scope observations
by actor, metadata backlink and ID. The scope survives loss of local-player observation and retires before native
cleanup. Later callbacks compare captured identities without reading the cleaned actor.

| Stage | Observed path |
| --- | --- |
| Removal request | `main+0x63baa8`; ordinary weapon pickup return site `main+0x1b4be78` |
| Removal queue | `main+0x3d45e0` from `main+0x63bc40`; removal-pending flag set |
| Cleanup | `main+0xa4a194` from `main+0x992610`; actor state 11 in the observed weapon path |
| Disposal scope | `main+0x9925dc` calls `main+0x992644` before virtual cleanup |
| Allocator handoff | Captured owner/allocator/virtual target matched at `main+0x85d170` from `main+0x108cebc`, inside `main+0x108c8cc` |
| Resource binding | Descriptor +0xf8 equals actor +0x370 at initialization and cleanup, with the same actor ID |

The strict object diagnostic requires one identity's initialization -> request -> queue -> cleanup -> optional
allocator handoff and resource correlation. Another same-named actor, duplicate/reordered stage, stale metadata ID
or unrelated allocator cannot satisfy it. Resource equality does not establish reference counts, unique ownership,
cancellation behavior or permission to release it. An allocator entry is a handoff observation, not proof that
deallocation completed. Ownerless destruction and a safe externally callable removal API remain unverified.

The tested return-to-title route lost and regained player observation with the same actor/metadata/ID and only
one matching construction. The game exited normally but actor-recreation acceptance failed. That route therefore
cannot be reused as evidence of player destruction/recreation.

## Bounded native weapon experiment

`coop_native_probe_request` runs at request entry before generated locals cache registers or change SP. It checks
1.4.3, explicit timed-profile opt-in/marker, the known weapon-drop return site `main+0x20a57d8`, world age, ActorMgr
identity at `main+0x3ad7450`, exact weapon name, argument flags, optional arguments and an entry SHA-256. It preserves
the full Cpu and host FP environment and leaves the original watcher untouched. There is no render-time mutation.

The observed ABI has eight register arguments plus three stacked arguments: a byte flag and two optional output
pointers. The local drop initializes optional arguments to zero. Static inspection identifies a 32-bit status
output and a pointer output, but ownership of that returned object remains unverified; the probe requests neither.
Native context copying acquires actor references through engine helpers, not host shallow copies of owning data.

| Mode | Request data | Limit |
| --- | --- | --- |
| Clone | Original synchronous CreateArg, null watcher, unchanged zero extras | Borrows a legitimate inventory producer |
| Owned | Static process-lifetime CreateArg/name/empty BlackboardInit, zero actor dependencies, identity rotation/unit scale | Storage is never reused; position starts +2 m world X and +2 m Y |

Both modes issue at most one extra request and still use the authentic drop call as their scheduling trigger.
Owned data does not establish independent scheduling, general destination safety, dynamic storage reuse or
reconnect/cancellation ownership. Native receiver entries sample only the injected identity at a bounded rate,
stop when retirement begins and check metadata/ID before reading position. Ordinary pickup initiates retirement;
the host does not call a destruction API or write physics transforms.

## Recorded gameplay evidence

| Experiment | Result and interpretation |
| --- | --- |
| Borrowed request, original picked up first | Extra actor initialized; original retired while extra remained with a full inventory. Not injected-actor retirement proof |
| Borrowed request, targeted pickup | Injected actor's own request/queue/cleanup/resource/allocator path passed, without the figure |
| First owned request | Initialized, descended about 1.54 m and rested; diagnostic failed because the script collected neither weapon. Game exit 0 was not a complete pass |
| Strict owned request, no figure | Creation, gradual descent/rest and same-actor pickup/resource/allocator checks passed; 1.59 m descent, 66.24 s wall time |
| Strict owned request, figure enabled | All requested checks passed; 114 receiver observations, 1.53 m descent, 64.42 s wall time, source save unchanged |

The last two runs covered 30 world seconds each and exited cleanly. The final screenshot was inspected and showed
the local player and black-haired figure. The figure and physical weapon remain different objects. Initialization
order may differ from request order; identify the injected probe by its request, not by probe index alone.

`tools/coop_diagnose.py` `diagnostic_acceptance` distinguishes game exit, requested gates and overall diagnostic
success. Unrequested checks are true as not applicable. Its `spawn_fall_summary` requires a matching origin,
ordered same-identity samples, gradual downward steps and later rest; a teleport alone cannot pass. Position
samples support observed fall/rest, not verified ground-contact queries or humanoid collision/controller behavior.
General companion/gameplay readiness remains false. Raw reports, images, generated code and full run history stay
in the local ignored diagnostic folders.

## Open limits and next research

The isolated 0.4.0 integration repeated the instruction, SIMD, atomic and full-function differential checks on
both x86-64-v3 and x86-64-v2 harnesses. Each variant passed 179,961 instruction cases, 159,976 SIMD cases,
12,672 atomic cases and 5,470 full-function cases; SIMD validity agreed on 1,048,640 encodings. Flag checks
passed at O0/O1. Exclusive-monitor contention passed, while the existing 32/64/128-bit ABA failures persisted.
Source checks also passed for the co-op observer, network impairments, figure, native probe, audit, diagnostic
acceptance, settings, ExeFS patches and shader freshness. These checks do not establish in-game compatibility.

The candidate passed selftest/config, kernel, NVN textures, shader translation/cache, replay, mods, graphics ABI
and play-time probes. Replay also passed with four recording workers, state checks and artificial chunk skew.
The shader census was regenerated locally, allowing the previously unavailable shader/draw probe portions to run.
The additional validated memory probe passed 42 GPU checks with zero validation errors after correcting its
fixtures: initialized textures retain pool flags, and a finalized slot follows only a compatible texel format.
The fixture now checks compatible reuse and rejection of an unrelated format; production texture rules were
unchanged. This isolated device result does not establish full-game validation or shutdown correctness.

Copied-save 0.4.0 scene checks passed local walking/camera input/basic animation and the owned weapon's
creation, gradual descent/rest and same-actor retirement with the figure. Ordinary replay sampled 108 native
positions with 1.52 m descent; four workers with artificial skew sampled 111 with 1.56 m descent and no replay
state disagreements. Both covered 30 world seconds, exited cleanly and preserved source-save hashes. Inspected
images show the local player and black-haired visual figure. They remain separate from the physical weapon.

The confirmed loaded-layer full-game run entered the scene and submitted the figure but timed out at the
120-second ceiling, with zero logged Vulkan errors. It failed acceptance. An earlier clean run requested the
layer but silently fell back without it; that run is ordinary-rendering evidence only. Diagnostics now require
an explicit layer-enabled marker when validation is requested. Device, memory and replay probes passed with
the layer confirmed loaded. The device probe also now frees upload pools before destroying VMA.

Two auxiliary suites fail on this Windows setup using files byte-identical to the 0.4.0 tag: the prompt test's
synthetic layout lacks `N_BtnB_00`, and the worktree test loses temporary markers when raw Git removes a worktree
containing directory junctions. They are recorded failures. The integration worktree has independent build
directories and no shared build junction; never use raw worktree deletion as a cleanup shortcut for linked data.

The 1.4.3 consolidation checks on 2026-11-13 passed the co-op observer, network impairment, figure, native probe,
audit and diagnostic fixtures (22 acceptance cases), settings, shader freshness and content checks. The packaged
executable passed selftest/config probes. The CPU entry-hook change was also checked against Unicorn:

| Differential check | Result |
| --- | --- |
| Sampled module instructions | 60,000 encodings, 179,961 cases, no discrepancies |
| FP/SIMD | 20,000 encodings, 159,976 cases, no discrepancies; full validity comparison also agreed |
| Atomics/exclusives | 198 instruction sequences, 12,672 cases, no discrepancies |
| Emitted functions | 1,174 generated; 878 exercised in 5,470 cases, no discrepancies; 8,618 random cases skipped |
| Flag helpers | 2,000,484 operand pairs each at O0/O1, no mismatches |

Skipped function cases did not complete within the test's admissible execution/memory limits and are not passes.
These CPU checks validate lowering and the harness ABI; they do not establish companion behavior or native
scheduling. No lifter algorithm or module layout was changed. The separate concurrency failure below remains.

The optional full-game Vulkan validation-layer shutdown times out with and without the figure, despite no logged
validation errors. Those runs are not validation passes. An isolated validated device probe passed; the replay
draw probe needs the private shader census. Normal game rendering/shutdown and the authored-triangle figure test
pass. Earlier unrecorded viewport/scissor/vertex-binding calls caused device loss; the current figure goes through
the async recorder and restores replay state.

During consolidation, `tests/excl_mt.py` failed its 32/64/128-bit ABA cases on both the working tree and the
unchanged pre-consolidation CPU headers. The contention cases passed on both. The cooperative CPU-header change
only forwards Cpu to the entry hook; no exclusive-monitor semantics changed. Treat the ABA failure as an existing
CPU issue requiring a separate fix, not a passing check. Differential CPU results are recorded separately.

PouchPlayer's parameter composition references the Player model without direct PlayerRef/PlayerCameraTargetRef
components, but its pause-menu physics, AI, animation and render dependencies remain unverified. It has not been
created as a separate world companion.

A read-only 1.4.3 pack comparison during the 0.4.0 integration gives a more specific next investigation:

| Actor pack | Direct Player/camera references in its own ActorParam | Character-body references found in inspected parameters |
| --- | --- | --- |
| Player | Both | Player character controller and several Player matter-body configurations |
| PouchPlayer | Neither | None in the inspected Physics/ControllerSet parameters |
| Npc_Road_001 | Neither | Npc_Size_M character controller and matter body |
| Npc_BaseCamp001 | Neither | Npc_Size_M character controller and matter body |
| Npc_Tulin_Sage | Neither | Rito young-character controller/body, including battle variants |

These are parameter references, not observed live bodies or a complete dependency analysis. Their absence from
one ActorParam does not prove that inherited code avoids all player or story state. Prioritize observing the
ordinary Hylian NPC's authentic creation and Npc_Size_M controller lifecycle before trying a menu-display actor
as a physical companion. Establish its AI ownership, native movement inputs and destruction contract first.
The sage remains a comparison case with additional battle/story dependencies. That read-only comparison injected
no actor. A subsequent separately gated experiment extends the creation probe to exactly Npc_Road_001, as below.
Full parameter findings stay in ignored build reports.

## First native humanoid creation

Mode 3 uses the already verified generic request ABI at the same authentic weapon-drop call boundary, but its
owned name is exactly Npc_Road_001. It requires its own `isolated-npc-road-001-v1` copied-profile marker; weapon
markers cannot enable it. The request has independent process-lifetime storage, empty blackboard, no inherited
actor dependencies, identity rotation/unit scale and the same bounded offset from the legitimate producer.
It preserves CPU/FP state, requests no watcher and performs no direct physics writes or player cloning.

The first 20-world-second run passed creation acceptance: one injected request and initialization callback with
matching task, actor name, resource and metadata identity. Seventy-six native receiver observations recorded
about 1.54 m of gradual descent and later rest. The game exited cleanly, source-save hashes were unchanged and
the inspected image shows Link beside a rendered native humanoid NPC. The optional Link figure was disabled,
so this is engine actor/model evidence. Position observations still do not establish verified contact queries
or a reusable character-controller API.

A second run also passed and applied local walking/camera input after NPC creation. Local-player observations
recorded about 4.35 m of displacement in that later interval; the NPC retained its separate identity and source
saves remained unchanged. This checks local control after creation, not remote control of the NPC. Observed NPC
receiver entries include `main+0x2e27b0`, `main+0x54cb00` and `main+0x245030`; none is yet a verified callable
movement function or a safe command-consumption phase.

The NPC remains under engine behavior. No remote input, Link appearance binding, host-driven removal, reconnect
or independent scheduling is implemented. Creation still requires a real weapon drop. Session capabilities
remain presence-only; neither this result nor the NPC's parameter references complete Phase 2. Next inspect
the NPC's controller and native movement/update contract, then verify controlled retirement and scene changes.

Likewise, the inspected transform builder at `main+0xa0f3f0` does not
establish the removed five-argument teleport signature. Keep guessed calls and direct render-time physics writes
prohibited. Next verify a suitable companion actor/controller, reusable ownership and native movement/update
operations before associating the Link figure with a native body.

## Scoped NPC body and velocity experiment

`coop_adapter.c:npc_physics_capture` records two bounded ownership snapshots: the observed Physics
transform-builder entry and the same NPC's later native actor-update entry. It checks the request name,
actor/metadata backlinks and IDs, generation and retirement state before following the component. The
component's owner at `+0x38` must be that NPC; its `+0x20` points to the controller set. These checks do not
establish that arbitrary calls from that phase are safe.

The inspected 1.4.3 transform/bounds paths identify these live links:

| Link or entry | Observation and implication |
| --- | --- |
| Set `+0x10`, then `+8`, then `+0x18` | Reaches a body with vtable `main+0x392af88` |
| Set `+0x150` | Reaches that same body in the controlled NPC; this is an alias, not another movement target |
| Body type-name getter `main+0x298da40` | Identifies `CharacterMatterRigidBody` |
| Set `+0x148` and body's optional `+0x158` getter | Null in both initial and later observations; neither supplies a verified controller |
| Body's virtual `+0x40` getter | Follows `+0x1e0`, then `+0x28`; the latter was null, so no controller is claimed |
| Native actor-update receiver `main+0x2e27b0` | Repeatedly observes the initialized NPC; still not an accepted production command phase |

`coop_native_probe.c:coop_native_probe_npc_update` adds mode 4, distinct from creation-only mode 3. It requires
its own copied-profile marker, the exact scoped primary body, current metadata/world identity and matching
1.4.3 entry hashes. It calls the inspected `main+0x567750` with two arguments: body and three-float velocity.
The native routine checks the vector, copies it to the body's change request at `+0x44` and sets request
flag 7 under its own lock. Its native consumers were inspected as well. No generated function is copied
into public source and no host code directly stores into a physics transform or velocity field.

The bounded experiment requests +2 m/s on world X, then -2 m/s, then zero horizontal velocity. It preserves
the observed vertical velocity, restores the complete original CPU and host FP environment after calls,
and retains a stop call within its 96-call budget. The hook runs only at the native actor-update entry;
rendering and the network worker cannot execute it. Ordinary guest commands remain rejected.

Three copied-save runs made 57, 59 and 59 requests respectively. All exited normally and preserved source-save
hashes, but all **failed movement acceptance**: forward/reverse displacement was zero. Additional feedback
observed a native request with flag `0x80` and the requested velocity immediately after the call. At the next
observed actor update, the request was absent, cached velocity was zero and body position was unchanged.
This establishes queued requests without effective character movement at that early actor-update phase.
The later consumer-entry experiment below distinguishes that failure from the request API itself.

`coop_diagnose.py:npc_velocity_summary` requires the same initialized NPC and world, strictly ordered bounded
direction changes, at least 0.4 m of travel in each direction, no sampled teleport and later positional rest.
Synthetic checks reject stationary actors, another probe/world, duplicate/missing requests and missing rest.
Unrequested gates remain not applicable. A zero process exit or successful native queue call cannot pass the
explicit movement diagnostic.

Further controller research must resolve locomotion ownership. The creation-only run also captured controller-set
receiver entries `main+0x434fb0`,
`main+0x679cfc` and `main+0x456d70`. The last selects a body by role; the first two need further inspection
and argument/phase correlation. They are research targets, not callable movement APIs. An inspected
immediate velocity setter (`main+0x9da5c4`) also writes cached body state;
its appropriate calling phase is unverified and it has **not** been invoked as a fallback. Keep the Link
figure separate until safe binding/removal and repeatable lifecycle ownership are established.

## Native request consumption and effective NPC movement

`coop_adapter.c:coop_adapter_npc_velocity_consume` and `npc_velocity_backend_observe` correlate a request with
the same live NPC body, SDK body identity, thread and world generation. Every consumer entry clears the previous
thread-local handoff, including consumers for other actors. The bounded trace stores at most 192 records and
never writes guest state. Lock-entry/unlock-entry observations additionally track a matching request under the
body's native mutex; an entry observation does not claim the lock has already been acquired or released.

An early actor-update pulse run produced 108 consumer/backend records. All observed vectors were already zero
at the consumer `main+0x182eb0` and its backend dispatch `main+0x11c96ec`, despite immediate post-request feedback
showing the requested +/-2 m/s. The native velocity is overwritten before consumption. This does not identify
the exact writer or establish a Havok activation/sleep failure.

Inspection of `main+0x182410` verifies its call to `main+0x182eb0`, returning at `main+0x1824f8`, with request,
body, output-mask pointer and worker flag as its four arguments. At this entry the parent has not yet acquired
the body's `+0x78` mutex. Normal request cleanup takes that lock after the consumer returns. The owned body's
pending request at `+0x60` still equals the consumer's request argument in the successful experiment.

`coop_native_probe.c:coop_native_probe_npc_consume` adds separately armed mode 5. The actor-update pulse latches
its target velocity; at consumer entry the probe revalidates the same live NPC/body/world, exact pending request,
velocity flag, native caller and consumer/parent code hashes. It rejects a command older than 100 ms and allows
at most one correction per world timestamp, with a separate 96-call ceiling. It invokes only the existing
inspected `main+0x567750` body/vector API, which takes its own native lock, then restores the complete CPU and
host FP environment before the original consumer runs. It does not replace consumer arguments, call a guessed
controller ABI or store directly into a request/body. A shared try-lock and thread-local recursion guard prevent
concurrent or nested probe calls. Creation-only and mode 4 markers cannot arm mode 5.

Two copied-save runs with the optional Link figure disabled passed displacement/rest acceptance:

| Run | Actor-update requests | Consumer reapplications | Forward / reverse | Result |
| --- | --- | --- | --- | --- |
| 20 world seconds, scripted local walking/camera input during the pulse | 57 | 61 | 1.993 m / 1.933 m | Later rest, normal exit, source-save hashes unchanged |
| 22 world seconds, no local movement after creation | 62 | 61 | 1.931 m / 1.867 m | Later rest, normal exit, source-save hashes unchanged |

The saved logs also passed the stricter consumer-correlation parser after its addition: correction sequence,
generation and timestamps match the same bounded pulse. Images confirm the original Hylian NPC appearance;
there is no Link model binding yet. Synthetic fixtures cover incorrect callers/hashes, changed pending request,
stale commands, duplicate timestamps, recursion and CPU/FP preservation. Diagnostic acceptance requires real
actor displacement in both directions and later rest, rather than successful API calls alone.

This proves bounded effective movement of the native NPC in the controlled scene. Mode 5 commands are synthetic;
no human peer controls it. The mode 6 experiment below extends that result to a bounded ENet stream and stop
recovery. Native locomotion animation, grounding/collision on varied terrain, full local camera/input independence,
removal and repeated scene/session lifecycle remain unverified. Ordinary native commands still reject mutation
and session capabilities remain presence-only.

## Leased ENet velocity diagnostic

`coop.c:coop_guest_observe` offers a decoded worker snapshot to `coop_native_probe.c:coop_native_probe_peer_offer`
only while separately armed mode 6 is active. The observer copies data into one slot protected by the same
nonblocking probe lock; it performs no guest mutation. At native actor update and request consumption, the probe
checks the exact owned NPC/body/world again before applying horizontal velocity through the existing verified
API. The renderer and network worker never call the native velocity routine. Normal gameplay capabilities and
the ordinary guest command queue remain disabled.

The binding identifies the negotiated session, peer player, peer generation and the scoped local generation.
A change revokes it without creating or rebinding an actor. Expiry within the same epoch permits recovery.
Only a newly published sender timestamp and newer receive timestamp can replace a command. Sender time is used
for ordering, never compared with the receiver's clock. The local receive-time lease lasts 200 ms; repeated
transmissions of the same pose cannot extend it. Native consumption rechecks expiry independently of actor
update, so an old latched horizontal velocity cannot continue through a publication gap. Missing actor updates
also request a stop, and an eight-world-second duration plus 256 calls per hook bound the diagnostic.

`tools/coop_velocity_peer.c` is a game-free loopback client using the production ENet worker and protocol/content
negotiation. After a reliable readiness label it publishes forward velocity, pauses, publishes reverse, pauses,
publishes diagonal velocity and stops. The worker continues retransmitting the old sample during each short
pause. This specifically exercises stale publication rather than relying on a transport disconnect. It uses
presence packets as an explicit diagnostic velocity source, not a new gameplay-command protocol or a shared
scene identity. Its absolute position and vertical velocity are ignored. No guest pointer crosses the wire.

The first ENet run failed acceptance despite moving in each requested direction. Feeding the cached body's
vertical velocity back at consumption caused artificial ascent and eventually a stale actor-update stop. The
corrected mode 6 instead retains Y from the exact pending native request at `+0x44`, after native preparation,
before replacing X/Z. This preserves the current native gravity/ground response. Synthetic checks deliberately
make pending Y differ from cached Y and require the native call to retain pending Y. Do not remove the stale
update guard to make this failed run pass.

Two corrected 28-world-second runs passed all requested ENet gates:

| Local input | Producer / consumer calls | Sampled forward / reverse | Sampled diagonal X/Z | Stops and exit |
| --- | --- | --- | --- | --- |
| Idle after creation | 237 / 125 | 2.066 m / 2.208 m | 1.039 m / 1.073 m | Two three-axis expiry rests, final rest, normal game/peer exit, source save unchanged |
| Walking and camera input during the stream | 234 / 123 | 2.311 m / 2.483 m | 0.776 m / 0.808 m | Same stop/exit/save requirements passed; local horizontal travel 4.230 m |

`coop_diagnose.py:npc_peer_velocity_summary` matches the initialized actor and world, bounded ordered commands,
one binding, direction-specific displacement, both expiry rests and final positional rest. All three axes must
rest; unreasonable horizontal steps fail acceptance. Consumer correction sequence/generation/time and the peer's
exit are separate required gates. Distances use sampled segments with transition margins. They are not exact
integrals of network velocity. Images show the native Hylian NPC, with the optional Link figure disabled.

This establishes a local ENet-to-native movement diagnostic with stop/recovery. It does not establish human
control, arbitrary native movement, animation, safe removal/reconnect, shared world identities or Internet
acceptance. Keep the experiment isolated until those lifecycle and movement contracts are verified.

The older [Lotuskit physics behavior notes](https://github.com/aquacluck/totk-lotuskit/blob/59dcfccd77b6d4bcfa718bff806bc55be640edb7/src/program/structs/phive.hpp)
were read as a GPL behavior reference only. No code or layouts were copied; its older game addresses were
not used as 1.4.3 call targets. The observations and guards above come from this user's local 1.4.3 inputs.
