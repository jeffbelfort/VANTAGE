"""Fail closed before uploading: audit ZIP, relocate, run frozen engine and both GUIs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT/'dist/VANTAGE'
OUT = ROOT/'windows-artifacts'

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def validate_process_result(run, report, label):
    """Surface the windowed executable's JSON traceback without weakening exit gates."""
    result = None
    report_error = None
    if report.is_file():
        try:
            result = json.loads(report.read_text(encoding='utf-8'))
            if not isinstance(result, dict):
                report_error = 'Completion report is not a JSON object'
                result = None
        except (ValueError, OSError) as exc:
            report_error = f'Cannot read completion report: {exc}'
    if run.returncode != 0:
        details = (result or {}).get('traceback') or (result or {}).get('error') or report_error
        if not details:
            details = (run.stderr or run.stdout or 'No Python completion report; possible bootloader/native startup failure')[-8000:]
        raise RuntimeError(f'{label} exited {run.returncode}:\n{details}\nReport: {report}')
    require(report.is_file(), f'{label} produced no completion report')
    require(result is not None, f'{label}: {report_error}')
    require(result.get('passed') is True, f'{label} failed: {result}')
    return result

def audit(directory):
    files = [p for p in directory.rglob('*') if p.is_file()]
    names = {p.name.lower() for p in files}
    required = {'vantage.exe','python312.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','qtwebengineprocess.exe','qt6webenginecore.dll',
                'qt6webenginewidgets.dll','qt6webchannel.dll','qt6core.dll','qt6gui.dll',
                'qt6widgets.dll','qt6network.dll','qwindows.dll','icudtl.dat',
                'qtwebengine_resources.pak','qtwebengine_resources_100p.pak',
                'qtwebengine_resources_200p.pak','app.js','boot.js','index.html','style.css','icon.svg'}
    require(not required-names, 'Missing runtime payload: '+str(sorted(required-names)))
    require(any('qtwebengine_locales' in p.parts and p.suffix=='.pak' for p in files), 'Missing WebEngine locales')
    for name in ('securities.json','fx-reference-snapshot.json','verified-equity-references.json',
                 'market-classifications.json','lifestyle-catalogue.json'):
        require(name in names, 'Missing reference data: '+name)
    forbidden = {'runtime','data','reports','evidence','.git','.vantage-git','.aws','.codex','node_modules','__pycache__'}
    for file in files:
        relative = file.relative_to(directory)
        require(not file.is_symlink(), 'Symlink in payload: '+str(relative))
        require(not forbidden.intersection(part.lower() for part in relative.parts), 'Private directory: '+str(relative))
        require(file.suffix.lower() not in {'.sqlite','.db','.log','.map','.pem','.key'}, 'Private file: '+str(relative))
        require(not file.name.endswith(('.sqlite-wal','.sqlite-shm')), 'SQLite sidecar in payload')
    # Verify the main application and Chromium subprocess really are AMD64 PE binaries.
    for executable in (directory/'VANTAGE.exe',next(p for p in files if p.name.lower()=='qtwebengineprocess.exe')):
        with executable.open('rb') as stream:
            require(stream.read(2)==b'MZ','Missing PE executable header')
            stream.seek(0x3c); offset=struct.unpack('<I',stream.read(4))[0]
            stream.seek(offset); require(stream.read(4)==b'PE\0\0','Invalid PE signature')
            require(struct.unpack('<H',stream.read(2))[0]==0x8664,'Executable is not x64')
    # Check static and delay-load DLL imports against shipped DLLs or the Windows OS.
    import pefile
    unresolved = set()
    for file in files:
        if file.suffix.lower() not in {'.exe','.dll','.pyd'}:
            continue
        pe=pefile.PE(str(file),fast_load=True)
        try:
            pe.parse_data_directories(directories=[1,13])
            for entry in [*getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]),*getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[])]:
                name=entry.dll.decode('ascii').lower()
                if name.startswith(('api-ms-','ext-ms-')):
                    continue
                if name.startswith(('msvcp140','vcruntime140','concrt140')) and name not in names:
                    unresolved.add((file.name,name))
                elif name not in names and not (Path(os.environ['SystemRoot'])/'System32'/name).is_file():
                    unresolved.add((file.name,name))
        finally:pe.close()
    require(not unresolved,'Unresolved DLL imports: '+repr(sorted(unresolved)))
    return {p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def main():
    require(sys.platform=='win32','This validation requires a native Windows x64 runner')
    expected=os.environ.get('VANTAGE_BUILD_PYTHON')
    if expected:
        require(Path(sys.executable).resolve()==Path(expected).resolve() and sys.prefix!=sys.base_prefix,
                'Packaged validation must run from the isolated build environment')
    OUT.mkdir(exist_ok=True)
    diagnostics=OUT/'diagnostics';diagnostics.mkdir(exist_ok=True)
    hashes=audit(DIST)
    archive=OUT/'VANTAGE-Windows-x64.zip'
    shutil.make_archive(str(archive.with_suffix('')),'zip',DIST.parent,DIST.name)
    results={}
    # Keep tests/profiles outside the source tree and outside the archive, with spaces in paths.
    with tempfile.TemporaryDirectory(prefix='VANTAGE Windows release ') as folder:
        folder=Path(folder)
        with zipfile.ZipFile(archive) as zipped:zipped.extractall(folder)
        package=folder/'VANTAGE'
        require(audit(package)==hashes,'ZIP payload differs from audited frozen directory')
        for label,flag in [('engine','--release-self-test'),('native-gui','--smoke-test'),('webengine-gui','--webengine-smoke-test')]:
            profile=folder/('fresh '+label);profile.mkdir()
            report=diagnostics/(label+'.json')
            report.unlink(missing_ok=True)
            env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QT_QPA_PLATFORM','QTWEBENGINE_CHROMIUM_FLAGS','QTWEBENGINE_REMOTE_DEBUGGING','VANTAGE_DATABASE','VANTAGE_LOG_DIR'}}
            env.update(LOCALAPPDATA=str(profile),XDG_DATA_HOME=str(profile),VANTAGE_VALIDATION_REPORT=str(report))
            # Test the actual Windows desktop platform (qwindows), not offscreen Chromium.
            run=subprocess.run([str(package/'VANTAGE.exe'),flag],cwd=folder,env=env,capture_output=True,text=True,timeout=120)
            (diagnostics/(label+'.txt')).write_text((run.stdout or '')+'\n'+(run.stderr or ''),encoding='utf-8')
            results[label]=validate_process_result(run,report,label)
        require(audit(package)==hashes,'Application modified the distributed payload during tests')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (OUT/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    validation={'built':True,'tested_on':sys.platform,'architecture':'x64','sha256':digest,
                'compressed_bytes':archive.stat().st_size,'extracted_bytes':sum(p.stat().st_size for p in DIST.rglob('*') if p.is_file()),
                'payload_files':len(hashes),'tests':results}
    (OUT/'WINDOWS-VALIDATION.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    print(json.dumps(validation,indent=2))

if __name__=='__main__':main()
