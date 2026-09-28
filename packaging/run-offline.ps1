$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker with Compose is required.' }
$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($arch -eq 'x64') { $arch = 'amd64' }
elseif ($arch -eq 'arm64') { $arch = 'arm64' }
else { throw "Unsupported architecture: $arch" }
$archive = Join-Path $root "dist/raptorgate-$arch.tar"
$manifest = Join-Path $root "dist/raptorgate-$arch.tar.sha256"
if (-not (Test-Path $archive) -or -not (Test-Path $manifest)) { throw "Missing archive or checksum: $archive" }
$expected = ((Get-Content $manifest -First 1).Split(' ',[System.StringSplitOptions]::RemoveEmptyEntries))[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw 'Offline archive SHA256 mismatch.' }
$env:RG_ARCH = $arch
docker load -i $archive
if ($LASTEXITCODE -ne 0) { throw 'Docker image load failed.' }
$portalArch = docker image inspect "raptorgate-portal:$arch" --format '{{.Architecture}}'
if ($LASTEXITCODE -ne 0 -or $portalArch.Trim() -ne $arch) { throw 'Portal image architecture mismatch.' }
$dbArch = docker image inspect "raptorgate-postgres:$arch" --format '{{.Architecture}}'
if ($LASTEXITCODE -ne 0 -or $dbArch.Trim() -ne $arch) { throw 'PostgreSQL image architecture mismatch.' }
docker compose -f packaging/docker-compose.offline.yml up --no-build --pull never
if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed.' }
