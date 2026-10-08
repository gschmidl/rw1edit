# rw1edit - RW1-EDITOR for any system

A port of `RW1_EDIT.EXE` 1.0.4 (SHABUN / Luneg S.V., 1999), the Windows 95 editor that comes with
the DOS game **Robot Warfare 1** by Alexander Shabarshin, to Python 3 and Tk. It runs on Windows,
Linux and macOS and works like the original: same cursor movement, same smart Tab and auto-indent,
same colouring of RW1 programs, same file format (CP866 on disk).

Unlike the original it doesn't freeze or crash (dragging the mouse to the right edge, deleting
certain selections and Select all + Copy in a one-line text did), keeps a last line without a line
end, and asks for a name when a new text is saved. It also has what an editor has today: undo and
redo, Ctrl+C/X/V/S/O, Find, a mouse wheel, selections that typing replaces, Shift+click and
double/triple click, a file name on the command line and a bigger window. `--no-fixes` gives the
original, bugs and all (only where it froze or crashed the port stops instead) - see
[NOTES.md](NOTES.md) for both.

Compile (F8) and Run (F9) start the game's DOS programs `RW1_COMP.EXE` and `RW1_DUEL.EXE` in
DOSBox; the Help menu opens the HTML rules in the web browser.

## Requirements

- Python 3.8 or newer with tkinter (on Linux e.g. the `python3-tk` package)
- DOSBox (0.74, Staging, DOSBox-X ...) for Compile and Run

## Use

Put `rw1edit.py` into the game folder (next to `RW1_COMP.EXE`, `RW1_DUEL.EXE` and `HTML\`) and run

    python3 rw1edit.py [--dosbox PATH] [--dosbox-conf FILE]... [FILE]

FILE is opened at the start (a new file of that name if there is none). Options:

- `--game-dir DIR` - the folder with RW1_COMP.EXE, RW1_DUEL.EXE and HTML (default: the script's
  folder if they are there, else the current folder)
- `--dosbox PATH` - DOSBox for Compile and Run (default: `$DOSBOX`, else `dosbox`, `dosbox-staging`
  or `dosbox-x` on the PATH)
- `--dosbox-conf FILE` - a DOSBox configuration to use (repeatable; its `[autoexec]` is skipped)
- `--dosbox-option=ARG` - another argument for DOSBox (repeatable)
- `--font FAMILY[:SIZE]` - a fixed-width font (default: Fixedsys on Windows, the Tk fixed font
  elsewhere)
- `--no-fixes` - the original: its bugs, its keys and its 35 x 28 window

The file dialogs start in the current folder, so start it from the game folder.

## Keys

| Key | |
|---|---|
| arrows, Home, End, PgUp, PgDn | move (Ctrl+PgUp/PgDn: start/end of the text, Ctrl+Left/Right: words) |
| Shift + movement, Shift+click, mouse drag | select |
| double click, triple click | select the word, the line |
| typing, Del, Backspace | replace / delete the selection; Esc drops it |
| mouse wheel, Shift+wheel | scroll the text up/down, sideways (the cursor keeps its place in the window) |
| Ctrl+C, Ctrl+X, Ctrl+V (also Ctrl+Ins, Shift+Del, Shift+Ins) | copy, cut, paste |
| Ctrl+Z, Ctrl+Shift+Z | undo, redo |
| Ctrl+F, F3 | find, find the next one (any case) |
| Ctrl+S (F2), Ctrl+O | save, open |
| Ctrl+A | select all |
| Ctrl+Y | delete the line |
| Insert | insert/overwrite |
| Tab | to the next word of the line above |
| F1 | About |
| F8, F9 | Compile, Run |

With `--no-fixes` the original's keys: F3 opens, Ctrl+Del deletes the selection and Ctrl+letters
type control characters.

## eXoDOS patches

Two patches for eXoDOS's Robot Warfare 1 (1999), each a folder with a Python script (3.8 or newer)
that takes eXoDOS's "eXo" folder, with `--check` (show what it would do) and `--revert`:

- **rw1edit-windows-fix**: `python fix_windows.py EXO_FOLDER` replaces
  `eXoDOS\RoboWar1\RW1_EDIT.EXE` with a fixed one (`RW1_EDIT.EXE.orig` keeps the original). It has
  the port's fixes, not its additions: no freezes (mouse drag to the right edge, deleting
  selections, Ctrl+Right into an empty line), no crashes (Select all + Copy in a one-line text,
  Ctrl+Left in an empty text, empty files, long lines), Edit > Copy lets go of Ctrl, a last line
  without a line end is kept, a new text asks for a name when saved. Lines stop at 254 characters.
  It is still a Windows program: the rules (`start html\...`) don't open on Windows NT and later,
  and Compile and Run can't start the DOS programs on 64-bit Windows. `build_fix.py ORIGINAL`
  makes it from `fix.asm` (NASM).
- **rw1edit-port**: `python install_port.py EXO_FOLDER` puts `rw1edit.py` next to RW1_EDIT.EXE and
  makes the launcher's "windows based editor" choice run it - from the game folder, with eXo's
  DOSBox and the game's `dosbox.conf` for Compile and Run. Without Python (`py`) or `rw1edit.py`
  it starts RW1_EDIT.EXE as before. `exception.bat.orig` keeps the original launcher.

Only the installed game is changed, not its zip: after reinstalling the game run them again. The
two work together (the launcher falls back to the fixed RW1_EDIT.EXE).

## Tests

`tests/ab.py` runs the original `RW1_EDIT.EXE` (Windows) side by side with the port (`--no-fixes`)
and compares their complete state after every step - with `--fixed` the fixed RW1_EDIT.EXE with the
port's fixes; `tests/test_fixes.py`, `tests/fuzz_fixed.py` and `tests/test_ui_additions.py` check
the fixes and additions, `tests/test_patches.py EXO_FOLDER` the two patches; see NOTES.md.
