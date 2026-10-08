"""test_fixes.py: the port's fixes (Editor(fixes=True)) one by one, against the
same steps without them (no original needed)"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ab  # noqa: E402
import rw1edit as rw  # noqa: E402
from scenarios import CTRL, LINES3, SHIFT, chars, keys  # noqa: E402


def run(steps, fixes, host=None):
    """fixes: False the original, True the port as it starts (fixes and additions),
    'fixes' the fixes alone (as the fixed RW1_EDIT.EXE)"""
    host = host or ab.Host()
    ed = rw.Editor(host, 8, 15, fixes=bool(fixes), additions=fixes is True)
    ed.wm_size(287, 441)
    ed.ticks = 2
    for step in steps:
        clip = ab.step_clip(step)
        if clip is not None:
            host.clip = clip
        ab.apply_port(step, ed, host, (287, 441))
    return ed, host


def texts(ed):
    return [line.text() for line in ed.lines()]


CHECKS = []


def check(f):
    CHECKS.append(f)
    return f


@check
def drag_right_edge():
    steps = chars('some text') + [('lclick', 16, 5), ('drag', 283, 5)]
    a, _ = run(steps, False)
    b, _ = run(steps, True)
    assert a.faults and not b.faults, (a.faults, b.faults)
    assert (b.hscroll, b.col) == (0, 34) and (b.c0, b.c1) == (2, 34), (b.hscroll, b.col, b.c0, b.c1)


@check
def delete_upward_selection():
    steps = LINES3 + keys(rw.VK_HOME, rw.VK_RIGHT, rw.VK_RIGHT, SHIFT, rw.VK_UP, rw.VK_UP) + \
        [('keyup', SHIFT), ('cmd', rw.ID_DELETE)]
    a, _ = run(steps, False)
    b, _ = run(steps, True)
    assert a.faults and not b.faults, (a.faults, b.faults)
    # from line 0 column 2 to line 2 column 2, line breaks included (the original keeps one)
    assert texts(b) == [b'fiird line'], texts(b)
    assert (b.index_of(b.cur), b.hscroll + b.col) == (0, 2)
    c, _ = run(steps, 'fixes')
    assert not c.faults and texts(c) == [b'fi', b'ird line'], texts(c)


@check
def delete_past_line_end():
    steps = chars('ab\rcdef\rgh\rlast') + keys(rw.VK_UP, rw.VK_UP, rw.VK_UP) + keys(rw.VK_END) + \
        keys(rw.VK_RIGHT, rw.VK_RIGHT, SHIFT, rw.VK_DOWN) + [('keyup', SHIFT), ('cmd', rw.ID_CUT)]
    a, _ = run(steps, False)
    b, hb = run(steps, True)
    assert a.faults and not b.faults, (a.faults, b.faults)
    # the selection: line 0 after its end to line 1 column 4 (= its end): nothing of line 2 goes
    assert texts(b) == [b'ab', b'gh', b'last'], texts(b)
    assert hb.clip == b'\r\ncdef', hb.clip
    c, hc = run(steps, 'fixes')
    assert not c.faults and texts(c) == [b'ab', b'', b'gh', b'last'] and hc.clip == b'\r\ncdef', texts(c)


@check
def select_all_copy_one_line():
    steps = chars('abc def ghi') + [('cmd', rw.ID_SELALL), ('copy',)]
    a, _ = run(steps, False)
    b, hb = run(steps, True)
    assert a.faults and not b.faults, (a.faults, b.faults)
    assert hb.clip == b'abc def ghi', hb.clip


@check
def select_all_cut():
    for text in ('one line', 'one\rtwo\rthree'):
        b, hb = run(chars(text) + [('cmd', rw.ID_SELALL), ('cmd', rw.ID_CUT)], True)
        assert not b.faults and texts(b) == [b''], (text, b.faults, texts(b))
        assert hb.clip == text.encode().replace(b'\r', b'\r\n'), hb.clip


@check
def select_all_copy_no_leftovers():
    steps = chars('one\r') + chars('a long last line') + chars('\x08' * 10) + [('cmd', rw.ID_SELALL), ('copy',)]
    a, ha = run(steps, False)
    b, hb = run(steps, True)
    assert ha.clip == b'one\r\na long last line', ha.clip      # the original: the old bytes too
    assert hb.clip == b'one\r\na long', hb.clip


@check
def copy_releases_ctrl():
    steps = chars('abc def\rx') + [('cmd', rw.ID_SELALL), ('cmd', rw.ID_COPY)]
    a, _ = run(steps, False)
    b, _ = run(steps, True)
    assert a.ctrl == 1 and b.ctrl == 0, (a.ctrl, b.ctrl)


@check
def last_line_kept():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'T.RW1')
        with open(p, 'wb') as f:
            f.write(b'line1\r\nline2 no newline')
        a = rw.Editor(ab.Host())
        b = rw.Editor(ab.Host(), fixes=True)
        a.load(p)
        b.load(p)
        assert texts(a) == [b'line1'] and texts(b) == [b'line1', b'line2 no newline'], (texts(a), texts(b))
        out = os.path.join(d, 'OUT.RW1')
        b.save(out)
        with open(out, 'rb') as f:
            assert f.read() == b'line1\r\nline2 no newline\r\n'


@check
def save_new_text_asks():
    with tempfile.TemporaryDirectory() as d:
        for fixes in (False, True):
            host = ab.Host()
            host.save_path = os.path.join(d, 'NAMED.RW1')
            ed = rw.Editor(host, cwd=d, fixes=fixes)
            old = os.getcwd()
            os.chdir(d)
            try:
                ed.guarded(ed.wm_char, ord('x'))
                ed.guarded(ed.wm_command, rw.ID_SAVE)
            finally:
                os.chdir(old)
            names = sorted(os.listdir(d))
            if fixes:
                assert names == ['NAMED.RW1', 'noname.rw1'] and ed.filename == host.save_path, names
                assert host.title == rw.TITLE % host.save_path and not ed.modified
            else:
                assert names == ['noname.rw1'], names
        # "File is not saved. Save it?" -> Yes -> the name dialog -> cancelled: nothing happens
        host = ab.Host()
        host.answers = [rw.IDYES]
        quit_called = []
        host.quit = lambda: quit_called.append(1)
        ed = rw.Editor(host, cwd=d, fixes=True)
        ed.guarded(ed.wm_char, ord('x'))
        ed.guarded(ed.wm_command, rw.ID_EXIT)
        assert not quit_called


@check
def ctrl_y_first_row():
    steps = sum((chars('line %d\r' % n) for n in range(40)), []) + keys(rw.VK_UP) * 30 + chars('\x19')
    a, _ = run(steps, False)
    b, _ = run(steps, True)
    assert a.index_of(a.top) is None, 'the original keeps the deleted line on the screen'
    assert b.top is b.cur and b.index_of(b.top) == b.top_idx, (b.index_of(b.top), b.top_idx)


@check
def ctrl_right_empty_line():
    steps = chars('abc\r') + keys(rw.VK_UP, rw.VK_END, CTRL, rw.VK_RIGHT) + [('keyup', CTRL)]
    a, _ = run(steps, False)
    b, _ = run(steps, True)
    assert a.hscroll + a.col == 256, (a.hscroll, a.col)
    assert (b.hscroll, b.col, b.index_of(b.cur)) == (0, 0, 1), (b.hscroll, b.col)


@check
def ctrl_left_empty():
    a, _ = run(keys(CTRL, rw.VK_LEFT), False)
    b, _ = run(keys(CTRL, rw.VK_LEFT), True)
    assert a.faults and not b.faults


@check
def mouse_wheel():
    ed, _ = run(sum((chars('line %d\r' % n) for n in range(60)), []), True)
    assert (ed.top_idx, ed.row, ed.index_of(ed.cur)) == (33, 27, 60), (ed.top_idx, ed.row)
    ed.wheel(-3)
    assert (ed.top_idx, ed.row, ed.index_of(ed.cur), ed.index_of(ed.top)) == (30, 27, 57, 30)
    ed.wheel(-1000)
    assert (ed.top_idx, ed.row, ed.index_of(ed.cur), ed.index_of(ed.top)) == (0, 27, 27, 0)
    ed.wheel(5)
    assert (ed.top_idx, ed.index_of(ed.cur), ed.index_of(ed.top)) == (5, 32, 5)
    ed.wheel(1000)
    assert (ed.top_idx, ed.row, ed.index_of(ed.cur), ed.index_of(ed.top)) == (33, 27, 60, 33)
    # sideways: the cursor keeps its column on the screen, the text column changes
    ed2, _ = run(chars('x' * 100) + keys(rw.VK_HOME) + keys(rw.VK_RIGHT) * 5, True)
    ed2.wheel(30, True)
    assert (ed2.hscroll, ed2.col) == (30, 5), (ed2.hscroll, ed2.col)
    ed2.wheel(-100, True)
    assert ed2.hscroll == 0
    ed2.wheel(1000, True)
    assert ed2.hscroll + ed2.col == 256
    assert not ed.faults and not ed2.faults


def select_back(n):
    """Shift+Left n times, then Shift up"""
    return keys(SHIFT) + keys(rw.VK_LEFT) * n + [('keyup', SHIFT)]


@check
def typing_replaces_selection():
    b, _ = run(chars('hello world') + select_back(5) + chars('X'), True)
    assert texts(b) == [b'hello X'] and b.no_sel, texts(b)
    a, _ = run(chars('hello world') + select_back(5) + chars('X'), False)
    assert texts(a) == [b'hello Xworld'], texts(a)          # the original just types
    b, _ = run(LINES3 + keys(rw.VK_HOME, rw.VK_RIGHT, rw.VK_RIGHT, SHIFT, rw.VK_UP, rw.VK_UP) +
               [('keyup', SHIFT)] + chars('Z'), True)
    assert texts(b) == [b'fiZird line'], texts(b)


@check
def backspace_del_delete_selection():
    for key in (chars('\x08'), keys(rw.VK_DELETE), keys(CTRL, rw.VK_DELETE) + [('keyup', CTRL)]):
        b, h = run(chars('hello world') + select_back(6) + key, True)
        assert texts(b) == [b'hello'] and h.clip is None, (key, texts(b), h.clip)
    b, h = run(chars('hello world') + select_back(6) + keys(SHIFT, rw.VK_DELETE) + [('keyup', SHIFT)], True)
    assert texts(b) == [b'hello'] and h.clip == b' world', (texts(b), h.clip)
    # without a selection: Del deletes a character, Shift+Del and Ctrl+Del nothing
    b, _ = run(chars('abc') + keys(rw.VK_HOME, rw.VK_DELETE), True)
    assert texts(b) == [b'bc']
    b, _ = run(chars('abc') + keys(rw.VK_HOME, CTRL, rw.VK_DELETE), True)
    assert texts(b) == [b'abc'] and not b.modified or texts(b) == [b'abc']


@check
def moving_drops_selection():
    b, _ = run(chars('hello world') + select_back(5) + keys(rw.VK_LEFT), True)
    assert not b.has_selection() and b.no_sel
    a, _ = run(chars('hello world') + select_back(5) + keys(rw.VK_LEFT), False)
    assert not a.no_sel                                         # the original keeps it
    b, _ = run(chars('hello world') + select_back(5) + [('lclick', 8, 5)], True)
    assert not b.has_selection()
    b, _ = run(chars('hello world') + select_back(5) + chars('\x1b'), True)
    assert not b.has_selection() and texts(b) == [b'hello world']


@check
def shift_goes_on():
    b, _ = run(chars('hello world') + keys(rw.VK_HOME) + keys(SHIFT, rw.VK_RIGHT, rw.VK_RIGHT) +
               [('keyup', SHIFT)] + keys(SHIFT, rw.VK_RIGHT) + [('keyup', SHIFT)], True)
    assert (b.l0, b.c0, b.l1, b.c1) == (0, 0, 0, 3), (b.l0, b.c0, b.l1, b.c1)
    a, _ = run(chars('hello world') + keys(rw.VK_HOME) + keys(SHIFT, rw.VK_RIGHT, rw.VK_RIGHT) +
               [('keyup', SHIFT)] + keys(SHIFT, rw.VK_RIGHT) + [('keyup', SHIFT)], False)
    assert (a.c0, a.c1) == (2, 3)                               # the original starts anew


@check
def paste_replaces_selection():
    b, _ = run(chars('hello world') + select_back(5) + [('paste', b'there')], True)
    assert texts(b) == [b'hello there'], texts(b)


@check
def shortcuts():
    b, h = run(chars('hello world') + select_back(5), True)
    b.with_keys(0, 1, b.wm_keydown, rw.VK_INSERT)               # Ctrl+C
    assert h.clip == b'world' and texts(b) == [b'hello world'] and (b.shift, b.ctrl) == (0, 0)
    b.with_keys(1, 0, b.wm_keydown, rw.VK_DELETE)               # Ctrl+X
    assert texts(b) == [b'hello'] and h.clip == b'world'
    h.clip = b'you'
    b.with_keys(1, 0, b.wm_keydown, rw.VK_INSERT)               # Ctrl+V (where "world" was)
    assert texts(b) == [b'hello you'] and (b.shift, b.ctrl) == (0, 0), texts(b)
    assert [rw.typed_control(c) for c in (0x03, 0x16, 0x0A, 0x00, 0x7F, 0x02)] == [True] * 6
    assert [rw.typed_control(c) for c in (0x01, 0x08, 0x09, 0x0D, 0x19, 0x1B, 0x41, None)] == [False] * 8


@check
def undo_redo():
    b, _ = run(chars('abc def') + chars('\r') + chars('xy'), True)
    assert texts(b) == [b'abc def', b'xy'] and b.modified
    steps = [texts(b)]
    while b.undo():
        steps.append(texts(b))
    # typing in a row is one step, Enter one, and the next typing one
    assert steps == [[b'abc def', b'xy'], [b'abc def', b''], [b'abc def'], [b'']], steps
    assert not b.modified and (b.index_of(b.cur), b.hscroll + b.col) == (0, 0)
    while b.redo():
        pass
    assert texts(b) == [b'abc def', b'xy'] and b.modified and (b.index_of(b.cur), b.col) == (1, 2)
    # Backspace in a row is one step; moving in between starts a new one
    b, _ = run(chars('abcdef') + chars('\x08\x08') + keys(rw.VK_LEFT) + chars('\x08'), True)
    b.undo()
    assert texts(b) == [b'abcd']
    b.undo()
    assert texts(b) == [b'abcdef']
    # a cut, Ctrl+Y, a paste over a selection
    b, _ = run(LINES3 + [('cmd', rw.ID_SELALL), ('cmd', rw.ID_CUT)], True)
    assert texts(b) == [b'']
    b.undo()
    assert texts(b) == [b'first line', b'second line', b'third line'] and b.has_selection()
    b, _ = run(LINES3 + keys(rw.VK_UP) + chars('\x19') + [('paste', b'P')], True)
    b.undo()
    b.undo()
    assert texts(b) == [b'first line', b'second line', b'third line'], texts(b)
    # after saving, undoing back to the saved text is "not modified"
    with tempfile.TemporaryDirectory() as d:
        b, _ = run(chars('one'), True)
        b.save(os.path.join(d, 'X.RW1'))
        b.wm_char(ord('!'))
        assert b.modified
        b.undo()
        assert texts(b) == [b'one'] and not b.modified


@check
def find():
    b, _ = run(chars('ROBOT "a"\r  robot STEP\rx\r% Привет\rend'), True)
    b.goto(0, 0)
    assert b.find(b'Robot') and (b.l0, b.c0, b.c1, b.index_of(b.cur), b.hscroll + b.col) == (0, 0, 5, 0, 5)
    assert b.find(b'robot') and (b.l0, b.c0) == (1, 2)
    assert b.find(b'ROBOT') and (b.l0, b.c0) == (0, 0)          # around the end
    # (Enter indents the lines after the indented one)
    assert b.find('ПРИВЕТ'.encode('cp1251')) and (b.l0, b.c0) == (3, 4)
    assert not b.find(b'nothing') and (b.l0, b.c0) == (3, 4)
    b.wm_char(ord('Q'))                                         # typing replaces what was found
    assert texts(b)[3] == b'  % Q', texts(b)
    # far down: the window follows
    c, _ = run(sum((chars('line %d\r' % n) for n in range(100)), []) + chars('needle'), True)
    c.goto(0, 0)
    assert c.find(b'needle') and c.index_of(c.top) == c.top_idx and c.top_idx <= 100 <= c.top_idx + c.max_row


@check
def mouse_selection():
    b, _ = run(chars('ROBOT "x"   STEP') + keys(rw.VK_HOME), True)
    b.shift_click(8 * 5 + 2, 5)
    assert (b.l0, b.c0, b.l1, b.c1) == (0, 0, 0, 5) and b.has_selection()
    b.shift_click(8 * 3 + 2, 5)                                 # from the same start
    assert (b.c0, b.c1) == (0, 3)
    b.select_at(8 * 1 + 2, 5, False)                            # double click in ROBOT
    assert (b.c0, b.c1, b.hscroll + b.col) == (0, 5, 5)
    b.select_at(8 * 10 + 2, 5, False)                           # in the spaces
    assert (b.c0, b.c1) == (9, 12), (b.c0, b.c1)
    b.select_at(8 * 6 + 2, 5, False)                            # on the quote
    assert (b.c0, b.c1) == (6, 7)
    b.select_at(8 * 2, 5, True)                                 # triple: the line
    assert (b.c0, b.c1) == (0, 16)


@check
def file_on_command_line():
    with tempfile.TemporaryDirectory() as d:
        b = rw.Editor(ab.Host(), fixes=True)
        new = os.path.join(d, 'NEW.RW1')
        b.open_path(new, True)
        assert texts(b) == [b''] and b.filename == new and b.host.title == rw.TITLE % new
        assert not b.host.messages
        a = rw.Editor(ab.Host())
        a.open_path(new, False)
        assert a.host.messages and 'Load file error' in a.host.messages[0][2]


def main():
    bad = 0
    for f in CHECKS:
        try:
            f()
            print('ok      %s' % f.__name__)
        except AssertionError as e:
            bad += 1
            print('FAILED  %s: %s' % (f.__name__, e))
    print('%d of %d failed' % (bad, len(CHECKS)))
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
