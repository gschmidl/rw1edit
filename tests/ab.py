"""A/B test: the original RW1_EDIT.EXE against the port's Editor (Windows only).

Both get the same window messages; after every step the original's memory
(its globals, the editor object and the whole line list) is read and compared
with the port's state.

    py tests/ab.py fuzz [--seeds 1-20] [--steps 300] EXE
    py tests/ab.py load EXE FILE...       (File > Open in both, compare the lines)
    py tests/ab.py save EXE FILE...       (open, Save as, compare the written files)

EXE is a copy of RW1_EDIT.EXE; it runs from a scratch folder next to the
test's output. The test takes the clipboard and puts the old text back.
"""
import argparse
import os
import random
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import rw1edit as rw  # noqa: E402

try:
    import win32 as w  # noqa: E402
except (ImportError, AttributeError):
    w = None        # not Windows: no original to drive (the port's tests import this file too)

G = {'row': 0x40E7A4, 'col': 0x40E7A8, 'hscroll': 0x40E7AC, 'top_idx': 0x40E7B0, 'max_row': 0x40E7C8,
     'max_col': 0x40EB30, 'insert': 0x40E880, 'nlines': 0x40D078, 'pasting': 0x40D040, 'c0': 0x40D060,
     'c1': 0x40D064, 'l0': 0x40D068, 'l1': 0x40D06C, 'modified': 0x40D088, 'ticks': 0x40D090,
     'ctrl': 0x40D094, 'shift': 0x40D098, 'selecting': 0x40D09C, 'no_sel': 0x40D0A4, 'active': 0x40D0A8,
     'i': 0x40E9F0, 'j': 0x40E9F4}
P = {'p0': 0x40D070, 'p1': 0x40D074, 'tmp': 0x40E9F8, 'cur': 0x40E9FC, 'top': 0x40EA00, 'head': 0x40EA04,
     'tail': 0x40EA08}
CW, LH = 0x40E94C, 0x40E7D4


class Host:
    """the port's side of the window system, for tests"""

    def __init__(self):
        self.clip = None
        self.statustext = '1 : 1'
        self.answers = []
        self.messages = []
        self.title = rw.TITLE0
        self.faults = []
        self.open_path = self.save_path = ''

    def status(self, t):
        self.statustext = t

    def invalidate(self):
        pass

    def fault(self, what):
        self.faults.append(what)

    def message(self, kind, title, text):
        self.messages.append((kind, title, text))
        return self.answers.pop(0) if kind == 'yesnocancel' else 1

    def clipboard_get(self):
        return self.clip

    def clipboard_set(self, data):
        self.clip = data

    def set_title(self, t):
        self.title = t

    def open_dialog(self, d):
        return self.open_path

    def save_dialog(self, d):
        return self.save_path

    def quit(self):
        pass

    def new_editor(self):
        return True

    def open_help(self, name):
        return True

    def compile(self, path):
        pass

    def run(self, path):
        pass


# -- state of both sides ------------------------------------------------------

def orig_state(o):
    s = {k: o.i32(a) for k, a in G.items()}
    addr = o.u32(P['head'])
    index, lines, n = {}, [], 0
    while addr and n < 100000:
        node = o.read(addr, 0x10C)
        index[addr] = n
        ln = int.from_bytes(node[0x108:0x10C], 'little', signed=True)
        lines.append((ln, node[:0x100]))
        addr = int.from_bytes(node[0x104:0x108], 'little')
        n += 1
    for k, a in P.items():
        v = o.u32(a)
        s[k] = None if v == 0 else index.get(v, 'dangling')
    s['lines'] = lines
    return s


def port_state(ed):
    s = {k: getattr(ed, k) for k in G}
    index = {}
    lines = []
    for n, line in enumerate(ed.lines()):
        index[id(line)] = n
        lines.append((line.len, bytes(line.buf)))
    for k in P:
        v = getattr(ed, k)
        s[k] = None if v is None else index.get(id(v), 'dangling')
    s['lines'] = lines
    return s


