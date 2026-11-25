# Co-op plan: deliver a playable exploration prototype

Updated November 25, 2026. This delivery order supersedes earlier investigation-first and equipment-first
instructions. Phase 2 is still incomplete. The next deliverable is a build the user can control and play.

## First playable target

Two people on separate PCs, connected through the private VPN, walk and run together in one supported outdoor
area. Each controls their original local Link with their own camera. Each game creates one independently owned
remote companion, presents the other player's pose and keeps it physically active when the local Link moves
away within that loaded area. The user can launch, connect and move without a developer input script.

Start with ground exploration and basic idle/run presentation. Use isolated development profiles and the fixed
black-haired Link figure. The first prototype does not promise shared combat, inventory, quests or saves.

## Starting point

- ENet sessions, copied snapshots, original Link poses and bounded native NPC creation/movement/removal exist.
- Two private longer-walk experiments passed all requested bounded gates. The smaller successful version
  preserves the native active-policy branch; it has not been integrated into public builds.
- Public source checkpoint: `20b738680e07111855b5a90018037bcd1a233ec4`. The restored ordinary executable has
  observation only. Movement still has eight-second/256-request limits, activity a private twenty-second
  limit, and creation two retained slots. There is no continuous human-controlled companion yet.
- Each PC's world is currently independent. Shared enemies, items and progression require later authority work.

Use [native research](coop-native-research.md) for evidence and [the handover](coop-next-session.md) to resume.
Use [the development guide](coop-development.md) for build commands. Reuse the current 0.4.0 integration and
1.4.3 content, generated objects, figure and networking code.

## Delivery order

| Delivery | Implementation | Result the user can observe |
| --- | --- | --- |
| 1. Integrate distance activity | Bring the smaller successful policy wrapper into authored runtime code, with explicit v143 build/profile opt-in and verified lifetime/expiry guards | The same long-walk case passes on a reproducible source build; the companion remains active |
| 2. Manual control in one game | Connect keyboard/gamepad input from a lightweight ENet peer to the existing bounded native command path | The user can steer, stop and change the real companion's direction; local Link input/camera remain independent |
| 3. Sustained exploration | Replace the fixed diagnostic timeline with a session-owned movement/activity lifecycle and renewable local receive leases; retain identity, phase and code validation | At least five minutes of manual movement, including separation, stopping and packet silence, without an eight-second cutoff |
| 4. Two-player build | Connect each PC's original Player capture to the other PC's owned companion, with an explicit same-area/origin setup and launch instructions | Two humans explore together for at least fifteen minutes over the private VPN |

Delivery 2 is a manually testable technical preview using one full game and a lightweight controller. Delivery 4
is the first playable multiplayer exploration prototype. A scripted peer or one-way visual echo cannot complete
delivery 4. Match both directions; displaying a pose is insufficient if the companion body stops or drifts away.

**Next session starts with delivery 1, then wires manual input for delivery 2.** Prefer a small executable feature
and a user launch command as the session output. If one cannot be delivered, record the exact failed operation
and the smallest code change needed next. Further investigation must resolve a blocker in these four deliveries.

## Checks attached to each delivery

1. For the activity integration, verify original forwarding, CPU/FP preservation, foreign/stale actor rejection,
   code mismatch, strict opt-in and expiry. Retain the known failed case and compare it with the integrated fix.
2. For manual control, check actual actor/body displacement and visual alignment, native ground contact in the
   chosen area, stop on lost input and continued local camera/input ownership. A controller disconnect revokes
   commands. Repeated old packets cannot renew a lease.
3. For sustained operation, establish a verified lifetime/renewal contract before replacing fixed time budgets.
   Do not simply remove caps, clear opaque flags, spoof worker/TLS ownership or write physics from rendering.
   Stop safely on departure/world change. Either verify reconnect within the supported lifecycle or require a
   clearly documented clean session restart; never duplicate actors or reuse freed request storage.
4. For the two-PC build, check both movement directions, compatible game/content versions, consistent coordinates,
   ground/figure alignment, separation and peer loss. The host must use its own native companion too.

Run checks appropriate to the changed path after implementing it. Add instrumentation only to decide a concrete
failing condition; stop extending it once it answers that question. Re-run wider checks when a change or failure
requires them. Keep failed outcomes visible and keep content/staged checks before commits.

## Prototype acceptance

- A documented local build and host/client launch flow; each user supplies their own game content.
- Both players independently walk/run/stop, see the other and retain their own camera/input for fifteen minutes.
- Remote actor, physical body and displayed figure agree; no reproducible freeze when the local player moves
  away within the tested loaded area. Support is limited to that verified area until transitions are implemented.
- Input/packet silence stops remote motion; disconnect invalidates commands and leaves the remaining game stable.
- Original executables and saves remain intact. Prototype profiles do not claim shared campaign persistence.
- Known limitations are listed in the launch guide. Phase 2 remains open after this exploration prototype.

## Deferred until after this prototype

The intermittent road-NPC carrier appearance is retained as a known visual bug, per the user's priority.
Keep the prepared black-haired Link figure fixed; address carrier visibility across creation/publication gaps,
disconnect and retirement after distance activity/control. Correct a visual/body mismatch earlier if it prevents
the user from steering or testing physical movement.

Jumping, climbing, swimming, equipment placement, shared combat/items, Ultrahand/Recall, region transitions and
story follow this prototype. Original Player behavior and poses remain references; copying Player memory,
camera/input ownership or singleton references does not create a separate player.

The complete Phase 2 still requires robust repeated lifecycle/reconnection, scene load/unload, verified native
execution context, adverse-network checks and two-PC VPN acceptance for thirty minutes with reconnect/save/reload.
The campaign stages and agreed host/world/individual-inventory rules remain in [coop.md](coop.md).

## Work and publication constraints

Use one full game instance during local development; measure memory before two full instances. Reuse incremental
builds and assets, and avoid duplicate installations or generated rebuilds for runtime-only changes. Code,
documentation and commit messages stay English. Publish authored source, tests and dependency notices only;
keep game-derived code, assets, executables, saves and evidence ignored. Follow `AGENTS.md`, keep generated C
and `refs/` unchanged, and run `tools/check_content.py --staged` before a normal source commit.

The existing fork branch is the development publication target. An exploration prototype is an intermediate
milestone; full campaign completion retains the gameplay, persistence, abilities and story gates in the design.
