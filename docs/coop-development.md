# Co-op development guide

This is an experimental TotK 1.4.3 prototype on Windows. It provides ENet presence sessions, an optional
animated Link figure and isolated native weapon experiments. It does not provide a playable second Link
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
| Protocol | Version 3, explicit serialization, game/content checks, session/player identities, freshness and deduplication | Older peers must rebuild; no gameplay-command decoder |
| Pose | Position, velocity, yaw, optional unit quaternion and FSKA animation name/frame | No final blended bone palette or native animation controller |
| Presentation | Interpolated animated Link, black hair, scene depth, lighting and shadows; silhouette fallback | No native body, collision, input, inventory or combat |
| Native diagnostics | Scoped request/task/actor/resource/reference/retirement observations | Observation does not establish an unrestricted calling contract |
| Native experiment | One additional weapon with borrowed or independently prepared arguments; observed fall and pickup retirement | Copied-profile, one-shot probe triggered by an authentic weapon drop |

State packets are 152 bytes. Rotation and animation fields have explicit presence flags; malformed/nonfinite
values and noncanonical strings are rejected. Stale observations clear optional pose data. Quaternion blending
uses the shortest path; clip changes and loop restarts hold the earlier frame until the next sample. Equipment,
blended poses and character audio are deferred.

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

The bot follows a synthetic trajectory and estimates height from the local player. It has no terrain collision.
A successful local-reader check, pose packet or submitted draw does not prove a playable remote character.

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

Current controlled runs **fail this diagnostic**: requests enter the native queue, but neither the actor nor
the observed body travels in the requested directions. This is a reproducible movement blocker, not a playable
companion. `native_npc_velocity_experiment` requires matching NPC identity/world, ordered bounded requests,
forward and reverse travel, and later rest; queued calls alone cannot pass. Ownership/receiver observations
are reported under `native_npc_physics_observations`. See [native research](coop-native-research.md) for findings.

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
.venv/Scripts/python.exe tests/coop_native_audit_check.py
.venv/Scripts/python.exe tests/coop_native_probe_check.py
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
