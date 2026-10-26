"""Validate wheel versions separately from binding build and loaded Qt versions."""
from pathlib import Path
import sys

EXPECTED = {'PyQt6':'6.9.1','PyQt6-Qt6':'6.9.1',
            'PyQt6-WebEngine':'6.9.0','PyQt6-WebEngine-Qt6':'6.9.0','PyQt6-sip':'13.10.2'}

def validate_versions(packages, compiled, before, after, library, webengine):
    for name, expected in EXPECTED.items():
        if packages.get(name) != expected:
            raise RuntimeError(f'{name}: expected {expected}, found {packages.get(name)}')
    # PyQt6 6.9.1 Windows wheels were compiled against Qt 6.9.0 headers.
    # QT_VERSION_STR is that build constant, not the loaded Qt DLL version.
    if compiled != '6.9.0':
        raise RuntimeError(f'Unexpected PyQt Qt build version: {compiled}')
    if (before, after, library) != ('6.9.1','6.9.1','6.9.1'):
        raise RuntimeError(f'Qt runtime must remain 6.9.1 before/after WebEngine: {(before, after, library)}')
    if webengine != '6.9.0':
        raise RuntimeError(f'Qt WebEngine runtime must be 6.9.0: {webengine}')

def inspect_runtime():
    import importlib.metadata as metadata
    from PyQt6.QtCore import QT_VERSION_STR, QLibraryInfo, qVersion
    packages = {name:metadata.version(name) for name in EXPECTED}
    before = qVersion()
    dll_before = core_dll_path() if sys.platform == 'win32' else None
    from PyQt6.QtWebEngineCore import qWebEngineVersion
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    after = qVersion()
    dll_after = core_dll_path() if sys.platform == 'win32' else None
    library = QLibraryInfo.version().toString()
    webengine = qWebEngineVersion()
    validate_versions(packages, QT_VERSION_STR, before, after, library, webengine)
    if sys.platform == 'win32':
        expected = Path(metadata.distribution('PyQt6-Qt6').locate_file('PyQt6/Qt6/bin/Qt6Core.dll')).resolve()
        if dll_before != dll_after or dll_after != expected:
            raise RuntimeError(f'Unexpected Qt6Core.dll: before={dll_before}, after={dll_after}, expected={expected}')
    return {'packages':packages, 'binding_compiled_qt':QT_VERSION_STR,
            'runtime_before_webengine':before, 'runtime_after_webengine':after,
            'library_runtime':library, 'webengine_runtime':webengine,
            'qt_core_dll':str(dll_after) if dll_after else None}

def core_dll_path():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    handle = kernel.GetModuleHandleW('Qt6Core.dll')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetModuleFileNameW(handle,buffer,len(buffer))
    if not length or length >= len(buffer):
        raise RuntimeError('Cannot resolve loaded Qt6Core.dll path')
    return Path(buffer.value).resolve()

if __name__ == '__main__':
    import json
    print(json.dumps(inspect_runtime(), indent=2))
