#!/usr/bin/env python3
"""Patch 1: the fixed RW1_EDIT.EXE for eXoDOS's Robot Warfare 1 (1999).

RW1-EDITOR 1.0.4 with its crashes and freezes fixed (see README.md): dragging the
mouse to the right edge or deleting certain selections no longer hangs it, Select
all + Copy in a one-line text, Ctrl+Left in an empty text, an empty file, a line
of 255 characters and long lines with TABs no longer crash it; Edit > Copy lets
go of Ctrl, a last line without a line end is kept, and a new text asks for a
name when it is saved. Everything else is the original program; it still needs
Windows.

- eXoDOS\\RoboWar1\\RW1_EDIT.EXE is replaced with the RW1_EDIT.EXE next to this
  script; RW1_EDIT.EXE.orig keeps the original.

usage: python fix_windows.py [--check | --revert] EXO_FOLDER

EXO_FOLDER is eXoDOS's "eXo" folder, the one with eXoDOS, emulators and util
in it. --check shows what would change, --revert undoes it. Only the installed
game is patched: its zip is left alone, so after a reinstall run this again.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL_SHA1 = 'a8eaa3e48dcfc1e0aceb378afb13cbce30c3c873'     # RW1_EDIT.EXE 1.0.4 in eXoDOS
TARGET = Path('eXoDOS') / 'RoboWar1' / 'RW1_EDIT.EXE'


def sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true', help='only show what would change')
    group.add_argument('--revert', action='store_true', help='put the original RW1_EDIT.EXE back')
    ap.add_argument('--force', action='store_true',
                    help='replace an RW1_EDIT.EXE that is neither the original nor the fixed one')
    ap.add_argument('exo', metavar='EXO_FOLDER')
    args = ap.parse_args()

    exo = Path(args.exo)
    if not (exo / 'eXoDOS').is_dir():
        sys.exit(f'{exo} is not eXoDOS\'s "eXo" folder (no eXoDOS in it)')
    fixed = HERE / 'RW1_EDIT.EXE'
    target = exo / TARGET
    orig = target.with_name('RW1_EDIT.EXE.orig')
    if not target.is_file():
        print(f'Robot Warfare 1 is not installed ({TARGET} is missing): nothing to do')
        return 0
    now = sha1(target)
    is_fixed = now == sha1(fixed)
    would = 'would ' if args.check else ''

    if args.revert:
        if not orig.is_file():
            print(f'{TARGET} has no {orig.name}: nothing to undo')
            return 0
        if not is_fixed and not args.force:
            sys.exit(f'{TARGET} is not the fixed RW1_EDIT.EXE any more; left alone (--force restores '
                     f'{orig.name} anyway)')
        print(f'{would}restore {TARGET} from {orig.name}')
        if not args.check:
            shutil.copy2(orig, target)
            orig.unlink()
        return 0

    if is_fixed:
        print(f'{TARGET} is already the fixed one')
        return 0
    if now != ORIGINAL_SHA1 and not args.force:
        sys.exit(f'{TARGET} is not the RW1_EDIT.EXE this patch was made for (sha1 {now}); left alone '
                 f'(--force replaces it anyway)')
    print(f'{would}replace {TARGET} with the fixed one (the original kept as {orig.name})')
    if not args.check:
        if not orig.is_file():
            shutil.copy2(target, orig)
        shutil.copyfile(fixed, target)
    return 0


if __name__ == '__main__':
    sys.exit(main())
