# Co-op development guide

This is an experimental TotK 1.4.3 prototype on Windows. It provides ENet presence sessions, an optional
animated Link figure and isolated native weapon/NPC experiments. It does not provide a playable second Link
or a cooperative campaign. Native session capabilities remain presence-only.

Start with [the public development plan](coop-phase2.md) for current status and the next milestone.
[coop.md](coop.md) defines the intended campaign. [Native research notes](coop-native-research.md) preserve
verified engine paths and their limitations. This guide covers building and reproducing checks.
The public plan is authoritative for resuming development; private notes under ignored `build/` are supplementary.

## Implemented behavior

| Layer | Implemented | Limit |
| --- | --- | --- |
| Build | Separate runtime/executable folders, verified 1.4.3 modules, explicit paths, isolated profiles | Each participant builds locally from their own content |
| Session | ENet 1.3.18 worker, direct VPN IPv4, reliable labels and 30 Hz presence | Labels are not gameplay transactions; Internet acceptance is pending |
| Protocol | Version 5, explicit serialization, game/content checks, session/player identities, freshness and deduplication | Older peers must rebuild; no gameplay-command decoder |
| Pose | Position, velocity, yaw, optional unit quaternion, FSKA clip/frame and final 58-bone body pose | No native animation controller |
| Equipped identities | Optional base weapon, shield and bow actor names, read from validated pouch arrays and carried in copied snapshots | No item ownership, native attachment transforms, fused additions or gear rendering |
| Native gear research | Opt-in original actor-reference observation and bounded ModelUnit discovery; copied first model matrices for three equipped base actors | No exclusive ownership, persistent attachment reference, rendering or mutation capability |
| Presentation | Interpolated animated Link, black hair, scene depth, lighting and shadows; silhouette fallback | No native body, collision, input, inventory or combat |
| Native diagnostics | Scoped request/task/actor/resource/reference/retirement observations | Observation does not establish an unrestricted calling contract |
| Native experiment | One additional weapon with borrowed or independently prepared arguments; observed fall and pickup retirement | Copied-profile, one-shot probe triggered by an authentic weapon drop |
| Native NPC movement | Owned humanoid and bounded forward/reverse/stop pulses through a verified native request-consumer entry | Fixed synthetic pulse; Link binding and removal API remain unverified |
| Native ENet diagnostic | One scoped NPC consumes a loopback peer's leased horizontal velocities and stops/restarts across publication gaps | Scripted peer; no human/Internet, Link binding or complete lifecycle acceptance |
| Native-origin figure diagnostic | Separately armed mode 7 draws Link at the scoped NPC's copied actor origin; two runs passed capture/submission agreement and native movement checks | Original NPC mesh remains visible; no complete appearance replacement, terrain/feet acceptance, retirement or human control |
| Native appearance diagnostic | Mode 8 hides the owned NPC model through its native controller API while publishing Link, then restores it; images and movement gates passed | One controlled hide/restore pair; no persistent model-state authority, native retirement or human control |
| Native retirement diagnostic | Mode 9 requests removal after measured rest in a verified guest worker context; one complete copied-save creation/movement/visibility/cleanup run passed | One request per process; no creation-storage reuse, repeated in-session lifecycle, reconnect or human control |

State packets are 152 bytes without optional body/equipment data, 628 with the body, 296 with equipment
identities, and 772 with both (896-byte protocol ceiling; no larger fragmented equipment-pose packet).
The body adds 58 signed little-endian int16 quaternions and two three-axis translations in millimetres,
476 bytes total. Each optional field has an explicit presence flag. Malformed/nonfinite transforms,
non-unit quaternions, out-of-range translations and noncanonical strings are rejected. Body poses require
actor rotation. Stale observations clear optional data; a missing body in an interpolation bracket clears
the earlier skeleton. Quaternion blending uses the shortest path. Clip changes and loop restarts hold the
earlier frame until the next sample. Equipment placement and character audio remain deferred.

