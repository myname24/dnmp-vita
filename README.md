# Duke Nukem: Manhattan Project — PS Vita tester alpha.1

**Status: alpha preparation; no public download has been published yet.**

Experimental port of the original iOS ARMv7 build. This public repository contains the tester instructions and
image-preparation scripts; the VPK is staged in an unpublished draft. The port's runtime source code and development history remain private.
No original game data is included.

This is a compatibility/testing alpha, not a finished release. Earlier builds have been tested on a real Vita,
including levels and the helicopter boss. The new light/full profiling build has passed PC/ARM safety checks;
its profiling overhead and compatibility still need real-device feedback. Sustained 25 FPS combat is not assured.

## Requirements and installation

- A homebrew-enabled PS Vita, VitaShell and a working kubridge.skprx setup (the development baseline uses v0.3.1).
- libshacccg.suprx extracted/installed for vitaGL on your own console.
- Your own supported original iOS 1.0.11 game files, plus a locally prepared dnmp_ios.img from that exact ARMv7 binary.
  The PC/Steam game files are not compatible with this loader.

**Generate your game image locally using [the preparation tools](https://github.com/myname24/dnmp-vita/tree/main/tools/data-prep).** New installations
require this image; extracting an IPA alone is not enough. The tools require Python 3 without additional packages.
Do not obtain or share a prebuilt game image or the original game data through this repository or its issue reports.

1. Back up your existing saves/data before testing. Keep Documents/ and your game configuration.
2. Put the contents of your supported DukeNukemMP.app folder and your locally prepared dnmp_ios.img in
   ux0:data/dnmp_ios/. Keep the original subfolder structure (including duke/, data/ and sys/ where present).
3. Install dnmp-vita-alpha.1.vpk using VitaShell. If upgrading an existing working installation, install the VPK
   only; there is no game-image change in this alpha.
4. Start the game. Menus use the front touchscreen. Use the same graphics settings when comparing performance.

Runtime projects: [kubridge](https://github.com/bythos14/kubridge) and [vitaGL](https://github.com/Rinnegatamante/vitaGL).
This package does not include game assets, the game image or console system modules.

## Data preparation for a fresh installation

1. Use your own supported iOS version 1.0.11 game files. The executable must contain usable, decrypted ARMv7
   code. Other versions and PC/Steam files are not supported by this build.
2. Extract the IPA as a ZIP archive and locate `Payload/DukeNukemMP.app/`.
3. Download the repository ZIP and extract it, or download the three Python files in `tools/data-prep/`.
   Keep them together. Open a terminal in that folder and generate the image, replacing the generic input path:

   Windows PowerShell:
   ```powershell
   py -3 prepare_image.py "C:\path\to\Payload\DukeNukemMP.app\DukeNukemMP" --output-dir output
   ```

   Linux/macOS/WSL:
   ```bash
   python3 prepare_image.py "/path/to/Payload/DukeNukemMP.app/DukeNukemMP" --output-dir output
   ```

   The image is written to `output/dnmp_ios.img`. The wrapper checks the exact supported ARMv7 slice,
   rejects encrypted inputs and preserves existing output files. The converter does not decrypt executables.
   The generated imports header is a preparation output and does not need to be copied to the Vita.
4. Copy the **contents** of `DukeNukemMP.app/` and the generated `dnmp_ios.img` into `ux0:data/dnmp_ios/`.
   Preserve the original filenames and directory structure. Do not add a nested `DukeNukemMP.app/` folder.

   ```text
   ux0:data/dnmp_ios/
   ├── dnmp_ios.img
   ├── DukeNukemMP
   ├── prism3d.ini
   ├── duke/
   ├── data/
   ├── sys/
   └── other original app files
   ```

5. Install the VPK through VitaShell after configuring the runtime requirements above. For an existing working
   installation, install only the new VPK; preserve `Documents/`, your configuration and the existing game image.
6. Launch with `fullprofile.txt` absent for normal testing. After exiting, collect the session folder identified
   by `ux0:data/dnmp_ios/latest_report.txt` as described below.

## Controls

| Input | Action |
| --- | --- |
| D-pad / left stick | Move |
| Cross | Jump |
| R | Attack |
| Circle | Kick |
| L | Pipe bomb |
| Square / Triangle | Previous / next weapon |
| Select | Zoom |
| Start | Pause / back |
| Front touchscreen | Menu selection and touch controls |

## Light profiling is the default

Leave ux0:data/dnmp_ios/fullprofile.txt absent for normal alpha testing.
Light mode records frame-time summaries, slow frames, optimization status and coarse render/audio statistics.
It does not walk the game stack. Reports are prepared in a background thread; the game thread queues bounded
records and never waits for report queue space. No data is uploaded automatically.

Frame summaries include approximate p50/p95/p99 of end-to-end frame cadence, using 1 ms buckets. They include
menus, pauses and loading; tell us which part of your session was actual gameplay. The overflow bucket is explicitly
labelled. Existing low-level counters and graphics diagnostics still have some cost: zero overhead is not claimed.

## Enable full profiling when investigating a problem

1. Create an empty file named fullprofile.txt in ux0:data/dnmp_ios/.
2. Fully close and relaunch the game. The session log must say mode full.
3. Reproduce the problem, then close the game and collect that session's reports.
4. Delete fullprofile.txt and relaunch to return to light mode.

Full mode targets 250 stack samples/second in a background thread below the audio decoder's priority. It also
records detailed hot.txt output and analyzes slow frames in the background. It remains enabled for that launch;
it does not automatically stop after 60 seconds. Capture only the useful reproduction, usually 1–2 minutes.

Full mode enables float-helper caller tracking unless the older nofloatprof.txt override is present. Keep that
file absent for the deepest profiling, or keep it present to retain plain float helpers while collecting stack
samples. Full mode can affect FPS and scheduling; compare normal-play FPS using light mode, not full captures.
Samples identify recorded call sites/stack chains, not the exact running instruction. Target rate is not guaranteed.

## Send a tester report

Each launch writes a separate folder under ux0:data/dnmp_ios/reports/session-.../.
The file ux0:data/dnmp_ios/latest_report.txt identifies the newest folder. Older root-level log.txt/hot.txt files
from earlier builds are not this alpha's reports.

Copy/ZIP the entire relevant session folder after exiting the game. It contains log.txt, stdout.txt, stderr.txt,
and hot.txt. In light mode hot.txt contains a status header, not a detailed profile. Include any Vita crash dump
separately if available. A crash can lose the final buffered messages; absence of a logged error does not rule it out.

Open an issue at https://github.com/myname24/dnmp-vita/issues and include:
- Alpha version and the session folder name, Vita model/firmware, and relevant plugins/clock overrides.
- Episode, level/checkpoint and steps to reproduce; identify pauses and loading periods.
- Whether the problem is a crash, visuals, sound, low FPS or stuttering.
- For bombs/explosions: whether it happens on the first use, on repeated use, or both.
- The session report ZIP and, if useful, a short video with a matching point in the session.

Review reports before posting. Do not attach game files, dnmp_ios.img, saves or private personal information.
Reports stay on your Vita until you manually submit them. Remove old session folders when you no longer need them.

## Known issues and testing priorities

- Heavy fights can remain below 25 FPS. Bomb/explosion stutters and first-use sound/resource pauses remain.
- Loading can be slow. An episode-transition warning was observed in earlier builds even though play continued.
- Full-game, every-boss and every-device compatibility has not been established.
- Test multiple levels, save/load, death/retry, episode transitions and longer sessions.

Three-core vertex work and the existing tested optimizations remain. The unused experimental animation
accumulator cache is disabled by default. Do not change developer optimization switches during a comparison.

## Package verification

VPK SHA256: c3269c489af0288ba3ce534d061d838642af3dfc88b32b7d065bd3086b373174
VPK size: 808945 bytes.

Release attachments contain only the VPK and README. The repository also provides image-preparation scripts.
Private runtime source, symbols, logs and game files are not release assets.
