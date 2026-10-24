#!/usr/bin/env python3
"""SHA-256 fingerprint of the raw data behind the 117 tutorial experiment.

Prints one line per file in the format of `shasum -a 256` / `sha256sum`,

    <64 hex digits>  <file name>

followed by a single combined digest: the SHA-256 of exactly those lines
(each ending in a newline). The combined digest therefore pins down the
contents of every file, their names, and their order, and anyone can
recompute it without this script:

    cd ../Data
    shasum -a 256 raw-sp26-gradescope-grades.csv raw-tutorial-assignments.csv \\
        raw-consent.csv raw-pretest-scores.csv | shasum -a 256

(on Linux, sha256sum in place of shasum -a 256). The digest covers the bytes on
disk, so a file re-exported from Gradescope or Google Sheets must be saved
without opening and re-saving it in a spreadsheet program, which can rewrite
numbers, dates and line endings.

By default the four raw files are hashed from --data-dir, in the order above;
passing file paths hashes those instead (in the order given), which is how the
pipeline also fingerprints its outputs. Names are printed as given relative to
--data-dir for the defaults, and as given on the command line otherwise.

Usage:
    python3 hash_raw_data.py [--data-dir DIR] [FILE ...]
    python3 hash_raw_data.py --check EXPECTED_COMBINED_DIGEST
"""

import argparse
import hashlib
import os
import sys

RAW_FILES = ("raw-sp26-gradescope-grades.csv",
             "raw-tutorial-assignments.csv",
             "raw-consent.csv",
             "raw-pretest-scores.csv")


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def manifest(paths, names):
    """The shasum-style lines, one per file."""
    return "".join(f"{file_digest(p)}  {name}\n" for p, name in zip(paths, names))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*",
                        help="files to hash (default: the four raw CSVs)")
    parser.add_argument("--data-dir", default="../Data",
                        help="directory holding the raw CSVs "
                             "(default: %(default)s)")
    parser.add_argument("--check", metavar="DIGEST",
                        help="exit with status 1 unless the combined digest "
                             "equals DIGEST")
    args = parser.parse_args(argv)

    if args.files:
        paths, names = args.files, args.files
    else:
        paths = [os.path.join(args.data_dir, name) for name in RAW_FILES]
        names = list(RAW_FILES)
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        sys.exit(f"not found: {', '.join(missing)}")

    lines = manifest(paths, names)
    combined = hashlib.sha256(lines.encode()).hexdigest()
    print(lines, end="")
    print(f"combined SHA-256: {combined}")

    if args.check:
        if args.check.strip().lower() != combined:
            print(f"MISMATCH: expected {args.check.strip().lower()}")
            return 1
        print("OK: combined digest matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
