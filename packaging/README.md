# Offline image bundle: build online, then boot offline

**Proof scope:** An independent operator's September 29 report records a successful offline cold boot on exact commit `4cd5a399c5c7979f544d6209053a0b6f8facba25` in a fresh disposable Ubuntu 24.04 x86_64 VM. Docker images and volumes were empty before the build; the amd64 archive was checked, target tags were absent before load, and `ens3` was down during boot and proof (internet probe failed with DNS error). The built image contained `/app/fixtures.json`; PostgreSQL became healthy, 41 project rows and 126 scores seeded, 40 canonical projects appeared in the gallery, gallery and CSS returned HTTP 200, and the official checker printed seven literal PASS, no FAIL, ending `claimed T1 T2, verified T1 T2`. The repository ships scripts, not container archives. Documentation and browser-flow fixes are later than the proved SHA; no later SHA, arm64 or Windows cold boot is covered by that run.

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

Mac/Linux: while online, `sh packaging/build-offline-bundle.sh` attempts both architectures; offline, run `sh packaging/run-offline.sh` with the archive for the destination CPU. The Linux build selects and tags each PostgreSQL architecture separately rather than retagging the mutable upstream tag. On a plain amd64 Docker Engine without QEMU/binfmt support, the arm64 PostgreSQL leg completed, but the arm64 portal build failed at `RUN pip install` with `exec format error`; the amd64 archive and independent cold boot passed. The script exits nonzero after the arm64 failure even when the amd64 archive is present. Check and use only a complete, checksum-verified archive for the destination CPU. Build arm64 natively or install and verify emulation before claiming an arm64 archive; no arm64 cold boot was proved. `dist/` is excluded from Git and Docker build context because the archives are binary and large. Carry only the matching architecture's archive and checksum into the offline checkout.

If Docker is not running or `buildx` is missing, start/update Docker Desktop and rerun the build online. If the archive is missing, carry both `.tar` and `.tar.sha256`. If the architecture differs, build on or for that architecture first; the scripts refuse to run an incorrect image. If port 8080 is occupied, free it before boot. If the database is unhealthy, inspect `docker compose -f packaging/docker-compose.offline.yml logs db`; do not delete an existing volume until you know it contains only disposable fixture data.

**Evidence caveats:** The independent report's raw `offline-proof.log` lists seven probe PASS lines. Its `done-criteria.log` incorrectly counted six because the operator's grep was too strict. A `sudo docker compose` query in `seed-counts.log` lost `RG_ARCH`, while the corrected plain-Docker `compose-ps.log` showed healthy services. Its shallow `python3 -m unittest packaging.tests...` attempt failed to import the test module; the fixture's presence was verified in the built image instead. The operator used a detached driver session rather than two terminals. These are report-harness discrepancies, not proof of a separate arm64 or Windows result.

**Security:** The fixture sessions and demo database key are fixed local-only values. Compose binds HTTP to `127.0.0.1`; never publish this stack as-is. Current image tags are not pinned by immutable digest, and checksum files do not authenticate a malicious replacement. Pin the sources and sign the archive manifest before calling this a reproducible secure release.