def compare(a, b):
    """differences between the original's state a and the port's b; and stale-byte notes"""
    diffs, notes = [], []
    for k in list(G) + list(P):
        if k in ('ticks', 'active'):
            continue        # set by the timer and by Windows activating the window, not by the test
        if k == 'i' and a['active']:
            continue        # an active window's WM_PAINT swaps a backward selection through i
        if a[k] != b[k]:
            if k in P and 'dangling' in (a[k], b[k]):
                # a pointer to a freed line that the original's heap has handed out again
                diffs.append('heap: %s: original %r, port %r' % (k, a[k], b[k]))
            else:
                diffs.append('%s: original %r, port %r' % (k, a[k], b[k]))
    la, lb = a['lines'], b['lines']
    if len(la) != len(lb):
        diffs.append('line count: original %d, port %d' % (len(la), len(lb)))
    for n, ((na, ba), (nb, bb)) in enumerate(zip(la, lb)):
        if na != nb:
            diffs.append('line %d length: original %d, port %d' % (n, na, nb))
        k = max(0, min(na, nb, 256))
        if ba[:k] != bb[:k]:
            diffs.append('line %d text: original %r, port %r' % (n, ba[:k], bb[:k]))
        elif ba[k:k + 2] != bb[k:k + 2]:
            notes.append('line %d after its end: original %r, port %r' % (n, ba[k:k + 4], bb[k:k + 4]))
    return diffs, notes


# -- the steps ----------------------------------------------------------------

PASTES = [
    b'ROBOT "Test"\r\n\r\n   START:\r\n     ACT FRONT   % look\r\n     if N!=6 : L1\r\n',
    b'abc def',
    b'  STEP\r\n  GOTO START\r\n',
    b'\tx = 1\r\n\ty = 2\r\n',
    b'% comment 123\r\nEND',
    b'one\r\ntwo\r\n\r\nthree\r\n',
    'привет МИР 42\r\n'.encode('cp1251'),
    b'x' * 40,
]
CHARS = (b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' * 2 + b'          ' +
         b'%:;.,()!=<>+-*"\'[]{}/?|' + 'аБвЯё«'.encode('cp1251') + b'\x08\x08\x08\x09\x0d\x0d\x19\x1b' +
         b'\x0a\x7f\x02\x00')
KEYS = [rw.VK_LEFT, rw.VK_RIGHT, rw.VK_UP, rw.VK_DOWN, rw.VK_HOME, rw.VK_END, rw.VK_PRIOR, rw.VK_NEXT,
        rw.VK_INSERT, rw.VK_DELETE, 0x41]


NOCLIP = False      # --no-clipboard: no steps that use the clipboard (it is the user's)


def random_step(rng, ed):
    while True:
        step = _random_step(rng, ed)
        if not NOCLIP or not uses_clipboard(step, ed):
            return step


def uses_clipboard(step, ed):
    if step[0] in ('paste', 'copy'):
        return True
    if step[0] == 'cmd':
        # (Edit > Delete with Shift down is Shift+Del: it copies first)
        return step[1] in (rw.ID_CUT, rw.ID_COPY, rw.ID_PASTE) or (step[1] == rw.ID_DELETE and ed.shift)
    if step[0] == 'key':
        return (step[1] == rw.VK_INSERT and (ed.shift or ed.ctrl)) or (step[1] == rw.VK_DELETE and ed.shift)
    return False


def _random_step(rng, ed):
    r = rng.random()
    if r < 0.40:
        c = CHARS[rng.randrange(len(CHARS))]
        if c not in (8, 9, 13, 0x19, 0x1B) and ed.cur.len > 200:
            c = 13
        return ('char', c)
    if r < 0.62:
        return ('key', rng.choice(KEYS))
    if r < 0.70:
        vk = rng.choice([rw.VK_SHIFT, rw.VK_CONTROL])
        return ('key', vk) if rng.random() < 0.5 else ('keyup', vk)
    if r < 0.76:
        # anywhere in the client area (above the status bar)
        x = rng.randrange(0, max(1, ed.client[0]))
        y = rng.randrange(0, max(1, ed.client[1] - 20))
        return (rng.choice(['lclick', 'lclick', 'rclick', 'drag', 'drag', 'drag']), x, y)
    if r < 0.78:
        return ('lup',)
    if r < 0.84:
        code = rng.choice([0, 1, 2, 3, 5])
        return ('vscroll', code, rng.randrange(0, 101) if code == 5 else 0)
    if r < 0.93:
        cmd = rng.choice([rw.ID_CUT, rw.ID_COPY, rw.ID_PASTE, rw.ID_SELALL, rw.ID_DELETE])
        if cmd == rw.ID_PASTE:
            return ('cmd', cmd, rng.choice(PASTES))
        return ('cmd', cmd)
    if r < 0.96:
        return ('paste', rng.choice(PASTES))
    if r < 0.98:
        return ('copy',)
    return ('size', rng.choice([200, 320, 480, 700]), rng.choice([150, 300, 500, 700]))


