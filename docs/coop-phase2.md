# Co-op status and public development plan

Phase 2 is in progress. There is no playable second Link or shared cooperative campaign yet. The current
milestone provides session infrastructure, an animated visual Link and a bounded native NPC creation/movement/removal experiment.
This public plan is the resumption reference; it does not depend on private notes in ignored `build/`.

See [the development guide](coop-development.md) for commands, [native research](coop-native-research.md) for
engine evidence and [the campaign design](coop.md) for the agreed final behavior.

Priority update after the visual-grounding report: verify the visible figure's binding to a native body and
its feet/terrain relationship before further equipment appearance work. Ordinary presence has no collider;
mode 7 now anchors the figure to the tested NPC origin, and mode 8 suppresses/restores that NPC's original
mesh through its native controller. Mode 9 passed one native retirement with resource/allocator correlation.
Visual feet/terrain and repeated native lifecycle acceptance remain open. The test echo's horizontal offset reuses
the sender's Y and can misplace it on slopes. An origin calibration or scale adjustment cannot complete this gate.

**Resume here:** [the next-session handover](coop-next-session.md) records the tested source/build checkpoint,
the latest reference review and the ordered work toward original Link movement and attacks. The next
character milestone includes final blended pose and equipment replication, original run/jump/attack evidence,
and a verified native companion lifecycle. The current NPC stream does not establish Player behavior.

## Current status

| Area | Verified result | Remaining gate |
| --- | --- | --- |
| Phase 1: isolated build | 1.4.3 module hashes, separate runtime/executable, dedicated profiles, selftest/config probe | Each participant supplies their own local build |
| Phase 2: transport | ENet worker, protocol v5, reliable labels, 30 Hz pose, compatibility/freshness and local impairment tests; acknowledged incompatibility rejection and isolated proxy client endpoints | Real two-PC private-VPN validation; gameplay authority is not implemented |
| Phase 2: visual companion | Textured animated Link with black hair, scene lighting/depth/shadows | No associated native body/controller, collision or gameplay |
| Phase 2: final body pose | 58-bone capture/encoding/interpolation/application; one-game ENet echo passed with 387 body samples and unchanged source saves | Equipment, full run/jump/attack fidelity and binding to a native body remain pending |
| Phase 2: equipped identities | Bounded pouch observation and optional weapon/shield/bow names; live echo received 394 equipped snapshots; selected models prepared privately | No gear placement/rendering, fused additions, bow-string replication or inventory transaction |
| Phase 2: native equipment research | Original reference-setter identities and bounded ModelUnit discovery; three models and 81 raw first-palette matrices observed | Persistent ownership, coordinate conversion and hand/back attachment binding remain unverified |
| Phase 2: engine observation | Local-player request/task/construction/reference paths and weapon retirement/resource/allocator correlation | General ownership, cancellation, scheduling and safe callable operations |
| Phase 2: native experiment | One independent weapon request falls, rests and is collected; strict checks passed with/without the visual figure | Still one-shot and triggered by an authentic weapon drop; not companion spawning |
| Phase 2: humanoid creation experiment | One owned Npc_Road_001 request initialized; visible native NPC with the visual figure disabled, observed descent/rest, source save preserved | Reusable session ownership, rejection and cancellation remain unverified |
| Phase 2: NPC body/velocity diagnosis | Early actor-update pulses failed; scoped consumer/backend tracing showed their velocity was already zero before consumption | The exact native override writer remains unconfirmed |
| Phase 2: isolated NPC movement | Two consumer-entry pulse runs passed: about 2 m forward, 1.9 m reverse and positional rest; normal exits and unchanged source saves | Synthetic commands only; no peer control, verified locomotion animation/grounding contract or Link model binding |
| Phase 2: ENet NPC diagnostic | A game-free loopback peer drives forward/reverse/diagonal movement; two lease-expiry stops, recovery and final positional rest passed | Scripted peer only; no human/Internet acceptance or complete native companion lifecycle |
| Phase 2: native-origin figure experiment | Mode 7 copies the owned NPC's actor origin to the Link figure; 194 exact capture/submission matches and native movement gates passed on a slope | The original NPC appearance remains; ground/feet visual acceptance, appearance replacement, retirement and human control are still pending |
| Phase 2: native appearance experiment | Mode 8 suppresses the owned NPC mesh while publishing Link and restores it after the peer exits; images, origin and native movement gates passed | One controlled hide/restore pair; no native retirement, repeated creation, persistent model-state authority or human control |
| Phase 2: native retirement experiment | Mode 9 passed one complete creation/movement/visibility/retirement run; the same NPC reached request, queue, resource cleanup and allocator handoff | No repeated lifecycle in one process, creation-storage reuse, reconnect/load acceptance or human control |
| Phase 2: two native cycles | Mode 10 passed two creation/pulse/rest/removal cycles in one world with distinct IDs and separately correlated cleanup | Two retained slots, inventory-drop scheduling and no figure/peer; session-driven recreation, reusable storage, scene transitions and human control remain pending |
| Phase 2: session-driven native creation | Mode 11 passed one negotiated connection creating its NPC at the verified local actor-update worker, ENet motion, native-origin Link presentation and correlated removal without an inventory drop | One retained slot and bounded movement; second join/reconnect, scene transitions, body/model fit and human control remain pending |
| Phase 2: bounded native reconnection | Mode 12 passed two session-owned native lifetimes in one running game, stable test-player ID, distinct session/actor identities and separately correlated cleanup; idle and local-control runs passed | Two retained slots and existing motion limits; indefinite reuse, scene transitions, body/model fit and continuous human control remain pending |
| Phase 2: ordinary native character commands | Disabled; the ordinary command queue rejects mutation and capabilities remain presence-only | Production movement/animation contract, Link binding, removal, shared world identities and repeated lifecycle tests |
| Phase 3: cooperative adventure | Design and acceptance requirements documented | Combat/items, persistence, travel/abilities and complete story remain unimplemented |

