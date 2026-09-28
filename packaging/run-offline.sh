#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Docker with Compose is required.' >&2; exit 1; }
arch=$(uname -m)
case "$arch" in x86_64|amd64) arch=amd64 ;; aarch64|arm64) arch=arm64 ;; *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; esac
archive="dist/raptorgate-$arch.tar"
[ -f "$archive" ] || { echo "Missing offline image archive: $archive" >&2; exit 1; }
[ -f "dist/raptorgate-$arch.tar.sha256" ] || { echo "Missing checksum manifest" >&2; exit 1; }
expected=$(awk 'NR==1 {print $1}' "dist/raptorgate-$arch.tar.sha256")
if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$archive" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
  actual=$(shasum -a 256 "$archive" | awk '{print $1}')
else
  echo 'SHA-256 checksum utility required.' >&2; exit 1
fi
[ "$actual" = "$expected" ] || { echo 'Offline archive SHA256 mismatch.' >&2; exit 1; }
[ ${#expected} -eq 64 ] || { echo "Invalid SHA-256 manifest" >&2; exit 1; }
docker load -i "$archive"
docker image inspect "raptorgate-portal:$arch" --format '{{.Architecture}}' | grep -qx "$arch"
docker image inspect "raptorgate-postgres:$arch" --format '{{.Architecture}}' | grep -qx "$arch"
export RG_ARCH="$arch"
docker compose -f packaging/docker-compose.offline.yml up --no-build --pull never
