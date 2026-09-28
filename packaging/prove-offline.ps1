$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required.' }
Write-Host "Network status and empty Docker profile must be recorded manually before this proof. This script does not disconnect your network or delete images/volumes."
$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($arch -eq 'x64') { $arch = 'amd64' }
elseif ($arch -ne 'arm64') { throw "Unsupported architecture: $arch" }
$manifest = "dist/raptorgate-$arch.tar.sha256"
$archive = "dist/raptorgate-$arch.tar"
if (-not (Test-Path $manifest) -or -not (Test-Path $archive)) { throw 'Missing archive and/or checksum.' }
Write-Host 'Archive SHA256:'
Get-FileHash -Algorithm SHA256 $archive | Select-Object -ExpandProperty Hash
Write-Host 'Manifest:'
Get-Content $manifest
Write-Host 'Docker/Compose:'
docker version --format '{{.Server.Version}}'
docker compose version
Write-Host 'Image architecture and IDs:'
foreach ($name in @('raptorgate-portal','raptorgate-postgres')) {
  docker image inspect "${name}:$arch" --format '{{.Id}} {{.Architecture}}'
  if ($LASTEXITCODE -ne 0) { throw "Missing image: ${name}:$arch" }
}
Write-Host 'Compose service status:'
$env:RG_ARCH = $arch
docker compose -f packaging/docker-compose.offline.yml ps
Write-Host 'HTTP checks:'
$gallery = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8080/projects' -TimeoutSec 15
if ($gallery.StatusCode -ne 200 -or $gallery.Content -notmatch 'Projects') { throw 'Gallery failed.' }
$css = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8080/static/rg_public_theme.css' -TimeoutSec 15
if ($css.StatusCode -ne 200 -or $css.Content -notmatch 'data-theme') { throw 'CSS failed.' }
Write-Host "Gallery $($gallery.StatusCode), theme CSS $($css.StatusCode)."
$output = if (Get-Command python3 -ErrorAction SilentlyContinue) {
  python3 run.py .dogfood.toml
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 run.py .dogfood.toml
} else { throw 'Python 3 is needed to run the official checker on this machine.' }
if ($LASTEXITCODE -ne 0) { throw 'Checker failed to run.' }
$output | ForEach-Object { Write-Host $_ }
$passes = @($output | Where-Object { $_ -match '^T[12]  .+PASS\s*$' }).Count
$fails = @($output | Where-Object { $_ -match '^T[12]  .+FAIL\s*$' }).Count
if ($passes -ne 7 -or $fails -ne 0) { throw "Checker literal probes failed: PASS=$passes FAIL=$fails" }
Write-Host 'Seven literal official checker probes PASS.'
