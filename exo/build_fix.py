#!/usr/bin/env python3
"""build_fix.py ORIGINAL [-o OUT]: the fixed RW1_EDIT.EXE

Assembles fix.asm (NASM: --nasm CMD, $RW1_NASM or nasm on the PATH; a command
starting with "wsl" gets /mnt/ paths), adds it to the program as a new section
.fix at 00415000 and patches the places of the original code that lead there.
ORIGINAL must be RW1_EDIT.EXE 1.0.4 as eXoDOS has it. OUT: RW1_EDIT.EXE next to
this script.
"""
import argparse
import hashlib
import os
import shlex
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_SHA1 = 'a8eaa3e48dcfc1e0aceb378afb13cbce30c3c873'
BASE = 0x400000
CAVE = 0x415000

# the jump table of fix.asm
ENTRY = {name: CAVE + 5 * n for n, name in enumerate([
    'expand', 'load_end', 'key_bs', 'key_space', 'key_default', 'key_y1', 'key_y2', 'del_join',
    'word_right', 'word_left', 'copy_buffer', 'copy_null', 'copy_clamp', 'select_all', 'global_alloc',
    'close_clip', 'del_selection', 'drag_column', 'ask_open', 'ask_compile', 'ask_run', 'ask_exit'])}
NONAME = 0x40D1E4           # "noname.rw1"


def rel32(src_end, dst):
    return struct.pack('<i', dst - src_end)


def jmp(at, dst, length=5):
    return at, b'\xE9' + rel32(at + 5, dst) + b'\x90' * (length - 5)


def jcc(at, cc, dst):
    """a 6-byte Jcc (0F 8x rel32); cc: 0x84 JZ, 0x85 JNZ, 0x8E JLE"""
    return at, bytes([0x0F, cc]) + rel32(at + 6, dst)


def dword(at, value):
    return at, struct.pack('<I', value)


def patches():
    """(address, new bytes, the original bytes they replace)"""
    out = [
        # load: go on while fgets returns a line (not until the end-of-file flag: the last
        # line without a line end got lost)
        (0x401283, b'\x85\xC0' + b'\x90' * 8, bytes.fromhex('8B85FCFEFFFFF6400C10')),
        (0x40128D, bytes.fromhex('0F8505000000'), bytes.fromhex('0F8405000000')),
        # load: TAB expansion and conversion by fix.asm (the original overruns its buffer)
        (0x401298, bytes.fromhex('8D8500FFFFFF50') + b'\xE8' + rel32(0x401298 + 12, ENTRY['expand']) +
         bytes.fromhex('83C404') + b'\xE9' + rel32(0x401298 + 20, 0x4013AB),
         bytes.fromhex('C785F8FEFFFF00000000E906000000FF85F8FEFF')),
        # load: never no lines
        jmp(0x4014FB, ENTRY['load_end'], 7) + (bytes.fromhex('5F5E5BC9C20400'),),
        # Ctrl+Y
        jmp(0x401E0E, ENTRY['key_y1'], 9) + (bytes.fromhex('508B4DF8E840F9FFFF'),),
        jcc(0x401E23, 0x85, ENTRY['key_y2']) + (bytes.fromhex('0F850C000000'),),
        # the key switch: case 8, case 0x20, default (and the default of the bounds check)
        dword(0x402060, ENTRY['key_bs']) + (struct.pack('<I', 0x401A03),),
        dword(0x402060 + 5 * 4, ENTRY['key_space']) + (struct.pack('<I', 0x401CE5),),
        dword(0x402060 + 6 * 4, ENTRY['key_default']) + (struct.pack('<I', 0x401E5E),),
        jcc(0x402048, 0x87, ENTRY['key_default']) + (bytes.fromhex('0F8710FEFFFF'),),
        # Del at a line end
        jcc(0x402488, 0x85, ENTRY['del_join']) + (bytes.fromhex('0F8505000000'),),
        # Ctrl+Right, Ctrl+Left
        jmp(0x4026C9, ENTRY['word_right']) + (bytes.fromhex('A1ACE74000'),),
        jcc(0x40272F, 0x8E, ENTRY['word_left']) + (bytes.fromhex('0F8EB2000000'),),
        # copy
        jmp(0x402911, ENTRY['copy_buffer']) + (bytes.fromhex('A16CD04000'),),
        jmp(0x4029F0, ENTRY['copy_null'], 9) + (bytes.fromhex('8B45F8390574D04000'),),
        jmp(0x402A95, ENTRY['copy_clamp'], 6) + (bytes.fromhex('8B0D64D04000'),),
        # the window procedure
        jmp(0x403C9A, ENTRY['select_all'], 10) + (bytes.fromhex('A178D04000A36CD04000'),),
        jmp(0x40421D, ENTRY['global_alloc']) + (bytes.fromhex('A16CD04000'),),
        jmp(0x4042FD, ENTRY['close_clip']) + (b'\xE9' + rel32(0x404302, 0x4047C0),),
        jcc(0x4043DF, 0x84, ENTRY['del_selection']) + (bytes.fromhex('0F8405000000'),),
        # deleting a selection: while the line is longer than the start column (not: until
        # it is exactly as long - it may never be)
        (0x4044E4, bytes.fromhex('0F8E0F000000'), bytes.fromhex('0F840F000000')),
        jmp(0x40487A, ENTRY['drag_column']) + (bytes.fromhex('8B451425FF'),),
        # Save: a new text goes to Save as
        dword(0x404E5A, NONAME) + (struct.pack('<I', 0x40D20C),),
        jcc(0x404E6D, 0x84, 0x404EC3) + (bytes.fromhex('0F8417000000'),),
        # Edit > Copy lets go of Ctrl, not of Shift
        (0x404E42, b'\x94', b'\x98'),
    ]
    # "Save it?" Yes: a new text asks for a name
    for push, jz, entry, old_jz in ((0x404FD0, 0x404FE4, 'ask_open', 0x405001),
                                    (0x405267, 0x40527B, 'ask_compile', 0x405298),
                                    (0x4053DE, 0x4053F2, 'ask_run', 0x40540F),
                                    (0x405539, 0x40554D, 'ask_exit', 0x40556A)):
        old_push = {0x404FD0: 0x40D27C, 0x405267: 0x40D440, 0x4053DE: 0x40D498, 0x405539: 0x40D4F0}[push]
        out.append(dword(push + 1, NONAME) + (struct.pack('<I', old_push),))
        out.append(jcc(jz, 0x84, ENTRY[entry]) + (b'\x0F\x84' + rel32(jz + 6, old_jz),))
    return out


