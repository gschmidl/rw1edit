"""crossplat.py OUTDIR FILE...: load and save every file with the port's Editor
and print a SHA-1 per file (lines as loaded + the saved file), to compare the
port on different systems"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rw1edit as rw  # noqa: E402


class Host:
    def __getattr__(self, name):
        return lambda *a, **k: None


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for path in sorted(sys.argv[2:], key=lambda p: os.path.basename(p).lower()):
        ed = rw.Editor(Host())
        h = hashlib.sha1()
        ok = ed.load(path)
        for line in ed.lines():
            h.update(line.len.to_bytes(4, 'little', signed=True) + bytes(line.buf))
        dst = os.path.join(out, os.path.basename(path))
        if ok:
            ed.save(dst)
            with open(dst, 'rb') as f:
                h.update(f.read())
        print(h.hexdigest()[:16], ok, os.path.basename(path))


if __name__ == '__main__':
    main()
