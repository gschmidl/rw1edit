"""the WM_CHAR the port makes of a key event (App.char_of)"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rw1edit as rw  # noqa: E402

CASES = [
    # keysym, char, ctrl, alt -> WM_CHAR or None
    ('a', 'a', 0, 0, 0x61),
    ('A', 'A', 0, 0, 0x41),
    ('a', '\x01', 1, 0, 0x01),
    ('A', '\x01', 1, 0, 0x01),
    ('y', '\x19', 1, 0, 0x19),
    ('Return', '\r', 0, 0, 0x0D),
    ('KP_Enter', '\r', 0, 0, 0x0D),
    ('Return', '\r', 1, 0, 0x0A),
    ('BackSpace', '\b', 0, 0, 0x08),
    ('BackSpace', '\x7f', 1, 0, 0x7F),
    ('Tab', '\t', 0, 0, 0x09),
    ('Tab', '\t', 1, 0, None),
    ('Escape', '\x1b', 0, 0, 0x1B),
    ('bracketleft', '\x1b', 1, 0, 0x1B),
    ('space', ' ', 0, 0, 0x20),
    ('space', ' ', 1, 0, 0x20),
    ('Delete', '\x7f', 0, 0, None),
    ('KP_Delete', '\x7f', 0, 0, None),
    ('Left', '', 0, 0, None),
    ('Insert', '', 0, 0, None),
    ('F2', '', 0, 0, None),
    ('Shift_L', '', 0, 0, None),
    ('2', '2', 1, 0, None),
    ('at', '@', 1, 1, 0x40),            # AltGr+Q on a German keyboard
    ('backslash', '\\', 1, 1, 0x5C),    # AltGr+sz
    ('Cyrillic_a', 'а', 0, 0, 0xE0),
    ('Cyrillic_YA', 'Я', 0, 0, 0xDF),
    ('EuroSign', '€', 0, 0, 0x88),
    ('eacute', 'é', 0, 0, 0x3F),   # not in CP1251
    ('odiaeresis', 'ö', 0, 0, 0x3F),
    ('section', '§', 0, 0, 0xA7),
]


def main():
    bad = 0
    for ks, ch, ctrl, alt, want in CASES:
        got = rw.App.char_of(SimpleNamespace(keysym=ks, char=ch), bool(ctrl), bool(alt))
        if got != want:
            bad += 1
            print('%s %r ctrl=%d alt=%d: %r, expected %r' % (ks, ch, ctrl, alt, got, want))
    print('%d of %d key cases wrong' % (bad, len(CASES)))
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
