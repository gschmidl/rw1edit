"""replay.py SEED STEP [EXE]: the fuzz steps of a seed in the port only (with
EXE also in the original), printing the state before the given step"""
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ab  # noqa: E402


def show(s):
    print({k: v for k, v in s.items() if k != 'lines'})
    for n, (ln, b) in enumerate(s['lines']):
        print('  %3d %3d %r' % (n, ln, b[:max(0, ln)]))


def main():
    seed, stop = int(sys.argv[1]), int(sys.argv[2])
    exe = sys.argv[3] if len(sys.argv) > 3 else None
    rng = random.Random(seed)
    if exe:
        scratch = tempfile.mkdtemp(prefix='rw1ab')
        o, ed, host = ab.fresh(ab.w.scratch_copy(exe, scratch), scratch)
    else:
        o = None
        host = ab.Host()
        ed = ab.rw.Editor(host, 8, 15)
        ed.wm_size(287, 441)
        ed.ticks = 2
    steps = []
    try:
        for n in range(stop + 1):
            step = ab.random_step(rng, ed)
            steps.append(step)
            if n == stop:
                break
            if o:
                ab.apply_step(step, o, ed, host)
            else:
                ab.apply_step(step, NoOriginal(), ed, host)
        print('steps:', steps[-15:])
        print('port before step %d %r:' % (stop, steps[-1]))
        show(ab.port_state(ed))
        if o:
            print('original:')
            show(ab.orig_state(o))
    finally:
        if o:
            o.kill()


class NoOriginal:
    def send(self, *a, **k):
        return 0

    def place(self, *a):
        pass

    def client(self):
        return (287, 441)


if __name__ == '__main__':
    main()
