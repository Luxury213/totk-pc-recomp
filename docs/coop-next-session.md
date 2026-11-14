# Co-op handover and next character milestone

Checkpoint: 2026-11-14. Read this before resuming implementation, then consult
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

The current integration targets port 0.4.0 and game 1.4.3. It is experimental; the preserved port 0.3.11 build
remains available. Reuse the installed ExeFS/indexed RomFS, generated sources, shader preparation and existing
objects. Do not repeat extraction, full generation or shader warm-up merely to resume.

## What actually works

- ENet worker and protocol v3; explicit serialization, identities/freshness, reliable notices and 30 Hz poses.
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

1. **Close the pose gap first.** Compare the pinned MIT reference's `frame_rate.c` `game_player_body`,
   `link_figure.c` `link_body_encode` / `link_figure_pose_body`, and equipment capture with our
   `coop_adapter.c`, `link_figure.c/.h` and `coop_wire.c/.h`. Our figure has palette mapping fields, but no
   exposed body-pose encode/apply API; `CoopSample` currently carries clip/frame, not final bones or equipment.
   Identify the smallest complete capture -> serialization -> receive -> pose application slice. Revalidate
   live 1.4.3 ownership; keep exact permissive attribution. Do not rebuild asset conversion from scratch.
2. **Implement and test a bounded pose/equipment path.** Account explicitly for protocol version/packet limits,
   malformed/nonfinite data, freshness, world changes and clearing stale optional fields. Never transmit pointers
   or raw C structures. Preserve the verified native movement experiment while extending the visual path.
3. **Demonstrate original movement and attack poses.** Script the real local Link running, jumping and performing
   a basic weapon attack, then reproduce its captured pose/equipment on the remote representation. A deterministic
   game-free peer can help before a human/two-PC run. Clip-name agreement alone does not prove blended pose or
   attack fidelity. Keep visual acceptance separate from native gameplay acceptance.
4. **Resolve the native companion contract.** Compare an independently owned remote body with a Player-derived
   puppet/controller if needed. Verify model binding/replacement, safe removal, asynchronous completion and
   repeated creation across load/leave/reconnect. Do not assume a mesh replacement inherits the Player action
   graph, or force a second Player into the local manager. Preserve original local input/camera ownership.
5. **Prove one real cooperative combat outcome.** Inspect the MIT hit-hook research as a starting point, then
   verify the native enemy damage route, stable enemy/attack IDs, host authority and deduplication. The existing
   local-Link PvP damage hook is not an enemy-combat adapter. Animation, a health-memory write or a notification
   alone cannot satisfy this gate. Shared items, projectiles and abilities follow their own authority contracts.
6. **Complete the Phase 2 lifecycle and Internet gates**, then proceed through campaign stages in `coop.md`.
   Two actual PCs, a private VPN and a 30-minute session with reconnect/save/reload are still required.

Steps 1-3 improve original-Link fidelity; steps 4-6 remain mandatory for calling it a playable native companion.
Report each result at its actual level. Neither successful rendering nor a native NPC stream completes Phase 2.

## Working constraints

Read `AGENTS.md` and the development guide. All handwritten code/docs/commit messages are English. Keep game
data, derived source, binaries, assets, screenshots and saves ignored. Never edit generated C or `refs/`.
Retain permissive source headers and notices; GPL is behavior-only. Before a commit run staged content checks
and the normal hook. Reviewed source publication to the existing fork branch is authorized; do not force-push
or push upstream. No PR approval or hosted CI result should be invented.

Keep at least 25 GiB free; roughly 30 GiB remained at this checkpoint. Use one game instance, an offline seed
copy, background scripted input and only owned child PIDs. Do not overwrite the original executable or copy
active saves. Exact local paths, diagnostic commands and original executable hash are in the ignored
`build/coop-v143/NEXT_SESSION.md` of the active source worktree.
