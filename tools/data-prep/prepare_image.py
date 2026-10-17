#!/usr/bin/env python3
"""Prepare the supported DNMP iOS ARMv7 game image using Python's standard library."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import sys

from macho import MachO


# Exact decrypted ARMv7 slice used to verify the loader's fixed-address patches.
SUPPORTED_SLICE_SHA256 = "00fa5d6861568cb730a337f9a207d7c55739125745f33849533545190381076b"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="Path to your own extracted DukeNukemMP executable")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Destination directory (default: output)")
    args = parser.parse_args()

    try:
        image = MachO(args.binary)
        cpu, subtype = struct.unpack_from("<II", image.d, 4)
        if cpu != 12 or (subtype & 0xFFFFFF) != 9:
            raise ValueError("The executable must contain the supported 32-bit ARMv7 slice.")
        if image.crypt and image.crypt[2]:
            raise ValueError("The executable is marked encrypted. This tool does not decrypt game files.")
        digest = hashlib.sha256(image.d).hexdigest()
        if digest != SUPPORTED_SLICE_SHA256:
            raise ValueError("Unsupported ARMv7 slice SHA256: " + digest + ". Use the exact supported iOS 1.0.11 build.")
        output = args.output_dir / "dnmp_ios.img"
        header = args.output_dir / "imports-preparation.h"
        if output.exists() or header.exists():
            raise ValueError("Output files already exist. Choose a different --output-dir to preserve them.")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            sys.executable, str(Path(__file__).with_name("prelink.py")),
            str(args.binary), str(output), str(header),
        ], check=True)
    except (OSError, ValueError, struct.error, AssertionError, StopIteration, SystemExit,
            subprocess.CalledProcessError) as error:
        print("Preparation failed: " + (str(error) or "Invalid or unsupported Mach-O executable."), file=sys.stderr)
        return 1

    print("Success. Copy dnmp_ios.img and the original app contents to ux0:data/dnmp_ios/.")
    print("The generated imports-preparation.h is not needed on the Vita.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