Equipment adds three zero-padded 48-byte ASCII actor names. Names are validated by slot; weapon names cannot
occupy the shield or bow slot. Explicit empty names mean unequipped, while a missing flag means unavailable
observation. Changes are discrete; interpolation, stale-observation handling, generation changes and disconnect
clear old optional identities. A second pouch read and descriptor/root rechecks reject unstable snapshots.
Hash-map lookups have a 64-probe bound. Guest reads occur only in the observer: no render/network memory search,
heap scan, guest mutation or inventory transaction is added.

The guest observer copies the 1.4.3 final skinning palette through the pinned MIT reference's model path,
validates transforms and the render-origin proximity, and rechecks model links, actor identity and transform.
The render-origin search remains heuristic. Rendering consumes copies and never reads/writes guest actors.
Supported figures apply the transmitted body chains while unmapped face/hair children retain their local
animation. Older assets without palette mapping keep clip-based fallback. Native capabilities remain unchanged.

UI/rendering consume snapshots. Guest observations run before the blocking scope in
`runtime/nvn_api_obj.c` `nvnQueuePresentTexture`; this is not a verified mutation phase. The ordinary native
command queue rejects commands, and teleport remains disabled. Raw scene pointers and the current player-origin
heuristic are not stable world identities. A negotiated connection cannot enable native readiness by itself.

## Build and launch

Use the toolchain in [building.md](building.md): Python 3.12 in `.venv`, MSYS2 UCRT64 Clang/Ninja, and your
own indexed 1.4.3 ExeFS/RomFS installation. Python 3.14 in `.venv-py314` supplies zstd for asset preparation.

```powershell
.venv/Scripts/python.exe tools/build_coop.py --game-dir "<installed game directory>" --jobs 4
```

The builder verifies module hashes and writes below `build/coop-v143/`. Generated C, runtime and executable
outputs stay separate. An input/generator fingerprint avoids unnecessary regeneration; Ninja tracks source/header
changes. The builder runs `--selftest` and `--probe-cfg`, then packages `game/totk-coop.exe` and its manifest.
The input installation must not overlap the output directory.

Packaging creates `start-host.bat`, `start-client.bat` and `start-bot.bat` with separate profiles. Client asks for
the host's VPN IPv4 address; UDP port 7777 is the default. Host/client profiles start fresh. Do not replace an
original executable or use an original campaign as a cooperative profile. Connection/presence is available;
shared pause, progression and native companion control remain disabled.

`--package-only` probes/packages an existing build; it does not incorporate newer C or shader edits. Never
publish or send the build folder to another participant: the executable contains game-derived code.

## Prepare the optional Link figure

The conversion, pose and rendering code is adapted from the pinned MIT reference recorded in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). It reads the user's own assets; no model is distributed.

Fetch pinned references using `tools/fetch_refs.sh`, then use a .NET SDK and Python 3.14:

```powershell
.venv/Scripts/python.exe tools/build_mcsharp.py --dotnet "<SDK dotnet.exe>"
.venv-py314/Scripts/python.exe tools/prepare_coop_figure.py --romfs "<indexed RomFS directory>" --mcsharp "build/tools/mcsharp/c837ee41217fd5b330ea31cc21448cf4985320f8/bin/mcsharp-cli.exe"
.venv/Scripts/python.exe tools/build_coop.py --game-dir "<installed game directory>" --package-only
```

Pillow is needed for texture resizing. McSharp builds an ignored copy of the pinned source, leaving `refs/`
read-only. Conversion outputs are restricted to `build/` or `generated/`. The default figure is
`build/coop-v143/assets/link-figure.bin`, with a SHA-256 manifest. Packaging and diagnostics install the immutable
model using a hardlink on the same volume, with a copy fallback. Preparation replaces the source atomically;
existing profiles retain their previous model snapshot. Writable saves are always independent copies.
Rebuild normally before packaging if runtime/shader source changed.

The figure uses basic idle/walk/run clips, or a received captured clip/frame when available. The black hair tint
changes only the figure's hair material. Missing local/peer publication clears the figure; stale publication
expires after 500 ms. Every draw command must pass through the asynchronous Vulkan recorder. The figure uses
recorded viewport/scissor/vertex-buffer operations, invalidates replay state after its passes and releases GPU
resources before VMA. It remains separate from the native weapon experiment.

