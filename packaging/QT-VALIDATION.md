# Qt validation fix for run 40388082882

The reported `QT_VERSION_STR == 6.9.0` is PyQt's compile-time Qt header version. It is not a measurement of the loaded Qt DLL. The old assertion incorrectly required this build constant to equal the Qt runtime wheel's 6.9.1 version. PyQt6's own version (6.9.1), its build-time Qt version (6.9.0), the loaded Qt Core version (expected 6.9.1), and the Qt WebEngine component version (6.9.0) are separate values.

Qt documents the distinction between `QT_VERSION_STR` and `qVersion()`:
https://doc.qt.io/qt-6.5/qtversion-qtcore-proxy.html
Riverbank's PyQt discussion explicitly describes the same behavior:
https://www.riverbankcomputing.com/pipermail/pyqt/2025-December/046408.html
Qt's patch-release binary compatibility policy:
https://wiki.qt.io/Coding_Conventions#Binary_and_Source_Compatibility

This failure is explained by an incorrect validation assumption; the observed build constant alone is not evidence that WebEngine loads a different runtime or that the binaries are incompatible. Actual Windows DLL provenance/runtime measurements are still required; this session has no Windows interpreter and has not executed a Windows build.

No dependency pins were changed. The existing Qt/PyQt6 6.9.1 and WebEngine 6.9.0 wheel pins remain reproducible within the existing isolated virtual environment, with mandatory `pip check`.

The new `python -m vantage.qt_runtime` preflight checks:

- Exact installed versions of all five Qt/PyQt/SIP distributions.
- The expected build constant 6.9.0 for the selected Windows PyQt wheel.
- `qVersion()` equals 6.9.1 before and after importing WebEngine.
- `QLibraryInfo.version()` also equals 6.9.1.
- `qWebEngineVersion()` equals 6.9.0.
- The actual loaded `Qt6Core.dll` path, read using Windows loader APIs, is unchanged after WebEngine imports and belongs to the pinned PyQt6-Qt6 distribution.

The frozen WebEngine GUI smoke test repeats these checks using bundled wheel metadata before verifying the existing React onboarding/bridge. Its report now labels the loaded Qt version and binding build version separately. Native GUI tests, packaged engine regressions, clean profile checks, DLL closure audit, and download publication gates are retained.

Seven new tests accept the legitimate compile/runtime distinction and reject an old loaded runtime, runtime replacement after WebEngine import, conflicting QLibraryInfo, WebEngine version drift, wheel version drift and unexpected binding builds. They run alongside the existing 44 synthetic-profile regressions (51 tests total). Historical-save tests remain excluded.

Local checks: 51 regressions passed; Python/spec/workflow syntax passed; TypeScript/production frontend build and JavaScript syntax passed; synthetic engine lifecycle/acquisition checks passed; offscreen native GUI launch with 30 pages passed. Windows DLL provenance, frozen Windows packaging and real WebEngine rendering cannot be verified on this Linux host. The Linux release archive remains unchanged. No GitHub push or workflow dispatch was attempted for this fix.
