from pathlib import Path
import os, sys
from PyInstaller.utils.hooks import copy_metadata
root = Path(SPECPATH).parent
runtime_binaries=[]
if sys.platform=='win32':
    system=Path(os.environ['SystemRoot'])/'System32'
    for pattern in ('msvcp140*.dll','vcruntime140*.dll','concrt140.dll'):
        runtime_binaries += [(str(p),'.') for p in system.glob(pattern)]
metadata=[]
for distribution in ('PyQt6','PyQt6-Qt6','PyQt6-WebEngine','PyQt6-WebEngine-Qt6','PyQt6-sip'):
    metadata += copy_metadata(distribution)
# Explicit resource allowlist: never collect runtime/, data/, reports/ or user homes.
a = Analysis([str(root/'packaging/entry.py')], pathex=[str(root)],
    binaries=runtime_binaries,
    datas=[(str(root/'assets'), 'assets'), (str(root/'static'), 'static')]+metadata,
    hiddenimports=['PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebChannel', 'PyQt6.QtWebEngineCore', 'vantage.release_checks'],
    excludes=['tkinter','unittest','numpy','pandas','matplotlib','IPython', 'vantage.save_migration'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VANTAGE', console=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VANTAGE')
