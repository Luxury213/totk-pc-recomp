# Co-op native research notes

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
The sage remains a comparison case with additional battle/story dependencies. No NPC was injected by this audit,
and the weapon-only probe whitelist remains unchanged. Full parameter findings stay in ignored build reports.

Likewise, the inspected transform builder at `main+0xa0f3f0` does not
establish the removed five-argument teleport signature. Keep guessed calls and direct render-time physics writes
prohibited. Next verify a suitable companion actor/controller, reusable ownership and native movement/update
operations before associating the Link figure with a native body.
