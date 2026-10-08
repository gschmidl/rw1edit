"""The two eXo patches (exo/fix_windows.py, exo/install_port.py) on a scratch eXo folder.

    py tests/test_patches.py EXO_FOLDER

EXO_FOLDER is an eXoDOS "eXo" folder; only RW1_EDIT.EXE from the game's zip and
!dos\\RoboWar1\\exception.bat (or exception.bat.orig, if a patch is applied there)
are read. Each patch is checked, applied, applied again, reverted; the files must
end up as they were. Then the patched launcher's editor lines run (cmd, with stubs
for setconsole.exe, the port and RW1_EDIT.EXE): with Python, without rw1edit.py.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXO_DIR = os.path.join(HERE, '..', 'exo')
SHA1_ORIGINAL = 'a8eaa3e48dcfc1e0aceb378afb13cbce30c3c873'
STUB = "import os, sys\nprint('PORT-RAN', os.path.basename(os.getcwd()), sys.argv[1:])\n"
BAD = []


def check(cond, what):
    print('%-8s %s' % ('ok' if cond else 'FAILED', what))
    if not cond:
        BAD.append(what)


def sha1(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(EXO_DIR, script)] + list(args), capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def scratch_tree(exo, root):
    game = os.path.join(root, 'eXoDOS', 'RoboWar1')
    dos = os.path.join(root, 'eXoDOS', '!dos', 'RoboWar1')
    for d in (game, dos, os.path.join(root, 'util'), os.path.join(root, 'emulators', 'dosbox')):
        os.makedirs(d)
    with zipfile.ZipFile(os.path.join(exo, 'eXoDOS', 'Robot Warfare 1 (1999).zip')) as z:
        name = next(n for n in z.namelist() if n.lower().endswith('robowar1/rw1_edit.exe'))
        with open(os.path.join(game, 'RW1_EDIT.EXE'), 'wb') as f:
            f.write(z.read(name))
    live = os.path.join(exo, 'eXoDOS', '!dos', 'RoboWar1')
    src = os.path.join(live, 'exception.bat.orig')
    shutil.copyfile(src if os.path.exists(src) else os.path.join(live, 'exception.bat'),
                    os.path.join(dos, 'exception.bat'))
    shutil.copyfile(os.path.join(live, 'dosbox.conf'), os.path.join(dos, 'dosbox.conf'))
    return game, dos


def launcher(root, dos, game, dosbox_var):
    """the :winedit lines of the patched exception.bat, from the game's !dos folder"""
    bat = read(os.path.join(dos, 'exception.bat')).decode('latin-1')
    branch = bat[bat.index(':winedit\r\n'):bat.index(':dosbox\r\n')]
    test = os.path.join(dos, 'test.bat')
    with open(test, 'wb') as f:
        f.write(('@echo off\r\nset GameDir=RoboWar1\r\nset var=%s\r\nset dosbox=%s\r\ncd /d "%%var%%"\r\n'
                 'goto winedit\r\n%s:end\r\necho BACK %%CD%%\r\n' % (dos, dosbox_var, branch)).encode('latin-1'))
    r = subprocess.run(['cmd', '/c', test], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding='cp850', errors='replace')
    os.remove(test)
    return r.stdout.replace(root.replace('\\', '\\\\'), '<eXo>').replace(root, '<eXo>')