For the 0.4.0 integration, co-op replay chunks record in order because the figure's camera, shadows and tile
state are shared. A submission snapshots whether co-op is enabled before workers run. The normal non-co-op
renderer retains upstream parallel recording. Test both ordinary replay and multiple workers before accepting
this integration; no parallel co-op performance improvement is claimed.

## Keep development storage bounded

Reuse the installed ExeFS and indexed RomFS through explicit paths instead of extracting them for each build.
Keep the working baseline and one integration candidate. In the current constrained workspace, stop before
starting another large job if less than 25 GiB is free. Incremental builds reuse generated inputs and objects.

Maintain a local cleanup inventory of superseded installer tests, build objects, shader caches, copied test
profiles and diagnostic captures. At the end of development, retain source and the chosen runnable build, then
review and remove expendable artifacts. Folder totals can count hardlinked assets more than once: deleting
one name may recover no blocks until the last link is removed. Never include original game inputs, keys or
original saves in cleanup, and never share writable save files through hardlinks.

Retain the offline seed and at most two useful copied diagnostic profiles; retain reports, logs and selected
images separately. Do not rebuild full installer fixtures or restore archived test outputs merely to resume.
Existing co-op shader packs are directly readable; no loose-file expansion or shader preparation is needed.

## Run an isolated diagnostic

Stop existing game instances and use an offline test profile containing a `save` directory:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --seconds 5
```

The runner verifies the packaged executable hash, copies/verifies the save and account identity into a new
`build/coop-v143/diagnostics/run-*/profile`, then starts one background instance. It refuses to run beside an
existing game. Source saves are hashed before/after; on timeout only its own child is stopped. Logs, reports,
screenshots and optional frame series remain ignored. Never copy an actively written save.

Choose a scenario and requirements:

| Option | Required evidence |
| --- | --- |
| `--scenario controls` | Timed walking, camera input and two attack inputs; horizontal displacement during walking, not loading settlement |
| `--require-animation` | Correlated local rotation and advancing native animation frames |
| `--require-figure` | Model loaded and submitted, without logged Vulkan validation errors; inspect images separately |
| `--without-figure` | Omit the optional asset for a rendering baseline; incompatible with `--require-figure` |
| `--scenario reload --input-script "<script>"` | Old player cleanup, later generation and at least two matched constructions |
| `--scenario object --input-script "<script>"` | One weapon's initialization, removal request, queue and cleanup in order |
| `--probe-name "<Weapon_ name>"` | Require that exact name while retaining distinct identities for same-named actors |
| `--require-allocator --require-resource` | The same retired probe's allocator handoff and resource correlation through cleanup |
| `--shots 2` | Frame series at two-world-second intervals, at most 64 images |

Controls default to 15 world seconds, idle to 5, object to 24 and reload to 45. Menu navigation is profile-specific;
object/reload scenarios require an explicit normal-input script. A changed generation, a menu press or return
from title alone does not prove actor recreation. See [controls.md](controls.md) for `input_script` syntax.

For a local visual/control check:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --scenario controls --require-animation --require-figure --shots 2
```

