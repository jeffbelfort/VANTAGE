# Publish an existing verified Windows build

Workflow: `.github/workflows/publish-windows.yml`, displayed as **Publish verified Windows release**.

After this workflow is pushed to the default branch, open Actions, select the workflow, and choose Run workflow. Set:

- `run_id`: successful **Windows x64 release** build run, default `40390722454`.
- `release_tag`: new version tag, default `v1.0.0`.

The workflow does not check out or rebuild the game. GitHub's runner downloads only the `VANTAGE-Windows-x64` artifact from the selected run with `actions/download-artifact@v4`, using the repository, run ID and GitHub token. Nothing downloads to the local Linux machine.

Before release creation it verifies source workflow identity, completed/success conclusion, source repository, artifact availability, the three expected files, ZIP SHA-256 and size, and successful engine/native GUI/WebEngine GUI validation. It publishes exactly:

- `VANTAGE-Windows-x64.zip`
- `SHA256SUMS.txt`
- `WINDOWS-VALIDATION.json`

The release tag targets the verified build's source commit, not the publishing workflow's newer commit. An existing tag pointing elsewhere or an existing release is refused. Assets are uploaded to a draft first; the release becomes published only after successful upload. If upload fails after draft creation, inspect/remove the incomplete draft before retrying; existing release assets are never silently overwritten.

Permissions: `contents: write`, `actions: read`, using `GITHUB_TOKEN`; no personal access token is needed. A publicly accessible release requires the repository to be public. The workflow explicitly refuses private repositories and does not change visibility or expose private source/history. Repository/tag protection policies may also restrict release creation.

Local validation used synthetic tiny fixtures only: workflow YAML and embedded JavaScript/Python/Bash syntax, ten source-run/release preflight cases, and seven artifact/checksum/validation cases passed. No GitHub API mutation, push, workflow dispatch, rebuild or actual build-artifact download was performed during implementation.
