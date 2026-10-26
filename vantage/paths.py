"""Separate immutable application resources from per-user release state."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
RELEASE = bool(getattr(sys, 'frozen', False)) or (ROOT / '.vantage-release').is_file()
def runtime_directory():
    if not RELEASE:
        return ROOT / 'runtime'
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    return base / 'VANTAGE'
def prepare_release():
    if RELEASE:
        os.environ.pop('QTWEBENGINE_REMOTE_DEBUGGING', None)
        directory = runtime_directory()
        directory.mkdir(parents=True, exist_ok=True)
        # Never inherit a developer database override into a distributed release.
        os.environ['VANTAGE_DATABASE'] = str(directory / 'vantage.sqlite')
        os.environ['VANTAGE_LOG_DIR'] = str(directory / 'logs')
