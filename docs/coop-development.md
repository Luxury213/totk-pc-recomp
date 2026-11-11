# Co-op development status

The target is a two-player private-VPN cooperative campaign on TotK 1.4.3. The host owns the world and story,
each player has their own inventory/health, ordinary pickups have one winner, and either player's death reloads
the common checkpoint. The final campaign must work from the prologue. Players initially stay in the same area.

## What this build implements

- ENet 1.3.18 at commit `2662c0de09e36f2a2030ccc2c528a3e4c9e8138a`, with original source/headers and MIT licence.
  Transport runs on its own worker with no render/UI tick dependency. Windows and llvm-mingw build paths link Winsock.
- Protocol v2 explicitly serializes little-endian integers and finite floats. It rejects malformed lengths,
  unsupported protocol versions and invalid state. Reliable ordered negotiation/notifications use channel 0;
  sequenced movement uses channel 1 at 30 Hz. This replaces the incompatible native-struct v1 protocol.
- Negotiation checks game version and the combined identity of main/sdk/subsdk0. Each connection has a fresh random
  session nonce and a challenge; profiles retain a random player identity. Old sessions, sender generations,
  sequences and duplicate notification IDs cannot update the current presence state.
- Native gameplay readiness requires both peers' verified actor/world-control capabilities and matching stable scene
  identities. The current adapter advertises presence only. A loaded player observation does not enable gameplay.
- Presentation interpolates a bounded history with a 100 ms delay, takes speed from transmitted velocity and holds
  the last pose when the buffer runs out. It never sends the smoothed pose into physics.
- `runtime/coop_adapter.c` samples the real actor before `nvnQueuePresentTexture` releases its virtual core.
  It records observed lifecycle generations and invalidates stale presence; it does not claim this is the world
  update's safe mutation phase. The render/UI path no longer reads actor memory.
- A bounded queue admits at most 256 diagnostic native requests. Observation rejects expired/stale requests and
  reports the remaining requests as unverified. It never invokes guessed guest functions or writes actor/physics memory.
- Opt-in `coop_trace_guest` captures up to 64 entries of the inspected transform-related functions and the observed
  actor virtual method, with caller/argument and physical host-thread metadata (not a guest scheduling guarantee).
  Captures begin only after a playable actor has been observed: 32 slots are reserved for that player's own method
  and 16 each for the two physics candidates, so title traffic and common body updates cannot exhaust every slot.
  Resolution discovery and co-op tracing use separate profiler
  bits, so disabling tracing preserves the resolution observer.
- A separate opt-in, bounded constructor trace starts before player observation. It retains at most 16,384
  `GameActor` constructor entries and reports only entries whose object pointer matches the observed local player.
  The diagnostic also records the entry count at first playable observation. It does not call the constructor.

The remote silhouette and local bot are diagnostic overlays. Native remote actors, shared pause, combat, inventory,
quest events, checkpoints and cinematic control are **not implemented or enabled**. Losing a peer disconnects its
presence; pausing a real shared simulation remains gated on verified world control.

Notifications use reliable transport but remain labels, not authoritative gameplay events. Only the latest received
label is presented by the UI, with the total received count. The networking code has no gameplay-command decoder.
This prevents a network message from being treated as authorization to mutate the guest.

## Build and launch

Use Python 3.12 in `.venv` and MSYS2 UCRT64 Clang/Ninja. Python 3.14 is reserved for extraction/shader tooling.

```powershell
.venv/Scripts/python.exe tools/build_coop.py --game-dir "<installed game directory>" --jobs 6
```

The builder verifies all 1.4.3 ExeFS hashes, generates C below `build/coop-v143/generated`, builds the runtime archive
and executable in separate folders, and runs `--selftest` and `--probe-cfg`. It always supplies explicit game/version
paths. Outputs must remain below the repository's `build/`; no output may overlap the input installation.

The first build needs time to lift and compile the full guest. An input/generator fingerprint lets subsequent runs
reuse generation; Ninja handles C/header changes. Logs remain in `build/coop-v143/`. `--package-only` probes and
packages an already built executable; it does not incorporate newer source edits.