SENTINEL = b'<sentinel>'


def step_clip(step):
    """what the clipboard holds before a step that uses it"""
    if step[0] == 'paste':
        return step[1]
    if step[0] in ('cmd', 'copy'):
        return step[2] if len(step) > 2 else SENTINEL
    return None


def send_original(step, o):
    """the step as window messages to the original (TimeoutError: it hangs)"""
    kind = step[0]
    if kind == 'key':
        o.send(w.WM_KEYDOWN, step[1])
    elif kind == 'keyup':
        o.send(w.WM_KEYUP, step[1])
    elif kind == 'char':
        o.send(w.WM_CHAR, step[1])
    elif kind in ('lclick', 'rclick', 'drag'):
        msg = {'lclick': w.WM_LBUTTONDOWN, 'rclick': w.WM_RBUTTONDOWN, 'drag': w.WM_MOUSEMOVE}[kind]
        o.send(msg, 1 if kind == 'drag' else 0, (step[2] << 16) | step[1])
    elif kind == 'lup':
        o.send(w.WM_LBUTTONUP)
    elif kind == 'vscroll':
        o.send(w.WM_VSCROLL, step[1] | (step[2] << 16))
    elif kind in ('paste', 'copy'):
        vk = rw.VK_SHIFT if kind == 'paste' else rw.VK_CONTROL
        o.send(w.WM_KEYDOWN, vk)
        o.send(w.WM_KEYDOWN, rw.VK_INSERT)
        o.send(w.WM_KEYUP, vk)
    elif kind == 'cmd':
        o.send(w.WM_COMMAND, step[1])
        if step[1] == rw.ID_SELALL:
            time.sleep(0.05)        # the original posts itself a WM_CHAR 1
    elif kind == 'size':
        o.place(-2400, 80, step[1], step[2])


def apply_port(step, ed, host, client=None):
    kind = step[0]
    if kind == 'key':
        ed.guarded(ed.wm_keydown, step[1])
    elif kind == 'keyup':
        ed.wm_keyup(step[1])
    elif kind == 'char':
        ed.guarded(ed.wm_char, step[1])
    elif kind == 'lclick':
        ed.guarded(ed.wm_lbuttondown, step[1], step[2])
    elif kind == 'rclick':
        ed.guarded(ed.wm_rbuttondown, step[1], step[2])
    elif kind == 'drag':
        ed.guarded(ed.wm_mousemove, step[1], step[2], True)
    elif kind == 'lup':
        ed.wm_lbuttonup()
    elif kind == 'vscroll':
        ed.guarded(ed.wm_vscroll, step[1], step[2])
    elif kind in ('paste', 'copy'):
        vk = rw.VK_SHIFT if kind == 'paste' else rw.VK_CONTROL
        ed.wm_keydown(vk)
        ed.guarded(ed.wm_keydown, rw.VK_INSERT)
        ed.wm_keyup(vk)
    elif kind == 'cmd':
        ed.guarded(ed.wm_command, step[1])
    elif kind == 'size':
        ed.wm_size(*client)


def apply_step(step, o, ed, host):
    """the step in both; differences in the clipboard. TimeoutError: the
    original hangs (the port has done the step too)"""
    clip = step_clip(step)
    if clip is not None:
        w.clipboard_set_bytes(clip)
        host.clip = clip
        time.sleep(0.15)    # clipboard listeners (history, ...) open it after every change
    try:
        send_original(step, o)
    finally:
        apply_port(step, ed, host, o.client() if step[0] == 'size' else None)
    if NOCLIP:
        return []
    if clip is not None or (step[0] == 'key' and step[1] in (rw.VK_INSERT, rw.VK_DELETE)):
        got = w.clipboard_get_text()
        if got != host.clip:
            if got and host.clip and got.startswith(host.clip):
                # the copy went past the end line's text into bytes the port has as 0
                # and the original as whatever its heap block held before
                return ['stale']
            return ['clipboard: original %r, port %r' % (got, host.clip)]
    return []


