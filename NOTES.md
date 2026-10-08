# RW1_EDIT.EXE: notes

RW1-EDITOR 1.0.4, "(c) SHABUN 1999, (c) Luneg S.V. uneg@mail.ru": the Windows 95 editor of
Robot Warfare 1 (Alexander Shabarshin, 1998-2000). eXo's copy: `eXoDOS\RoboWar1\RW1_EDIT.EXE`,
64512 bytes, SHA-1 `a8eaa3e48dcfc1e0aceb378afb13cbce30c3c873`, PE timestamp 1 June 1999.

## The program

A Win32 GUI program written in C++ with Microsoft Visual C++ 4.2 (linker 4.20, the CRT's "old" small
block heap). There are no dialogs, no accelerators and no icon in the resources: only the menu. The
editor is entirely hand-made:

- a doubly linked list of line nodes `{char text[256]; node *prev, *next; int len;}` (0x10C bytes,
  `operator new`), held by one editor object at 0040E9F0 (`+0` and `+4` loop variables, `+8` a
  scratch line, `+C` current line, `+10` first line on the screen, `+14` head, `+18` tail);
- the cursor as *screen* row/column (`DAT_0040e7a4/a8`) plus the first column and line on the screen
  (`DAT_0040e7ac/b0`), limited by the last row/column of the window (`DAT_0040e7c8`, `DAT_0040eb30`,
  set in WM_SIZE from the client area minus "line height + 4" for the status bar);
- text drawn with `SYSTEM_FIXED_FONT` (Fixedsys, 8x15) into a bitmap 256 characters wide, copied to
  the window in WM_PAINT; the cursor (a blue box in overwrite mode, a 2-pixel blue bar in insert
  mode) is drawn on top and blinks with a 170 ms timer;
- every WM_PAINT redraws all visible lines (the "only the current line" branch is dead code);
- colouring per line (FUN_00405ff0): black text; the digits blue (0000BE); the 20 keywords ROBOT ACT
  SPY START SAY PRINT CALL GOTO END RET STEP LEFT RIGHT BACK FRONT IF DUMP SEND GET DEF dark red
  (960000), case-insensitive, bounded by a delimiter `` .,:;'(){}[]/?!|<>+=-*"`` or the line's ends;
  from `%` to the end of the line green (00A000); the selection black on grey C8C8C8 (only as far as
  the text goes);
- Shift and Ctrl are not read from the keyboard but tracked from their WM_KEYDOWN/WM_KEYUP;
- files are read with `fgets(s, 0xFF)` in text mode and converted from CP866 to CP1251 (80-AF +40,
  E0-EF +10), written in text mode converted back (C0-EF -40, F0-FF -10); a TAB becomes 8 spaces.

Menu ids: 99 New editor (`WinExec("rw1_edit.exe")`), 101 Open (F3), 102 Save (F2), 103 Save as,
104 Exit, 105 About (F1), 106 Cut, 107 Copy, 108 Paste, 111 Compile (F8,
`CreateProcess("<start dir>\rw1_comp.exe <file>")`), 112 Run (F9, `rw1_duel.exe <file> -s0`),
113 Select all (= Ctrl+A, WM_CHAR 1), 114 Delete, 1051/1052 the rules (`WinExec("start
html\rules_.htm")` / `rules.htm`). Id 110 opens a dialog "FindDialog" that is not in the resources and
can't be reached anyway.

Keys: arrows, Home, End, PgUp/PgDn (Ctrl: start/end of the text), Ctrl+Left/Right (words),
Insert (insert/overwrite), Shift+Ins paste, Ctrl+Ins copy, Shift+Del cut, Ctrl+Del delete selection,
Del, Backspace, Enter (auto-indent if the line starts with a space), Tab ("smart": to the next word
start of the line above, else 8 spaces), Ctrl+Y delete line, Ctrl+A select all, F1 F2 F3 F8 F9.
Mouse: left click moves the cursor, dragging selects, right click moves the cursor and drops the
selection. Scroll bar 0..100.

The decompilation (Ghidra 12.1.4) is in `re/out` (`decomp.c`, `listing.asm`; not published).

## How the port works

