# Co-op architecture and acceptance gates

The first target is a two-player private-VPN campaign on Windows with TotK 1.4.3. See
[coop-development.md](coop-development.md) for implemented behavior, build commands and validation.
The current status, next implementation steps and acceptance gates are in the
[public development plan](coop-phase2.md); verified engine paths are in [native research notes](coop-native-research.md).
This document describes the intended campaign; it does not claim those features already work.

## Campaign contract

The host owns a separate co-op campaign and controls story dialogue and cinematic advancement. Each player keeps
their own inventory, equipment and health within that campaign. Ordinary pickups have one winner; quest progress
belongs to the group. Either player's death restores the common checkpoint for both players.

The final acceptance run starts a new campaign from the prologue. Development may use copied advanced saves.
Initially both players remain in the same region and coordinate travel. Simulation-pausing menus pause both peers;
story transitions wait for both players to be ready. Replicating a button press does not synchronize a cinematic.
Both characters use Link's body; the companion has black hair to distinguish it from the local player.
Public servers, split screen, a full character customization system and PvP are outside this target.

## Responsibilities and authority

Use a listen server: the host also plays and decides persistent world state, AI, enemy health, spawning, loot and
shared physics. Clients request interactions; the host validates them and publishes accepted results. Each pickup
needs a unique identity and revision so simultaneous requests cannot award the same object twice.

Local movement should stay responsive, with explicit limits and reconciliation for host validation. This does not
establish that two independent engine simulations agree. Full deterministic lockstep or rollback would require
evidence about threading, physics, RNG, streaming and complete state capture that the project does not yet have.

| Layer | Responsibility | Execution context |
| --- | --- | --- |
| Transport | Explicit serialization, negotiation, freshness checks, bounded queues | Independent ENet worker |
| Game adapter | Version-specific capture, lifecycle and validated native commands | Observation now; verified world update phase required for mutation |
| Presentation | Snapshot interpolation, camera projection and status | Renderer/UI |

Transport uses ENet 1.3.18 with direct VPN IPv4 addresses. Reliable ordered messages carry negotiation and
notifications; sequenced unreliable movement runs at 30 Hz. Notifications currently carry diagnostic labels only.
Game version/content identity, session nonce, player identity, source generation and sequence numbers prevent
incompatible or stale presence updates. Gameplay commands will also need stable entity identities and world epochs.
Guest pointers must never become network entity IDs.

Native readiness requires verified capabilities and stable scene identities on both peers. The current adapter
advertises presence only. Raw scene pointers and the current origin-position heuristic do not establish a loaded,
unpaused world or a shared region. A successful connection cannot open the gameplay gate.

On a future shared simulation, losing the guest pauses the campaign until reconnection or host closure; losing the
host returns the guest to the lobby. Those behaviors require verified pause/world control before they can be enabled.

## Native integration gate

The first playable deliverable is a real remote actor that appears, moves and disappears without claiming local
input, camera or player singletons. A projected overlay is only a diagnostic. Do not assume a second `PlayerLink`
allocation is safe. Establish the actor factory, update scheduling, destruction and transform/controller request
contracts, including their actual ABI, lifetime checks and locking requirements.

`runtime/nvn_api_obj.c` `nvnQueuePresentTexture` calls the read-only observer before its blocking scope releases
the virtual core. This identifies an observation opportunity, not a safe mutation phase. Trace host-thread IDs
describe where a callback ran; they do not prove guest scheduling or physics synchronization.

The removed co-op warp wrote actor/physics memory from presentation and repeated the writes for several frames.
Pointer readability and a co-op mutex cannot make that operation safe against engine workers. The inspected
physics function at main+0xa0f3f0 builds a transform from its owning actor; it does not establish the previously
suggested five-argument teleport signature. No guessed native call or direct-memory fallback is allowed.

Teleport stays disabled until an ordinary engine warp has been traced from request through completion, including
streaming readiness, terrain validation, controller updates, velocity and physics synchronization. Consume requests
in a verified phase, rechecking session/entity generation, destination scene, expiry and request ID. Report success
only after engine acceptance. Never hold the co-op lock while calling the guest.

If safe actor operations remain unverified, deliver reproducible diagnostics and instrumentation with that limit
stated explicitly. Keep capability bits disabled until real-game tests demonstrate the required behavior.

## Persistence and progression

The host stores world progress and stable per-player guest state in its isolated campaign. Checkpoints bind both
players' states to the same revision. Persistent operations need identifiers, deduplication and transactional
recovery across reconnect/save/reload. Never copy a save folder while the game is writing it.

Late join requires an authoritative baseline before incremental events. Ultrahand, constructions and Recall need
exclusive object ownership and host-approved transfer; implement and validate them after ordinary combat and items.

## Delivery stages

| Stage | Required evidence |
| --- | --- |
| Session infrastructure and diagnostics | Synthetic protocol/adapter checks, real ENet workers, malformed/stale packet rejection and network impairment; isolated reproducible build |
| Native characters | Spawn/move/despawn; independent camera/input; repeated load/unload and reconnect without duplicate or stale actors |
| Combat and items | Host-decided damage/death/pickups; simultaneous pickup has one winner; no initial friendly fire |
| Persistence | Guest identity and inventory survive reconnect; either death restores one common checkpoint; consistent save/reload |
| Travel and abilities | Both destinations ready; coordinated region changes; ownership validated per ability |
| Complete story | New prologue campaign; mandatory transitions, tutorials, rewards, dialogue/skips and disconnects during scenes |

Test reliable interactions at 100/200 ms latency with jitter and 5% loss. Local headless workers can validate
transport before spending memory on two full game instances. Measure memory before that step. Real Internet
acceptance requires the friend's PC and at least 30 minutes with reconnect and save/reload tests. A build or a
network connection alone does not complete the campaign.

## Public source boundary

Publish handwritten implementation, synthetic tests, dependency attribution and documentation. Every player builds
locally from their own game content. Extracted/generated game code, executables, game-derived shaders, copied saves and private
diagnostic artifacts stay under ignored `build/` or `generated/`. Follow AGENTS.md and CONTRIBUTING.md, and run
`tools/check_content.py --staged` before a source commit.
