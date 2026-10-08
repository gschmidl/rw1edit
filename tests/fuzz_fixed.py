"""fuzz_fixed.py [--seeds 1-200] [--steps 1000]: random steps (as ab.py fuzz)
for the port with its fixes, no original: it must never stop (apart from the
255-character line limit) and its line list, cursor and screen must stay
consistent"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ab  # noqa: E402
import rw1edit as rw  # noqa: E402

SIZES = {200: 167, 320: 287, 480: 447, 700: 667}       # window width -> client width (as measured)


def invariants(ed):
    lines = list(ed.lines())
    bad = []
    if len(lines) != ed.nlines or not lines:
        bad.append('nlines %d, list %d' % (ed.nlines, len(lines)))
    ci, ti = ed.index_of(ed.cur), ed.index_of(ed.top)
    if ci is None or ti is None:
        bad.append('cur %r top %r not in the text' % (ci, ti))
    elif ti != ed.top_idx or ci != ed.top_idx + ed.row:
        bad.append('top %d (top_idx %d), cur %d (row %d)' % (ti, ed.top_idx, ci, ed.row))
    if ed.head is not lines[0] or ed.tail is not lines[-1] or lines[0].prev or lines[-1].next:
        bad.append('head/tail')
    for line in lines:
        if not 0 <= line.len <= rw.LINE_CAP:
            bad.append('length %d' % line.len)
    if not 0 <= ed.hscroll + ed.col <= 256:
        bad.append('column %d' % (ed.hscroll + ed.col))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=ab.seed_list, default=ab.seed_list('1-200'))
    ap.add_argument('--steps', type=int, default=1000)
    ap.add_argument('--no-fixes', action='store_true', help='(to see that the checks find something)')
    ap.add_argument('--fixes-only', action='store_true', help='the fixes without the additions')
    args = ap.parse_args()
    bad = 0
    total = 0
    additions = not args.no_fixes and not args.fixes_only
    for seed in args.seeds:
        rng = random.Random(seed)
        host = ab.Host()
        host.clip = ab.SENTINEL
        ed = rw.Editor(host, 8, 15, fixes=not args.no_fixes, additions=additions)
        client = (287, 441)
        ed.wm_size(*client)
        ed.ticks = 2
        failed = False
        for n in range(args.steps):
            step = ab.random_step(rng, ed)
            if additions and rng.random() < 0.15:
                step = addition_step(rng, ed, host, client)
                nf = len(ed.faults)
                apply_addition(step, ed, host)
                problems = ed.faults[nf:] + invariants(ed)
                if problems:
                    bad += 1
                    failed = True
                    print('seed %d step %d %r:' % (seed, n, step), *problems, sep='\n  ')
                    break
                continue
            if step[0] == 'size':
                client = (SIZES[step[1]], step[2] - 59)
            clip = ab.step_clip(step)
            if clip is not None:
                host.clip = clip
            nf = len(ed.faults)
            ab.apply_port(step, ed, host, client)
            total += 1
            faults = [f for f in ed.faults[nf:] if 'longer than' not in f]
            problems = faults + invariants(ed)
            if problems:
                bad += 1
                failed = True
                print('seed %d step %d %r:' % (seed, n, step), *problems, sep='\n  ')
                break
        if not failed and additions and len(ed.undo_stack) + len(ed.redo_stack) < 1000:
            # everything undone: the empty start; everything redone: the last text there was
            while ed.redo():
                pass
            final = ed.texts()
            while ed.undo():
                pass
            first = ed.texts()
            while ed.redo():
                pass
            if first != (b'',) or ed.texts() != final or invariants(ed):
                bad += 1
                print('seed %d: undo all -> %r, redo all -> %s' % (seed, first[:3], ed.texts() == final))
    print('%d of %d seeds with problems, %d steps' % (bad, len(args.seeds), total))
    return bad


WORDS = [b'robot', b'STEP', b'goto', b'x', b'%', b'1', b' ', 'привет'.encode('cp1251')]


def addition_step(rng, ed, host, client):
    r = rng.random()
    x, y = rng.randrange(0, client[0]), rng.randrange(0, max(1, client[1] - 20))
    if r < 0.2:
        return ('wheel', rng.choice([-30, -3, -3, 3, 3, 30]), rng.random() < 0.2)
    if r < 0.4:
        return (rng.choice(['undo', 'undo', 'redo']),)
    if r < 0.5:
        return ('find', rng.choice(WORDS))
    if r < 0.6:
        return ('shiftclick', x, y)
    if r < 0.7:
        return ('select', x, y, rng.random() < 0.3)
    return ('shortcut', rng.choice('cxv'), rng.choice(ab.PASTES))


def apply_addition(step, ed, host):
    kind = step[0]
    if kind == 'wheel':
        ed.guarded(ed.wheel, step[1], step[2])
    elif kind == 'undo':
        ed.guarded(ed.undo)
    elif kind == 'redo':
        ed.guarded(ed.redo)
    elif kind == 'find':
        ed.guarded(ed.find, step[1])
    elif kind == 'shiftclick':
        ed.guarded(ed.shift_click, step[1], step[2])
    elif kind == 'select':
        ed.guarded(ed.select_at, step[1], step[2], step[3])
    else:
        host.clip = step[2]
        shift, ctrl, vk = {'c': (0, 1, rw.VK_INSERT), 'x': (1, 0, rw.VK_DELETE), 'v': (1, 0, rw.VK_INSERT)}[step[1]]
        ed.guarded(ed.with_keys, shift, ctrl, ed.wm_keydown, vk)


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
