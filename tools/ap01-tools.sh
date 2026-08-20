#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
image="cuktech-ap01-build-tools:1.0"

docker info --format '{{.ServerVersion}}' >/dev/null
docker build \
    --platform linux/amd64 \
    --tag "$image" \
    --file "$repo_root/tools/docker/Dockerfile" \
    "$repo_root/tools/docker"

exec docker run \
    --rm \
    --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$repo_root,target=/workspace" \
    --workdir /workspace \
    "$image" \
    "$@"