The ordinary visual Link and the native weapon are separate objects. A separately armed NPC/figure experiment
now shares a copied native origin, while retaining the NPC's original appearance. An observed weapon fall does not establish humanoid
collision/controller behavior. Negotiation cannot enable gameplay readiness without verified native capabilities
and stable shared world identities. Raw guest addresses must never become network entity IDs.

## Next implementation milestone

Upstream compatibility review (2026-11-13): [v0.4.0](https://github.com/valentderah/totk-pc-recomp/releases/tag/v0.4.0)
was published on November 10 at `7a37fc3c346cd6f2b3c80637effb27b880ce817b`. The preserved cooperative baseline
uses port version 0.3.11; an isolated integration candidate targets 0.4.0. Both target TotK 1.4.3. The release changes renderer replay,
memory/resolution handling, CPU/runtime behavior and diagnostics. Several touched files also contain our
figure hooks, including vk_exec_draw.c, vk_exec.c/.h, vk_device.c, nvn_api_obj.c, main.c and menu.cpp.
The candidate preserves the figure recorder hooks and invalidates the new per-context draw caches after figure
passes. Camera capture uses replay-local uniform values. While co-op is enabled, replay chunks record in order
through the existing hold scheduler because figure/camera/shadow/tile state is shared. Mode is sampled once per
submission, so enabling co-op cannot expose that state to already-parallel chunks. Ordinary non-co-op recording
keeps upstream behavior. This is a correctness constraint, not a co-op parallel-rendering speedup.

The candidate passed CPU differential checks on both variants, runtime probes, fresh shader preparation,
local controls/animation and copied-save native weapon/figure tests, including four replay workers. Full-game
validation with the layer confirmed loaded still timed out after entering the scene, with no logged Vulkan
errors. Keep this integration experimental and preserve the old build; that timeout is not an acceptance pass.
No full performance comparison or two-PC gameplay acceptance is claimed. A source merge does not complete Phase 2.

Deliver a real companion actor that appears, moves independently and disappears through verified engine
operations, while the local player's camera and input continue working. Keep the native capability bits disabled
until the complete gate below passes.

1. Assess a suitable companion actor/controller and its native body, including a Player-derived puppet if its
   ownership can be verified. The existing Player's resident record and manager link are scene-owned; copying
   them or allocating another PlayerLink is not a verified shortcut. The
   ordinary Hylian NPC packs reference Npc_Size_M character controllers/bodies without direct Player/camera
   components in their own ActorParam. The first Npc_Road_001 creation experiment passed; inspect its native
   controller and movement contract further. Early actor-update velocity requests are overwritten before
   consumption. Reapplying through the same native API at the verified request-consumer entry passed two
   bounded movement tests. This is an isolated scheduling result, not yet a production locomotion contract.
   The initial and later ownership snapshots identify the same primary body; trying that alias again is not
   a different controller. The inventory-display PouchPlayer
   remains a weaker research candidate, not a verified world actor. Parameter references alone are not live-body proof.
2. Verify creation/storage ownership beyond the one-shot experiment: asynchronous completion, rejection,
   cancellation and safe storage reuse. Retain scoped request, actor, metadata ID and world-generation identities.
3. Extend the bounded ENet velocity experiment into a production movement contract. Its 200 ms receive-time
   lease stops repeated stale samples and permits recovery within the same session; a changed session/player or
   generation revokes the actor binding. Verify world transitions, broader ground/collision behavior and local
   input/camera ownership while keeping network work on its worker. No direct physics writes from
   rendering, guessed function signatures or teleport fallback.
4. Reproduce the original Link's final blended pose, equipment and run/jump/attack actions, then establish their
   binding to the native companion. The model, extraction and ENet infrastructure already exist; do not restart
   those implementations. Exact attack appearance and cooperative enemy damage are separate acceptance gates.
5. Exercise repeated creation/removal, scene load/unload and reconnect. Only then enable supported native
   capabilities and validate with two PCs over the private VPN.

## Phase 2 acceptance

| Test | Required result |
| --- | --- |
| Independent characters | Two positions and facing states with basic animation, independent local camera/input |
| Join and leave | One companion is created and removed through verified native operations |
| Reconnection | No duplicate actor, stale generation command or access to a retired actor |
| Scene lifetime | Repeated load/unload preserves valid references and coordinates both peers' readiness |
| Execution context | No guest mutation in rendering or the network worker; native calling/locking contract verified |
| Adverse network | Reliable interactions survive 100/200 ms latency, jitter and 5% loss without duplication |
| Internet session | Two actual PCs on the private VPN, at least 30 minutes with reconnection and save/reload |

Local workers and short copied-save diagnostics support development; they do not replace these gameplay tests.
If the engine still prevents safe companion operations, the diagnostic milestone can be reviewed with its limit
stated. A rendered figure or native weapon experiment cannot be labelled a completed Phase 2.

## Adventure after native characters

The campaign contract remains host-owned progress in a separate profile, per-player inventory/equipment/health,
unique ordinary pickups, shared quest progress and a common checkpoint restored after either player's death.
Both players initially stay in the same region; the host advances story text/cinematics. Simulation-pausing menus
pause both peers and transitions wait until both are ready.

| Stage | Completion evidence |
| --- | --- |
| Combat and items | Host decides enemies/damage/death and gives each simultaneous pickup one winner; no initial PvP |
| Persistence | Stable guest identity, correct individual inventory after reconnect, atomic common checkpoints/save recovery |
| Travel and abilities | Coordinated destinations/streaming; exclusive object ownership for Ultrahand, constructions and Recall |
| Full story | New campaign through the prologue and mandatory transitions, tutorials/rewards, dialogue/skips and scene disconnects |

Persistent operations need identifiers, revisions and recovery semantics. Reliable notification labels are not
persistent events. Do not copy actively written save folders. Personalization beyond the fixed black hair,
public servers, split screen and PvP remain outside the initial target.

## Reusing Link's appearance and behavior

The companion may reuse Link's locally extracted mesh, skeleton and animation data. The current figure already
provides a visual starting point. Giving a native companion that appearance still requires a verified model
binding or replacement path and removal of the NPC's original visible model. Drawing both at the same position
would not establish that binding.

Keep the companion's actor/body identity and lifetime independent. Copying the local Player's component memory,
input owner, camera links or singleton references cannot create a second independent human-controlled player.
Each PC keeps its own local Player and camera. Its original movements and attacks can supply final pose,
equipment and action data for the other PC's independently owned representation. A complete extra Player
instance remains an investigation route requiring a verified control/camera/manager contract. The current NPC
does not inherit that behavior through a mesh change. Neither appearance replication nor a successful spawn
establishes shared combat, abilities or campaign authority. See the handover for the next pose/combat gates.

## Source delivery and known limits

Consolidate handwritten source, synthetic fixtures, dependency notices and these public documents in reviewable
commits on the cooperative branch. Each copied permissive component needs its original license/header and exact
source revision in THIRD_PARTY_NOTICES.md. Keep all game-derived code, binaries, extracted models, save copies,
screenshots and private reports ignored; every player supplies their own content.

Run the development-guide checks and `tools/check_content.py --staged` before a source commit. CPU-header/lifter
changes also need the differential checks in building.md. Report failed or unrequested checks honestly. The
research notes preserve known validation limitations, including the optional Vulkan validation-layer shutdown
and the pre-existing exclusive-monitor ABA test failure. Hosted CI has to run after publication; local results
are not a hosted CI approval.
