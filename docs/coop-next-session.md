# Co-op handover and next character milestone

Checkpoint: 2026-11-23. Read this before resuming implementation, then consult
[the public plan](coop-phase2.md), [development commands](coop-development.md) and
[native evidence](coop-native-research.md). These public documents are authoritative; private diagnostics
under ignored `build/` supplement them.

## User's intended result

Two people on separate PCs, connected over a private VPN, play as Links with the original game's movement,
attacks and equipment. The companion's black hair is the agreed initial visual difference. A shared campaign
starts at the prologue, with host-owned story/world progress, individual inventory/health, unique pickups and
a common checkpoint restored when either player dies. The first implementation requires the same region.

The NPC experiment is evidence about networking and a native body. Replacing its visible mesh does not grant
Player's action graph, weapons, abilities or damage. Do not quietly redefine the objective as an NPC with Link's
appearance. Likewise, a full independent Player instance is an investigation route, not something proven
impossible or safe. Copying live Player memory or shared input/camera/manager references is not an implementation
of independent ownership.

For two PCs, each human already controls the original local Link. The other game can reproduce that Link's
final pose, equipment and actions on an independently owned remote representation. Shared enemies, projectiles,
items and abilities still require world identities and authoritative outcomes. Matching an attack's pose does
not establish that it damages the same enemy in both games.

## Source and build checkpoint

Mode 11 now passes one session-driven creation without any inventory-drop input. A copied negotiated peer
candidate is consumed only at the verified local Player's actor-update worker, with resident/metadata/world,
native dispatch/TLS/code and mapped writable guest-stack guards. Three optional stack arguments use a separate
aligned outgoing area; complete CPU/FP state and its prior bytes are restored. The first run `run-a507426c10`
passed creation, leased ENet motion, Link figure/native hide-restore and native removal/resource/allocator
correlation, with normal game/peer exits and unchanged source saves. See the native notes and development
commands for mode 11. It still permits one retained creation slot, bounded motion and one peer lifecycle;
second joins/reconnects, load transitions and human control remain unverified.
A second run `run-a95babe3c7` passed the built-in local control sequence: 9.937337 m local displacement,
122 exact native-origin figure submissions, native visibility/rest/removal and unchanged source saves.
Its inspected frame shows both Links. The attack buttons were applied; successful strikes/shared damage
and unobstructed feet/terrain fit are not claimed. The two runs used separate processes.

Development resumed at the user's request after the reference review. Mode 10 now passes two native
creation/pulse/rest/removal cycles in one world, using separate retained argument/blackboard slots and
per-probe physics snapshots. The adapter publication/TLS-scope audit, synthetic address-reuse and retired
identity tests, 38 diagnostic report tests and six runtime probes passed. The copied-save run is
`run-16b6eb3cd9` (45 world seconds, normal exit, source saves unchanged); see the native notes for identities
and measured movement. Mode 10 deliberately has no figure/peer. It is a bounded lifecycle test, not the
playable second-Link goal, session-driven spawning or permission to reuse native request storage.
The same executable passed the mode 9 ENet/Link-figure regression `run-90cad6854a`: 160 exact origin
submissions, both lease-expiry stops/recovery, native model hide/restore and retirement, normal game/peer
exits and unchanged source saves. Two synthetic cycles plus one peer cycle are not peer reconnection proof.

