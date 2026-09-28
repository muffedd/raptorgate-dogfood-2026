# Offline image bundle: build online, then boot offline

**Status: unverified plan.** This repository currently ships scripts, not container archives. No Docker-capable cold, network-off rehearsal has been run here. Do not claim the one-command offline requirement is met until a real destination run passes.

## Windows PC (Docker Desktop running)

Open PowerShell in this repository while **online**. Run one build command:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build-offline-bundle.ps1
```

This builds Linux amd64 or arm64 portal/PostgreSQL images for the machine's architecture and writes `dist/raptorgate-<arch>.tar` plus its `.sha256` file. It requires Docker Desktop, Compose, buildx, enough free disk space, and online access to Docker Hub and PyPI. The archive can be large. Watch for the final `Built ... SHA256 ...` line; a failed command produces no proof.

Then disconnect the network. With the whole checkout and `dist/` present, run one boot command from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/run-offline.ps1
```

This checks the SHA-256, loads the local images, checks CPU architecture and starts Compose with `--no-build --pull never`. Leave that PowerShell window open. On another terminal, check `http://127.0.0.1:8080/projects`; a fresh volume should seed the sample event. Run `powershell -ExecutionPolicy Bypass -File packaging/prove-offline.ps1` in another PowerShell window. It captures Docker/image identifiers, verifies gallery and CSS HTTP 200s, and executes `run.py` with Python 3 or Windows `py -3`. The proof script itself checks all seven literal `PASS` lines (and no `FAIL`), rather than trusting the checker exit code. The proof script does not disconnect the network or delete Docker data; record those preconditions separately. Capture the Docker/Compose versions, archive SHA, startup log, actual HTTP responses, checker output, and whether the network was disabled. To prove a *cold* boot, use an isolated machine or throwaway Docker data directory with no prior images or volumes, rather than a warmed dev profile.

Mac/Linux: while online, `sh packaging/build-offline-bundle.sh` builds both architectures; offline, run `sh packaging/run-offline.sh`. Both scripts are untested on real Docker here. `dist/` is excluded from Git and Docker build context because the archives are binary and large. Carry only the matching architecture's archive and checksum into the offline checkout.

If Docker is not running or `buildx` is missing, start/update Docker Desktop and rerun the build online. If the archive is missing, carry both `.tar` and `.tar.sha256`. If the architecture differs, build on or for that architecture first; the scripts refuse to run an incorrect image. If port 8080 is occupied, free it before boot. If the database is unhealthy, inspect `docker compose -f packaging/docker-compose.offline.yml logs db`; do not delete an existing volume until you know it contains only disposable fixture data.

**Security:** The fixture sessions and demo database key are fixed local-only values. Compose binds HTTP to `127.0.0.1`; never publish this stack as-is. Current image tags are not pinned by immutable digest, and checksum files do not authenticate a malicious replacement. Pin the sources and sign the archive manifest before calling this a reproducible secure release.
