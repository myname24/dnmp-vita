# DNMP Vita game-image preparation

These three Python scripts generate `dnmp_ios.img` locally from your own supported iOS executable.
They contain no original game files and do not decrypt encrypted executables.

1. Install Python 3. No extra Python packages or VitaSDK are needed.
2. Download this folder, or download the repository ZIP and extract it. Keep `prepare_image.py`, `prelink.py`
   and `macho.py` together in the same folder.
3. Extract your own iOS 1.0.11 IPA as a ZIP archive. Locate `Payload/DukeNukemMP.app/DukeNukemMP`.
4. Open a terminal in this tools folder and run:

   Windows PowerShell:
   ```powershell
   py -3 prepare_image.py "C:\path\to\Payload\DukeNukemMP.app\DukeNukemMP" --output-dir output
   ```

   Linux/macOS/WSL:
   ```bash
   python3 prepare_image.py "/path/to/Payload/DukeNukemMP.app/DukeNukemMP" --output-dir output
   ```

5. Copy `output/dnmp_ios.img` and the **contents** of `DukeNukemMP.app/` into `ux0:data/dnmp_ios/`.
   Keep the original subfolders; do not nest another `DukeNukemMP.app/` folder. Do not copy the generated
   `imports-preparation.h` to the Vita. Preserve existing saves in `Documents/` when upgrading.
6. Follow the main repository README for runtime requirements, VPK installation and tester reports.

The wrapper rejects encrypted inputs, unsupported architectures, nonmatching ARMv7 slices and existing output
files. Its SHA256 check deliberately accepts only the exact decrypted ARMv7 slice used for this loader's
fixed-address patches. A differently packaged or modified executable may be rejected even if labelled 1.0.11.
Choose a different output folder to generate another image without overwriting existing files.

Never upload your executable, generated image or game data to the repository or issue reports.
