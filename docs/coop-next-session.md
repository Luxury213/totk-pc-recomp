# Co-op handover and next character milestone

Checkpoint: 2026-11-17. Read this before resuming implementation, then consult
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
- An extracted, textured, animated Link figure with black hair. It remains separate from the native NPC.
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

Last implementation checks: native/adapter suites; 28 diagnostic parser tests; settings documentation;
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

The visible figure still has no terrain collider. Prepared idle geometry measures about 1.763 metres tall,
and no uniform shrink factor was found; runtime size equivalence remains unverified. The echo's default
three-metre X offset preserves source Y and can sink into a slope. A zero-offset 12-world-second audit
(`run-c42b09a872`) passed with 291 body poses and unchanged source saves, but a horse occluded the comparison.
This is a calibration aid, not a scale or collision fix. Native body/feet binding is now the first priority.

Checks for this diagnostic slice: bounded synthetic graph/reference/model lifetime checks, adapter and native
probe/audit suites, 34 report-parser tests, all six runtime probes and full/staged content checks. No lifter or
wire-format change was made. Linux, loaded-layer gameplay, performance and Internet acceptance remain unrun.

## Reference review on 2026-11-14

| Reference | Verified state | Use and limit |
| --- | --- | --- |
| [arnaldolima1/totk-recomp](https://github.com/arnaldolima1/totk-recomp/blob/7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c/docs/multiplayer.md) | Main still equals the pinned `7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c`; API comparison returned identical; latest release checked was game-v0.5.2, November 2 | MIT. More remains usable: final blended skeletal pose, equipment/attachment placement and native local-player hit research. Its separate worlds/saves and PvP do not establish our cooperative campaign |
| [daurosk/totk-recomp-multiplayer](https://github.com/daurosk/totk-recomp-multiplayer) | Main `8695a9bc7a44dd208916ca594ceb4345f3e9a52d`; multiplayer unreleased. Working branches were inspected too | Its new code is GPL-3.0-or-later: behavior reference only under this repository's rules; do not copy it |
| [Daurosk puppets branch](https://github.com/daurosk/totk-recomp-multiplayer/blob/9e9648b968fb7c5165c43d8b34a159fa83a99ca4/docs/puppets-handover.md) | Network smoothing, local position/rotation and name-tag work exist; the latest handover leaves native body, local animation and two-game testing pending | A Player-model pack without control/camera components is proposed, not demonstrated as a complete second Player |
| [Daurosk actors branch](https://github.com/daurosk/totk-recomp-multiplayer/blob/7143114ba2ea6bc9ca8eea81b1bbcec49b97feac/runtime/net_actors_game.c) | `g_make_copy` returns zero; `g_hit` only logs an unapplied hit. Native adapter is guarded to game 1.2.1 | Ownership, epochs, game-thread separation and laboratory cases are useful behavior references. Do not reuse its addresses on 1.4.3 or call it finished combat |
| [LFarhi's updates](https://www.reddit.com/user/LFarhi/comments/) | Author announces upcoming minimal early access through the linked Discord; no inspectable public TotK source repository was verified | Monitor primary updates; a video does not establish the actor class or cloning technique. Some unauthenticated GitHub discovery requests were rate-limited, so the search is not exhaustive |

The source/behavior distinctions are intentional. No GPL implementation was incorporated and no completed
1.4.3 Player-clone implementation was found in the inspected sources.

## Ordered work for the next session

1. **Prioritize native body binding and ground contact.** The visible figure has no collider. The user reported
   apparent small size and sinking in grass: the diagnostic echo moves three metres along X while retaining
   the source Y, and the synthetic bot also has no terrain query. Confirm the actor-origin/feet relationship
   on flat ground, slopes and steps, then associate the visible model with an independently owned native body
   through verified engine operations. Preserve the tested native movement guards and original camera/input.
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