def main():
    exo = sys.argv[1]
    root = tempfile.mkdtemp(prefix='rw1patch')
    try:
        game, dos = scratch_tree(exo, root)
        exe, bat = os.path.join(game, 'RW1_EDIT.EXE'), os.path.join(dos, 'exception.bat')
        orig_bat = read(bat)
        check(sha1(exe) == SHA1_ORIGINAL, 'the game zip has the original RW1_EDIT.EXE')

        # patch 1
        rc, out = run('fix_windows.py', '--check', root)
        check(rc == 0 and 'would replace' in out and sha1(exe) == SHA1_ORIGINAL, 'fix_windows --check')
        rc, out = run('fix_windows.py', root)
        check(rc == 0 and sha1(exe) == sha1(os.path.join(EXO_DIR, 'RW1_EDIT.EXE')) and
              sha1(exe + '.orig') == SHA1_ORIGINAL, 'fix_windows: the fixed exe, the original kept')
        rc, out = run('fix_windows.py', root)
        check(rc == 0 and 'already' in out, 'fix_windows again: nothing to do')
        rc, out = run('fix_windows.py', '--revert', root)
        check(rc == 0 and sha1(exe) == SHA1_ORIGINAL and not os.path.exists(exe + '.orig'), 'fix_windows --revert')
        with open(exe, 'ab') as f:
            f.write(b'x')
        rc, out = run('fix_windows.py', root)
        check(rc != 0 and 'not the RW1_EDIT.EXE' in out, 'fix_windows leaves an unknown exe alone')
        with open(exe, 'r+b') as f:
            f.truncate(os.path.getsize(exe) - 1)

        # patch 2
        rc, out = run('install_port.py', '--check', root)
        check(rc == 0 and 'original' in out and 'missing' in out, 'install_port --check')
        rc, out = run('install_port.py', root)
        port = os.path.join(game, 'rw1edit.py')
        check(rc == 0 and os.path.isfile(port) and read(bat + '.orig') == orig_bat and read(bat) != orig_bat,
              'install_port: rw1edit.py, exception.bat patched, original kept')
        check(b'\n' not in read(bat).replace(b'\r\n', b''), 'exception.bat: CR LF line ends only')
        rc, out = run('install_port.py', root)
        check(rc == 0 and 'already patched' in out, 'install_port again')
        rc, out = run('install_port.py', '--check', root)
        check('patched' in out and 'current' in out, 'install_port --check: installed')

        # both, and the launcher
        run('fix_windows.py', root)
        shutil.copyfile(os.path.join(os.environ['SystemRoot'], 'System32', 'where.exe'),
                        os.path.join(root, 'util', 'setconsole.exe'))
        saved_port = read(port)
        with open(port, 'w') as f:
            f.write(STUB)
        out = launcher(root, dos, game, 'DOSBox.exe')
        expect = "PORT-RAN RoboWar1 ['--dosbox', '<eXo>\\\\emulators\\\\dosbox\\\\DOSBox.exe', '--dosbox-conf', " \
                 "'<eXo>\\\\eXoDOS\\\\!dos\\\\RoboWar1\\\\dosbox.conf', '--dosbox-conf', " \
                 "'<eXo>\\\\emulators\\\\dosbox\\\\options.conf']"
        check(expect in out and 'BACK <eXo>\n' in out.replace('\r', ''), 'launcher: the port, from the game folder:\n'
              '         ' + out.strip().replace('\n', '\n         '))
        out = launcher(root, dos, game, '')
        check('DOSBox.exe' in out, 'launcher without %dosbox%: DOSBox.exe')
        os.remove(port)
        shutil.copyfile(exe, exe + '.keep')
        shutil.copyfile(os.path.join(os.environ['SystemRoot'], 'System32', 'where.exe'), exe)
        out = launcher(root, dos, game, 'DOSBox.exe')
        check('windows editor still runs' in out and 'PORT-RAN' not in out, 'launcher without rw1edit.py: '
              'the old note and RW1_EDIT.EXE')
        shutil.copyfile(exe + '.keep', exe)
        os.remove(exe + '.keep')
        with open(port, 'wb') as f:
            f.write(saved_port)

        # undo both
        rc, out = run('install_port.py', '--revert', root)
        check(rc == 0 and read(bat) == orig_bat and not os.path.exists(port) and not os.path.exists(bat + '.orig'),
              'install_port --revert: exception.bat as it was')
        rc, out = run('fix_windows.py', '--revert', root)
        check(sha1(exe) == SHA1_ORIGINAL, 'fix_windows --revert after both')
        left = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)
        check(left == sorted(['eXoDOS\\RoboWar1\\RW1_EDIT.EXE', 'eXoDOS\\!dos\\RoboWar1\\exception.bat',
                              'eXoDOS\\!dos\\RoboWar1\\dosbox.conf', 'util\\setconsole.exe']),
              'nothing else left: %r' % left)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print('%d failed' % len(BAD))
    return len(BAD)


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