For final-body capture -> ENet -> interpolation -> rendering, using one game and a game-free echo peer:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --pose-echo --scenario controls --require-animation --require-figure --seconds 15 --shots 3
```

Add `--require-equipment` to require at least ten received equipment snapshots with an equipped item.
The `equipment_echo` report separately leaves `placement_verified` and `inventory_replication_verified` false.
Synthetic checks cover item changes/unequip; a steady live echo does not prove those interactions in the game.

For a scale/origin comparison, `--pose-echo-offset 0` removes the synthetic side offset. The default echo adds
three metres along world X and preserves the sender's Y: it has no destination ground query. On slopes the
test figure can intersect terrain/grass or float. The visual figure has no collider and remains separate from
the native NPC. A matching sampled origin does not establish ground contact or native physics. This option
only changes the game-free diagnostic peer; it does not move the local Link or add a scale correction.

The peer starts after the world-clock marker, echoes fresh captured samples three metres along X and never
creates a native actor. The runner requires at least ten body samples, changing bones, renderer application,
both successful exits and unchanged source saves. This gate proves the copied-pose path, not jump/attack
fidelity, independent human input, equipment, collision or cooperative combat. `--pose-echo` is mutually
exclusive with native creation/movement options and requires the figure. Diagnostic results and images stay private.

## Prepare selected equipment assets

Ground contact and native body binding now take priority over additional equipment appearance work; see
`docs/coop-next-session.md`. The native-gear probe below supplies research evidence for later attachment binding.

`tools/prepare_coop_gear.py` prepares only the requested one to sixteen base actors, reusing the pinned MIT
BFRES/texture converter and a small attributed BYML reader. It avoids converting all armor, the base Link,
animations or shader caches. Model aliases in the actor's ModelInfo are retained. For example:

```powershell
.venv-py314/Scripts/python.exe tools/prepare_coop_gear.py --romfs "<indexed RomFS directory>" --mcsharp "<mcsharp-cli.exe>" --actor Weapon_Sword_103 --actor Weapon_Shield_005 --actor Weapon_Bow_004
```

The default private output is `build/coop-v143/assets/link-gear.bin` (LNKA2) with a hash manifest. Work paths
and outputs must remain below ignored `build/` or `generated/`; at least 25 GiB free is required before work.
Only requested models are decoded. This library is not installed into live profiles or drawn yet. Native
hand/back anchors, their poses, a bounded rendering asset cache, bow-string deformation and fused additions
remain separate gates. Never distribute the library or decoder outputs.

The bot follows a synthetic trajectory and estimates height from the local player. It has no terrain collision.
A successful local-reader check, pose packet or submitted draw does not prove a playable remote character.

## Inspect original equipment transforms

Add `--equipment-graph` to a timed diagnostic of at least 12 world seconds after preparing at most one model
per equipment slot. This is mutually exclusive with native mutation experiments. The runner verifies the private
library hash and writes `coop-gear-probe.tsv` only into its isolated profile. Normal untimed launches cannot arm it.
The observer bounds Player graph work to 2,048 nodes, depth six and sixteen node expansions per tick, with branch
quotas. It also records up to 64 distinct actor/metadata identities at the existing original reference-setter
hook and searches their ModelUnit descendants (64 nodes per actor, depth three, a shared sixteen-node budget
per 500 ms sample, at most four expansions for one actor). The log is bounded; no full-heap search is performed.

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --pose-echo --require-equipment --equipment-graph --scenario controls --require-animation --require-figure --seconds 15 --shots 3
```

`equipment_graph.search_completed` means the bounded diagnostic ran. Its separate native model/pose records
do not enable ownership, rendering, collision or gameplay. Player/world/equipment identity loss revokes the
probe; changed metadata IDs and changed model paths reject reused storage. Native reference setters can use
temporary stack references, so reference liveness is reported separately from actor identity. First model
matrices remain in each model's render-origin coordinates; no native hand/back binding or bow-string palette
is claimed. No guest actor is created, moved or destroyed by this diagnostic.

## Explicit native weapon experiments

Ordinary diagnostics explicitly disable native creation, including an inherited environment setting. The options
below write distinct opt-in markers into the verified copy, require a timed 1.4.3 run and leave session capabilities
disabled. Both use the authentic `Weapon_Sword_101` drop request as their scheduling trigger after six world seconds.

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --scenario object --input-script "<drop and collect script>" --probe-name Weapon_Sword_101 --native-clone-weapon --require-spawn-retirement
```

`--native-clone-weapon` borrows the original synchronous argument, with a null watcher. Instead, use
`--native-owned-weapon` for process-lifetime argument/name/empty-blackboard storage with zero inherited actor
dependencies, identity rotation and unit scale. The owned origin is two metres higher and two metres along world X.
These modes are mutually exclusive and each attempts only one request per process. They do not provide arbitrary
spawning, destination validation, production cancellation or reusable request storage.

A strict owned-argument run is:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --scenario object --input-script "<owned drop and collect script>" --probe-name Weapon_Sword_101 --native-owned-weapon --require-spawn-fall --require-spawn-retirement --without-figure --seconds 30
```

