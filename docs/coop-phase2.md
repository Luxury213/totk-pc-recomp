# Co-op status and public development plan

Phase 2 is in progress. There is no playable second Link or shared cooperative campaign yet. The current
milestone provides session infrastructure, an animated visual Link and bounded native weapon experiments.
This public plan is the resumption reference; it does not depend on private notes in ignored `build/`.

See [the development guide](coop-development.md) for commands, [native research](coop-native-research.md) for
engine evidence and [the campaign design](coop.md) for the agreed final behavior.

## Current status

| Area | Verified result | Remaining gate |
| --- | --- | --- |
| Phase 1: isolated build | 1.4.3 module hashes, separate runtime/executable, dedicated profiles, selftest/config probe | Each participant supplies their own local build |
| Phase 2: transport | ENet worker, protocol v3, reliable labels, 30 Hz pose, compatibility/freshness and local impairment tests | Real two-PC private-VPN validation; gameplay authority is not implemented |
| Phase 2: visual companion | Textured animated Link with black hair, scene lighting/depth/shadows | No associated native body/controller, collision or gameplay |
| Phase 2: engine observation | Local-player request/task/construction/reference paths and weapon retirement/resource/allocator correlation | General ownership, cancellation, scheduling and safe callable operations |
| Phase 2: native experiment | One independent weapon request falls, rests and is collected; strict checks passed with/without the visual figure | Still one-shot and triggered by an authentic weapon drop; not companion spawning |
| Phase 2: remote native character | Disabled; native commands are rejected and capabilities remain presence-only | Actor/controller selection, native movement, safe update phase and repeated lifecycle tests |
| Phase 3: cooperative adventure | Design and acceptance requirements documented | Combat/items, persistence, travel/abilities and complete story remain unimplemented |

The visual Link and the native weapon are separate objects. An observed weapon fall does not establish humanoid
collision/controller behavior. Negotiation cannot enable gameplay readiness without verified native capabilities
and stable shared world identities. Raw guest addresses must never become network entity IDs.

## Next implementation milestone

Deliver a real companion actor that appears, moves independently and disappears through verified engine
operations, while the local player's camera and input continue working. Keep the native capability bits disabled
until the complete gate below passes.

1. Inspect a suitable non-Player actor/controller and its native body. The existing Player's resident record and
   manager link are scene-owned; copying them or allocating another PlayerLink is not a safe shortcut. The
   inventory-display PouchPlayer remains only a research candidate, not a verified world actor.
2. Verify creation/storage ownership beyond the one-shot experiment: asynchronous completion, rejection,
   cancellation and safe storage reuse. Retain scoped request, actor, metadata ID and world-generation identities.
3. Locate a verified native movement/controller update phase. Keep network work on its worker, consume bounded
   commands on the appropriate guest phase and preserve local input/camera ownership. No direct physics writes
   from rendering, guessed function signatures or teleport fallback.
4. Bind the existing visual Link to that native character and route the peer's movement/orientation/basic
   animation. The model, extraction and ENet infrastructure already exist; do not restart those implementations.
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