`rw1edit.py`'s `Editor` is the window procedure and everything below it, function by function, with
the same variables (the comments name the original's functions and globals). The line list is a
linked list of `Line` objects with a 256-byte buffer each, so that the bytes a line leaves behind
when it gets shorter are still there when the original would read them (Select all + Copy, Ctrl+Right
past a line end). `App` is the window: a Tk canvas drawn the same way (Fixedsys on Windows, the Tk
fixed font elsewhere; text decoded as CP1251), the menu, a three-part status bar
(6 characters | rest | 14 characters, as FUN_00403630) and a scroll bar with the original's 0..100
range.

Necessary changes:

- Compile and Run start RW1_COMP.EXE / RW1_DUEL.EXE in DOSBox (`--dosbox`, `$DOSBOX` or the PATH):
  `mount c <game folder>`, `mount d <the robot's folder>`, `RW1_COMP.EXE D:\NAME.RW1`, `pause`,
  `exit` (Run: `RW1_DUEL.EXE D:\NAME.RW1 -s0`, no pause). A name DOS can't use is compiled from a
  copy `RW1Ennnn.RW1` next to it; the RW0 is renamed back and the copy removed when DOSBox ends.
  `-noautoexec`, so a game configuration (`--dosbox-conf`) only sets the machine.
- The rules open in the web browser, from `html\` in the game folder.
- New editor starts another copy of the port.
- Where the original crashes, hangs or overwrites its own memory, the port stops short (see below).
- The text is always shown as CP1251 (the original shows it in the system's ANSI code page, so the
  Cyrillic comments of the robots were only readable on a Russian Windows).
- The heap: a new line in the port starts as 256 zero bytes; in the original it gets whatever block
  the CRT's small block heap hands out, with the bytes of an earlier line in it. These bytes are
  only read past a line's end (Select all + Copy copies the last line up to column 250 - the
  original then has some old text at the end of the clipboard).

## Bugs of the original

Crashes, hangs and memory corruption - the port does the harmless thing instead:

1. A line of 256 characters: the next repaint copies it with `strcpy` into a 256-byte stack buffer
   without room for the terminator and crashes (verified). The port refuses the 256th character
   (typing, pasting, Tab, Backspace/Del joining two lines).
2. Saving a line of 255 characters writes the line end's NUL into the low byte of the line's `prev`
   pointer (verified); the next Up arrow from that line goes into garbage. The port saves it.
3. Opening an empty file (or one that is only a ^Z): no lines at all; the next WM_PAINT divides by
   the line count (zero) and crashes. Same after "Load file error" (all lines are deleted before the
   file is opened). The port: one empty line.
4. Ctrl+Left at the start of the text when every line from there up is empty (a new, empty
   document!): endless recursion, stack overflow. The port: nothing happens.
5. Deleting a selection (Ctrl+Del, Shift+Del, Edit > Cut/Delete) of several lines hangs when the
   selection starts beyond the end of its first line or ends beyond the end of its last one: Del at a
   line's end joins the next line, the end line disappears, and the loop that deletes lines until it
   reaches it runs forever (`Ctrl+Y` on the last line only empties it). Also when Ctrl+Del gets a
   selection made upwards (the copy before Shift+Del sorts the ends, Ctrl+Del doesn't). Found by the
   fuzzer, ~1 in 15 random sessions. The port stops the loop (what has been deleted stays deleted).
6. Select all, then Copy, Cut or Delete in a text of **one line**: Select all sets the end line to
   the line *count* (1), so the copy takes the multi-line path, steps from the only line to NULL and
   reads it (crash). The same for any copy whose end line is no longer below the start (it was
   deleted, or Ctrl+Del got an upward selection): NULL or a walk through freed nodes (hang).
   The port stops; nothing is copied or deleted.
7. A line of the file with TABs that grow it past 255 characters: the expansion overflows the
   `fgets` buffer and the line list (verified: next pointer 0x11). The port keeps the first 256.
8. Dragging the mouse into the narrow strip at the right edge of the text area (the default
   window is 287 pixels wide = 35 columns + 7 pixels; x 280..286 is "column 35", one more than the
   cursor can reach): the drag loop scrolls to column 256 and then spins forever. Very easy to hit
   while selecting with the mouse. Also when scrolled right and the window is then made wider.
   The port stops (the view stays scrolled to the right).
9. Ctrl+Right at the end of a line moves to the next line and skips "delimiters" from its start:
   in an empty new line (zero bytes - the NUL counts as a delimiter) it runs to column 256 (the
   view jumps far right; the port does that too) and then reads the low byte of the line's own
   `prev` pointer: on the first line (NULL), or when the previous line's heap address ends in 00 or
   20 (1 in 8), it spins forever. The port stops on the first line; it can't know heap addresses.
10. Shift+Ins when the clipboard holds no text returns with the clipboard still open: no other
    program can use the clipboard until the editor closes it.

Behaviour that is odd or wrong but harmless to the program (kept as it is):

11. Edit > Copy sets Shift instead of Ctrl back to "up": Ctrl stays down until it is pressed and
    released. Meanwhile Left/Right jump by words, PgUp/PgDn go to the start/end, Ins copies,
    Del deletes the selection.
12. File > Save of a new text saves `noname.rw1` in the current folder without asking (in eXo: the
    eXo root).
13. Opening a file leaves the "modified" flag as it was: after "No" to "File is not saved" the newly
    opened file counts as modified.
14. The last line of a file is dropped when it has no line end (`while (fgets(...), !feof(f))`),
    and a line longer than 254 characters is split.
15. CP1251 characters 80-AF (punctuation such as « » №) are written as they are and become Cyrillic
    letters (C0-EF) after saving; CP866 box drawing (B0-DF) in a file is shown as other characters
    and C0-DF is changed on saving.
16. Deleting a selection of several lines leaves the line break between the two remaining parts;
    and a selection that starts or ends beyond its line's text deletes into the following lines.
17. Ctrl+Y on the first row of a scrolled window does not update the window's first line: the
    deleted line stays on the screen (and the cursor is drawn one row off) until it scrolls.
18. End on a short line while scrolled to the right puts the cursor off the screen to the left.
19. When the window gets smaller the cursor can stay below the last row.
20. A click below the last full row (the part-row above the status bar) scrolls to the end.
21. Dragging the scroll bar thumb moves about 1/101 of the distance per mouse move (the loop bound
    is recomputed after every line).
22. Mouse: no wheel; dragging only selects 0.34 s after the window was activated; releasing the
    button outside the window leaves Shift "down" (arrow keys keep extending the selection).
23. Control characters go into the text: Ctrl+B..Ctrl+Z (except Y, A, H, I, M), Ctrl+Enter (LF,
    splits the line when the file is read again), Ctrl+Backspace (DEL), Ctrl+@ (NUL: the line ends
    there when saved, and the next line is joined to it), ^Z (the file ends there when read again).
24. Pasted text is selected afterwards; TABs in it become smart tabs, trailing spaces vanish.
25. The rules use the `start` command (only Windows 9x has START.EXE: always error 202/203 on NT)
    relative to the current folder; Compile/Run look for the DOS programs in the folder the editor
    was started in and pass the full path (no long names, no spaces) - in eXo (started from the eXo
    root) and on 64-bit Windows neither works.

## Fixes

Chosen by the user 2026-10-08; on by default, `--no-fixes` turns them off (the A/B tests run without
them):

- Freezes and crashes: a mouse drag only goes as far as the cursor can (bug 8); deleting a selection
  puts its ends in order and takes columns past a line's end as the line's end, so it deletes exactly
  the selection and finishes (bug 5; see Additions: line breaks included, bug 16);
  Select all ends on the last line, not one past it, and a copy stops at the end line's text and at
  the end of the text (bug 6, and no leftover bytes in the clipboard); Ctrl+Y on the first row moves
  the screen's first line along (bug 17, which could later crash on scrolling); Ctrl+Right stops at
  the start of an empty line (bug 9); Ctrl+Left at the start of the text does nothing (bug 4).
- Edit > Copy lets go of Ctrl (bug 11).
- A last line without a line end is kept when a file is opened (bug 14).
- Saving a new text (F2, or "Yes" to "File is not saved. Save it?") asks for a name instead of
  writing `noname.rw1`; cancelling the dialog cancels Open/Exit/Compile/Run as Cancel would (bug 12).

Without fixes too: lines stop at 255 characters (bugs 1, 2), an empty file or a failed load leaves
one empty line (bug 3).

## Additions

Also on by default and off with `--no-fixes` (chosen by the user 2026-10-08):

- The mouse wheel, over the text and over the scroll bar: 3 lines per notch, Shift+wheel 3 columns
  sideways. The cursor of this editor is always on the screen (its row and column are kept relative
  to the window), so the text moves and the cursor keeps its place in the window, as with
  PgUp/PgDn; the original's scroll bar arrows instead move the cursor. Windows: `<MouseWheel>`,
  120 per notch, smaller steps of fine wheels added up; macOS: `<MouseWheel>`, 1 per line; X11:
  buttons 4 and 5 (Tk 8.6 has no binding for the sideways buttons 6 and 7).
- Keys: Ctrl+C, Ctrl+X, Ctrl+V do what Ctrl+Ins, Shift+Del, Shift+Ins do (with Shift and Ctrl as
  they were afterwards); Ctrl+S saves, Ctrl+O opens (Cmd on a Mac; on Windows by the key, so also
  with a Russian layout); the other control characters (Ctrl+B, Ctrl+Enter, Ctrl+Backspace,
  Ctrl+@ ...) are not typed any more. Ctrl+A, Ctrl+H/I/M and Ctrl+Y keep their meaning.
- Undo (Ctrl+Z) and redo (Ctrl+Shift+Z; Ctrl+Y stays "delete line"), Edit menu too: before each
  edit a snapshot of the text, the cursor and the selection; typing, Backspace and Del in a row
  are one step (a move, click, wheel, command or save starts a new one), Enter, Ctrl+Y, paste and
  cut one each; up to 1000 steps; an edit that changed nothing is skipped; Open forgets them.
  Undoing back to the saved text counts as not modified.
- Selections as today: typing and pasting replace the selection, Backspace, Del and Ctrl+Del delete
  it (Shift+Del cuts it), Esc and any move without Shift or a click drop it, Shift+movement goes on
  from where the last one ended. Deleting a selection deletes exactly it, line breaks included -
  the two remaining parts make one line (bug 16; if that would be longer than 255 characters they
  stay two lines). The cursor goes where the selection started, perhaps past the line's end.
- Find (Ctrl+F, a small dialog; F3 the next one - F3 opened files in the original): from the
  cursor on, around the end, in any case (ASCII and Cyrillic); the place found is selected, the
  window follows; "Cannot find".
- Mouse: Shift+click selects from the selection's start (or the cursor), double click the word
  (or the run of spaces, or the one delimiter), triple click the line; a drag goes on from there.
  Letting go of the button outside the window ends the drag (the original keeps "Shift" down),
  and when the window becomes active Shift and Ctrl count as up. A click into the part-column at
  the right edge puts the cursor into the last full column.
- `rw1edit.py FILE`: opens FILE at the start (a new file of that name if there is none).
  New editor starts the port without it.
- The window opens with 80 x 30 characters instead of the original's 35 x 28.

Checks: `tests/test_fixes.py` (23), `tests/test_ui_additions.py` (21, Tk with made-up events),
`tests/fuzz_fixed.py` with additions (wheel, undo, redo, find, Shift+click, double/triple click,
Ctrl+C/X/V; at the end of each run undo all must give the empty start and redo all the last text):
400 runs of 1000 steps clean.

`tests/test_fixes.py` checks each fix (and that the unfixed editor still has the bug);
`tests/fuzz_fixed.py` fuzzes the fixed editor alone and checks after every step that the line
list, the cursor and the first screen line are consistent and that it never had to stop: 300 runs
of 1000 steps clean (without the fixes it finds the original's bugs in 45 of 60 runs).

## The fixed RW1_EDIT.EXE (exo/)

`exo/build_fix.py ORIGINAL` (SHA-1 a8eaa3e4...) assembles `exo/fix.asm` with NASM (`--nasm`,
`$RW1_NASM`; here `wsl -d Debian -- .../nasm`) into a new section `.fix` (00415000, RWX) and
patches the original code to lead there - every patch checks the bytes it replaces first. The
program is marked as not relocatable (RELOCS_STRIPPED, no base relocations): the new code uses
fixed addresses, and with relocations Windows' mandatory ASLR could move it.

What it does is `Editor(fixes=True, additions=False)` of the port:

| where | what |
|---|---|
| load 00401283 | go on while `fgets` returns a line (the last line without LF is kept) |
| load 00401298 | TAB expansion and CP866 conversion in fix.asm, at most 254 characters |
| load 004014FB | no lines (empty file, fopen failed): one empty line |
| key switch 00402060/00402048 | case 8, 0x20, default: refuse what would make a line longer than 254 |
| Ctrl+Y 00401E0E, 00401E23 | the deleted line was the first on the screen: the new current line is |
| Del 00402488 | joining the next line must fit in 254 |
| Ctrl+Right 004026C9 | stop at the line's end |
| Ctrl+Left 0040272F | at the start of the text: nothing |
| copy 00402911, 004029F0, 00402A95 | buffer (lines + 1) * 258 (was lines * 256: overflowed), stop at NULL, last line up to its end |
| Select all 00403C9A | end line = last line (was the count) |
| Ctrl+Ins 0040421D | clipboard block (lines + 1) * 258 |
| Shift+Ins 004042FD | no text: close the clipboard |
| Del selection 004043DF, 004044E4 | sort the ends, check the lines, clamp the columns; `while len > c0` |
| mouse drag 0040487A | clamp the column to what the cursor can reach |
| Save 00404E59 | a new text ("noname.rw1"): Save as |
| Edit > Copy 00404E42 | Ctrl up afterwards, not Shift |
| "Save it?" Yes at Open, Compile, Run, Exit | a new text: Save as; its Cancel cancels |

The port saves a line with its LF and a NUL, so the fixed version stops lines at 254 characters
(the port with fixes too).

Checked with `tests/ab.py fuzz --fixed` (the fixed exe against the port with fixes, all state after
every step): 12 runs x 300 steps with cut/copy/paste, 30 x 400 and 60 x 500 without the clipboard
(`--no-clipboard`: someone was using it), all identical, no hang, no crash (one run differed only
in `i` while Windows had activated the test window - WM_PAINT swaps through it; alone it was
identical; `i` is not compared while the window is active since); `ab.py load --save
--fixed`: 174 shipped files and 21 edge cases identical (including the TAB line that corrupted the
original, the last line without LF, empty and missing files). `tests/test_patches.py EXO`: both
patches applied, reapplied, reverted on a scratch eXo folder, the launcher's lines run with stubs.

## Testing the original: what to know

- On 64-bit Windows an exception in a 32-bit window procedure that runs for a message sent from
  another thread (`SendMessage` from the harness) is swallowed: the message just ends. So in the
  tests most crashes of the original look like "nothing more happened" (the port stops at the same
  point: the states match), and the original is unreliable afterwards (a later message may hang).
  With real input the program crashes. `SetErrorMode(0x8003)` before starting it keeps the
  "has stopped working" box away.
- Edit > Select all posts itself a WM_CHAR 1: wait before reading its state.
- After writing the clipboard, wait ~0.15 s: Windows' clipboard listeners open it after every
  change, and the editor's `OpenClipboard` fails meanwhile (it then pastes nothing).
- The clipboard is everybody's: `fuzz` writes it before each copy/paste step, so whatever someone
  copies meanwhile is lost (and pasted into the test). With someone at the machine use
  `--no-clipboard`.
- The state is read with `ReadProcessMemory` (image base 00400000, no relocation); the status bar
  with `SB_GETTEXTA` into memory allocated in the editor's process; load and save run the
  original's own routines through a stub in a remote thread (`mov ecx, 0040E9F0; push name;
  call FUN_004011d0`), so no file dialog opens.
- Pointers into freed memory: the original's heap hands freed line nodes out again (the CRT's small
  block heap, laid out after the environment strings - so it differs per environment); a stale
  selection or screen pointer can then point at a new line. The port's freed lines stay freed.
  The fuzzer stops a run when that happens ("heap").

## Verification

`tests/ab.py` drives the original (a scratch copy, started without activation on the left monitor)
with window messages and reads its memory after every step: all globals, the editor object, every
line node (length and text; the bytes after the text are compared separately). The same messages go
to the port's `Editor`.

- `ab.py fuzz`: random keys, characters (incl. Cyrillic, control characters), Shift/Ctrl up/down,
  clicks, drags, scroll bar, cut/copy/paste/delete/select all with clipboard contents, window sizes.
  The clipboard text is compared after every step that may change it.
- `ab.py load [--save]`: the original's load and save routines (called in a thread of the original,
  no file dialog) against the port's, then the saved files and the state after saving.
- `tests/scenarios.py`: a fixed step list for each bug above, both programs.
- `tests/test_keys.py`: the WM_CHAR the port makes of key events.
- `tests/smoke_ui.py`: the Tk window with generated events.
- `tests/crossplat.py`: the port's load + save of a set of files, one hash per file (to compare
  systems).

Results (2026-10-08):
- load + save: 175 of 175 shipped files (robots\*.rw1, MONSTER7, WSIMPLE.RW1) identical; 14 edge
  cases identical except bug 7 (the original corrupts its memory).
- scenarios: 14 of 14 as described.
- the port on Linux (WSL Debian, Python 3.11, Tk 8.6): crossplat hashes of 188 files identical to
  Windows; the window works (Noto Sans Mono, 8x19).
- fuzz, last runs (seeds 100-160 x 400 steps, 300-399 x 500): 48,818 steps compared, no
  difference; the original hung 70 times and crashed 21 times (bugs 4-6, 8) - the port stopped at
  the same step every time, with the same state where the crash only ended the message; twice the
  original's heap handed a freed line out again ("heap"). 9,354 steps had different bytes after a
  line's end (heap contents), never visible except in Select all + Copy (3 times). After the fixes
  and additions went in: 40 x 400 and 25 x 400 (no clipboard) again identical, 171 files identical.