The script must allow space to collect the injected weapon; picking up the original first can fill the inventory.
`--require-spawn-retirement` requires the injected actor's own resource/allocator-correlated retirement, not the
original weapon's. `--require-spawn-fall` requires owned mode, a matching initial origin, several gradual downward
steps and later positional rest. Teleports, mixed identities and missing rest cannot satisfy it. Observed descent
and rest do not establish humanoid collision behavior or a general movement API. No host destruction function is
called: normal pickup initiates retirement. Use the controlled outdoor scenario, not arbitrary destinations.

## Interpret results

The optional `--native-owned-npc` experiment requests exactly Npc_Road_001 using the same verified creation ABI
and a separate NPC-only marker. Use `--scenario idle`, at least 15 world seconds and a recorded drop script that
closes the inventory without attempting to pick up or talk to the NPC. For example:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --native-owned-npc --input-script "<recorded drop script>" --seconds 20 --without-figure
```

This is a one-shot humanoid creation diagnostic. It has no remote movement, Link model binding or removal API;
the NPC retains engine behavior. Fall and retirement requirements remain weapon-only. The first NPC run
initialized and rendered a real humanoid with the optional figure disabled, while preserving source-save hashes.
An initialized NPC is not a playable second Link.

For a separately gated native velocity experiment:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --native-npc-motion --input-script "<recorded drop script>" --seconds 20 --without-figure
```

This creates the same owned NPC, validates its live metadata/world/body links, waits for a later native actor
update and requests forward/reverse/stop velocity through the inspected 1.4.3 engine entry. It preserves
vertical velocity and CPU/FP state, limits requests to 96 and uses its own `isolated-npc-velocity-v1` marker.
The creation-only marker cannot arm movement. Ordinary diagnostics explicitly set mode zero.

Mode 4 controlled runs **fail this diagnostic**: requests enter the native queue, but neither the actor nor
the observed body travels in the requested directions. This is a reproducible movement blocker, not a playable
companion. `native_npc_velocity_experiment` requires matching NPC identity/world, ordered bounded requests,
forward and reverse travel, and later rest; queued calls alone cannot pass. Ownership/receiver observations
are reported under `native_npc_physics_observations`. See [native research](coop-native-research.md) for findings.

