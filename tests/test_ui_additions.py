"""test_ui_additions.py: the window's part of the additions - the keys, the mouse,
the menu and the window size - with key and mouse events made up in Python (the
clipboard and the dialogs are replaced; the window opens on the left monitor)"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rw1edit as rw  # noqa: E402

SHIFT, CTRL = 0x1, 0x4
BAD = []


def check(cond, what):
    print('%-8s %s' % ('ok' if cond else 'FAILED', what))
    if not cond:
        BAD.append(what)


def make(no_fixes=False):
    args = rw.argparse.Namespace(game_dir=os.getcwd(), dosbox=None, dosbox_conf=[], dosbox_option=[], font=None,
                                 no_fixes=no_fixes, file=None)
    app = rw.App(args)
    app.root.geometry('+-2400+100')
    app.root.update()
    app.activate(True)
    app.clip = None
    app.clipboard_get = lambda: app.clip
    app.clipboard_set = lambda data: setattr(app, 'clip', data)
    app.asked = []
    app.message = lambda kind, title, text: app.asked.append((kind, text)) or rw.IDNO
    return app


def key(app, keysym, char='', state=0):
    """a key as Tk reports it (keycode: the Windows virtual key of a letter)"""
    code = ord(keysym.upper()) if len(keysym) == 1 and keysym.isalpha() else 0
    if state & CTRL:
        app.on_key(SimpleNamespace(keysym='Control_L', char='', state=0, keycode=0x11))
    if state & SHIFT:
        app.on_key(SimpleNamespace(keysym='Shift_L', char='', state=0, keycode=0x10))
    app.on_key(SimpleNamespace(keysym=keysym, char=char, state=state, keycode=code))
    if state & SHIFT:
        app.on_keyup(SimpleNamespace(keysym='Shift_L'))
    if state & CTRL:
        app.on_keyup(SimpleNamespace(keysym='Control_L'))


def type_text(app, text):
    for ch in text:
        key(app, {' ': 'space', '\r': 'Return'}.get(ch, ch), ch)


def texts(app):
    return [line.text() for line in app.ed.lines()]


def main():
    app = make()
    ed = app.ed
    check((ed.max_col, ed.max_row) == (79, 29), 'the window: 80 x 30 characters (%d x %d)'
          % (ed.max_col + 1, ed.max_row + 1))
    edit = app.root.nametowidget(app.root['menu']).winfo_children()[1]
    labels = [edit.entrycget(i, 'label') for i in range(edit.index('end') + 1) if edit.type(i) == 'command']
    check(labels[:2] == ['Undo   ', 'Redo   '] and 'Find...   ' in labels, 'Edit menu: %r' % labels)

    type_text(app, 'hello world')
    key(app, 'b', '\x02', CTRL)
    key(app, 'Return', '\r', CTRL)
    check(texts(app) == [b'hello world'], 'Ctrl+B, Ctrl+Enter type nothing')
    for _ in range(5):
        key(app, 'Left', '', SHIFT)
    key(app, 'c', '\x03', CTRL)
    check(app.clip == b'world' and texts(app) == [b'hello world'], 'Ctrl+C copies')
    key(app, 'x', '\x18', CTRL)
    check(app.clip == b'world' and texts(app) == [b'hello'], 'Ctrl+X cuts')
    app.clip = b'there'
    key(app, 'v', '\x16', CTRL)
    check(texts(app) == [b'hello there'], 'Ctrl+V pastes')
    check((ed.shift, ed.ctrl) == (0, 0), 'Shift and Ctrl up afterwards')
    key(app, 'z', '\x1a', CTRL)
    check(texts(app) == [b'hello'], 'Ctrl+Z undoes the paste (%r)' % texts(app))
    key(app, 'Z', '\x1a', CTRL | SHIFT)
    check(texts(app) == [b'hello there'], 'Ctrl+Shift+Z redoes it')
    # a Russian keyboard: the key is still the one with C on it
    app.on_key(SimpleNamespace(keysym='Control_L', char='', state=0, keycode=0x11))
    app.on_key(SimpleNamespace(keysym='Cyrillic_es', char='\x03', state=CTRL, keycode=0x43))
    app.on_keyup(SimpleNamespace(keysym='Control_L'))
    check(texts(app) == [b'hello there'] or os.name != 'nt', 'Ctrl+C on a Russian layout types nothing')

    # mouse: click, Shift+click, double and triple click
    cw = ed.cw
    app.mouse('down', SimpleNamespace(x=2, y=2, state=0))
    app.mouse('up', SimpleNamespace(x=2, y=2, state=0))
    app.mouse('down', SimpleNamespace(x=5 * cw + 2, y=2, state=SHIFT))
    check((ed.c0, ed.c1) == (0, 5) and ed.has_selection(), 'Shift+click selects')
    app.mouse('up', SimpleNamespace(x=-50, y=-50, state=0))       # let go outside the window
    check((ed.shift, ed.selecting) == (0, 0), 'the button let go outside the window')
    app.mouse('double', SimpleNamespace(x=7 * cw + 2, y=2, state=0))
    check((ed.c0, ed.c1) == (6, 11), 'double click selects "there" (%d, %d)' % (ed.c0, ed.c1))
    app.mouse('triple', SimpleNamespace(x=2, y=2, state=0))
    check((ed.c0, ed.c1) == (0, 11), 'triple click selects the line')
    type_text(app, 'new')
    check(texts(app) == [b'new'], 'typing replaces the selection')

    # Find, F3
    type_text(app, '\rrobot ROBOT\rRobot')
    key(app, 'Home')
    key(app, 'Prior', '', CTRL)
    app.last_find = 'robot'
    key(app, 'F3')
    first = (ed.l0, ed.c0)
    key(app, 'F3')
    second = (ed.l0, ed.c0)
    check((first, second) == ((1, 0), (1, 6)), 'F3 finds the next one: %r %r' % (first, second))
    app.last_find = 'nowhere'
    key(app, 'F3')
    check(app.asked and 'Cannot find' in app.asked[-1][1], 'F3: "Cannot find"')

    # the wheel
    for n in range(60):
        type_text(app, '\rline %d' % n)
    key(app, 'Prior', '', CTRL)
    app.on_wheel(SimpleNamespace(delta=-120, state=0))
    check(ed.top_idx == 3, 'the wheel: 3 lines (%d)' % ed.top_idx)
    app.quit()

    # without the fixes: the original's window, menu and keys
    app = make(no_fixes=True)
    ed = app.ed
    check((ed.max_col, ed.max_row) == (34, 27), 'original window: 35 x 28')
    type_text(app, 'ab')
    key(app, 'b', '\x02', CTRL)
    check(texts(app) == [b'ab\x02'], 'original: Ctrl+B types a control character')
    app.on_wheel(SimpleNamespace(delta=-120, state=0))
    edit = app.root.nametowidget(app.root['menu']).winfo_children()[1]
    check(edit.entrycget(0, 'label') == 'Cut   ', 'original Edit menu')
    app.quit()
    print('%d failed' % len(BAD))
    return len(BAD)


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