FIXED = False       # --fixed: the fixed RW1_EDIT.EXE against Editor(fixes=True)


def fresh(exe, scratch):
    o = w.Original(exe, scratch)
    host = Host()
    if not NOCLIP:
        w.clipboard_set_bytes(SENTINEL)
        host.clip = SENTINEL
        time.sleep(0.15)
    ed = rw.Editor(host, o.i32(CW), o.i32(LH), cwd=scratch, fixes=FIXED)
    cw, ch = o.client()
    ed.wm_size(cw, ch)
    ed.ticks = 2
    return o, ed, host


def fuzz(args):
    clip = None if NOCLIP else w.clipboard_get_unicode()
    scratch = tempfile.mkdtemp(prefix='rw1ab')
    exe = w.scratch_copy(args.exe, scratch)
    failures = 0
    stats = {'steps': 0, 'faults': 0, 'stale': 0}
    try:
        for seed in args.seeds:
            t0 = time.time()
            rng = random.Random(seed)
            o, ed, host = fresh(exe, scratch)
            trail = []
            try:
                d, _ = compare(orig_state(o), port_state(ed))
                if d:
                    print('seed %d: differs at the start:' % seed, *d, sep='\n  ')
                    failures += 1
                    continue
                for n in range(args.steps):
                    step = random_step(rng, ed)
                    trail.append(step)
                    nf = len(ed.faults)
                    try:
                        cdiff = apply_step(step, o, ed, host)
                    except TimeoutError:
                        pf = ed.faults[nf:]
                        if not pf and step == ('key', rw.VK_RIGHT) and ed.ctrl and ed.hscroll + ed.col == 256:
                            # Ctrl+Right ran through zero bytes to column 256 and read the low byte
                            # of the line's prev pointer: 00 or 20 (a heap address) keeps it going
                            print('seed %d step %d %r: original hangs at column 256 (heap address); stopping'
                                  % (seed, n, step))
                            stats['heap'] = stats.get('heap', 0) + 1
                            break
                        if not pf:
                            failures += 1
                        print('seed %d step %d %r: original hangs; port %s'
                              % (seed, n, step, 'stops too: %r' % pf if pf else 'does NOT'))
                        stats['hangs'] = stats.get('hangs', 0) + 1
                        break
                    if not o.alive():
                        print('seed %d step %d %r: original died; port faults %r'
                              % (seed, n, step, ed.faults[nf:]))
                        break
                    fault = ed.faults[nf:]
                    if fault:
                        stats['faults'] += 1
                    try:
                        a = orig_state(o)
                    except OSError as e:
                        # the original has written over its line list (a line past 255 characters)
                        if not any('longer than' in f for f in fault):
                            failures += 1
                        print('seed %d step %d %r: the original corrupted its memory (%s); port: %r'
                              % (seed, n, step, e, fault))
                        break
                    d, notes = compare(a, port_state(ed))
                    ed.ticks, ed.active = a['ticks'], a['active']
                    if fault:
                        # where the original crashes, the harness's SendMessage ends the window
                        # procedure (WOW64 swallows the exception): the port's stop should leave
                        # the same state. After that the original is not to be trusted.
                        print('seed %d step %d %r: port stops (%s), state %s'
                              % (seed, n, step, '; '.join(fault), 'identical' if not (d or cdiff) else 'DIFFERS'))
                        if (d or cdiff) and not any('longer than' in f for f in fault):
                            failures += 1
                            print('  ', *(cdiff + d)[:8], sep='\n  ')
                        break
                    if d and all(x.startswith('heap: ') for x in d):
                        stats['heap'] = stats.get('heap', 0) + 1
                        print('seed %d step %d %r: %s (the original reuses a freed line; stopping)'
                              % (seed, n, step, '; '.join(d)))
                        break
                    if cdiff == ['stale']:
                        cdiff = []
                        notes.append('clipboard')
                        stats['stale clipboard'] = stats.get('stale clipboard', 0) + 1
                    stats['steps'] += 1
                    stats['stale'] += bool(notes)
                    if d or cdiff:
                        failures += 1
                        print('seed %d: step %d %r differs:' % (seed, n, step), *(cdiff + d)[:12], sep='\n  ')
                        print('  last steps:', trail[-12:])
                        break
                    st = o.status_text()
                    if st != host.statustext:
                        failures += 1
                        print('seed %d: step %d %r status: original %r, port %r'
                              % (seed, n, step, st, host.statustext))
                        break
                else:
                    print('seed %d: %d steps identical (%.0f s, %d lines)'
                          % (seed, args.steps, time.time() - t0, ed.nlines))
            finally:
                o.kill()
    finally:
        try:
            if not NOCLIP:
                w.clipboard_set_unicode(clip)
        except RuntimeError:
            print('could not restore the clipboard')
        shutil.rmtree(scratch, ignore_errors=True)
    print('%d failing seeds; %d steps compared, %d with differing bytes after a line end, %d port faults'
          % (failures, stats['steps'], stats['stale'], stats['faults']), stats)
    return failures