The separate mode 5 tests reapplication through that same native API immediately before the inspected native
request consumer runs:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --native-npc-consumer-motion --input-script "<recorded drop script>" --seconds 22 --shots 2 --without-figure
```

Use an idle scenario and at least 20 world seconds. The script must trigger the authentic drop and close the
inventory; leave enough time to observe the NPC after the pulse. This mode needs its own
`isolated-npc-consumer-velocity-v1` marker. It retains the 96 actor-update request limit and allows at most 96
consumer reapplications. Each reapplication checks the live body/world, exact current request, verified
consumer/caller hashes and command age of at most 100 ms. CPU and host FP state are restored after each call;
no host write sets a physics transform or request vector.

Two copied-save runs passed actual forward/reverse/rest acceptance: 1.993/1.933 m and 1.931/1.867 m respectively.
Each made 61 consumer reapplications, exited normally and preserved source-save hashes. The first also scripted
local walking/camera input during the pulse; this does not establish the full camera/input independence gate.
`native_consumer_reapply` additionally requires ordered corrections in the same world and command interval.
The NPC still has its own native appearance and behavior. These short synthetic pulses do not verify peer
control, locomotion animation, grounding/collision across terrain, safe removal or a playable second Link.

For the separately armed ENet diagnostic, the runner builds a small game-free peer, starts one copied-profile
host and connects the peer over loopback once the native NPC is ready:

```powershell
.venv/Scripts/python.exe tools/coop_diagnose.py --seed-profile "<offline test profile>" --native-npc-peer-motion --input-script "<recorded drop script>" --seconds 28 --shots 2 --without-figure
```

This mode requires at least 27 world seconds and the `isolated-npc-enet-velocity-v1` marker. The peer uses the
normal protocol/content negotiation and ENet worker. It sends forward velocity, pauses publication, resumes
in reverse, pauses again, sends diagonal velocity and stops. Its repeated old samples during the gaps must not
renew movement. Host observer code copies one peer sample; only the native actor-update/request-consumer hooks
can apply it. Commands expire 200 ms after their local receive timestamp, even if the consumer runs before
the next actor update. Sender clocks supply ordering only. A changed session/player, peer generation or local
world generation revokes that actor's binding. Same-epoch fresh samples can recover after an expiry stop.

Horizontal speed is limited to 2 m/s; incoming vertical velocity and absolute position are ignored. At consumption
the current native request supplies vertical motion, including gravity/ground response, rather than feeding back
the body's older cached vertical velocity. The experiment ends after eight world seconds, with at most 256 actor-update
requests and 256 consumer calls including a final stop opportunity. It neither spawns another actor on reconnect
nor enables ordinary native commands. The report requires bidirectional/diagonal native displacement, two
positional rests during expiry, recovery, final rest, consumer correlation and a successful peer process.
This local scripted peer does not validate another person's PC, Internet play, shared scene identities or
the complete companion lifecycle. Peer output remains in the ignored diagnostic folder beside the game report.

Two 28-world-second runs passed the ENet diagnostic, including the stricter three-axis rest and no-horizontal-
teleport checks. The idle-local run sampled 2.066 m forward, 2.208 m reverse and diagonal displacement
(1.039, 1.073) m on X/Z. The run with scripted local walking/camera input sampled 2.311 m forward, 2.483 m
reverse and (0.776, 0.808) m diagonally; local horizontal travel during world seconds 15-18 was 4.230 m.
Both rested during each publication gap and after the final stop, exited normally and preserved source-save
hashes. These sampled segment distances exclude transition margins. Full camera/input independence and varied
terrain behavior are still acceptance gates, not conclusions from the input script alone.

### Bind the diagnostic figure to the native origin

Add `--native-npc-figure` to the ENet command above and omit `--without-figure`. This separate mode 7 requires
its own `isolated-npc-body-figure-v1` marker; the mode 6 marker cannot arm it. It retains the same native
creation and movement restrictions and requires the prepared figure asset. The original NPC appearance is
retained, so this is an origin-binding experiment with overlapping models, not a completed appearance replacement.

`coop_adapter.c` `npc_figure_observe` copies the owned NPC's actor origin, body translation and velocity after
validating live body links, metadata ID, retirement stage and local generation. It rechecks identity after the
reads. The actor origin drives the figure; the body transform origin is recorded for comparison, never converted into feet
using a guessed height. No scale, terrain query or physics write is added to rendering.

Only a matching negotiated session/player/remote generation may publish that copy. The UI requires the local
generation to match and the observation to be at most 250 ms old. A missing/stale observation hides the figure
instead of falling back to the test peer's arbitrary coordinates. Velocity expiry still stops the body under
the existing 200 ms lease. Rendering receives copied values and no guest pointers. This diagnostic uses clip
fallback driven by native horizontal velocity; it does not establish Player's original action/controller behavior.

The `native_body_figure` report compares submitted figure origins to the separately logged native captures by
timestamp, generation and actor ID. At least ten ordered submissions must agree within 0.1 mm. Its appearance
suppression, terrain contact, native retirement and human-peer fields remain false. Disappearing presentation
after disconnect does not prove native actor removal. Check both the existing native movement gates and this
origin gate; neither completes the companion lifecycle.

### Suppress and restore the original NPC appearance

Add `--native-npc-visibility` to the body/figure command. It requires `--native-npc-figure` and its ENet option,
and writes the distinct `isolated-npc-native-visibility-v1` marker for mode 8. A mode 7 marker cannot arm this
mutation. Existing speed, receive-time lease, duration and native velocity-call limits remain unchanged.

The original 1.4.3 `OneShotSetOnlyModelVisible` path uses the getter at `main+0x1b9ce0` and setter at
`main+0x1b87b50`. The controller is at `[actor+0x228]+0x280`, with its actor owner at +0x18 and the observed
NPC vtable at `main+0x3673b58`. `coop_adapter_npc_probe_model` validates those links, the exact type and the
existing live actor/body identity before returning a native-hook-only receiver. No pointer enters presentation.

The UI acknowledges copied figure publication through one bounded slot. Only the owned NPC's native update
hook can consume it. Publication expires after 250 ms; a wrong actor/generation, peer revocation or completion
cannot maintain the hide. At most one hide and one restore call are allowed. Initially invisible controllers
are not claimed. Getter, setter and update-entry code hashes, controller identity and CPU/host FP restoration
guard each invocation. Changing the controller or observing a competing visibility value aborts further calls.
It never writes a visibility flag directly from the host or changes physics transforms.

The corrected mode 8 run passed 28 world seconds: the model was hidden for 6.499937 world seconds spanning
195 figure samples, with 196 exact native-origin submissions overall. Native movement, expiry rests/recovery,
normal exits and source-save preservation passed. Full-size images show only the black-haired Link at the
companion position while hidden, followed by the original NPC after the peer exits. Grass still obscures feet.

`native_model_visibility` requires the same actor/generation as the figure, an ordered native hide/restore
pair, matching post-call values, no abort, at least two world seconds and thirty figure samples between calls.
Its image-verification field remains false because the parser does not inspect pixels; manual image evidence
is recorded separately. Native retirement and human-peer fields remain false. A same-value visibility request
from another native subsystem cannot be attributed by this experiment. Persistent model-state authority,
arbitrary scenes/terrain, safe actor removal and repeated lifecycle remain production requirements.
First/last-frame transitions around native visibility propagation have not received separate visual acceptance.

### Request native NPC retirement

Add `--native-npc-retirement` to the visibility command and allow at least 29 world seconds (32 is useful
for observing later frames). Mode 9 requires `isolated-npc-native-retirement-v1`; earlier markers cannot arm it.
It waits for the eight-second native movement experiment to finish and native visibility to be restored.
After the final grace period, it requires at least twelve distinct world-time samples spanning one second:
actor and body origins must remain within one centimetre of their anchors, all cached native velocity
components at most 0.05 m/s, and observation gaps at most 100 ms. Invalid positions/velocity or drift restart
this measurement. An already-idle body may produce no fresh velocity-consumer event; that absence alone
neither proves rest nor authorizes removal. The measured rest gate handles this case.

`coop_retirement.c` `coop_retirement_try` accepts only the owned live NPC body/epoch at the observed native
update caller. It checks GameActor's exact vtable and callback targets, SDK TLS getter binding/code, task type,
worker index and the worker's current actor slot. These are guest scheduling identities read through the
inspected 1.4.3 ABI; a host thread ID is not authorization. Request, queue and update code are independently
guarded too. An incompatible context refuses without issuing a request.

The original request at `main+0x63baa8` receives that actor and reason zero, handles its own native locking,
marks removal pending and enqueues asynchronous cleanup. The host never frees the actor. A request is never
retried, including a rejected result, because native callbacks may have side effects. CPU/host FP state is
restored and the module performs no guest reads after the call. Existing scoped teardown/resource/allocator
observers provide later evidence at their actual native callbacks. Their NPC support is limited to the one
explicitly requested actor name; an unrelated object's cleanup cannot satisfy this gate.
The figure binding and old velocity-consumer work close after any issued request, even if an earlier final
stop request still has no consumer acknowledgement.

`native_npc_retirement` requires one accepted request matching the figure's actor ID and generation, and the
same initialization's ordered request/queue/cleanup with matching resource and allocator handoff. The request
return alone cannot pass. Repeated creation, reconnect, load/unload and request-storage reuse remain separate
requirements. All normal native capability bits remain disabled.

The unchanged-build repeat `run-29935d2488` passed the complete 32-world-second diagnostic: native movement,
lease stops/recovery, 174 exact origin matches, model hide/restore, one retirement with matching cleanup,
resource and allocator observations, normal exits and unchanged source saves. The first attempted retirement
never issued a request; the next passed retirement but failed the full movement check after an extra lease
expiry. These failures and the corrected rest requirement are retained in the native research notes.

Check `diagnostic_passed` and `acceptance_checks`, not just the game's `exit_code`. Unrequested checks evaluate
true as not applicable; they are not evidence those scenarios ran. `native_spawn_experiment` reports creation,
owned arguments, fall/rest and retirement separately. Its creation acceptance alone cannot establish the later
requirements. General companion/gameplay capability fields stay false even after a weapon experiment passes.

When requesting Vulkan validation, also check `vulkan_validation_requested` and
`vulkan_validation_enabled`. The diagnostic requires an explicit layer-enabled log message; a missing layer
cannot pass its validation gate. With the MSYS2 layer installed but not registered system-wide, set
`VK_LAYER_PATH=C:/msys64/ucrt64/bin` and put that directory on PATH before setting `TOTK_VK_VALIDATION=1`.
The runtime logs `validation layer enabled (VK_LAYER_KHRONOS_validation)` only after successful instance creation.

The final normal-rendering owned experiment passed with the figure enabled: 30 world seconds, clean game and
diagnostic exit, source save unchanged, 114 receiver samples, 1.53-metre descent and same-actor retirement/resource/
allocator correlation. A separate figure-free strict run passed with 1.59-metre descent. These are bounded local
weapon tests, not a 30-minute Internet session or a playable second Link. Further evidence and failed experiments
are preserved in [the research notes](coop-native-research.md).

On the preserved 0.3.11 build, full-game shutdown under the optional Vulkan validation layer timed out, including a run without the
figure. Zero logged validation errors does not make those timeouts passes. An isolated validated device probe
passed. The draw portion of the replay probe requires the private shader census, such as
`build/v143/shaders/jobs.json`; it was unavailable during that baseline test. The 0.4.0 candidate has a fresh
census and passed the shader and full replay probes, including four workers. Its isolated memory probe also
passed with validation after correcting outdated texture fixtures. These do not replace the full-game tests.

## Source checks

Run with `.venv` and UCRT64; these synthetic checks need no game, keys, saves or GPU:

```powershell
.venv/Scripts/python.exe tests/coop_check.py --cc C:/msys64/ucrt64/bin/clang.exe --deps C:/msys64/ucrt64/include
.venv/Scripts/python.exe tests/coop_network_check.py --cc C:/msys64/ucrt64/bin/clang.exe
.venv/Scripts/python.exe tests/coop_figure_check.py
.venv/Scripts/python.exe tests/coop_equipment_check.py
.venv/Scripts/python.exe tests/coop_gear_prepare_check.py
.venv/Scripts/python.exe tests/coop_gear_probe_check.py
.venv/Scripts/python.exe tests/coop_native_audit_check.py
.venv/Scripts/python.exe tests/coop_native_probe_check.py
.venv/Scripts/python.exe tests/coop_retirement_check.py
.venv/Scripts/python.exe tools/build_coop_velocity_peer.py
.venv/Scripts/python.exe tests/coop_diagnose_check.py
.venv/Scripts/python.exe tests/settings_doc_check.py
.venv/Scripts/python.exe tools/build_shaders.py --check
.venv/Scripts/python.exe tools/check_content.py
git diff --check
```

The network suite uses two real workers, 50 reliable labels, stale observation handling, incompatibility and
reconnect checks. A local UDP proxy repeats it at nominal 100/200 ms RTT with 5% configured random loss, jitter,
duplication and reordering. Aggregate results stay in `build/tests/coop-network-results.json`; this is not Internet
acceptance. Native/figure tests use authored fixtures, and diagnostic tests reject false-positive acceptance.
The Windows co-op workflow runs synthetic checks; hosted CI evidence requires a push/PR.

Changes to CPU headers or the lifter require the differential checks in [building.md](building.md). Keep native
reports, generated C, executables, copied saves, extracted models and game-derived shaders out of public source.
Our own runtime GLSL and its matching C headers are maintained through `tools/build_shaders.py`. Before committing
an explicit source selection, run `tools/check_content.py --staged`; never bypass the repository hook.