def assemble(nasm):
    src = os.path.join(HERE, 'fix.asm')
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'fix.bin')
        cmd = shlex.split(nasm, posix=os.name != 'nt')
        paths = [src, out]
        if cmd[0].lower().startswith('wsl'):
            paths = ['/mnt/%s%s' % (p[0].lower(), p[2:].replace('\\', '/')) for p in map(os.path.abspath, paths)]
        r = subprocess.run(cmd + ['-f', 'bin', '-o', paths[1], paths[0]], capture_output=True, text=True)
        if r.returncode:
            sys.exit('nasm: %s%s' % (r.stdout, r.stderr))
        with open(out, 'rb') as f:
            return f.read()


def align(n, a):
    return (n + a - 1) // a * a


def build(original, nasm):
    data = bytearray(original)
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec, = struct.unpack_from('<H', data, pe + 6)
    optsize, = struct.unpack_from('<H', data, pe + 20)
    opt = pe + 24
    salign, falign = struct.unpack_from('<II', data, opt + 32)
    sections = []
    for i in range(nsec):
        h = opt + optsize + 40 * i
        vsize, va, rsize, raw = struct.unpack_from('<IIII', data, h + 8)
        sections.append((va, vsize, raw, rsize))

    def offset(addr):
        rva = addr - BASE
        for va, vsize, raw, rsize in sections:
            if va <= rva < va + max(vsize, rsize):
                return raw + rva - va
        raise ValueError('%08X is not in the file' % addr)

    for addr, new, old in patches():
        at = offset(addr)
        if bytes(data[at:at + len(old)]) != old:
            sys.exit('%08X: %s, not %s as expected' % (addr, data[at:at + len(old)].hex(), old.hex()))
        data[at:at + len(new)] = new
    cave = assemble(nasm)
    # the new section
    h = opt + optsize + 40 * nsec
    if h + 40 > struct.unpack_from('<I', data, opt + 60)[0]:
        sys.exit('no room for another section header')
    rva = CAVE - BASE
    if rva != align(max(va + vsize for va, vsize, _, _ in sections), salign):
        sys.exit('the section would not follow the last one')
    raw = align(len(data), falign)
    data += b'\0' * (raw - len(data))
    rsize = align(len(cave), falign)
    data += cave + b'\0' * (rsize - len(cave))
    struct.pack_into('<8sIIIIIIHHI', data, h, b'.fix', len(cave), rva, rsize, raw, 0, 0, 0, 0, 0xE0000060)
    struct.pack_into('<H', data, pe + 6, nsec + 1)
    struct.pack_into('<I', data, opt + 56, rva + align(len(cave), salign))       # SizeOfImage
    # fixed addresses everywhere now: the program must not be moved
    chars, = struct.unpack_from('<H', data, pe + 22)
    struct.pack_into('<H', data, pe + 22, chars | 0x0001)                       # RELOCS_STRIPPED
    struct.pack_into('<II', data, opt + 96 + 5 * 8, 0, 0)                       # no base relocations
    return bytes(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('original')
    ap.add_argument('-o', '--out', default=os.path.join(HERE, 'RW1_EDIT.EXE'))
    ap.add_argument('--nasm', default=os.environ.get('RW1_NASM', 'nasm'))
    a = ap.parse_args()
    with open(a.original, 'rb') as f:
        original = f.read()
    if hashlib.sha1(original).hexdigest() != ORIGINAL_SHA1:
        sys.exit('%s is not RW1_EDIT.EXE 1.0.4 (sha1 %s)' % (a.original, ORIGINAL_SHA1))
    fixed = build(original, a.nasm)
    with open(a.out, 'wb') as f:
        f.write(fixed)
    print('%s: %d bytes, sha1 %s' % (a.out, len(fixed), hashlib.sha1(fixed).hexdigest()))


if __name__ == '__main__':
    main()
