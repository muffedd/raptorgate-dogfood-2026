#!/bin/sh
set -eu
# Run ONLINE on a Docker host with buildx support and enough disk for two architectures.
# Builds application images and stages them in a local registry-independent archive.
cd "$(dirname "$0")/.."
command -v docker >/dev/null
mkdir -p dist
command -v sha256sum >/dev/null || { echo "sha256sum required to build manifest" >&2; exit 1; }
for arch in amd64 arm64; do
  docker pull --platform "linux/$arch" postgres:16-alpine
  docker tag postgres:16-alpine "raptorgate-postgres:$arch"
  docker image inspect "raptorgate-postgres:$arch" --format '{{.Architecture}}' | grep -qx "$arch" || { echo "PostgreSQL image architecture mismatch: $arch" >&2; exit 1; }
  docker buildx build --platform "linux/$arch" --load -f packaging/Dockerfile.offline -t "raptorgate-portal:$arch" .
  docker image inspect "raptorgate-portal:$arch" --format '{{.Architecture}}' | grep -qx "$arch" || { echo "Portal image architecture mismatch: $arch" >&2; exit 1; }
  docker image inspect "raptorgate-portal:$arch" --format '{{.Id}} {{.Architecture}}' > "dist/portal-$arch.inspect"
  docker image inspect "raptorgate-postgres:$arch" --format '{{.Id}} {{.Architecture}}' > "dist/postgres-$arch.inspect"
  docker save -o "dist/raptorgate-$arch.tar" "raptorgate-portal:$arch" "raptorgate-postgres:$arch"
  (cd dist && sha256sum "raptorgate-$arch.tar" > "raptorgate-$arch.tar.sha256")
done
printf '%s\n' 'Copy dist/ archives and this repository to the offline machine, then run packaging/run-offline.sh.'
