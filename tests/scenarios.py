"""scenarios.py EXE [NAME...]: fixed step lists for the bugs in NOTES.md, run in
the original and the port side by side (as ab.py fuzz does)"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ab  # noqa: E402
import rw1edit as rw  # noqa: E402

w = ab.w            # (None when not on Windows: test_fixes.py only takes the step lists)


def chars(text):
    return [('char', b) for b in text.encode('cp1251')]


def keys(*vks):
    return [('key', vk) for vk in vks]


SHIFT, CTRL = rw.VK_SHIFT, rw.VK_CONTROL
LINES3 = chars('first line') + chars('\r') + chars('second line') + chars('\r') + chars('third line')

SCENARIOS = {
    # bug 5: Ctrl+Del of a selection made upwards
    'delete-upward-selection': (
        LINES3 + keys(SHIFT, rw.VK_UP, rw.VK_UP) + [('keyup', SHIFT), ('cmd', rw.ID_DELETE)],
        'fail'),
    # bug 5: the selection starts beyond the end of its line
    'delete-from-past-line-end': (
        chars('ab') + chars('\r') + chars('cdef') + chars('\r') + chars('gh') +
        keys(rw.VK_UP, rw.VK_UP, rw.VK_RIGHT, rw.VK_RIGHT, rw.VK_RIGHT, SHIFT, rw.VK_DOWN) +
        [('keyup', SHIFT), ('key', SHIFT), ('key', rw.VK_DELETE), ('keyup', SHIFT)],
        'fail'),
    # bug 4: Ctrl+Left in an empty text (a stack overflow; the harness's SendMessage only
    # ends the window procedure)
    'ctrl-left-empty': (keys(CTRL, rw.VK_LEFT), 'fail'),
    # bug 6: Select all + Copy in a text of one line
    'copy-all-one-line': (chars('abc def ghi') + [('cmd', rw.ID_SELALL), ('copy',)], 'fail'),
    # bug 10: Edit > Copy leaves Ctrl down (Right then jumps a word)
    'copy-leaves-ctrl': (
        chars('abc def ghi\rjkl') + [('cmd', rw.ID_SELALL), ('cmd', rw.ID_COPY)] +
        keys(rw.VK_UP, rw.VK_HOME, rw.VK_RIGHT),
        'same'),
    # bug 16: Ctrl+Y on the first row of a scrolled window
    'ctrl-y-first-row': (
        sum((chars('line %d\r' % n) for n in range(40)), []) + keys(rw.VK_UP) * 30 + chars('\x19'),
        'same'),
    # the bytes a shortened last line leaves behind go into Select all + Copy
    'copy-all-leftovers': (
        chars('one\r') + chars('a long last line') + chars('\x08' * 10) +
        [('cmd', rw.ID_SELALL), ('copy',)],
        'same'),
    # bug 17: End while scrolled right
    'end-scrolled-right': (
        chars('x' * 60) + chars('\r') + chars('short') + keys(rw.VK_UP, rw.VK_END, rw.VK_DOWN, rw.VK_END),
        'same'),
    # bug 22: control characters in the text
    'control-chars': (chars('a\x02b\x0ac\x7fd\x00e'), 'same'),
    # bug 15: deleting a selection over three lines leaves two lines
    'delete-keeps-break': (
        LINES3 + keys(rw.VK_UP, rw.VK_UP, rw.VK_HOME, rw.VK_RIGHT, rw.VK_RIGHT, SHIFT, rw.VK_DOWN, rw.VK_DOWN) +
        [('keyup', SHIFT), ('cmd', rw.ID_DELETE)],
        'same'),
    # smart tab and auto-indent
    'tab-indent': (
        chars('  ROBOT "x"   COLOR FF\r\t\tSTEP\r') + chars('next'), 'same'),
    # bug 19: a click in the part-row above the status bar
    'click-part-row': (
        sum((chars('row %d\r' % n) for n in range(60)), []) + keys(CTRL, rw.VK_PRIOR) + [('keyup', CTRL)] +
        [('lclick', 10, 15 * 28 + 5)],
        'same'),
    # bug 8: dragging into the part-column at the right edge (x 280..286 of 287: column 35,
    # one more than the cursor can reach)
    'drag-right-edge': (chars('some text') + [('lclick', 16, 5), ('drag', 283, 5)], 'fail'),
    # bug 8: dragging to a column past 256 (scrolled right in a narrow window, then made wider)
    'drag-past-256': (
        chars('y' * 250) + keys(rw.VK_RIGHT) * 6 + keys(rw.VK_LEFT) * 20 + [('size', 700, 500), ('drag', 8 * 60, 5)],
        'fail'),
}


def run(exe, name, steps, expect):
    scratch = tempfile.mkdtemp(prefix='rw1ab')
    o, ed, host = ab.fresh(w.scratch_copy(exe, scratch), scratch)
    outcome = 'same'
    try:
        for n, step in enumerate(steps):
            nf = len(ed.faults)
            try:
                cd = ab.apply_step(step, o, ed, host)
            except TimeoutError:
                outcome = 'hang' if o.alive() else 'crash'
            else:
                if not o.alive():
                    outcome = 'crash'
                else:
                    d, _ = ab.compare(ab.orig_state(o), ab.port_state(ed))
                    d += [c for c in cd if c != 'stale']
                    if d:
                        outcome = 'differs'
                        print('  step %d %r:' % (n, step), *d[:8], sep='\n    ')
                    elif ed.faults[nf:]:
                        outcome = 'stop'    # the original's crash only ended the message
            if outcome != 'same':
                print('  %s at step %d %r; port: %s' % (outcome, n, step, ed.faults[nf:] or 'no fault'))
                break
        # 'fail': the original hangs or crashes (or, under the harness's SendMessage, its
        # crash only ends the message) and the port stops at that step instead
        if expect == 'fail':
            ok = outcome in ('hang', 'crash', 'stop') and bool(ed.faults)
        else:
            ok = outcome == expect
        print('%-26s %-7s %s' % (name, outcome, 'as expected' if ok else 'EXPECTED %s' % expect))
        return ok
    finally:
        o.kill()
        shutil.rmtree(scratch, ignore_errors=True)


def main():
    exe = sys.argv[1]
    names = sys.argv[2:] or list(SCENARIOS)
    clip = w.clipboard_get_unicode()
    try:
        bad = sum(not run(exe, n, *SCENARIOS[n]) for n in names)
    finally:
        w.clipboard_set_unicode(clip)
    print('%d of %d scenarios not as expected' % (bad, len(names)))
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