Working branch: `feature/coop-native-npc-probe`, published to
[Luxury213's fork](https://github.com/Luxury213/totk-pc-recomp/tree/feature/coop-native-npc-probe).
The active source worktree in the existing workspace is `build/coop-v040-source/`. The outer
`feature/coop-multiplayer` worktree and its older executable are preserved. Do not switch to that older checkout
and accidentally resume from it. On another clone, use the published branch and normal local build instructions.

| Commit | Result |
| --- | --- |
| `a708ac5` | Guarded native NPC body/velocity diagnosis; early update requests queued but did not move it |
| `59e668e` | Consumer-entry native velocity reapplication; two bounded forward/reverse/rest runs passed |
| `2c65804` | A separate game-free ENet peer drives the native NPC, with expiry stops and same-epoch recovery |
| `2bc6e7d` | Capture, encode, interpolate and apply the original Link's final body pose |
| `c4d6345` | Observe and replicate equipped identities; prepare selected models privately |
| `62d1ace` | Bound original equipment actor/model observations and prepare selected models |
| `3fc1151` | Anchor the separately armed figure to a copied native NPC origin |
| `53d5067` | Suppress and restore that NPC's original model through its native controller |
| `a41fefc` | Retire the owned NPC in its verified native worker context with resource/allocator correlation |
| `d164cab` | Reliable incompatibility rejection and isolated test-client endpoints; hosted co-op and content checks passed |
| `1c1d507` | Two native lifecycles with separate retained requests and per-probe snapshots; hosted co-op/content checks passed |

The current retirement slice adds mode 9 and a complete copied-save creation/movement/visibility/removal
diagnostic. Its evidence and limitations below supersede earlier statements that native removal is unverified;
repeatable lifecycle and general native operations remain unverified.

The current integration targets port 0.4.0 and game 1.4.3. It is experimental; the preserved port 0.3.11 build
remains available. Reuse the installed ExeFS/indexed RomFS, generated sources, shader preparation and existing
objects. Do not repeat extraction, full generation or shader warm-up merely to resume.

## What actually works

- ENet worker and protocol v5; explicit serialization, identities/freshness, reliable notices and 30 Hz poses.
- Final body-pose slice: a copied 1.4.3 palette, 58 bounded actor-space bone rotations and two root translations,
  explicit 476-byte encoding, interpolation and application to the figure's mapped skeleton. Face/hair children
  retain local animation; unsupported assets keep clip fallback. Equipment placement remains absent.
- Optional base weapon/shield/bow identities from bounded, double-read pouch arrays. Protocol v5 uses a
  slot-validated 144-byte extension and clears stale/unavailable equipment. No inventory mutation is added.
- Selective local preparation of one to sixteen equipment models using the pinned MIT converter; the tested
  weapon/shield/bow library is 203,876 bytes. It is private and not yet loaded into rendering profiles.
- An extracted, textured, animated Link figure with black hair; ordinary presence remains separate from the NPC.
- Isolated mode 8 associates that figure with the owned NPC origin and suppresses its original mesh through
  a guarded native controller call; one hide/restore pair passed with native movement and inspected images.
- Isolated mode 9 adds one asynchronous native retirement in the verified guest worker/current-actor context,
  after measured native rest. The same actor's request/queue, resource cleanup and allocator handoff passed.
- One owned native `Npc_Road_001`, created by the isolated authentic weapon-drop experiment.
- Mode 6 (`--native-npc-peer-motion`): a loopback ENet peer supplies horizontal velocities. A one-slot bridge
  checks session/player and remote/local generations. A 200 ms receive-time lease expires even if the worker
  retransmits the same sender sample. Fresh same-epoch samples resume movement; identity changes revoke binding.
- Native calls use the verified actor-update/request-consumer boundaries, with live body/metadata/world and
  code guards, complete CPU/FP restoration, an eight-world-second ceiling and at most 256 calls per hook.
  Incoming position/Y velocity are ignored. At consumption preserve Y from the current native pending request,
  not the older cached body velocity. Physics writes from rendering/network work and teleport remain prohibited.

General native commands still reject mutation. Negotiated capabilities remain presence-only. There is no
human-controlled second Link, complete shared world or completed Phase 2.

## Evidence to retain

The two successful corrected ENet diagnostics ran for 28 world seconds with the optional figure disabled:

| Private run | Producer / consumer calls | Sampled forward / reverse | Diagonal X/Z | Other evidence |
| --- | --- | --- | --- | --- |
| `run-4814e975fd` | 237 / 125 | 2.066 / 2.208 m | 1.039 / 1.073 m | Two three-axis expiry rests, final rest, game/peer exit 0, source-save hashes unchanged |
| `run-39d138c75d` | 234 / 123 | 2.311 / 2.483 m | 0.776 / 0.808 m | Same gates passed; scripted local walking/camera, local horizontal travel 4.230 m |

Distances use sampled segments with transition margins. Full camera/input independence, arbitrary terrain and
human/Internet play are not established by these runs. The first failed ENet run (`run-b3df75e13a`) fed cached Y
back into simulation, caused ascent and hit the stale-update stop. The corrected pending-request Y path passed;
do not remove the stale-update guard to conceal the failure.

Earlier ENet-slice checks: native/adapter suites; 28 diagnostic parser tests; settings documentation;
game-free peer compilation; transport workers at nominal 0/100/200 ms with configured loss/jitter/duplication/
reordering; runtime selftest, cfg, kernel, texture, shader and Vulkan replay probes; staged/full content checks.
Adverse-network transport checks are not native gameplay tests under those impairments. Hosted CI approval
was not verified. No lifter/CPU-header change occurred in the latest movement commits.

Earlier unresolved results remain: exclusive-monitor ABA failures and a full-game shutdown timeout with the
Vulkan validation layer confirmed loaded. A timeout with zero logged errors is not an acceptance pass.

The November 17 body-pose diagnostic ran one copied-save game for 15 world seconds and a separate game-free
ENet echo peer: 388 samples, 387 body poses, 242 changed poses, both exits zero, renderer body-pose application
logged for a 97-entry palette/191-bone figure, and source saves unchanged. Scripted local running/camera and
two attack inputs passed; `Sword_Blunt_Attack_S1` was observed. This proves transport/application of the final
pose, not exact attack fidelity, jumping, equipment, native companion collision or independent human play.
The first attempt started its peer during loading and failed negotiation before the world was available.
The corrected runner starts on the world-clock marker, with a regression test. No loaded validation-layer
or heavy-scene performance acceptance is claimed for this new slice.

Body-slice checks passed: adapter/figure/protocol suites, native probe/audit checks, 29 diagnostic parser tests,
settings documentation, ENet workers at nominal 0/100/200 ms with configured impairment, and current selftest,
configuration, kernel, texture, shader and Vulkan replay probes. Content/diff checks passed. Linux, exact
run/jump/attack pose comparison, equipment and two-PC Internet testing remain unrun for this slice.

The equipment-identity slice then passed a 15-world-second copied-save echo: 394 equipment snapshots with
nonempty equipped identities, 394 body poses, 243 changed poses, both game/peer exits zero and unchanged source
saves. Base weapon/shield/bow names were received; hand/back placement, fused additions and bow-string poses
are not implemented. Item changes and unequip passed synthetic checks; the live equipped identities stayed
constant. One native profile copy sufficed; the shader cache and base figure were reused.

Equipment-slice checks passed: stable/unstable synthetic pouch reads, wire/slot validation, explicit unequip,
discrete identity changes and clearing, both worker directions under the existing 0/100/200 ms impairment
scenarios, four authored BYML/asset-selection tests, 30 diagnostic parser tests, adapter/figure/native probe
suites, settings documentation and all six runtime probes. The selected three-model library was converted
and structurally validated on the user's local content; all generated files remain ignored. No renderer
attachment, inventory transaction, exact attack/jump fidelity, heavy-scene performance or Internet acceptance
is claimed. Linux remains untested. Earlier loaded-validation-layer and ABA limitations remain open.

The native-equipment diagnostic subsequently observed three original model candidates and 81 first-palette
matrices in a 15-world-second copied-save run (`run-680b347778`). All processes exited zero and the source
saves were unchanged. The existing original-reference setter supplies actor identities, but its observed
caller creates a temporary stack reference. Neither nearby position nor matching names establish persistent
exclusive ownership. The bounded search is read-only, opt-in and diagnostic-only; it grants no native capability.
The capped Player-root searches were unproductive. Reuse the original actor/ModelUnit route instead.

The ordinary presence figure still has no terrain collider. Prepared idle geometry measures about 1.763 metres tall,
and no uniform shrink factor was found; runtime size equivalence remains unverified. The echo's default
three-metre X offset preserves source Y and can sink into a slope. A zero-offset 12-world-second audit
(`run-c42b09a872`) passed with 291 body poses and unchanged source saves, but a horse occluded the comparison.
This is a calibration aid, not a scale or collision fix. Native body/feet binding is now the first priority.

Checks for this diagnostic slice: bounded synthetic graph/reference/model lifetime checks, adapter and native
probe/audit suites, 34 report-parser tests, all six runtime probes and full/staged content checks. No lifter or
wire-format change was made. Linux, loaded-layer gameplay, performance and Internet acceptance remain unrun.

The separate mode 7 now publishes the owned native NPC's actor origin to the Link figure. In the controlled
28-world-second run `run-41013c678c`, all 194 submitted origins matched captured native positions exactly;
forward/reverse/diagonal travel, expiry stops, consumer correlation and peer/game exits passed, with unchanged
source saves. The forward segment rose about 0.427 m and reverse descended about 0.437 m on the tested slope.
The figure receives native actor Y without a manual offset; the sampled body translation agreed there too.
The camera/input script moved the local player, placing the companion outside the view for much of that run;
position agreement does not establish visual feet alignment. Original NPC appearance remains and overlaps
the Link figure when visible. This opt-in experiment does not enable normal native commands or gameplay readiness.

Mode 7 requires a distinct copied-profile marker, matching peer/session and local/remote generations, and a
native observation no older than 250 ms. Missing observations hide the figure instead of reusing peer absolute
coordinates. Tests cover marker isolation, actual mode 7 native calls, identity mismatches, retirement, invalid
positions, stale copies and title/loading peer samples. Native removal and reusable creation remain unverified.

The second corrected run (`run-553fbda54a`) retained a stationary local camera after the recorded drop. Its
189 submitted origins also matched exactly, native movement gates and all process exits passed, and source
saves were unchanged. Full-size frames show the black-haired Link superimposed on the original NPC while
the peer is active, then only the NPC after peer shutdown. Tall grass obscures the feet. This confirms the
visible origin association and presentation clearing, while also demonstrating the unresolved native mesh
replacement and retirement requirements; it is not a clean two-Link appearance or terrain-contact acceptance.

Body-origin slice checks passed: adapter and figure suites, native probe suite, 35 diagnostic report tests,
settings documentation, all six runtime probes and full/staged content checks. Protocol v5 is unchanged.
Linux, loaded-layer gameplay, heavy-scene performance and two-PC Internet acceptance remain unrun.

The visibility slice then identified the original `OneShotSetOnlyModelVisible` getter/setter path, and a
read-only copied-save audit matched the owned NPC controller's actor link and vtable `main+0x3673b58`.
Separate mode 8 passed a 28-world-second run (`run-bca5cca87a`): one native hide and one restore, 6.499937
world seconds hidden across 195 figure samples, 196 exact native-origin submissions, native movement/
expiry/rest/recovery gates, zero process exits and unchanged source saves. Inspected full-size images show
the black-haired Link without the NPC mesh while hidden, followed by the original NPC after peer exit.
The actor itself remains alive. Grass obscures the feet. The automatic report verifies flags and correlation;
it deliberately leaves pixel verification and native retirement false. See the native notes for guards/limits.

Visibility-slice checks passed: adapter/figure/native suites, 36 diagnostic report tests, all six runtime
probes, settings documentation and full/staged content checks. A changed owner/type/epoch, future/stale
publication, initially hidden controller or incompatible getter/setter/update code cannot authorize a hide.
General native capabilities and protocol v5 remain unchanged. No new Internet/performance acceptance.

The November 18 retirement slice passed the complete 32-world-second run `run-29935d2488`: 227 producer
requests, 120 consumer reapplications, forward/reverse/diagonal displacement, two scheduled lease stops and
recovery, 174 exact native-origin submissions, a 5.933282-second model hide/restore pair and one retirement.
The native request at world 25.151521 s followed 31 rest samples spanning 1.031515 s. Actor ID 917/generation 3,
probe 10/request 15 matched the native queue/resource/allocator sequence. Game/peer exits were zero and
source-save hashes were unchanged. Images show the black-haired Link, restored NPC and later empty position.
Grass still hides the feet. Tests cover guest task/TLS/worker/code/ownership guards, measured rest, single-shot
rejection, full CPU/FP restoration and no guest reads after a request; 37 diagnostic report tests passed,
alongside native/adapter/figure suites, six runtime probes and content/settings checks.

Retain the failed runs too: `run-ae4482476d` never requested removal because it waited for a fresh velocity
consumer event from an already-idle body; measured rest now handles that case. `run-a820c571be` passed the
native retirement gate but failed overall movement acceptance when an extra receive-lease expiry split its
diagonal segment. The successful repeat changed no code or thresholds. Do not weaken the receive-time lease.
One retirement per fresh process does not prove repeated in-session creation or permission to reuse static
creation arguments/blackboard storage. Check completion/rejection/cancellation ownership before adding reuse.

### Network rejection and hosted CI follow-up (November 18)

The co-op workflow for `a41fefc` failed at the content-incompatibility assertion in the 100 ms impairment
case. Earlier `53d5067` and `3fc1151` runs succeeded. The failed workflow stopped before native retirement
tests; it does not invalidate the separate copied-save evidence above. An unchanged local rerun passed,
then repeated and varied-loss diagnostics motivated stronger endpoint/state evidence.

Two reproducible defects were isolated. The UDP test bridge routed responses to the most recent client,
even when they belonged to an earlier endpoint; a two-client socket fixture failed before the bridge gained
separate upstream sockets. The runtime also reset an incompatible peer with an unacknowledged immediate
disconnect. Deliberately dropping that datagram left the guest negotiating; the new regression failed on
that worker. Rejections now use ENet's acknowledged disconnect, keep the peer for bounded retransmission,
ignore application traffic while closing and preserve incompatibility after completion/timeout. Explicit
configuration or a new connection initializes the state again. No protocol/gameplay capabilities changed.

The strengthened suite checks both peers, retains failure counters, and includes forced first-disconnect loss
for content and old-protocol rejection plus a compatible reconnect. Its proxy endpoint isolation has separate
socket tests. Five-second rejection/application timeouts and the 200 ms native-motion lease were not enlarged.
One later hosted success alone should not be described as exhaustive resolution of every intermittent timing
failure; retain failures and their endpoint diagnostics if they recur. Continue native creation-storage and
repeated actor lifecycle work after the transport checks.

## Reference review on 2026-11-23

| Reference | Verified state | Use and limit |
| --- | --- | --- |
| [arnaldolima1/totk-recomp](https://github.com/arnaldolima1/totk-recomp/blob/7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c/docs/multiplayer.md) | API recheck: main and develop remain `7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c`; latest release remains game-v0.5.2, November 2. No new revision since our November 14 review | MIT. Continue reusing permitted final-pose/equipment presentation research with attribution. The documented experience uses separate worlds/saves and blocks the prologue; room progress display/PvP do not establish our shared campaign or remote native controller |
| [daurosk/totk-recomp-multiplayer](https://github.com/daurosk/totk-recomp-multiplayer) | API recheck: main remains `8695a9bc7a44dd208916ca594ceb4345f3e9a52d`, last push November 9; no releases. The actors and inspected puppets tips are unchanged | Its multiplayer code is GPL: behavior reference only under this repository's rules. Activity in the author's other games is not evidence of new TotK implementation |
| [Daurosk puppets branch](https://github.com/daurosk/totk-recomp-multiplayer/blob/9e9648b968fb7c5165c43d8b34a159fa83a99ca4/docs/puppets-handover.md) | Re-read the same handover: body, local animation and the two-game round remain unfinished | The proposed Player-model pack still lacks verified native-controller/ownership acceptance; no newly completed second-Link implementation found there |
| [Daurosk actors branch](https://github.com/daurosk/totk-recomp-multiplayer/blob/7143114ba2ea6bc9ca8eea81b1bbcec49b97feac/runtime/net_actors_game.c) | Re-read actual code: `g_make_copy` still returns zero, `g_hit` remains unapplied and the adapter targets 1.2.1 | Session ownership, epochs and authoritative interaction tests remain behavioral references. Do not copy GPL code or reuse those addresses for 1.4.3 |
| [LFarhi's demonstration and author comments](https://www.reddit.com/r/decomps/comments/1xpt33w/comment/19s98nqyajgww/) | Demonstration uses two local game instances. The author says the mod changes ARM code with few changes to the recomp fork. No public TotK implementation/release was verified in this review | Useful native-hook/mod architecture lead, not inspectable cloning code. The November 22 news story links the earlier November demonstration; publication date alone is not a new technical milestone |

Discovery also found [firefloc's server image](https://github.com/firefloc/totk-online-multiplayer-amp-image)
and [airnod's Optimizer compatibility patch](https://github.com/airnod/totk-optimizer-online-fix). Their source
describes server packaging and an emulator-mod compatibility fix, respectively, not a new native recomp
character implementation. They do not supply the missing actor lifecycle/controller route.

GitHub metadata, branches, releases and targeted source were checked rather than relying on README claims.
Repository discovery included forks: the broad README query had 307 results and only its first 100 ranked
results were inspected. Initial unauthenticated search was rate-limited; authenticated public-repository
search succeeded. Reddit's submitted-post JSON was blocked. This is a bounded public-source review, not a
claim that no private or unindexed project exists. A similarly named GitHub account was not attributed to
LFarhi without an author-provided link. No external implementation was copied and no feature work resumed.

Our priority remains the independent native companion and repeatable lifecycle. The existing permissive
render/pose extraction should be extended for gear/action fidelity rather than rebuilt. No inspected update
provides a verified drop-in 1.4.3 Player clone, shared enemy authority or prologue-capable co-op campaign.

## Ordered work for the next session

1. **Complete native lifecycle and ground-contact acceptance.** Ordinary presence has no collider; mode 7 follows
   the validated NPC's native origin, and mode 8 now suppresses/restores only that NPC's original model through
   the inspected native controller API. Retain its bounded publication lease, identity/code guards and restore
   fallback. Mode 9 now passes one native retirement with resource/allocator correlation.
   Mode 10 also passes two native pulse/removal cycles in the same world using separately retained slots.
   Mode 11 now passes one connection-driven creation/movement/retirement without an inventory drop.
   Next verify a second peer join with fresh identities after complete native cleanup, retaining distinct
   storage until reuse/cancellation ownership is established. Then test disconnect/load/reconnect and
   unobstructed feet on flat ground, slopes and steps. The user reported
   apparent small size and sinking in grass: the diagnostic echo moves three metres along X while retaining
   the source Y, and the synthetic bot also has no terrain query. Confirm the actor-origin/feet relationship
   on flat ground, slopes and steps, extending the new copied-origin association through verified engine
   operations. Preserve the tested native movement guards and original camera/input.
   Evaluate a Player-derived puppet where its ownership can be verified; do not copy Player singleton references.
   Safe repeated creation/removal across scene changes/reconnect is part of this contract. Use
   `--pose-echo-offset 0` only for origin calibration, not as a ground-contact or physics acceptance pass.
2. **Reuse the original equipment actors and matrices.** `coop_gear_probe.c` now observes the verified original
   actor-reference setter through `coop_adapter_actor_bind`, deduplicates native actor/metadata IDs and searches
   only their bounded ModelUnit references for exact prepared model names. Three native models and 81 first
   palette matrices were observed. Exclusive ownership remains unverified; the recorded setter can refer to a
   temporary stack object. Validate a persistent owner relation and hand/back transforms before binding.
   Broad Player graph searches were capped and unproductive; do not expand them or restart a full-heap scan.
3. **Integrate validated body/pose/equipment data into rendering.** Reuse `coop_body.c/.h`, `coop_equipment.c/.h`,
   the selected LNKA2 library, native matrices and the original animation data. The renderer still has no gear
   model cache or verified native attachment binding. Keep native/render ownership separate and retire GPU
   resources safely. Account for malformed data, freshness, world changes, unequipping and clearing optional
   fields. Protocol v5 states are 152 bytes base, 628 with body, 296 with identities, or 772 with both (896-byte
   ceiling). Animated attachment palettes require an explicit size/fragmentation design. Never transmit pointers
   or raw C structures. Retain permissive attribution; no base asset/animation conversion restart is needed.
4. **Demonstrate original movement and attack poses.** Script the real local Link running, jumping and performing
   a basic weapon attack, then reproduce its captured pose/equipment on the remote representation. A deterministic
   game-free peer can help before a human/two-PC run. Clip-name agreement alone does not prove blended pose or
   attack fidelity. Keep visual acceptance separate from native gameplay acceptance.
5. **Prove one real cooperative combat outcome.** Inspect the MIT hit-hook research as a starting point, then
   verify the native enemy damage route, stable enemy/attack IDs, host authority and deduplication. The existing
   local-Link PvP damage hook is not an enemy-combat adapter. Animation, a health-memory write or a notification
   alone cannot satisfy this gate. Shared items, projectiles and abilities follow their own authority contracts.
6. **Complete the Phase 2 lifecycle and Internet gates**, then proceed through campaign stages in `coop.md`.
   Two actual PCs, a private VPN and a 30-minute session with reconnect/save/reload are still required.

These steps reuse the original game's behavior. The native body/lifecycle and Internet gates remain mandatory
for calling the result a playable companion. Ground contact now precedes further visual equipment work.
Report each result at its actual level. Neither successful rendering nor a native NPC stream completes Phase 2.

## Working constraints

Read `AGENTS.md` and the development guide. All handwritten code/docs/commit messages are English. Keep game
data, derived source, binaries, assets, screenshots and saves ignored. Never edit generated C or `refs/`.
Retain permissive source headers and notices; GPL is behavior-only. Before a commit run staged content checks
and the normal hook. Reviewed source publication to the existing fork branch is authorized; do not force-push
or push upstream. No PR approval or hosted CI result should be invented.

Keep at least 25 GiB free. Development storage was cleaned and inactive outputs archived; reuse existing packed
shader caches and incremental objects. Retain the seed and only useful recent copied profiles, with evidence
separate. Free space changes independently; measure it before large jobs. Use one game instance, an offline seed
copy, background scripted input and only owned child PIDs. Do not overwrite the original executable or copy
active saves. Exact local paths, diagnostic commands and original executable hash are in the ignored
`build/coop-v143/NEXT_SESSION.md` of the active source worktree.
