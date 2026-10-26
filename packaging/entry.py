"""Windowed executable entrypoint; validation runs use the actual frozen runtime."""
import json
import os
from pathlib import Path
import sys
import traceback

def main():
    from vantage.paths import prepare_release
    prepare_release()
    report = os.environ.get('VANTAGE_VALIDATION_REPORT')
    try:
        if '--release-self-test' in sys.argv:
            from vantage.release_checks import engine_checks
            result = engine_checks()
            if not report:
                raise ValueError('A validation report path is required')
            Path(report).write_text(json.dumps(result, indent=2), encoding='utf-8')
            return 0
        from vantage.desktop import main as desktop_main
        return desktop_main()
    except Exception:
        if report:
            Path(report).write_text(json.dumps({'passed':False, 'traceback':traceback.format_exc()}, indent=2), encoding='utf-8')
        else:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, 'VANTAGE startup failed', traceback.format_exc())
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
