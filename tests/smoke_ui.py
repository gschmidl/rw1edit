"""smoke_ui.py [--keep SECONDS] [--font F]: the Tk window with simulated keys and
mouse clicks (event_generate, no real input); checks what the canvas shows.
The window opens on the left monitor (x -2400) unless --x says otherwise."""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import rw1edit as rw  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', type=float, default=0)
    ap.add_argument('--x', type=int, default=-2400)
    ap.add_argument('--font')
    ap.add_argument('--file', help='load this file first')
    a = ap.parse_args()
    args = rw.argparse.Namespace(game_dir=os.getcwd(), dosbox=None, dosbox_conf=[], dosbox_option=[], font=a.font,
                                 no_fixes=False)
    app = rw.App(args)
    root, c, ed = app.root, app.canvas, app.ed
    root.geometry('+%d+100' % a.x)
    root.update()
    app.activate(True)
    print('font', app.font.actual(), 'cw', ed.cw, 'lh', ed.lh, 'max_row', ed.max_row, 'max_col', ed.max_col,
          'canvas', c.winfo_width(), c.winfo_height())
    if a.file:
        ed.load(a.file)
        app.invalidate()

    def key(ks, char='', state=0):
        c.event_generate('<KeyPress>', keysym=ks, state=state, when='now')
        c.event_generate('<KeyRelease>', keysym=ks, state=state, when='now')
    if not a.file:
        for ch in 'ROBOT "x"':
            key({' ': 'space', '"': 'quotedbl'}.get(ch, ch))
        key('Return')
        for ch in '  ACT 12 % look':
            key({' ': 'space', '%': 'percent'}.get(ch, ch))
        key('Return')
    root.update()
    app.paint()
    root.update()
    items = []
    for it in c.find_all():
        if c.type(it) == 'text':
            items.append((tuple(int(v) for v in c.coords(it)), c.itemcget(it, 'text'), c.itemcget(it, 'fill')))
    for it in sorted(items, key=lambda t: (t[0][1], t[0][0])):
        print(it)
    if a.file and ed.nlines > 10:
        before = ed.top_idx
        for delta in (-120, -120, -40, -40, -40, 120):     # a notch = 3 lines; 3 x 40 = one more notch
            c.event_generate('<MouseWheel>', delta=delta, x=10, y=10, when='now')
        print('wheel: first line %d -> %d (expected +6)' % (before, ed.top_idx))
        app.sbar.event_generate('<MouseWheel>', delta=-120, x=5, y=50, when='now')
        print('wheel over the scroll bar: first line %d (expected +9)' % ed.top_idx)
    cur = app.cursor_item
    print('cursor', c.coords(cur), c.itemcget(cur, 'state'), 'status', app.parts[0].cget('text'),
          'title', root.title(), 'faults', ed.faults)
    if a.keep:
        root.after(int(a.keep * 1000), root.destroy)
        root.mainloop()
    else:
        root.destroy()


if __name__ == '__main__':
    main()
