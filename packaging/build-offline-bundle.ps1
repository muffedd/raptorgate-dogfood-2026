$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop with Compose and buildx is required. Start Docker Desktop first.' }
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop engine is not running.' }
docker buildx version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker buildx is required.' }
$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($arch -eq 'x64') { $arch = 'amd64' }
elseif ($arch -ne 'arm64') { throw "Unsupported architecture: $arch" }
New-Item -ItemType Directory -Force (Join-Path $root 'dist') | Out-Null
Write-Host "Building Linux/$arch images while ONLINE. This may take several minutes."
docker pull --platform "linux/$arch" postgres:16-alpine
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL image pull failed.' }
docker tag postgres:16-alpine "raptorgate-postgres:$arch"
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL tag failed.' }
docker buildx build --platform "linux/$arch" --load -f packaging/Dockerfile.offline -t "raptorgate-portal:$arch" .
if ($LASTEXITCODE -ne 0) { throw 'Portal image build failed.' }
foreach ($name in @('raptorgate-postgres','raptorgate-portal')) {
  $imageArch = docker image inspect "${name}:$arch" --format '{{.Architecture}}'
  if ($LASTEXITCODE -ne 0 -or $imageArch.Trim() -ne $arch) { throw "Image architecture mismatch: ${name}:$arch" }
}
$archive = Join-Path $root "dist/raptorgate-$arch.tar"
docker save -o $archive "raptorgate-portal:$arch" "raptorgate-postgres:$arch"
if ($LASTEXITCODE -ne 0) { throw 'Docker image archive export failed.' }
$hash = (Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant()
$manifest = Join-Path $root "dist/raptorgate-$arch.tar.sha256"
[System.IO.File]::WriteAllText($manifest, "$hash  raptorgate-$arch.tar`n")
Write-Host "Built $archive ($((Get-Item $archive).Length) bytes); SHA256 $hash"
Write-Host 'Transfer this checkout with dist/ to the offline machine. Then run: powershell -ExecutionPolicy Bypass -File packaging/run-offline.ps1'
