$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$image = "cuktech-ap01-build-tools:1.0"

docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker service is not running"
}

docker build `
    --platform linux/amd64 `
    --tag $image `
    --file (Join-Path $repoRoot "tools/docker/Dockerfile") `
    (Join-Path $repoRoot "tools/docker")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build the firmware tool image"
}

$runArguments = @(
    "run",
    "--rm",
    "--platform", "linux/amd64",
    "--mount", "type=bind,source=$repoRoot,target=/workspace",
    "--workdir", "/workspace",
    $image
) + $args

& docker @runArguments
exit $LASTEXITCODE
