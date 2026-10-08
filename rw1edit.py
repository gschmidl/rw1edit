#!/usr/bin/env python3
"""rw1edit.py - a platform-independent port of RW1_EDIT.EXE 1.0.4, the
Windows 95 editor of Robot Warfare 1 (c) SHABUN 1999 / Luneg S.V.

The original is a small hand-written Win32 program: its own line list, its own
cursor, scrolling, selection and colouring, drawn into a bitmap with the
system fixed font. This port repeats its logic step by step (the names in the
comments are the original's functions and variables), so that every key,
mouse click and menu command changes the text, the cursor and the selection
exactly as in the original. Where the original corrupts memory, crashes or
hangs, the port stops short and leaves things as they are (see NOTES.md).

Compile and Run start the DOS programs RW1_COMP.EXE and RW1_DUEL.EXE in
DOSBox, the help menu opens the HTML rules in the web browser.

Needs Python 3.8+ with tkinter. Usage: rw1edit.py [--dosbox PATH] ...
(rw1edit.py --help).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

VERSION = '1.0'

# ---------------------------------------------------------------------------
# constants of the original

LINE_CAP = 256          # char text[256] of a line node (prev/next/len follow it)
LINE_MAX = 255          # longest line the port lets the editing code build
GARBAGE = 0x01          # stands for bytes outside a line's text (pointers, heap header)
DELIMS = b' .,:;\'(){}[]/?!|<>+=-*"'      # 0040D048
KEYWORDS = (b'ROBOT', b'ACT', b'SPY', b'START', b'SAY', b'PRINT', b'CALL', b'GOTO', b'END', b'RET',
            b'STEP', b'LEFT', b'RIGHT', b'BACK', b'FRONT', b'IF', b'DUMP', b'SEND', b'GET', b'DEF')
DIGITS = b'0123456789'
# COLORREFs of the original as RGB
BLACK = '#000000'
WHITE = '#ffffff'
KEYWORD_COLOR = '#960000'   # 0x96
DIGIT_COLOR = '#0000be'     # 0xBE0000
COMMENT_COLOR = '#00a000'   # 0xA000
SELECT_BG = '#c8c8c8'       # 0xC8C8C8
CURSOR_COLOR = '#0000ff'    # pen 0xFF0000

NONAME = 'noname.rw1'
TITLE0 = 'RW1-editor:  noname.rw1'
TITLE = 'RW1-Editor :  %s'
ABOUT = ' RW1-EDITOR\n Ver 1.0.4\n\n(c) SHABUN 1999\n(c) Luneg S.V. \n\nuneg@mail.ru      \n'
NOT_SAVED = 'File is not saved. Save it?'
COPYRIGHT = '(c) SHABUN 1999'
CHARSET = 'cp1251'      # the Windows code page the original was written for

# menu and command ids
ID_NEW, ID_OPEN, ID_SAVE, ID_SAVEAS, ID_EXIT, ID_ABOUT = 99, 101, 102, 103, 104, 105
ID_CUT, ID_COPY, ID_PASTE, ID_FIND, ID_COMPILE, ID_RUN = 106, 107, 108, 110, 111, 112
ID_SELALL, ID_DELETE, ID_RULES_RU, ID_RULES_EN = 113, 114, 1051, 1052
IDYES, IDNO, IDCANCEL = 6, 7, 2

# virtual keys
VK_SHIFT, VK_CONTROL = 0x10, 0x11
VK_PRIOR, VK_NEXT, VK_END, VK_HOME, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = range(0x21, 0x29)
VK_INSERT, VK_DELETE = 0x2D, 0x2E
VK_F1, VK_F2, VK_F3, VK_F8, VK_F9 = 0x70, 0x71, 0x72, 0x77, 0x78

# scroll bar codes
SB_LINEUP, SB_LINEDOWN, SB_PAGEUP, SB_PAGEDOWN, SB_THUMBTRACK = 0, 1, 2, 3, 5


def cdiv(a, b):
    """C integer division (truncates towards zero)"""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def is_delim(b):
    """strchr(" .,:;'(){}[]/?!|<>+=-*\\"", c) != NULL: the terminating NUL matches too"""
    return b == 0 or b in DELIMS


def to_ansi(b):
    """FUN_004010d0: CP866 (file) -> CP1251 (editor) for Cyrillic letters"""
    hi = b & 0xF0
    if hi in (0x80, 0x90, 0xA0):
        return b + 0x40
    if hi == 0xE0:
        return b + 0x10
    return b


def to_oem(b):
    """FUN_00401000: CP1251 (editor) -> CP866 (file)"""
    hi = b & 0xF0
    if hi in (0xC0, 0xD0, 0xE0):
        return b - 0x40
    if hi == 0xF0:
        return b - 0x10
    return b


def cstr(data):
    """a C string: everything up to the first NUL"""
    n = data.find(b'\0')
    return bytes(data if n < 0 else data[:n])


def _fold_table():
    """bytes.translate table: CP1251 letters to small letters (for Find)"""
    table = bytearray(range(256))
    for b in range(256):
        try:
            small = bytes([b]).decode(CHARSET).lower().encode(CHARSET)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
        if len(small) == 1:
            table[b] = small[0]
    return bytes(table)


FOLD = _fold_table()


def typed_control(ch):
    """with the additions, the control characters Ctrl makes (Ctrl+B, Ctrl+Enter, Ctrl+@,
    Ctrl+Backspace ...) are not typed; Ctrl+A, H, I, M, Y and [ keep their meaning"""
    return ch is not None and (ch < 0x20 or ch == 0x7F) and ch not in (0x01, 0x08, 0x09, 0x0D, 0x19, 0x1B)


class Hang(Exception):
    """the original would loop forever (or recurse until it crashes) here"""


# ---------------------------------------------------------------------------
# C runtime file I/O as RW1_EDIT.EXE does it (MSVC, text mode)

def read_text_mode(data):
    """what fopen(..., "rt") reads: CR LF -> LF, a lone CR stays, ^Z ends the file"""
    z = data.find(b'\x1a')
    if z >= 0:
        data = data[:z]
    return data.replace(b'\r\n', b'\n')


def fgets_lines(data, keep_last=False):
    """the strings of `while (fgets(s, 0xff, f), !feof(f))`: lines of at most
    254 bytes (a longer line continues in the next one); a last line without
    LF hits the end of file and is dropped - unless it fills the 254 bytes
    exactly (fgets stops before it would see the end). keep_last: keep it."""
    out = []
    pos, n = 0, len(data)
    while True:
        if pos >= n:
            return out          # EOF before any byte
        end = data.find(b'\n', pos, pos + 254)
        if end >= 0:
            out.append(data[pos:end + 1])
            pos = end + 1
        elif pos + 254 <= n:
            out.append(data[pos:pos + 254])
            pos += 254
        else:
            if keep_last:
                out.append(data[pos:])
            return out          # partial last line: EOF is set, the loop ends


def expand_line(raw, cap=False):
    """the per-line work of FUN_004011d0 on the fgets buffer char local_104[256]:
    each TAB becomes 8 spaces, each char goes through to_ansi. cap (fix): no more
    than 254 characters (the original writes past its buffer)"""
    if cap:
        out = bytearray()
        for b in cstr(raw):
            out += b'        ' if b == 9 else bytes([to_ansi(b)])
        return bytes(out[:LINE_MAX - 1])
    buf = bytearray(LINE_CAP)
    buf[:len(raw)] = raw            # fgets copies the bytes and a NUL
    if len(raw) < LINE_CAP:
        buf[len(raw)] = 0

    def strlen():
        n = buf.find(b'\0')
        return LINE_CAP if n < 0 else n     # (the original reads on past the buffer)
    i = 0
    while i < strlen():
        if buf[i] == 9:
            k = strlen()
            while i < k:
                if k + 7 < LINE_CAP:
                    buf[k + 7] = buf[k] if k < LINE_CAP else 0
                k -= 1
            for k in range(i, i + 8):
                if k < LINE_CAP:
                    buf[k] = 0x20
        buf[i] = to_ansi(buf[i])
        i += 1
    s = bytes(buf[:strlen()])
    return s


def load_file(path, fixes=False):
    """lines of the file as FUN_004011d0 builds them, or None if fopen fails"""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return [expand_line(raw, fixes) for raw in fgets_lines(read_text_mode(data), fixes)]


# ---------------------------------------------------------------------------
# the editor (the window procedure FUN_00403910 and everything below it)

class Line:
    """a line node: char text[256]; node *prev, *next; int len"""
    __slots__ = ('buf', 'len', 'prev', 'next')

    def __init__(self):
        self.buf = bytearray(LINE_CAP)
        self.len = 0
        self.prev = self.next = None

    def at(self, i):
        """the byte at text[i]; past the text come prev, next and len (a NULL
        pointer reads as zeros, a real one as unknown bytes), then the heap"""
        if 0 <= i < LINE_CAP:
            return self.buf[i]
        if LINE_CAP <= i < LINE_CAP + 8:
            p = self.prev if i < LINE_CAP + 4 else self.next
            return 0 if p is None else GARBAGE
        if LINE_CAP + 8 <= i < LINE_CAP + 12:
            return (self.len & 0xFFFFFFFF).to_bytes(4, 'little')[i - LINE_CAP - 8]
        return GARBAGE

    def put(self, i, b):
        if 0 <= i < LINE_CAP:
            self.buf[i] = b

    def text(self):
        return bytes(self.buf[:max(0, min(self.len, LINE_CAP))])


class Editor:
    """the state and logic of RW1_EDIT.EXE without the window system.
    `host` provides the clipboard, dialogs, the status bar and so on.
    fixes: repair the bugs listed in NOTES.md under "Fixes" (False: as the
    original, apart from stopping where it crashes or hangs)."""

    def __init__(self, host, cw=8, lh=15, cwd=None, fixes=False, additions=False):
        self.host = host
        self.fixes = fixes or additions
        self.additions = additions      # undo, modern selections, find ... (see NOTES.md)
        # (the fixed RW1_EDIT.EXE keeps a NUL after the line end when it saves: 254)
        self.line_max = LINE_MAX - 1 if self.fixes else LINE_MAX
        self.cw, self.lh = cw, lh       # DAT_0040e94c tmMaxCharWidth, DAT_0040e7d4 line height
        # the editor object at 0040E9F0 (constructed before WinMain, FUN_00405f20)
        self.i = self.j = 0             # +0, +4: the methods' loop variables
        self.tmp = None                 # +8
        self.cur = self.top = None      # +C current line, +10 first line on screen
        self.head = self.tail = None    # +14, +18
        self.nlines = 0                 # DAT_0040d078
        self.insert_after(None)
        self.tail.len = 0
        self.top = self.cur = self.head
        # globals
        self.row = 0                    # DAT_0040e7a4 cursor row on the screen
        self.col = 0                    # DAT_0040e7a8 cursor column on the screen
        self.hscroll = 0                # DAT_0040e7ac first column on the screen
        self.top_idx = 0                # DAT_0040e7b0 number of the first line on the screen
        self.max_row = 0                # DAT_0040e7c8 last cursor row
        self.max_col = 0                # DAT_0040eb30 last cursor column
        self.insert = 1                 # DAT_0040e880 insert (1) or overwrite (0)
        self.redraw = 0                 # DAT_0040ee88
        self.pasting = 0                # DAT_0040d040
        self.c0 = self.c1 = 0           # DAT_0040d060/64 selection start/end column
        self.l0 = self.l1 = 0           # DAT_0040d068/6c selection start/end line number
        self.p0 = self.p1 = None        # DAT_0040d070/74 selection start/end line
        self.modified = 0               # DAT_0040d088
        self.caret = 1                  # DAT_0040d08c cursor shown (blinks)
        self.ticks = 0                  # DAT_0040d090 timer ticks since activation (up to 2)
        self.ctrl = 0                   # DAT_0040d094
        self.shift = 0                  # DAT_0040d098
        self.selecting = 0              # DAT_0040d09c
        self.no_sel = 0                 # DAT_0040d0a4
        self.active = 0                 # DAT_0040d0a8
        self.filename = NONAME          # DAT_0040ea28
        self.startdir = cwd or os.getcwd()     # DAT_0040e958 (getcwd in WM_CREATE)
        self.lastdir = ''               # DAT_0040e7e8 directory of the last file dialog
        self.client = (0, 0)            # DAT_0040ea18 client rectangle (right, bottom)
        self.faults = []                # where the original would have crashed or hung
        # the port's additions (with fixes)
        self.undo_stack, self.redo_stack = [], []
        self.undo_kind = None           # the kind of the last edit (typing is undone in runs)
        self.saved_texts = self.texts()

    # -- the line list ------------------------------------------------------

    def insert_after(self, p):
        """FUN_0040165d: new line after p (p None: at the head)"""
        n = Line()
        n.prev = p
        if p is None:
            n.next = self.head
            if self.head is not None:
                self.head.prev = n
            self.head = n
            if self.tail is None:
                self.tail = n
        else:
            n.next = p.next
            p.next = n
            if n.next is None:
                self.tail = n
            else:
                n.next.prev = n
        self.nlines += 1
        return True

    def delete(self, p):
        """FUN_00401757 (the freed node keeps its contents, as freed heap memory does)"""
        if p.next is None:
            self.tail = p.prev
        else:
            p.next.prev = p.prev
        if p.prev is None:
            self.head = p.next
        else:
            p.prev.next = p.next
        self.nlines -= 1

    def index_of(self, p):
        i, q = 0, self.head
        while q is not None:
            if q is p:
                return i
            q, i = q.next, i + 1
        return None

    def lines(self):
        q = self.head
        while q is not None:
            yield q
            q = q.next

    # -- loading and saving -------------------------------------------------

    def load(self, path):
        """FUN_004011d0"""
        while self.tail is not None:
            self.delete(self.tail)
        lines = load_file(path, self.fixes)
        if lines is None:
            if self.fixes:
                self.empty_document()       # fix: not no lines at all (WM_PAINT divides by 0)
            return False
        for s in lines:
            self.insert_after(self.tail)
            self.tail.buf[:len(s)] = s      # strcpy: the text and its NUL
            if len(s) < LINE_CAP:
                self.tail.buf[len(s)] = 0
            self.tail.len = len(s) - 1 if s.endswith(b'\n') else len(s)
        self.top = self.cur = self.head
        self.hscroll = self.col = self.row = self.top_idx = 0
        self.c0 = self.c1 = self.l0 = self.l1 = 0
        if self.fixes and self.nlines == 0:
            self.empty_document()           # fix: an empty file
        self.forget_edits()
        return True

    def forget_edits(self):
        """a new text: nothing to undo; it counts as saved"""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.undo_kind = None
        self.saved_texts = self.texts()

    def save(self, path):
        """FUN_00401502"""
        out = bytearray()
        for line in self.lines():
            line.put(line.len, 0x0A)
            line.put(line.len + 1, 0)
            s = cstr(line.buf)
            out += bytes(to_oem(b) for b in s)
            # back to the editor's code page (not quite the inverse of to_oem)
            line.buf[:len(s)] = bytes(to_ansi(to_oem(b)) for b in s)
            self.i = len(s)
        try:
            with open(path, 'wb') as f:
                f.write(bytes(out).replace(b'\n', b'\r\n'))
        except OSError:
            return False
        self.saved_texts = self.texts()
        self.undo_kind = None       # (typing after a save is a step of its own)
        return True

    # -- cursor movement ----------------------------------------------------

    def home(self):
        """FUN_004021d7"""
        self.hscroll = 0
        self.col = 0

    def end(self):
        """FUN_00402201"""
        if self.cur.len < self.hscroll + self.max_col:
            self.col = self.cur.len - self.hscroll
        else:
            self.col = self.max_col
            self.hscroll = self.cur.len - self.max_col
            self.redraw = 1

    def up(self):
        """FUN_0040227c"""
        if self.row < 1:
            if self.top_idx > 0:
                self.cur = self.cur.prev
                self.top = self.top.prev
                self.top_idx -= 1
                self.redraw = 1
        else:
            self.row -= 1
            self.cur = self.cur.prev

    def down(self):
        """FUN_004022fd"""
        if self.cur.next is not None:
            if self.row < self.max_row:
                self.cur = self.cur.next
                self.row += 1
            else:
                self.cur = self.cur.next
                self.top = self.top.next
                self.top_idx += 1
                self.redraw = 1

    def left(self):
        """FUN_00402388"""
        if self.hscroll + self.col > 0:
            if self.col < 1:
                self.hscroll -= 1
                self.redraw = 1
            else:
                self.col -= 1

    def right(self):
        """FUN_004023d9"""
        if self.hscroll + self.col < 0x100:
            if self.col < self.max_col:
                self.col += 1
            else:
                self.hscroll += 1
                self.redraw = 1

    def page_up(self):
        """FUN_004020a1"""
        self.i = 0
        while True:
            if self.max_row <= self.i:
                self.redraw = 1
                return
            if self.top.prev is None:
                break
            self.cur = self.cur.prev
            self.top = self.top.prev
            self.top_idx -= 1
            self.i += 1
        self.row = 0
        self.cur = self.top
        self.redraw = 1

    def page_down(self):
        """FUN_00402147"""
        self.i = 0
        while self.i < self.max_row and self.cur.next is not None:
            self.cur = self.cur.next
            self.top = self.top.next
            self.top_idx += 1
            self.i += 1
        self.redraw = 1

    def doc_end(self):
        """FUN_0040254f"""
        while self.tail is not self.cur:
            self.down_or_hang()
        self.redraw = 1

    def doc_home(self):
        """FUN_0040258e"""
        while self.head is not self.cur:
            self.up_or_hang()
        self.redraw = 1

    def word_right(self):
        """FUN_004025cd"""
        self.j = self.hscroll + self.col
        cur = self.cur
        if self.j < cur.len:
            while not is_delim(cur.at(self.j)) and self.j < cur.len:
                self.right()
                self.j += 1
            while True:
                k = self.j
                self.j += 1
                if not is_delim(cur.at(k)) or cur.len < self.j:
                    break
                self.right()
        else:
            self.redraw = 1
            self.down()
            self.home()
            while is_delim(self.cur.at(self.hscroll + self.col)):
                if self.fixes and self.hscroll + self.col >= self.cur.len:
                    break       # fix: not on through the bytes after the line's end
                self.right_or_hang()

    def word_left(self, depth=0):
        """FUN_0040270b"""
        self.j = self.hscroll + self.col
        if self.j < 1:
            if self.fixes and self.cur is self.head:
                return          # fix: the start of the text (the original recurses forever)
            if depth > self.nlines + 1:
                raise Hang('Ctrl+Left above only empty lines (endless recursion)')
            self.redraw = 1
            self.up()
            self.end()
            self.word_left(depth + 1)
            return
        cur = self.cur
        self.j -= 1
        if self.j == 0:
            self.left()
        while is_delim(cur.at(self.j)) and 0 < self.j:
            self.left()
            self.j -= 1
        while True:
            k = self.j
            self.j -= 1
            if is_delim(cur.at(k)) or self.j < -1:
                break
            self.left()

    # loops of the original that stop only when the movement succeeds
    def _moved(self, before):
        if before == (self.cur, self.row, self.col, self.hscroll, self.top_idx):
            raise Hang('cursor loop without progress')

    def up_or_hang(self):
        before = (self.cur, self.row, self.col, self.hscroll, self.top_idx)
        self.up()
        self._moved(before)

    def down_or_hang(self):
        before = (self.cur, self.row, self.col, self.hscroll, self.top_idx)
        self.down()
        self._moved(before)

    def left_or_hang(self):
        before = (self.cur, self.row, self.col, self.hscroll, self.top_idx)
        self.left()
        self._moved(before)

    def right_or_hang(self):
        before = (self.cur, self.row, self.col, self.hscroll, self.top_idx)
        self.right()
        self._moved(before)

    # -- selection ----------------------------------------------------------

    def mark_start(self):
        """FUN_00402813"""
        self.c0 = self.hscroll + self.col
        self.l0 = self.top_idx + self.row
        self.p0 = self.cur

    def mark_end(self):
        """FUN_00402854"""
        self.c1 = self.hscroll + self.col
        self.l1 = self.top_idx + self.row
        self.p1 = self.cur

    def swap_sel(self):
        """FUN_00402895 (its temporary is the editor's loop variable)"""
        self.i = self.c0
        self.l0, self.l1 = self.l1, self.l0
        self.c0, self.c1 = self.c1, self.c0
        self.p0, self.p1 = self.p1, self.p0

    def reversed_sel(self):
        return self.l1 < self.l0 or (self.l1 == self.l0 and self.c1 < self.c0)

    def sel_text(self):
        """FUN_00402905 (the caller copies it to the clipboard with strcpy)"""
        p = self.p0
        out = bytearray()
        self.j = 0                      # the number of bytes copied

        def copy(line, start, stop):
            self.i = start
            while self.i < stop:
                out.append(line.at(self.i))
                self.i += 1
                self.j += 1

        def crlf():
            out.extend(b'\r\n')
            self.j += 2
        if self.l1 == self.l0:
            copy(p, self.c0, p.len if p.len < self.c1 else self.c1)
        else:
            copy(p, self.c0, p.len)
            crlf()
            q = p.next
            while self.p1 is not q:
                if q is None:
                    if self.fixes:
                        return cstr(out)
                    self.i = 0
                    raise Hang('copy: the end of the selection is not below its start (NULL)')
                copy(q, 0, q.len)
                q = q.next
                crlf()
            # up to the column, not to the line's end (fix: to the line's end at most)
            copy(q, 0, min(self.c1, q.len) if self.fixes else self.c1)
        return cstr(out)

    def paste_text(self, text):
        """FUN_00402b8f"""
        self.pasting = 1
        self.mark_start()
        for b in cstr(text):
            if b != 0x0A:
                self.key(b)
                if b == 0x0D:
                    self.home()
        self.mark_end()
        self.pasting = 0

    # -- typing -------------------------------------------------------------

    def too_long(self, n):
        """the port's limit: past it the original writes beyond the 256-byte
        line into its pointers (and crashes soon after); the port refuses
        the keystroke instead"""
        if n > self.line_max:
            self.fault('line longer than %d characters' % self.line_max)
            return True
        return False

    def fault(self, what):
        self.faults.append(what)
        self.host.fault(what)

    def key(self, ch):
        """FUN_00401805: a character typed (WM_CHAR) or pasted"""
        cur = self.cur
        total = self.hscroll + self.col
        if ch == 0x08:
            if total < cur.len + 1:
                if total < 1:
                    self.redraw = 1
                    if self.head is not cur and not self.too_long(cur.prev.len + cur.len):
                        self.tmp = cur.prev
                        self.i = 0
                        while self.i < cur.len:
                            self.tmp.put(self.tmp.len + self.i, cur.at(self.i))
                            self.i += 1
                        self.up()
                        self.end()
                        self.right()
                        self.cur.len += self.cur.next.len
                        self.delete(self.cur.next)
                else:
                    self.i = total - 1
                    while self.i < cur.len - 1:
                        cur.put(self.i, cur.at(self.i + 1))
                        self.i += 1
                    cur.len -= 1
                    while cur.at(cur.len - 1) == 0x20:
                        cur.len -= 1
            self.left()
        elif ch == 0x09:
            self.j = total
            if self.head is cur or cur.prev.len <= self.j:
                self.j = 0
                while self.j < 8:
                    self.key(0x20)
                    self.j += 1
            else:
                self.tmp = cur.prev
                while not is_delim(self.tmp.at(self.j)) and self.j < self.tmp.len:
                    self.key(0x20)
                    self.j += 1
                while True:
                    k = self.j
                    self.j += 1
                    if not is_delim(self.tmp.at(k)) or self.tmp.len < self.j:
                        break
                    self.key(0x20)
        elif ch == 0x0D:
            if self.insert_after(cur):
                self.redraw = 1
                self.tmp = cur.next
                self.i = total
                while self.i < cur.len:
                    self.tmp.put(self.i - total, cur.at(self.i))
                    self.i += 1
                if total < self.i:
                    self.tmp.len = cur.len - total
                    cur.len = total
                    while cur.at(cur.len - 1) == 0x20:
                        cur.len -= 1
                else:
                    self.tmp.len = 0
                if cur.at(0) == 0x20 and cur.len != 0 and not self.pasting:
                    self.home()
                    self.down()
                    self.key(0x09)
                    return
                self.home()
                self.down()
        elif ch == 0x19:
            if self.tail is cur:
                cur.len = 0
            else:
                self.cur = cur.next
                self.delete(self.cur.prev)
                if self.head is self.cur:
                    self.top = self.head
                elif self.fixes and self.top is cur:
                    self.top = self.cur     # fix: the deleted line was the first on the screen
            self.redraw = 1
        elif ch == 0x1B:
            pass
        elif ch == 0x20:
            if total <= cur.len - 1:
                if self.insert:
                    if self.too_long(cur.len + 1):
                        return
                    if cur.len < 0x100:
                        cur.put(cur.len, cur.at(cur.len - 1))
                    self.i = cur.len - 1
                    while total < self.i:
                        cur.put(self.i, cur.at(self.i - 1))
                        self.i -= 1
                cur.put(total, ch)
                cur.len += self.insert
            self.right()
        else:
            if self.too_long(max(cur.len, total + 1) + (self.insert if total < cur.len else 0)):
                return
            self.i = cur.len
            while self.i < total:
                cur.put(self.i, 0x20)
                self.i += 1
            if cur.len < 0x100 and total <= cur.len - 1 and self.insert:
                cur.put(cur.len, cur.at(cur.len - 1))
            cur.len += self.i - cur.len
            if self.insert:
                self.i = cur.len - 1
                while total < self.i:
                    cur.put(self.i, cur.at(self.i - 1))
                    self.i -= 1
            cur.put(total, ch)
            cur.len += self.insert
            if cur.len <= total and not self.insert:
                cur.len += 1
            if not self.insert:
                while cur.at(cur.len - 1) == 0x20:
                    cur.len -= 1
            self.right()

    def delete_char(self):
        """FUN_00402431: Del"""
        total = self.hscroll + self.col
        if total < self.cur.len:
            self.right()
            self.key(0x08)
        else:
            self.redraw = 1
            if self.tail is not self.cur:
                cur = self.cur
                if self.too_long(total + cur.next.len):
                    return
                self.i = cur.len
                while self.i < total:
                    cur.put(self.i, 0x20)
                    self.i += 1
                cur.len = total
                self.down()
                self.home()
                self.key(0x08)

    # -- window messages ----------------------------------------------------

    def status(self):
        """FUN_0040375c"""
        self.host.status('%u : %u' % ((self.hscroll + self.col + 1) & 0xFFFFFFFF,
                                      (self.top_idx + self.row + 1) & 0xFFFFFFFF))

    def invalidate(self):
        self.host.invalidate()

    def guarded(self, fn, *args):
        """run a message handler; where the original would hang or crash, stop"""
        try:
            return fn(*args)
        except Hang as e:
            self.fault(str(e))
        except (AttributeError, TypeError) as e:     # a NULL or dangling line pointer
            self.fault('invalid line pointer: %s' % e)
        self.pasting = 0
        self.invalidate()

    def wm_size(self, width, height):
        """WM_SIZE: the client area without the status bar"""
        self.client = (width, height)
        bottom = height - (self.lh + 4)
        self.max_row = cdiv(bottom, self.lh) - 1
        self.max_col = cdiv(width, self.cw) - 1
        self.redraw = 1

    def wm_activate(self, active):
        """WM_ACTIVATE (the original toggles a flag on every activation and deactivation)"""
        self.active = int(active)
        self.ticks = 0

    def wm_timer(self):
        """WM_TIMER, every 170 ms"""
        self.caret = int(self.caret == 0)
        self.invalidate()
        if self.ticks < 2:
            self.ticks += 1

    def _moving_key(self, move):
        if self.shift and not self.selecting:
            self.no_sel = 0
            self.selecting = 1
            if not (self.additions and self.at_selection_end()):
                self.mark_start()
        elif self.additions and not self.shift:
            self.no_sel = 1         # addition: moving without Shift drops the selection
        self.undo_kind = None
        move()
        if self.shift:
            self.mark_end()
        self.caret = 1
        self.status()
        self.invalidate()

    def wm_keydown(self, vk):
        """WM_KEYDOWN"""
        self.caret = 0
        if vk == VK_SHIFT:
            self.shift = 1
        elif vk == VK_CONTROL:
            self.ctrl = 1
        elif vk == VK_PRIOR:
            self._moving_key(self.doc_home if self.ctrl else self.page_up)
        elif vk == VK_NEXT:
            self._moving_key(self.doc_end if self.ctrl else self.page_down)
        elif vk == VK_END:
            self._moving_key(self.end)
        elif vk == VK_HOME:
            self._moving_key(self.home)
        elif vk == VK_LEFT:
            self._moving_key(self.word_left if self.ctrl else self.left)
        elif vk == VK_UP:
            self._moving_key(self.up)
        elif vk == VK_RIGHT:
            self._moving_key(self.word_right if self.ctrl else self.right)
        elif vk == VK_DOWN:
            self._moving_key(self.down)
        elif vk == VK_INSERT:
            if not self.ctrl:
                if not self.shift:
                    self.insert = int(self.insert == 0)     # FUN_00402513
                else:
                    text = self.host.clipboard_get()
                    if text is None:
                        return      # (and the clipboard stays open)
                    if self.additions:
                        self.edit_point('paste')
                        if self.has_selection():
                            self.remove_selection()     # addition: the paste replaces the selection
                    self.modified = 1
                    self.paste_text(text)
                    self.no_sel = 0
            else:
                if self.no_sel or (self.l1 == self.l0 and self.c1 == self.c0):
                    self.caret = 0
                    return
                if self.reversed_sel():
                    self.swap_sel()
                self.host.clipboard_set(self.sel_text())
            self.caret = 1
            self.status()
            self.invalidate()
        elif vk == VK_DELETE:
            if self.additions:
                # addition: Del, Shift+Del and Ctrl+Del delete the selection (Shift+Del copies it
                # first), the whole selection with its line breaks; without one Del deletes a
                # character and the other two do nothing
                if self.has_selection():
                    if self.shift and not self.ctrl:
                        saved = self.ctrl
                        self.ctrl = 1
                        self.wm_keydown(VK_INSERT)
                        self.ctrl = saved
                    self.edit_point('cut')
                    self.remove_selection()
                elif self.shift or self.ctrl:
                    return
                else:
                    self.edit_point('del')
                    self.delete_char()
            elif not self.shift and not self.ctrl:
                self.delete_char()
            else:
                if self.shift:
                    saved = self.ctrl
                    self.ctrl = 1
                    self.wm_keydown(VK_INSERT)
                    self.ctrl = saved if self.additions else 0
                if self.no_sel:
                    return
                self.delete_selection()
            self.no_sel = 1
            self.modified = 1
            self.caret = 1
            self.status()
            self.invalidate()
        elif vk == VK_F1:
            self.wm_command(ID_ABOUT)
            self.caret = 1
        elif vk == VK_F2:
            self.wm_command(ID_SAVE)
            self.caret = 1
        elif vk == VK_F3:
            self.wm_command(ID_OPEN)
            self.caret = 1
        elif vk == VK_F8:
            self.wm_command(ID_COMPILE)
            self.caret = 1
        elif vk == VK_F9:
            self.wm_command(ID_RUN)
            self.caret = 1

    def delete_selection(self):
        """the selection part of WM_KEYDOWN VK_DELETE (with the additions: remove_selection)"""
        if self.fixes:
            # fix: Ctrl+Del does not put the ends in order; a column past its line's end
            # makes the deletion join lines (and eat more than the selection, or never end)
            if self.reversed_sel():
                self.swap_sel()
            if self.p0 is None or self.p1 is None or self.index_of(self.p0) != self.l0 or \
                    self.index_of(self.p1) != self.l1:
                self.c1 = self.l1 = self.c0 = self.l0 = 0
                self.p1 = self.p0 = None
                return
            self.c0 = min(self.c0, self.p0.len)
            self.c1 = min(self.c1, self.p1.len)
        while self.top_idx + self.row < self.l0:
            self.down_or_hang()
        while self.l0 < self.top_idx + self.row:
            self.up_or_hang()
        while self.hscroll + self.col < self.c0:
            self.right_or_hang()
        while self.c0 < self.hscroll + self.col:
            self.left_or_hang()
        if self.l1 == self.l0:
            n = 0
            while n < self.c1 - self.c0:
                self.delete_char()
                n += 1
        else:
            while self.cur.len > self.c0 if self.fixes else self.cur.len != self.c0:
                before = (self.cur, self.cur.len, self.nlines)
                self.delete_char()
                if before == (self.cur, self.cur.len, self.nlines):
                    raise Hang('Del: the line never gets as short as the selection start')
            if self.cur.len == 0:
                self.wm_char(0x19)
            else:
                self.down()
            while self.cur is not self.p1:
                before = (self.cur, self.cur.len, self.nlines)
                self.wm_char(0x19)
                if before == (self.cur, self.cur.len, self.nlines):
                    raise Hang('Del: the end of the selection is never reached')
            self.home()
            n = 0
            while n < self.c1:
                self.delete_char()
                n += 1
            self.up()
            self.end()
        self.c1 = self.l1 = self.c0 = self.l0 = 0
        self.p1 = self.p0 = None

    def wm_keyup(self, vk):
        if vk == VK_SHIFT:
            self.shift = 0
            self.selecting = 0
        elif vk == VK_CONTROL:
            self.ctrl = 0

    def wm_char(self, ch):
        """WM_CHAR"""
        if ch == 1:
            self.c0 = 0
            self.l0 = 0
            self.c1 = 0xFA
            # (the original: the line count, one past the last line - in a text of one
            # line, Copy then runs into NULL; fix: the last line)
            self.l1 = self.nlines - 1 if self.fixes else self.nlines
            self.p0 = self.head
            self.p1 = self.tail
            self.no_sel = 0
        elif self.additions and ch == 0x1B:
            self.no_sel = 1         # addition: Esc drops the selection (and changes nothing)
        else:
            if self.additions:
                self.edit_point({0x0D: 'enter', 0x08: 'back', 0x19: 'line'}.get(ch, 'type'))
                if ch != 0x19 and self.has_selection():
                    # addition: typing replaces the selection, Backspace deletes it
                    self.remove_selection()
                    if ch == 0x08:
                        self.modified = 1
                        self.status()
                        self.invalidate()
                        return
            self.no_sel = 1
            self.modified = 1
            self.key(ch)
            self.status()
        self.invalidate()

    def _goto_row(self, y):
        target = cdiv(y, self.lh)
        if self.row < target:
            while target != self.row and self.tail is not self.cur:
                self.down()
        else:
            while target != self.row:
                self.up_or_hang()

    def wm_lbuttondown(self, x, y):
        if self.additions:
            self.no_sel = 1         # addition: a click drops the selection
            self.undo_kind = None
        self.click_to(x, y)
        self.status()
        self.invalidate()

    def click_to(self, x, y):
        """the cursor to the character under the mouse (as WM_LBUTTONDOWN does)"""
        self.col = cdiv(x, self.cw)
        if self.additions:
            self.col = min(self.col, max(0, self.max_col))     # (not into the part-column)
        self._goto_row(y)

    def wm_rbuttondown(self, x, y):
        self.no_sel = 1
        self.undo_kind = None
        self.col = cdiv(x, self.cw)
        self._goto_row(y)
        self.status()
        self.invalidate()

    def wm_mousemove(self, x, y, lbutton):
        if not lbutton or self.ticks != 2:
            return
        if not self.selecting:
            self.shift = 1
            self.no_sel = 0
            self.selecting = 1
            self.mark_start()
            self.mark_end()
        target = cdiv(x, self.cw)
        if self.fixes:
            # fix: the part-column at the right edge (and, scrolled right, columns past
            # 256) can't be reached: the original's loop below never ends
            target = max(0, min(target, self.max_col, 0x100 - self.hscroll))
        if self.col < target:
            while target != self.col:
                self.right_or_hang()
        else:
            while target != self.col:
                self.left_or_hang()
        self._goto_row(y)
        self.mark_end()

    def wm_lbuttonup(self):
        self.shift = 0
        self.selecting = 0

    def wm_vscroll(self, code, pos=0):
        if code == SB_LINEUP:
            self.up()
        elif code == SB_LINEDOWN:
            self.down()
        elif code == SB_PAGEUP:
            self.page_up()
        elif code == SB_PAGEDOWN:
            self.page_down()
        elif code == SB_THUMBTRACK:
            # for (n = 0; n < line * 100 - pos * nlines; n++) up(); -- the bound
            # changes with every line moved. up() and down() do nothing at the ends.
            there = pos * self.nlines
            if there < (self.top_idx + self.row) * 100:
                n = 0
                while n < (self.top_idx + self.row) * 100 - there:
                    before = (self.cur, self.row, self.top_idx)
                    self.up()
                    if before == (self.cur, self.row, self.top_idx):
                        break
                    n += 1
            elif there > (self.top_idx + self.row) * 100:
                n = 0
                while n < there - (self.top_idx + self.row) * 100:
                    before = self.cur
                    self.down()
                    if before is self.cur:
                        break
                    n += 1
        else:
            return
        self.status()
        self.invalidate()

    def scroll_pos(self):
        """SetScrollPos in WM_PAINT"""
        return cdiv((self.top_idx + self.row) * 100, self.nlines) if self.nlines else 0

    # -- additions of the port (the original has no mouse wheel) -------------

    def wheel(self, lines, horizontal=False):
        """the mouse wheel: the text moves by `lines` lines (or columns; < 0: up/left)
        and the cursor keeps its place in the window, as with PgUp/PgDn - in this
        editor the cursor is always on the screen"""
        if horizontal:
            low = max(0, -self.col)
            high = max(low, 0x100 - self.col)
            self.hscroll = min(max(self.hscroll + lines, low), high)
        elif lines < 0:
            for _ in range(-lines):
                if self.top.prev is None or self.cur.prev is None:
                    break
                self.top = self.top.prev
                self.cur = self.cur.prev
                self.top_idx -= 1
        else:
            for _ in range(lines):
                if self.top.next is None or self.cur.next is None:
                    break
                self.top = self.top.next
                self.cur = self.cur.next
                self.top_idx += 1
        self.undo_kind = None
        self.redraw = 1
        self.status()
        self.invalidate()

    def texts(self):
        return tuple(line.text() for line in self.lines())

    def line_at(self, idx):
        q = self.head
        for _ in range(idx):
            q = q.next
        return q

    def has_selection(self):
        """a selection that is shown and still where its line numbers say"""
        if self.no_sel or (self.l0, self.c0) == (self.l1, self.c1) or self.p0 is None or self.p1 is None:
            return False
        return self.index_of(self.p0) == self.l0 and self.index_of(self.p1) == self.l1

    def at_selection_end(self):
        """the cursor is at the moving end of the selection (makes it so if it is at the
        other end): Shift+movement goes on from there"""
        if not self.has_selection():
            return False
        here = (self.cur, self.top_idx + self.row, self.hscroll + self.col)
        if here == (self.p0, self.l0, self.c0):
            self.swap_sel()
        return here == (self.p1, self.l1, self.c1)

    def set_text(self, line, data):
        line.buf[:len(data)] = data
        line.len = len(data)

    def remove_selection(self):
        """addition: delete the selected text, line breaks included (the original keeps the
        break between the two remaining parts, and with columns past a line's end deletes
        more); the cursor goes to where the selection started"""
        if self.reversed_sel():
            self.swap_sel()
        p0, p1, l0 = self.p0, self.p1, self.l0
        c0, c1 = min(self.c0, p0.len), min(self.c1, p1.len)
        head, tail = p0.text()[:c0], p1.text()[c1:]
        if p0 is not p1:
            q = p0.next
            while True:
                nxt = q.next
                self.delete(q)
                if q is p1:
                    break
                q = nxt
        joined = head + tail
        if len(joined) <= LINE_MAX:
            self.set_text(p0, joined.rstrip(b' '))
        else:
            # too long for one line: as the original, two lines
            self.set_text(p0, head.rstrip(b' '))
            self.insert_after(p0)
            self.set_text(p0.next, tail)
        self.c1 = self.l1 = self.c0 = self.l0 = 0
        self.p1 = self.p0 = None
        self.no_sel = 1
        self.goto(l0, c0)           # (perhaps past the line's end, after its trailing spaces went)

    def goto(self, idx, col):
        """the cursor to line idx, column col; the window follows if it has to"""
        idx = max(0, min(idx, self.nlines - 1))
        rows = max(0, self.max_row)
        if not self.top_idx <= idx <= self.top_idx + rows or self.top_idx > self.nlines - 1:
            self.top_idx = max(0, idx - rows // 2)
        self.top = self.line_at(self.top_idx)
        self.cur = self.line_at(idx)
        self.row = idx - self.top_idx
        cols = max(0, self.max_col)
        col = max(0, min(col, 0x100))
        if not self.hscroll <= col <= self.hscroll + cols:
            self.hscroll = max(0, col - cols)
        self.col = col - self.hscroll
        self.redraw = 1

    # undo: a snapshot of the text, the cursor and the selection before each edit

    def doc_state(self):
        return (self.texts(), self.top_idx, self.row, self.hscroll, self.col,
                (self.l0, self.c0, self.l1, self.c1, self.no_sel))

    def edit_point(self, kind):
        """before an edit: typing, Backspace or Del in a row are undone together"""
        if kind in ('type', 'back', 'del') and kind == self.undo_kind and self.undo_stack:
            return
        self.undo_stack.append(self.doc_state())
        del self.undo_stack[:-1000]
        self.redo_stack.clear()
        self.undo_kind = kind

    def restore(self, state):
        texts, top_idx, row, hscroll, col, (l0, c0, l1, c1, no_sel) = state
        while self.tail is not None:
            self.delete(self.tail)
        for t in texts:
            self.insert_after(self.tail)
            self.set_text(self.tail, t)
        self.top_idx, self.hscroll = min(top_idx, self.nlines - 1), hscroll
        self.goto(top_idx + row, hscroll + col)
        self.l0, self.c0, self.l1, self.c1, self.no_sel = l0, c0, l1, c1, no_sel
        self.p0 = self.line_at(l0) if 0 <= l0 < self.nlines else None
        self.p1 = self.line_at(l1) if 0 <= l1 < self.nlines else None
        self.selecting = 0
        self.modified = int(texts != self.saved_texts)
        self.undo_kind = None
        self.status()
        self.invalidate()

    def _undo_redo(self, take, give):
        self.undo_kind = None
        now = self.doc_state()
        while take:
            state = take.pop()
            if state[0] != now[0]:          # (skip edits that changed nothing, like Esc)
                give.append(now)
                self.restore(state)
                return True
        return False

    def undo(self):
        return self._undo_redo(self.undo_stack, self.redo_stack)

    def redo(self):
        return self._undo_redo(self.redo_stack, self.undo_stack)

    def find(self, pattern):
        """addition: the next place of pattern (bytes, any case) after the cursor, around
        the end; selected, the cursor after it. False if it isn't there."""
        pat = pattern.translate(FOLD)
        if not pat:
            return False
        lines = list(self.lines())
        n = len(lines)
        start, col = self.index_of(self.cur), self.hscroll + self.col
        for k in range(n + 1):
            i = (start + k) % n
            text = lines[i].text().translate(FOLD)
            pos = text.find(pat, col if k == 0 else 0)
            if pos >= 0 and (k < n or pos < col):
                self.p0 = self.p1 = lines[i]
                self.l0 = self.l1 = i
                self.c0, self.c1 = pos, pos + len(pat)
                self.no_sel = 0
                self.selecting = 0
                self.undo_kind = None
                self.goto(i, pos + len(pat))
                self.status()
                self.invalidate()
                return True
        return False

    def with_keys(self, shift, ctrl, fn, *args):
        """fn with the Shift and Ctrl flags set so, and then as they were (Ctrl+C means
        Ctrl+Ins, Ctrl+X Shift+Del, Ctrl+V Shift+Ins)"""
        saved = self.shift, self.ctrl
        self.shift, self.ctrl = shift, ctrl
        try:
            return fn(*args)
        finally:
            self.shift, self.ctrl = saved

    def shift_click(self, x, y):
        """addition: Shift+click selects from the selection's start (or the cursor) to here"""
        if not self.at_selection_end() and not self.has_selection():
            self.mark_start()
        self.click_to(x, y)
        self.mark_end()
        self.no_sel = 0
        self.selecting = 1          # a drag from here goes on from the same start
        self.undo_kind = None
        self.status()
        self.invalidate()

    def select_at(self, x, y, whole_line):
        """addition: double click selects the word (or the run of spaces, or the one
        delimiter) under the mouse, triple click the line"""
        self.click_to(x, y)
        text, c = self.cur.text(), self.hscroll + self.col
        if whole_line:
            s, e = 0, len(text)
        elif c >= len(text):
            return
        elif is_delim(text[c]):
            s = e = c
            if text[c] == 0x20:
                while s > 0 and text[s - 1] == 0x20:
                    s -= 1
                while e < len(text) and text[e] == 0x20:
                    e += 1
            else:
                e = c + 1
        else:
            s = e = c
            while s > 0 and not is_delim(text[s - 1]):
                s -= 1
            while e < len(text) and not is_delim(text[e]):
                e += 1
        idx = self.top_idx + self.row
        self.p0 = self.p1 = self.cur
        self.l0 = self.l1 = idx
        self.c0, self.c1 = s, e
        self.no_sel = 0
        self.selecting = 1          # a drag from here goes on from the word's start
        self.undo_kind = None
        self.goto(idx, e)
        self.status()
        self.invalidate()

    def open_path(self, path, new_if_missing):
        """File > Open's work on a path (also the file named on the command line)"""
        self.lastdir = os.path.dirname(path) + os.sep
        self.filename = path
        if new_if_missing and not os.path.exists(path):
            self.empty_document()       # addition: a new file of that name
        elif not self.load(self.filename):
            self.error(103, 'Load file error')
            self.empty_document()
        elif self.nlines == 0:
            self.fault('empty file')
            self.empty_document()
        self.host.set_title(TITLE % self.filename)
        self.redraw = 1

    # -- WM_COMMAND ---------------------------------------------------------

    def error(self, code, text):
        """FUN_004037b1 and the MessageBox after it"""
        self.host.message('error', 'Error', '%i:\n\n%s\n' % (code, text))

    def ask_save(self, code=101):
        """the "File is not saved" question; False: Cancel"""
        r = self.host.message('yesnocancel', 'Warning', NOT_SAVED)
        if r == IDCANCEL:
            return False
        if r == IDYES:
            if self.fixes and self.filename == NONAME:
                return self.save_as()       # fix: ask for a name (no name: as Cancel)
            if self.filename == '' or not self.save(self.filename):
                self.error(code, 'Save file error')
                return None
            return True
        return None

    def save_as(self):
        """File > Save as; True: saved, None: it could not be saved, False: the
        dialog was cancelled"""
        path = self.host.save_dialog(self.lastdir or self.startdir)
        if not path:
            return False
        self.lastdir = os.path.dirname(path) + os.sep
        self.filename = path
        saved = self.save(self.filename)
        if not saved:
            self.error(102, 'Save file error')
        else:
            self.modified = 0
        self.host.set_title(TITLE % self.filename)
        return True if saved else None

    def file_exists(self):
        try:
            with open(self.filename, 'rb'):
                return True
        except OSError:
            return False

    def wm_command(self, cmd):
        if cmd == ID_RULES_RU:
            if not self.host.open_help('rules_.htm'):
                self.error(203, 'Possible cause:\nFile name of rules was changed')
        elif cmd == ID_RULES_EN:
            if not self.host.open_help('rules.htm'):
                self.error(202, 'Possible cause:\nFile name of rules was changed')
        elif cmd == ID_NEW:
            if not self.host.new_editor():
                self.error(201, 'Possible cause:\nFile name of the editor was changed')
        elif cmd == ID_OPEN:
            if self.modified:
                if self.ask_save() is False:
                    return
            path = self.host.open_dialog(self.lastdir or self.startdir)
            if path:
                self.open_path(path, False)
            self.redraw = 1
        elif cmd == ID_SAVE:
            if self.fixes and self.filename == NONAME:
                self.save_as()      # fix: a new text gets a name (the original writes noname.rw1)
            elif self.filename == '' or not self.save(self.filename):
                self.error(101, 'Save file error')
            else:
                self.modified = 0
        elif cmd == ID_SAVEAS:
            self.save_as()
        elif cmd == ID_EXIT:
            if self.modified and self.ask_save() is False:
                return
            self.host.quit()
        elif cmd == ID_ABOUT:
            self.host.message('info', 'About', ABOUT)
        elif cmd == ID_CUT:
            self.shift = 1
            self.wm_keydown(VK_DELETE)
            self.shift = 0
            self.redraw = 1
        elif cmd == ID_COPY:
            self.ctrl = 1
            self.wm_keydown(VK_INSERT)
            if self.fixes:
                self.ctrl = 0
            else:
                self.shift = 0      # (sic: Ctrl stays down)
            self.redraw = 1
        elif cmd == ID_PASTE:
            self.shift = 1
            self.ctrl = 0
            self.wm_keydown(VK_INSERT)
            self.shift = 0
            self.redraw = 1
        elif cmd in (ID_COMPILE, ID_RUN):
            if self.file_exists() and self.modified:
                r = self.ask_save()
                if r is False:
                    return
                if r:
                    self.modified = 0
            if cmd == ID_COMPILE:
                self.host.compile(self.filename)
            else:
                self.host.run(self.filename)
        elif cmd == ID_SELALL:
            self.wm_char(1)
        elif cmd == ID_DELETE:
            self.ctrl = 1
            self.wm_keydown(VK_DELETE)
            self.ctrl = 0
            self.redraw = 1

    def empty_document(self):
        """the port's way out where the original is left with no lines at all
        (and then divides by zero in its next WM_PAINT)"""
        while self.tail is not None:
            self.delete(self.tail)
        self.insert_after(None)
        self.top = self.cur = self.head
        self.hscroll = self.col = self.row = self.top_idx = 0
        self.forget_edits()

    # -- drawing ------------------------------------------------------------

    def row_cells(self, line, row):
        """FUN_00405ff0: the colours of a line as (fg, bg) per character"""
        c = max(0, line.len)
        text = bytes(line.at(i) for i in range(c))
        upper = cstr(bytes(b - 32 if 0x61 <= b <= 0x7A else b for b in text) + b'\n')
        idx = self.top_idx + row
        if self.l0 < idx < self.l1 and not self.no_sel:
            return text, [BLACK] * c, [SELECT_BG] * c
        fg, bg = [BLACK] * c, [WHITE] * c
        for i, b in enumerate(upper[:c]):
            if b in DIGITS:
                fg[i] = DIGIT_COLOR
        for kw in KEYWORDS:
            n = len(kw)
            at = upper.find(kw)
            while at >= 0:
                if (at == 0 or is_delim(upper[at - 1])) and \
                        (c <= at + n or is_delim(upper[at + n] if at + n < len(upper) else 0)):
                    for k in range(at, min(at + n, c)):
                        fg[k] = KEYWORD_COLOR
                at = upper.find(kw, at + 1)
        p = upper.find(b'%')
        while 0 <= p < c:
            e = upper.find(b'\n', p + 1)
            if e < 0:
                for k in range(p, c):
                    fg[k] = COMMENT_COLOR
                break
            for k in range(p, min(e, c)):
                fg[k] = COMMENT_COLOR
            if c <= e:
                break
            p = upper.find(b'%', e + 1)
        if (self.p0 is line or self.p1 is line) and not self.no_sel:
            if self.p0 is line:
                if self.l1 == self.l0:
                    n = self.c1 - self.c0 if self.c1 <= c else c - self.c0
                else:
                    n = c - self.c0
                for k in range(self.c0, self.c0 + n):
                    if 0 <= k < c:
                        fg[k], bg[k] = BLACK, SELECT_BG
                if self.l1 == self.l0:
                    return text, fg, bg
            if self.p1 is line and self.l1 != self.l0:
                for k in range(c if c < self.c1 else self.c1):
                    fg[k], bg[k] = BLACK, SELECT_BG
        return text, fg, bg

    def paint_rows(self):
        """the rows WM_PAINT draws: [(row, text, fg, bg)]"""
        swapped = self.reversed_sel()
        if swapped:
            self.swap_sel()
        out = []
        line = self.top
        r = 0
        while r < self.max_row + 1 and line is not None:
            out.append((r,) + self.row_cells(line, r))
            line = line.next
            r += 1
        self.redraw = 0
        if swapped:
            self.swap_sel()
        return out


# ---------------------------------------------------------------------------
# DOSBox: RW1_COMP.EXE and RW1_DUEL.EXE

DOS_NAME = re.compile(r"^[A-Z0-9!#$%&'()\-@^_`{}~]{1,8}(\.[A-Z0-9!#$%&'()\-@^_`{}~]{0,3})?$", re.I)


def find_file(folder, name):
    """name in folder, ignoring case"""
    p = os.path.join(folder, name)
    if os.path.exists(p):
        return p
    try:
        for f in os.listdir(folder):
            if f.lower() == name.lower():
                return os.path.join(folder, f)
    except OSError:
        pass
    return None


def find_dosbox(explicit):
    for cand in (explicit, os.environ.get('DOSBOX'), 'dosbox', 'dosbox-staging', 'dosbox-x'):
        if not cand:
            continue
        if os.path.isfile(cand):
            return cand
        found = shutil.which(cand)
        if found:
            return found
        if cand is explicit:
            return None
    return None


class DosRunner:
    """starts RW1_COMP.EXE or RW1_DUEL.EXE on a robot file in DOSBox"""

    def __init__(self, gamedir, dosbox=None, confs=(), extra=()):
        self.gamedir = gamedir
        self.dosbox = dosbox
        self.confs = list(confs)
        self.extra = list(extra)

    def start(self, exe, path, args='', pause=False, copy_back=None):
        """None or an error text"""
        dosbox = find_dosbox(self.dosbox)
        if not dosbox:
            return 'DOSBox not found (use --dosbox or set DOSBOX)'
        prog = find_file(self.gamedir, exe)
        if not prog:
            return '%s not found in %s' % (exe, self.gamedir)
        path = os.path.abspath(path)
        folder, name = os.path.split(path)
        stage = None
        if not DOS_NAME.match(name):
            # a name DOS can't open: a copy with a DOS name next to it, removed afterwards
            ext = os.path.splitext(name)[1]
            ext = ext.upper() if DOS_NAME.match('X' + ext) else '.RW1'
            for n in range(1, 10000):
                dosname = 'RW1E%04d%s' % (n, ext)
                if not find_file(folder, dosname) and not find_file(folder, dosname[:-len(ext)] + '.RW0'):
                    break
            stage = os.path.join(folder, dosname)
            try:
                shutil.copyfile(path, stage)
            except OSError:
                # (a folder we may not write to: then a temporary one)
                folder = tempfile.mkdtemp(prefix='rw1edit')
                stage = os.path.join(folder, dosname)
                try:
                    shutil.copyfile(path, stage)
                except OSError:
                    pass
            name = dosname
        cmds = ['mount c "%s"' % self.gamedir, 'mount d "%s"' % folder, 'c:',
                '%s D:\\%s%s' % (os.path.basename(prog).upper(), name.upper(), args)]
        if pause:
            cmds.append('pause')
        cmds.append('exit')
        argv = [dosbox]
        for c in self.confs:
            argv += ['-conf', c]
        argv += self.extra + ['-noautoexec']
        for c in cmds:
            argv += ['-c', c]
        kw = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
        if os.name == 'nt':
            kw['creationflags'] = 0x08000000        # CREATE_NO_WINDOW: no console for DOSBox
        try:
            proc = subprocess.Popen(argv, **kw)
        except OSError as e:
            if stage:
                self._unstage(None, stage, None, None)
            return '%s: %s' % (dosbox, e)
        self.last = proc
        if stage:
            threading.Thread(target=self._unstage, args=(proc, stage, path, copy_back), daemon=True).start()
        return None

    @staticmethod
    def _unstage(proc, stage, path, copy_back):
        """after DOSBox: the compiled RW0 under the real name, the copy away"""
        if proc:
            proc.wait()
        folder, name = os.path.split(stage)
        out = find_file(folder, os.path.splitext(name)[0] + '.RW0')
        if copy_back and out:
            stem, ext = os.path.splitext(path)
            try:
                os.replace(out, stem + (copy_back if ext.isupper() else copy_back.lower()))
            except OSError:
                pass
        for f in (stage, out):
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass
        if os.path.basename(folder).startswith('rw1edit') and folder.startswith(tempfile.gettempdir()):
            shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------------------
# the window

KEYSYM_VK = {
    'Shift_L': VK_SHIFT, 'Shift_R': VK_SHIFT, 'Control_L': VK_CONTROL, 'Control_R': VK_CONTROL,
    'Prior': VK_PRIOR, 'Next': VK_NEXT, 'End': VK_END, 'Home': VK_HOME,
    'Left': VK_LEFT, 'Up': VK_UP, 'Right': VK_RIGHT, 'Down': VK_DOWN,
    'Insert': VK_INSERT, 'Delete': VK_DELETE,
    'KP_Prior': VK_PRIOR, 'KP_Next': VK_NEXT, 'KP_End': VK_END, 'KP_Home': VK_HOME,
    'KP_Left': VK_LEFT, 'KP_Up': VK_UP, 'KP_Right': VK_RIGHT, 'KP_Down': VK_DOWN,
    'KP_Insert': VK_INSERT, 'KP_Delete': VK_DELETE,
    'KP_Page_Up': VK_PRIOR, 'KP_Page_Down': VK_NEXT, 'Page_Up': VK_PRIOR, 'Page_Down': VK_NEXT,
}
for _n in range(1, 13):
    KEYSYM_VK['F%d' % _n] = 0x6F + _n
CTRL_CHARS = {'bracketleft': 0x1B, 'backslash': 0x1C, 'bracketright': 0x1D, 'asciicircum': 0x1E,
              'underscore': 0x1F, 'at': 0x00, 'BackSpace': 0x7F, 'Return': 0x0A, 'KP_Enter': 0x0A,
              'space': 0x20}

MENU = [
    ('&File', [('&New  editor   ', ID_NEW), ('&Open...   \tF3', ID_OPEN), ('&Save   \tF2', ID_SAVE),
               ('S&ave as...   ', ID_SAVEAS), None, ('E&xit   ', ID_EXIT)]),
    ('&Edit', [('C&ut   \tShift+Del', ID_CUT), ('&Delete  \tCtrl+Del', ID_DELETE),
               ('&Copy   \tCtrl+Ins', ID_COPY), ('&Paste   \tShift+Ins', ID_PASTE), None,
               ('Select all   \tCtrl+A', ID_SELALL)]),
    ('&Action', [('Co&mpile   \tF8', ID_COMPILE), ('&Run   \tF9', ID_RUN)]),
    ('&Help', [('Rules in english', ID_RULES_EN), ('Rules in russian', ID_RULES_RU), ('About', ID_ABOUT)]),
]
# the port's additions: commands of the window, not of the original
ID_UNDO, ID_REDO, ID_FINDTEXT, ID_FINDNEXT = 2001, 2002, 2003, 2004
MENU_MODERN = [
    ('&File', [('&New  editor   ', ID_NEW), ('&Open...   \tCtrl+O', ID_OPEN), ('&Save   \tCtrl+S, F2', ID_SAVE),
               ('S&ave as...   ', ID_SAVEAS), None, ('E&xit   ', ID_EXIT)]),
    ('&Edit', [('U&ndo   \tCtrl+Z', ID_UNDO), ('&Redo   \tCtrl+Shift+Z', ID_REDO), None,
               ('C&ut   \tCtrl+X', ID_CUT), ('&Delete  \tDel', ID_DELETE),
               ('&Copy   \tCtrl+C', ID_COPY), ('&Paste   \tCtrl+V', ID_PASTE), None,
               ('Select all   \tCtrl+A', ID_SELALL), None,
               ('&Find...   \tCtrl+F', ID_FINDTEXT), ('Find &next   \tF3', ID_FINDNEXT)]),
    ('&Action', [('Co&mpile   \tF8', ID_COMPILE), ('&Run   \tF9', ID_RUN)]),
    ('&Help', [('Rules in english', ID_RULES_EN), ('Rules in russian', ID_RULES_RU), ('About', ID_ABOUT)]),
]


def control_glyph(b):
    """what the port shows for a byte with no printable character"""
    return '\u25a1'


def display_char(b):
    if b < 0x20 or b == 0x7F:
        return control_glyph(b)
    try:
        return bytes([b]).decode(CHARSET)
    except UnicodeDecodeError:
        return control_glyph(b)


class App:
    def __init__(self, args):
        import tkinter as tk
        import tkinter.font as tkfont
        self.tk = tk
        self.args = args
        self.gamedir = args.game_dir
        self.root = root = tk.Tk()
        root.title(TITLE0)
        self.font = self.pick_font(tkfont, args.font)
        cw = max(self.font.measure(c) for c in 'W0m')
        lh = self.font.metrics('linespace')
        self.ed = Editor(self, cw, lh, fixes=not args.no_fixes, additions=not args.no_fixes)
        self.runner = DosRunner(self.gamedir, args.dosbox, args.dosbox_conf, args.dosbox_option)
        self.make_menu()
        self.status_frame = tk.Frame(root, height=lh + 6)
        self.status_frame.pack(side='bottom', fill='x')
        self.status_frame.pack_propagate(False)
        self.parts = [tk.Label(self.status_frame, text=t, anchor='w', bd=1, relief='sunken', padx=2)
                      for t in ('1 : 1', '', COPYRIGHT)]
        self.sbar = tk.Scrollbar(root, orient='vertical', command=self.on_scroll, takefocus=0)
        self.sbar.pack(side='right', fill='y')
        # the original window (320x500 with its frame) has a client area of 287x441:
        # 35 columns and 28 rows of Fixedsys; the port's own size: 80 x 30
        if self.ed.additions:
            size = (80 * cw, 30 * lh)
        else:
            size = (35 * cw + 7, 28 * lh)
        self.canvas = tk.Canvas(root, bg=WHITE, highlightthickness=0, bd=0, cursor='arrow', takefocus=1,
                                width=size[0], height=size[1])
        self.canvas.pack(side='left', fill='both', expand=True)
        self.rows = {}          # row -> what is drawn there
        self.cursor_item = None
        self.dirty = False
        self.shown_status = None
        self.last_find = ''
        self.bind()
        self.canvas.focus_set()
        root.protocol('WM_DELETE_WINDOW', lambda: self.command(ID_EXIT))
        self.timer_id = root.after(170, self.timer)
        if args.file:
            root.after_idle(lambda: self.ed.guarded(self.ed.open_path, os.path.abspath(args.file), self.ed.additions))

    @staticmethod
    def pick_font(tkfont, name):
        if name:
            fam, _, size = name.partition(':')
            return tkfont.Font(family=fam, size=int(size or 10))
        if os.name == 'nt' and 'Fixedsys' in tkfont.families():
            return tkfont.Font(family='Fixedsys', size=9)
        return tkfont.nametofont('TkFixedFont')

    def make_menu(self):
        tk = self.tk
        bar = tk.Menu(self.root, tearoff=0)
        for title, items in MENU_MODERN if self.ed.additions else MENU:
            m = tk.Menu(bar, tearoff=0)
            for it in items:
                if it is None:
                    m.add_separator()
                    continue
                label, cmd = it
                label, _, acc = label.partition('\t')
                u = label.find('&')
                m.add_command(label=label.replace('&', ''), underline=u, accelerator=acc,
                              command=lambda c=cmd: self.command(c))
            u = title.find('&')
            bar.add_cascade(label=title.replace('&', ''), underline=u, menu=m)
        self.root.config(menu=bar)

    def bind(self):
        c = self.canvas
        c.bind('<KeyPress>', self.on_key)
        c.bind('<KeyRelease>', self.on_keyup)
        c.bind('<Button-1>', lambda e: self.mouse('down', e))
        c.bind('<B1-Motion>', lambda e: self.mouse('move', e))
        c.bind('<ButtonRelease-1>', lambda e: self.mouse('up', e))
        c.bind('<Button-2>' if sys.platform == 'darwin' else '<Button-3>', lambda e: self.mouse('right', e))
        c.bind('<Configure>', self.on_configure)
        c.bind('<FocusIn>', lambda e: self.activate(True))
        c.bind('<FocusOut>', lambda e: self.activate(False))
        self.status_frame.bind('<Configure>', self.layout_status)
        if self.ed.additions:
            # the wheel, over the text and over the scroll bar (instead of Tk's own binding,
            # which would step the cursor like the scroll bar's arrows)
            for w in (c, self.sbar):
                w.bind('<MouseWheel>', self.on_wheel)
                w.bind('<Shift-MouseWheel>', lambda e: self.on_wheel(e, True))
                for n, lines in ((4, -3), (5, 3)):      # X11 (Tk 8.6 knows no buttons 6, 7)
                    w.bind('<Button-%d>' % n, lambda e, ln=lines: self.wheel(ln, bool(e.state & 1)))
            c.bind('<Double-Button-1>', lambda e: self.mouse('double', e))
            c.bind('<Triple-Button-1>', lambda e: self.mouse('triple', e))
        self.wheel_rest = 0

    def on_wheel(self, e, horizontal=False):
        """<MouseWheel>: Windows 120 per notch (less with fine-grained wheels), macOS
        about 1 per line"""
        if sys.platform == 'darwin':
            lines = -e.delta
        else:
            self.wheel_rest += e.delta
            notches = int(self.wheel_rest / 120)
            self.wheel_rest -= notches * 120
            lines = -3 * notches
        return self.wheel(lines, horizontal)

    def wheel(self, lines, horizontal):
        if lines:
            self.ed.guarded(self.ed.wheel, lines, horizontal)
        return 'break'

    # -- host services for the editor --------------------------------------

    def status(self, text):
        if text != self.shown_status:
            self.parts[0].config(text=text)
            self.shown_status = text

    def invalidate(self):
        if not self.dirty:
            self.dirty = True
            self.root.after_idle(self.paint)

    def fault(self, what):
        sys.stderr.write('rw1edit: stopped where the original would crash or hang: %s\n' % what)

    def message(self, kind, title, text):
        from tkinter import messagebox
        if kind == 'yesnocancel':
            r = messagebox.askyesnocancel(title, text, icon='warning', parent=self.root)
            return IDYES if r else IDNO if r is False else IDCANCEL
        if kind == 'error':
            messagebox.showerror(title, text, parent=self.root)
        else:
            messagebox.showinfo(title, text, parent=self.root)
        return 1

    FILETYPES = [('RW1 files ', ('*.rw1', '*.RW1', '*.Rw1')), ('All Files(*.*)', '*')]

    def open_dialog(self, initialdir):
        from tkinter import filedialog
        p = filedialog.askopenfilename(parent=self.root, initialdir=initialdir, filetypes=self.FILETYPES)
        return os.path.normpath(p) if p else ''

    def save_dialog(self, initialdir):
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(parent=self.root, initialdir=initialdir, filetypes=self.FILETYPES,
                                         defaultextension='.rw1')
        return os.path.normpath(p) if p else ''

    def clipboard_get(self):
        try:
            text = self.root.clipboard_get()
        except self.tk.TclError:
            return None
        # CF_TEXT: Windows line ends, the ANSI code page
        text = text.replace('\r\n', '\n').replace('\n', '\r\n')
        return text.encode(CHARSET, errors='replace')

    def clipboard_set(self, data):
        text = data.decode(CHARSET, errors='replace').replace('\r\n', '\n')
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def set_title(self, text):
        self.root.title(text)

    def quit(self):
        self.root.after_cancel(self.timer_id)
        self.root.update_idletasks()        # (a pending repaint)
        self.root.destroy()

    def new_editor(self):
        exe = sys.executable
        if os.name == 'nt' and os.path.basename(exe).lower() == 'python.exe':
            w = os.path.join(os.path.dirname(exe), 'pythonw.exe')
            if os.path.isfile(w):
                exe = w
        a = self.args
        opts = ['--game-dir', a.game_dir]
        if a.dosbox:
            opts += ['--dosbox', a.dosbox]
        for c in a.dosbox_conf:
            opts += ['--dosbox-conf', c]
        opts += ['--dosbox-option=' + o for o in a.dosbox_option]
        if a.font:
            opts += ['--font', a.font]
        if a.no_fixes:
            opts.append('--no-fixes')
        try:
            subprocess.Popen([exe, os.path.abspath(__file__)] + opts)     # (an empty text)
        except OSError:
            return False
        return True

    def open_help(self, name):
        import webbrowser
        html = find_file(self.gamedir, 'html')
        page = html and find_file(html, name)
        if not page:
            return False
        try:
            from pathlib import Path
            return webbrowser.open(Path(os.path.abspath(page)).as_uri())
        except Exception:      # noqa: BLE001 - any failure means "could not start it"
            return False

    def compile(self, path):
        err = self.runner.start('RW1_COMP.EXE', path, pause=True, copy_back='.RW0')
        if err:
            self.message('error', 'Error', err)

    def run(self, path):
        err = self.runner.start('RW1_DUEL.EXE', path, args=' -s0')
        if err:
            self.message('error', 'Error', err)

    # -- events -------------------------------------------------------------

    def command(self, cmd):
        ed = self.ed
        ed.undo_kind = None
        if cmd == ID_UNDO:
            ed.guarded(ed.undo)
        elif cmd == ID_REDO:
            ed.guarded(ed.redo)
        elif cmd == ID_FINDTEXT:
            self.find_dialog()
        elif cmd == ID_FINDNEXT:
            self.find_next()
        else:
            ed.guarded(ed.wm_command, cmd)

    def find_dialog(self):
        from tkinter import simpledialog
        text = simpledialog.askstring('Find', 'Find what:', initialvalue=self.last_find, parent=self.root)
        if text:
            self.last_find = text
            self.find_next()

    def find_next(self):
        if not self.last_find:
            self.find_dialog()
        elif not self.ed.guarded(self.ed.find, self.last_find.encode(CHARSET, errors='replace')):
            self.message('info', 'Find', 'Cannot find "%s"' % self.last_find)

    def on_key(self, e):
        ks = e.keysym
        state = e.state
        ctrl = bool(state & 0x4)
        alt = bool(state & 0x20000) if os.name == 'nt' else bool(state & 0x8)
        if self.ed.additions and self.shortcut(e, ctrl, alt):
            return 'break'
        if (alt and not ctrl) or ks in ('Alt_L', 'Alt_R', 'Meta_L', 'Meta_R', 'Super_L', 'Super_R'):
            return None         # WM_SYSKEYDOWN: menus
        vk = KEYSYM_VK.get(ks, 0xFF)
        if vk == 0x79:          # F10 opens the menu
            return None
        self.ed.guarded(self.ed.wm_keydown, vk)
        ch = self.char_of(e, ctrl, alt)
        if self.ed.additions and typed_control(ch):
            ch = None
        if ch is not None:
            self.ed.guarded(self.ed.wm_char, ch)
        return 'break'

    def shortcut(self, e, ctrl, alt):
        """the additions' keys: Ctrl+C X V S O Z (Shift: redo) F (Cmd on a Mac), F3"""
        command = sys.platform == 'darwin' and bool(e.state & 0x8)
        key = e.keysym.lower()
        if os.name == 'nt' and 0x41 <= getattr(e, 'keycode', 0) <= 0x5A:
            key = chr(e.keycode).lower()        # the key, whatever the keyboard layout
        ed = self.ed
        if (ctrl and not alt) or command:
            if key == 'c':
                ed.guarded(ed.with_keys, 0, 1, ed.wm_keydown, VK_INSERT)
            elif key == 'x':
                ed.guarded(ed.with_keys, 1, 0, ed.wm_keydown, VK_DELETE)
            elif key == 'v':
                ed.guarded(ed.with_keys, 1, 0, ed.wm_keydown, VK_INSERT)
            elif key == 's':
                self.command(ID_SAVE)
            elif key == 'o':
                self.command(ID_OPEN)
            elif key == 'z':
                self.command(ID_REDO if e.state & 1 else ID_UNDO)
            elif key == 'f':
                self.command(ID_FINDTEXT)
            else:
                return False
            return True
        if e.keysym == 'F3' and not alt:
            self.command(ID_FINDNEXT)
            return True
        return False

    @staticmethod
    def char_of(e, ctrl, alt):
        """the WM_CHAR TranslateMessage would make of this key, or None"""
        ks = e.keysym
        if ks in ('Delete', 'KP_Delete') or ks in KEYSYM_VK:
            return None
        if ctrl and not alt:
            if len(ks) == 1 and ks.isalpha() and ks.isascii():
                return ord(ks.upper()) - 64
            return CTRL_CHARS.get(ks)
        ch = e.char
        if not ch:
            return None
        if len(ch) != 1:
            ch = ch[:1]
        if ch == '\n':
            ch = '\r'
        if ord(ch) < 0x20 and ch not in '\b\t\r\x1b':
            return None
        try:
            return ch.encode(CHARSET)[0]
        except UnicodeEncodeError:
            return 0x3F

    def on_keyup(self, e):
        vk = KEYSYM_VK.get(e.keysym)
        if vk in (VK_SHIFT, VK_CONTROL):
            self.ed.wm_keyup(vk)

    def inside(self, e):
        return 0 <= e.x < self.canvas.winfo_width() and 0 <= e.y < self.canvas.winfo_height()

    def mouse(self, what, e):
        self.canvas.focus_set()
        ed = self.ed
        if what == 'down':
            if ed.additions and e.state & 1:
                ed.guarded(ed.shift_click, e.x, e.y)
            else:
                ed.guarded(ed.wm_lbuttondown, e.x, e.y)
        elif what in ('double', 'triple'):
            ed.guarded(ed.select_at, e.x, e.y, what == 'triple')
        elif what == 'right':
            ed.guarded(ed.wm_rbuttondown, e.x, e.y)
        elif what == 'up' and ed.additions:
            ed.wm_lbuttonup()   # (the original misses a release outside its window: Shift stays down)
        elif not self.inside(e):
            return              # outside the client area the original gets no mouse messages
        elif what == 'move':
            self.ed.guarded(self.ed.wm_mousemove, e.x, e.y, True)
        else:
            self.ed.wm_lbuttonup()

    def on_scroll(self, *a):
        if a[0] == 'scroll':
            n = int(a[1])
            if a[2] == 'units':
                code = SB_LINEUP if n < 0 else SB_LINEDOWN
            else:
                code = SB_PAGEUP if n < 0 else SB_PAGEDOWN
            self.ed.guarded(self.ed.wm_vscroll, code)
        elif a[0] == 'moveto':
            first, last = self.sbar.get()
            span = 1.0 - (last - first)
            pos = int(round(float(a[1]) / span * 100)) if span > 0 else 0
            self.ed.guarded(self.ed.wm_vscroll, SB_THUMBTRACK, max(0, min(100, pos)))

    def on_configure(self, e):
        h = e.height + self.status_frame.winfo_reqheight()
        self.ed.wm_size(e.width, h)
        self.layout_status()
        self.rows.clear()
        self.canvas.delete('all')
        self.cursor_item = None
        self.invalidate()

    def layout_status(self, e=None):
        """FUN_00403630: parts end at 6 characters, 14 characters before the right edge, the edge"""
        w = self.status_frame.winfo_width()
        cw = self.ed.cw
        edges = [0, 6 * cw, max(6 * cw, w - 14 * cw), w]
        for i, part in enumerate(self.parts):
            part.place(x=edges[i], y=0, width=max(1, edges[i + 1] - edges[i]), relheight=1)

    def activate(self, on):
        if on and self.ed.additions:
            # Shift and Ctrl may have been let go of in another window (or a dialog)
            self.ed.shift = self.ed.ctrl = self.ed.selecting = 0
        if on != bool(self.ed.active):
            self.ed.wm_activate(on)
            self.invalidate()

    def timer(self):
        self.ed.wm_timer()
        self.timer_id = self.root.after(170, self.timer)

    # -- WM_PAINT -----------------------------------------------------------

    def paint(self):
        self.dirty = False
        ed = self.ed
        c = self.canvas
        if not ed.active:
            # the original only copies its bitmap: no new text, no cursor
            if self.cursor_item is not None:
                c.itemconfigure(self.cursor_item, state='hidden')
            return
        pos = ed.scroll_pos()
        h = max(1, c.winfo_height())
        thumb = min(0.5, 17.0 / h)
        self.sbar.set(pos / 100.0 * (1 - thumb), pos / 100.0 * (1 - thumb) + thumb)
        cw, lh = ed.cw, ed.lh
        ncols = c.winfo_width() // cw + 1
        drawn = set()
        for r, text, fg, bg in ed.paint_rows():
            drawn.add(r)
            key = (ed.hscroll, text, tuple(fg), tuple(bg))
            if self.rows.get(r, (None,))[0] == key:
                continue
            self.draw_row(r, key, text, fg, bg, ncols)
        for r in list(self.rows):
            if r not in drawn:
                c.delete('row%d' % r)
                del self.rows[r]
        if self.cursor_item is None:
            self.cursor_item = c.create_rectangle(0, 0, 0, 0, outline=CURSOR_COLOR, fill=WHITE)
        if ed.caret:
            x = ed.col * cw
            if ed.insert == 0:
                c.coords(self.cursor_item, x, ed.row * lh, x + cw - 1, (ed.row + 1) * lh - 1)
                c.itemconfigure(self.cursor_item, fill=WHITE)
            else:
                y = (ed.row + 1) * lh
                c.coords(self.cursor_item, x, y - 3, x + cw - 1, y - 2)
                c.itemconfigure(self.cursor_item, fill=CURSOR_COLOR)
            c.itemconfigure(self.cursor_item, state='normal')
            c.tag_raise(self.cursor_item)
        else:
            c.itemconfigure(self.cursor_item, state='hidden')

    def draw_row(self, r, key, text, fg, bg, ncols):
        c = self.canvas
        tag = 'row%d' % r
        c.delete(tag)
        cw, lh = self.ed.cw, self.ed.lh
        y = r * lh
        first = self.ed.hscroll
        last = min(len(text), first + ncols)
        k = max(0, first)
        while k < last:
            e = k + 1
            if 0x20 <= text[k] < 0x7F:
                # a run of ASCII characters in one colour; anything else on its own,
                # in case the font has to borrow the glyph from a wider one
                while e < last and fg[e] == fg[k] and bg[e] == bg[k] and 0x20 <= text[e] < 0x7F:
                    e += 1
            x = (k - first) * cw
            if bg[k] != WHITE:
                c.create_rectangle(x, y, x + (e - k) * cw - 1, y + lh - 1, fill=bg[k], outline='', tags=tag)
            c.create_text(x, y, anchor='nw', text=''.join(display_char(b) for b in text[k:e]), fill=fg[k],
                          font=self.font, tags=tag)
            k = e
        self.rows[r] = (key,)

    def mainloop(self):
        self.root.mainloop()


def default_game_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    if find_file(here, 'RW1_COMP.EXE'):
        return here
    return os.getcwd()


def main(argv=None):
    ap = argparse.ArgumentParser(description='RW1-EDITOR 1.0.4 (Robot Warfare 1), ported to Python/Tk.')
    ap.add_argument('--game-dir', metavar='DIR', default=None,
                    help='folder with RW1_COMP.EXE, RW1_DUEL.EXE and html\\ (default: the folder of this '
                         'script if they are there, else the current folder)')
    ap.add_argument('--dosbox', metavar='PATH',
                    help='DOSBox for Compile and Run (default: $DOSBOX, else dosbox, dosbox-staging or '
                         'dosbox-x on the PATH)')
    ap.add_argument('--dosbox-conf', metavar='FILE', action='append', default=[],
                    help='a configuration file for DOSBox (repeatable); its [autoexec] is skipped')
    ap.add_argument('--dosbox-option', metavar='ARG', action='append', default=[],
                    help='an extra command-line argument for DOSBox (repeatable)')
    ap.add_argument('--font', metavar='FAMILY[:SIZE]', help='a fixed-width font instead of the default')
    ap.add_argument('--no-fixes', action='store_true',
                    help="behave exactly like the original: its bugs, none of the additions (it only "
                         "stops where the original crashes or hangs)")
    ap.add_argument('file', nargs='?', help='a file to open (a new one if it does not exist)')
    ap.add_argument('--version', action='version', version='%(prog)s ' + VERSION)
    args = ap.parse_args(argv)
    args.game_dir = os.path.abspath(args.game_dir) if args.game_dir else default_game_dir()
    App(args).mainloop()


if __name__ == '__main__':
    main()
