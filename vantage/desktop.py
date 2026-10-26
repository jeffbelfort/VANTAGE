"""Native Qt 6 desktop shell. No cloud service or external browser required."""
import os, sys
from pathlib import Path
from .bridge import ROOT,Bridge
import logging

def main():
    from .paths import prepare_release
    prepare_release()
    if '--check' in sys.argv:
        from .diagnostics import report
        import json
        print(json.dumps(report(),indent=2));return 0
    use_native='--native' in sys.argv or '--smoke-test' in sys.argv
    if not use_native:
        import socket
        try:
            probe=socket.socket();probe.close()
        except PermissionError:use_native=True
    if not use_native:
        try:from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError:use_native=True
    if use_native and '--webengine-smoke-test' in sys.argv:
        raise RuntimeError('WebEngine smoke test cannot fall back to Qt Widgets')
    if use_native:
        from .native import main as native_main
        return native_main()
    if not (ROOT/'static'/'app.js').exists():raise SystemExit('Run npm run build first.')
    from PyQt6.QtCore import QUrl, Qt
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtGui import QIcon, QAction, QKeySequence
    from PyQt6.QtWidgets import QApplication,QMainWindow,QMessageBox
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile
    app=QApplication(sys.argv);app.setApplicationName('VANTAGE');app.setOrganizationName('Vantage Local')
    # Off-the-record web profile: authoritative state is entirely in SQLite.
    profile=QWebEngineProfile(app)
    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self,url,kind,main):
            return (url.isLocalFile() and Path(url.toLocalFile()).resolve().is_relative_to(ROOT/'static')) or url.toString()=='about:blank'
    window=QMainWindow();window.setWindowTitle('VANTAGE' if __import__('vantage.paths',fromlist=['RELEASE']).RELEASE else 'VANTAGE — DEVELOPMENT — SEPARATE SAVE');window.setWindowIcon(QIcon(str(ROOT/'static'/'icon.svg')));window.resize(1560,980);window.setMinimumSize(1050,700)
    from .logging_config import configure
    configure(ROOT)
    try:bridge=Bridge(parent=app)
    except Exception as exc:
        QMessageBox.critical(None,'VANTAGE cannot open this save',str(exc)+'\nYour database has not been reset.');return 1
    view=QWebEngineView();page=LocalPage(profile,view);view.setPage(page);window.setCentralWidget(view)
    channel=QWebChannel(page);channel.registerObject('vantage',bridge);page.setWebChannel(channel)
    zoomIn=QAction(window);zoomIn.setShortcut(QKeySequence('Ctrl++'));zoomIn.triggered.connect(lambda:view.setZoomFactor(min(2,view.zoomFactor()+.1)));window.addAction(zoomIn)
    zoomOut=QAction(window);zoomOut.setShortcut(QKeySequence('Ctrl+-'));zoomOut.triggered.connect(lambda:view.setZoomFactor(max(.6,view.zoomFactor()-.1)));window.addAction(zoomOut)
    view.load(QUrl.fromLocalFile(str(ROOT/'static'/'index.html')));window.show()
    if '--webengine-smoke-test' in sys.argv:
        from .release_checks import monitor_webengine
        monitor_webengine(app,view,bridge)
    code=app.exec();bridge.close();return code
if __name__=='__main__':sys.exit(main())