LOAD, SAVE, EDITOR = 0x4011D0, 0x401502, 0x40E9F0


def load(args):
    """the original's load routine (FUN_004011d0, called in a thread of its own:
    no file dialog) against Editor.load, then (save) both save routines"""
    scratch = tempfile.mkdtemp(prefix='rw1ab')
    exe = w.scratch_copy(args.exe, scratch)
    bad = 0
    o, ed, host = fresh(exe, scratch)
    try:
        for n, path in enumerate(args.files):
            path = os.path.abspath(path)
            ra = o.call_this(LOAD, EDITOR, path.encode('mbcs'))
            rb = ed.load(path)
            try:
                sa = orig_state(o) if o.alive() else None
            except OSError as e:
                sa = None
                print('%s: the original has corrupted its memory (%s)' % (os.path.basename(path), e))
            if sa is None:
                print('%s: the original %s; port loaded %d lines' % (
                    os.path.basename(path), 'died' if not o.alive() else 'is broken', len(list(ed.lines()))))
                bad += 1
                o.kill()
                o, ed, host = fresh(exe, scratch)
                continue
            d, notes = compare(sa, port_state(ed))
            if bool(ra) != rb:
                d.append('result: original %r, port %r' % (ra, rb))
            if args.save and ra:
                out_a = os.path.join(scratch, 'A%04d.RW1' % n)
                out_b = os.path.join(scratch, 'B%04d.RW1' % n)
                sa = o.call_this(SAVE, EDITOR, out_a.encode('mbcs'))
                sb = ed.save(out_b)
                with open(out_a, 'rb') as f:
                    da = f.read()
                with open(out_b, 'rb') as f:
                    db = f.read()
                if bool(sa) != sb:
                    d.append('save result: original %r, port %r' % (sa, sb))
                if da != db:
                    d.append('saved file: original %r, port %r' % (da[:200], db[:200]))
                d2, notes2 = compare(orig_state(o), port_state(ed))
                d += ['after saving: ' + x for x in d2]
                notes += notes2
            if d:
                bad += 1
                print('%s:' % path, *d[:10], sep='\n  ')
            elif args.verbose:
                print('%s: %s, %d lines identical%s' % (os.path.basename(path), 'loaded' if ra else 'NOT loaded',
                                                       len(list(ed.lines())),
                                                       ' (stale bytes differ)' if notes else ''))
    finally:
        o.kill()
    print('%d of %d files differ' % (bad, len(args.files)))
    return bad


def seed_list(s):
    out = []
    for part in s.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fuzz')
    f.add_argument('--seeds', type=seed_list, default=seed_list('1-10'))
    f.add_argument('--steps', type=int, default=300)
    f.add_argument('--no-clipboard', action='store_true',
                   help='no cut, copy or paste: leave the clipboard alone (someone is using it)')
    f.add_argument('exe')
    p = sub.add_parser('load')
    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('--save', action='store_true', help='also save each file with both and compare')
    p.add_argument('exe')
    p.add_argument('files', nargs='+')
    for s in (f, p):
        s.add_argument('--fixed', action='store_true',
                       help='EXE is the fixed RW1_EDIT.EXE (exo/build_fix.py): the port with its fixes')
    args = ap.parse_args()
    global FIXED, NOCLIP
    FIXED = args.fixed
    NOCLIP = getattr(args, 'no_clipboard', False) or args.cmd == 'load'
    sys.exit(1 if {'fuzz': fuzz, 'load': load}[args.cmd](args) else 0)


if __name__ == '__main__':
    main()
