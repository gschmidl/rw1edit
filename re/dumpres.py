"""dumpres.py EXE OUTDIR - sections, imports and resources (menus, dialogs,
accelerators, string tables, icons) of a Win32 executable, as text."""
import os
import struct
import sys

import pefile

RT = {v: k for k, v in pefile.RESOURCE_TYPE.items()}


def wstr(data, off):
    """sz_Or_Ord at off -> (value, new off)"""
    w = struct.unpack_from('<H', data, off)[0]
    if w == 0:
        return '', off + 2
    if w == 0xFFFF:
        return struct.unpack_from('<H', data, off + 2)[0], off + 4
    end = off
    while struct.unpack_from('<H', data, end)[0]:
        end += 2
    return data[off:end].decode('utf-16-le'), end + 2


def menu(data):
    out = []
    ver, hsize = struct.unpack_from('<HH', data, 0)

    def items(off, depth):
        while True:
            flags = struct.unpack_from('<H', data, off)[0]
            off += 2
            if flags & 0x10:   # MF_POPUP
                text, off = wstr(data, off)
                out.append('  ' * depth + 'POPUP %r flags=%04X' % (text, flags))
                off = items(off, depth + 1)
            else:
                mid = struct.unpack_from('<H', data, off)[0]
                off += 2
                text, off = wstr(data, off)
                out.append('  ' * depth + 'ITEM %5d %r flags=%04X' % (mid, text, flags))
            if flags & 0x80:   # MF_END
                return off

    items(4 + hsize, 0)
    return out


def dialog(data):
    out = []
    sig = struct.unpack_from('<HH', data, 0)
    if sig == (1, 0xFFFF):
        out.append('DIALOGEX (not decoded)')
        return out
    style, exstyle, n, x, y, cx, cy = struct.unpack_from('<IIHhhhh', data, 0)
    off = 18
    mnu, off = wstr(data, off)
    cls, off = wstr(data, off)
    title, off = wstr(data, off)
    out.append('DIALOG %d,%d %dx%d style=%08X ex=%08X menu=%r class=%r title=%r' %
               (x, y, cx, cy, style, exstyle, mnu, cls, title))
    if style & 0x40:   # DS_SETFONT
        pt = struct.unpack_from('<H', data, off)[0]
        face, off = wstr(data, off + 2)
        out.append('  FONT %d %r' % (pt, face))
    for _ in range(n):
        off = (off + 3) & ~3
        style, exstyle, x, y, cx, cy, cid = struct.unpack_from('<IIhhhhH', data, off)
        off += 18
        cls, off = wstr(data, off)
        text, off = wstr(data, off)
        extra = struct.unpack_from('<H', data, off)[0]
        off += 2 + extra
        names = {0x80: 'BUTTON', 0x81: 'EDIT', 0x82: 'STATIC', 0x83: 'LISTBOX', 0x84: 'SCROLLBAR', 0x85: 'COMBOBOX'}
        out.append('  %-9s id=%5d %r  %d,%d %dx%d style=%08X ex=%08X' %
                   (names.get(cls, cls), cid, text, x, y, cx, cy, style, exstyle))
    return out


def accel(data):
    out = []
    for off in range(0, len(data), 8):
        flags, key, cmd, _ = struct.unpack_from('<HHHH', data, off)
        out.append('  key=%04X cmd=%5d flags=%02X%s' % (key, cmd, flags,
                   ' (VIRTKEY' + (' SHIFT' if flags & 4 else '') + (' CTRL' if flags & 8 else '') +
                   (' ALT' if flags & 16 else '') + ')' if flags & 1 else ' (ASCII %r)' % chr(key)))
        if flags & 0x80:
            break
    return out


def strings(data, block):
    out = []
    off = 0
    for i in range(16):
        n = struct.unpack_from('<H', data, off)[0]
        off += 2
        if n:
            out.append('  %5d %r' % ((block - 1) * 16 + i, data[off:off + 2 * n].decode('utf-16-le')))
        off += 2 * n
    return out


def main():
    exe, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    pe = pefile.PE(exe)
    lines = ['ImageBase %08X  EntryPoint %08X  TimeDateStamp %08X  Linker %d.%d  Subsystem %d' % (
        pe.OPTIONAL_HEADER.ImageBase, pe.OPTIONAL_HEADER.AddressOfEntryPoint, pe.FILE_HEADER.TimeDateStamp,
        pe.OPTIONAL_HEADER.MajorLinkerVersion, pe.OPTIONAL_HEADER.MinorLinkerVersion, pe.OPTIONAL_HEADER.Subsystem)]
    for s in pe.sections:
        lines.append('%-8s va=%08X vsize=%06X raw=%06X rsize=%06X' % (
            s.Name.rstrip(b'\0').decode(), s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData,
            s.SizeOfRawData))
    for imp in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        lines.append(imp.dll.decode())
        for f in imp.imports:
            lines.append('  %08X %s' % (f.address, f.name.decode() if f.name else '#%d' % f.ordinal))
    if not hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
        lines.append('(no resources)')
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE') else []:
        tname = RT.get(t.id, str(t.name) if t.name else t.id)
        for e in t.directory.entries:
            ename = str(e.name) if e.name else e.id
            for lang in e.directory.entries:
                d = lang.data.struct
                data = pe.get_data(d.OffsetToData, d.Size)
                lines.append('%s %s lang=%04X rva=%08X size=%d' % (tname, ename, lang.id, d.OffsetToData, d.Size))
                try:
                    if tname == 'RT_MENU':
                        lines += menu(data)
                    elif tname == 'RT_DIALOG':
                        lines += dialog(data)
                    elif tname == 'RT_ACCELERATOR':
                        lines += accel(data)
                    elif tname == 'RT_STRING':
                        lines += strings(data, e.id)
                except Exception as ex:   # noqa: BLE001 - keep going, show what failed
                    lines.append('  !! %s' % ex)
                with open(os.path.join(outdir, '%s_%s_%04X.bin' % (tname, ename, lang.id)), 'wb') as f:
                    f.write(data)
    with open(os.path.join(outdir, 'resources.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
