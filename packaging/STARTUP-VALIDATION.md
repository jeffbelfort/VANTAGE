# Packaged engine startup fix: run 40389188636

The downloaded diagnostics artifact's `engine.json` contains:

```
File "entry.py", line 15, in main
File "vantage\release_checks.py", line 13, in engine_checks
File "vantage\engine.py", line 86, in __init__
ValueError: Development build refuses database outside its own runtime directory
```

The failure occurred at the first Engine constructor, before game creation. This is not a missing Qt or SQLite DLL: Python started and entered the engine's save-confinement check.

The engine resolves the candidate SQLite path, but release `runtime_directory()` previously returned an unresolved user-data path. The guard deliberately rejects a runtime directory unequal to its resolved representation. Aliases, Windows short paths/junctions and unnormalised path components can therefore reject a legitimate profile inside its own directory. The trace confirms the guard failure; it does not include the actual Windows alias spelling. The same failure was reproduced locally using an aliased disposable profile before the fix.

The fix resolves the release profile directory in `vantage.paths.runtime_directory()` before callers create/open state. The development runtime return value and engine confinement/backup checks remain unchanged. Databases outside the canonical release profile are still refused. The existing profile is not reset or overwritten; the fix only normalizes the name of the same directory.

The verifier now surfaces the child's JSON traceback in the Actions error instead of replacing it with `engine exited 1; see diagnostics`. It still requires exit code zero, a valid report and `passed: true`. It removes stale completion reports before launch. The windowed entrypoint now also captures exceptions during release-path preparation. All existing engine, native GUI, real WebEngine GUI, dependency/DLL and clean-save validation gates remain intact.

Local validation:

- 62 synthetic-profile regression tests passed: the existing 51, seven diagnostic failure/pass-gate tests and four canonical-profile/confinement tests.
- Full release engine lifecycle checks passed with a newly generated profile through an aliased directory, including save/reload, options, funds, lending, offline advance, acquisition and reconciliation.
- Native GUI launch passed offscreen with all 30 pages.
- Production frontend build/TypeScript and JavaScript syntax checks passed.
- Python/spec syntax, workflow YAML/embedded Python and source/upload parity checks passed.
- Linux payload audit verified all 1,097 files; existing Linux archive SHA-256 remains `a86eb30de2fdecc1d2f6f8c0964d90dba51157fd927feb99f1d4ae1ebc63af99`.

No personal saves were used, modified or packaged. Only disposable profiles were created for tests. No push or Actions dispatch was performed. This Linux environment cannot execute the frozen Windows application or Windows WebEngine GUI; a subsequent Windows workflow must verify the actual executable. This fix does not claim the Windows release has passed that rerun.
