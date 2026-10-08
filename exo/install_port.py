"""install_port.py [--check | --revert] EXO

Installs the port into an eXoDOS collection (Windows): rw1edit.py next to
eXoDOS\\RoboWar1\\RW1_EDIT.EXE, and exception.bat's "windows based editor"
option runs it - from the game folder, with the collection's DOSBox and the
game's dosbox.conf for Compile and Run - when Python (the `py` launcher) and
rw1edit.py are there; else the original RW1_EDIT.EXE as before.
exception.bat.orig keeps the original. EXO is the folder with eXoDOS\\ and util\\.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join('eXoDOS', 'RoboWar1')
BAT = os.path.join('eXoDOS', '!dos', 'RoboWar1', 'exception.bat')

OLD = """:winedit
cd ..
cd ..
cd ..
cls
echo.
"""
NEW = """:winedit
cd ..
cd ..
cd ..
cls
where py >nul 2>nul
if errorlevel 1 goto winedit_exe
if not exist ".\\eXoDOS\\%GameDir%\\rw1edit.py" goto winedit_exe
.\\util\\setconsole.exe /minimize
set rw1dosbox=%dosbox%
if "%rw1dosbox%"=="" set rw1dosbox=DOSBox.exe
set rw1dosbox=%CD%\\emulators\\dosbox\\%rw1dosbox%
set rw1options=%CD%\\emulators\\dosbox\\options.conf
cd ".\\eXoDOS\\%GameDir%"
py rw1edit.py --dosbox "%rw1dosbox%" --dosbox-conf "%var%\\dosbox.conf" --dosbox-conf "%rw1options%"
cd ..
cd ..
goto end

:winedit_exe
echo.
"""


def crlf(s):
    return s.replace('\n', '\r\n')


def source():
    """rw1edit.py: next to this script (a release) or one folder up (the project)"""
    for p in (os.path.join(HERE, 'rw1edit.py'), os.path.join(HERE, '..', 'rw1edit.py')):
        if os.path.isfile(p):
            return p
    sys.exit('rw1edit.py is not next to %s' % os.path.basename(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--check', action='store_true', help='only say whether it is installed')
    ap.add_argument('--revert', action='store_true', help='put the original exception.bat back, remove rw1edit.py')
    ap.add_argument('exo')
    a = ap.parse_args()
    bat = os.path.join(a.exo, BAT)
    game = os.path.join(a.exo, GAME)
    port = os.path.join(game, 'rw1edit.py')
    if not os.path.isfile(bat) or not os.path.isfile(os.path.join(game, 'RW1_EDIT.EXE')):
        sys.exit('%s: no Robot Warfare 1 there (%s, %s)' % (a.exo, BAT, GAME))
    with open(bat, 'rb') as f:
        text = f.read().decode('latin-1')
    patched = crlf(NEW) in text
    if a.check:
        with open(source(), 'rb') as f:
            same = os.path.isfile(port) and open(port, 'rb').read() == f.read()
        print('exception.bat: %s; rw1edit.py: %s' % ('patched' if patched else 'original',
                                                     'current' if same else 'present (different)'
                                                     if os.path.isfile(port) else 'missing'))
        return
    if a.revert:
        if os.path.isfile(bat + '.orig'):
            shutil.copy2(bat + '.orig', bat)
            os.remove(bat + '.orig')
            print('restored', bat)
        if os.path.isfile(port):
            os.remove(port)
            print('removed', port)
        return
    shutil.copyfile(source(), port)
    print('copied', port)
    if patched:
        print('exception.bat already patched')
        return
    if crlf(OLD) not in text:
        sys.exit('exception.bat: the :winedit part is not as expected - not changed')
    if not os.path.exists(bat + '.orig'):
        shutil.copy2(bat, bat + '.orig')
    with open(bat, 'wb') as f:
        f.write(text.replace(crlf(OLD), crlf(NEW), 1).encode('latin-1'))
    print('patched', bat, '(original: exception.bat.orig)')


if __name__ == '__main__':
    main()