Successful packaging writes `game/totk-coop.exe`, build metadata and `start-host.bat`, `start-client.bat`,
`start-bot.bat`. Each launcher passes a dedicated profile. Client prompts for the host's VPN IPv4 address; both sides
use UDP port 7777. The default host/client profiles are fresh, independent campaign sandboxes. Old co-op executables
elsewhere are not replaced. Every participant must build locally from their own game content; this folder contains
game-derived code and must not be published or distributed to another player.

For an advanced-save native diagnostic, stop any existing game instance first, then run:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --seconds 5
```

This creates and verifies a separate save copy under `build/coop-v143/diagnostics`, runs one background instance with
recorded title-screen input and bounded native tracing, and records a JSON report, log and screenshot. It compares
source-save hashes afterward. On timeout it stops only its own child. It never launches a second full game beside
an existing instance, stops an existing game, or changes the source profile. A native trace is evidence for further
investigation, not proof of a safe spawn/warp ABI or scheduling phase.

## Validation

```powershell
.venv/Scripts/python.exe tests/coop_check.py --cc C:/msys64/ucrt64/bin/clang.exe --deps C:/msys64/ucrt64/include
.venv/Scripts/python.exe tests/coop_network_check.py
.venv/Scripts/python.exe tests/coop_native_audit_check.py
.venv/Scripts/python.exe tests/settings_doc_check.py
.venv/Scripts/python.exe tools/check_content.py
.venv/Scripts/python.exe tools/check_content.py --staged
git diff --check
```

The adapter harness checks camera/title exclusion, observation loss, actor replacement, bot follow/stay,
trace/profiler isolation, disabled teleport and queue capacity/stale/unverified rejection, while asserting that the
synthetic actor bytes remain unchanged. Protocol checks cover canonical serialization, malformed packets,
compatibility, old sessions/generations, duplicates and native-readiness gating; interpolation checks include angle
wrap and generation reset.

The network harness uses two real ENet workers and production Windows platform threads, locks and file operations.
It checks independent positions, 50 reliable notifications, stale-observer invalidation, disconnect/reconnect with
a new session, incompatible content and corrupt persistent identities. It repeats through a UDP proxy at 100/200 ms
nominal RTT, 5% configured random loss, jitter, duplication and reordering. The test's seed and aggregate impairment
counts are saved in `build/tests/coop-network-results.json`; these are local simulations, not Internet validation.

These checks pass. The isolated 1.4.3 executable also passes `--selftest` (zero failures), `--probe-cfg` and a
selftest without the compiler directory on PATH. The single-instance diagnostic loaded the copied save, observed
the real player, captured 32 physics observations after player detection and a rendered frame, and exited successfully
after five world-clock seconds. It also identified a player vtable method candidate, with no observed invocation
during that idle interval. These are separate findings; the candidate is not a verified movement API.
Both the source test save and the 66 fingerprinted original executable/save files remained
byte-identical. Results are recorded in `build/coop-v143/validation.json` and the referenced diagnostic report.

The first diagnostic attempt timed out on title-screen navigation. The runner now forces background focus handling
and repeats confirmation instead of relying on four fixed button events; the corrected run succeeds. This checks
observation and isolation, not actor creation or a playable multiplayer campaign. No lifter algorithm or generated
C was edited by hand in this work.

The next isolated 1.4.3 diagnostic confirmed the local player's vtable and found a `GameActor` constructor entry
whose object pointer exactly matched the observed player. Its caller resolves to an allocator wrapper, and a
separate static path registers that wrapper as the `GameActor` factory. There were 779 constructor entries before
the first playable observation; the former 64-entry capture filled before reaching the player. The revised audit
reports the matched invocation and its caller without exporting generated bodies. The copied save exited cleanly,
and the source save remained byte-identical. This verifies construction of the existing player object; scene
registration requests, input/camera ownership, destruction requests and a safe world mutation phase remain unknown.

A further read-only trace followed the matched constructor through its allocator wrapper, factory dispatcher and
guarded initialization routine to a caller in the engine's task-processing path. The player's pointer also matched
the independent scene resident-actors list during gameplay. Constructor and presentation observations occurred on
different physical host threads. The audit records the caller chain and the scene-list match without exporting game
code. These observations establish how the existing player is constructed and where it resides; they do not establish
the request ABI, scene ownership, a safe call site, or how to create and remove a second actor.

A targeted indirect-dispatch observer now captures the task descriptor passed to the guarded initializer. One
copied-save 1.4.3 run linked a nonzero descriptor to the existing player's constructor and resident-scene match;
the original save remained byte-identical. The private audit reports the descriptor observation as a count and
does not export the pointer. Static inspection shows the task processor pops and orders descriptors, then calls
the initializer. The producer, complete request format and ownership rules remain unverified. This trace still
does not enable native actor creation or establish a safe world update phase.

Another bounded trace matched the factory's holder call to the existing player. The holder is embedded at task
descriptor `+0xf0`, and the observed virtual target is `main+0xd66bb0` with mode `1`. Static inspection of that
target shows actor metadata setup and an actor virtual call. The private audit reports the matched call and inline
holder relationship without exporting guest pointers or function bodies. The copied-save run exited cleanly and
left the original save unchanged. The resident-list insertion, task producer and destruction request remain open.

## Contributing and review milestones

The ENet session layer, isolated builder, read-only adapter and synthetic regression tests form one reviewable
experimental contribution. They do not need to wait for a complete multiplayer campaign. Keep the mode disabled
by default and describe the contribution as session infrastructure and diagnostics, not playable co-op.

`.github/workflows/coop-tests.yml` runs the synthetic observer, protocol, real ENet workers, network impairment,
native-audit mapping and content/documentation checks on Windows with MSYS2 UCRT64. It uses no game or save files,
keys, renderer or GPU. The workflow has been added; hosted CI results require a push/PR. Local execution of the
same checks is the pre-commit evidence, not a substitute for a future hosted run.

For private engine investigation, map a new diagnostic's scoped observations back to the generated functions:

```powershell
.venv/Scripts/python.exe tools/coop_native_audit.py --diagnostic "<diagnostic report.json>"
```

The audit stays under `build/`, includes the generated-content marker and emits function offsets, caller groups and
direct callee names, never source bodies. It resolves LR to the call instruction and excludes non-executable module
data. It distinguishes a vtable method candidate from an observed invocation. Legacy observations without a player
epoch remain labelled unscoped. Its synthetic test uses invented C and trace fixtures. Keep the private diagnostic
artifacts, generated C, binaries and save copies out of the source commit; describe findings using function names,
offsets and aggregate test results. Follow CONTRIBUTING.md for normal bug reports.

The next separate playable milestone is a native remote actor that can spawn, move and despawn through verified
engine operations while preserving local input/camera ownership. That contribution needs real-game lifecycle
and reconnect tests in addition to the synthetic suite. Shared combat and story should follow that milestone.

## Remaining gate and development order

The first playable milestone still requires a native remote actor with independent camera/input ownership and a
verified world update phase. Trace the engine's actor factory, scheduling, destruction and transform/controller
requests; establish their actual ABI and lifetime/locking contract. Do not replace this investigation with a second
`PlayerLink` allocation, direct position stores or calls from the presentation observer.

Before enabling native capability bits, demonstrate spawn/move/despawn and load/unload/reconnect stress tests with
the remote actor, preserving the local player and camera. Scene identity and world readiness must come from verified
engine state rather than raw pointers or the current origin-position heuristic.

Only after that gate: host-owned enemies and unique pickups; per-player inventory plus common checkpoints; coordinated
travel/physics ownership; then the complete prologue and story/cinematic acceptance suite. The host will advance story
text and skips, while transitions wait for both players. Persistent events need semantic validation, revisions and
transactional recovery; notification delivery is not a substitute. Real Internet acceptance requires the friend's PC
and a 30-minute session with reconnect/save/reload checks.
