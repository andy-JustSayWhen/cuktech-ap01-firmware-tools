[CmdletBinding()]
param(
    [switch]$RunFullTests
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$toolScript = Join-Path $PSScriptRoot "ap01-tools.ps1"
$imageBuildArguments = @("python", "-c", "pass")
$testArguments = @("python", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py")
$image = "cuktech-ap01-build-tools:1.0"
$input = "artifacts/firmware/第三方固件/物理旋钮交互优化/ap01-1.0.2_0031-opt-setting.bin"
$config = "env/agents-dashboard.env"
$outputRoot = "artifacts/build/personalized"
$cacheRelative = "$outputRoot/.opt-fast-test-cache.json"
$stamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
$outputDirectory = "$outputRoot/fast-$stamp"
$output = "$outputDirectory/ap01-1.0.2_0031-opt-personalized.bin"
$manifest = "$outputDirectory/ap01-1.0.2_0031-opt-personalized.manifest.json"
$report = "$outputDirectory/ap01-1.0.2_0031-opt-personalized.interaction-report.json"
$workDirectory = "$outputDirectory/work"

Set-Location $repoRoot

if (-not (Test-Path -LiteralPath $config)) {
    throw "缺少本机服务地址配置：$config"
}
if (-not (Test-Path -LiteralPath $input)) {
    throw "缺少已验收的设置菜单阶段固件：$input"
}

docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker 服务未启动"
}

$imageId = docker image inspect $image --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -ne 0 -or -not $imageId) {
    & $toolScript @imageBuildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "固件制作镜像创建失败"
    }
    $imageId = docker image inspect $image --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or -not $imageId) {
        throw "固件制作镜像不可用"
    }
}

$inputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $input).Hash.ToLowerInvariant()
$revision = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $revision) {
    throw "无法读取当前代码提交"
}
$implementationChanges = git status --porcelain -- app features tools
if ($LASTEXITCODE -ne 0) {
    throw "无法检查制作代码状态"
}

$cachePath = Join-Path $repoRoot ($cacheRelative -replace '/', '\\')
$cache = $null
if (Test-Path -LiteralPath $cachePath) {
    try {
        $cache = Get-Content -LiteralPath $cachePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        $cache = $null
    }
}
$canReuseTests = (
    -not $RunFullTests -and
    -not $implementationChanges -and
    $null -ne $cache -and
    $cache.revision -eq $revision -and
    $cache.input_sha256 -eq $inputHash -and
    $cache.image_id -eq $imageId
)

if (-not $canReuseTests) {
    & $toolScript @testArguments
    if ($LASTEXITCODE -ne 0) {
        throw "项目自动测试未通过，停止快速个人化制作"
    }
    $imageId = docker image inspect $image --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or -not $imageId) {
        throw "完整测试后无法读取固件制作镜像"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $cachePath) | Out-Null
    [PSCustomObject]@{
        revision = $revision
        input_sha256 = $inputHash
        image_id = $imageId
        verified_at = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $cachePath -Encoding UTF8
}

foreach ($relative in @($outputDirectory, $output, $manifest, $report)) {
    if (Test-Path -LiteralPath $relative) {
        throw "构建目标已存在，不能覆盖：$relative"
    }
}

$run = @(
    "run", "--rm", "--platform", "linux/amd64",
    "--mount", "type=bind,source=$repoRoot,target=/workspace",
    "--workdir", "/workspace", $image,
    "python", "app/ap01_firmware.py", "agents-personalized-build",
    "--input", $input,
    "--env-file", $config,
    "--output", $output,
    "--manifest", $manifest,
    "--build-dir", $workDirectory
)
& docker @run
if ($LASTEXITCODE -ne 0) {
    throw "个人固件制作失败"
}

& docker run --rm --platform linux/amd64 --mount "type=bind,source=$repoRoot,target=/workspace" --workdir /workspace $image python app/ap01_firmware.py agents-interaction-simulate --manifest $manifest --report $report --depth 8
if ($LASTEXITCODE -ne 0) {
    throw "最终固件交互模拟失败"
}

$document = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$payload = [IO.File]::ReadAllBytes((Join-Path $repoRoot ($output -replace '/', '\\')))
$actualSha256 = -join ([Security.Cryptography.SHA256]::Create().ComputeHash($payload) | ForEach-Object { $_.ToString("x2") })
$complete = (
    $payload.Length -eq $document.output.size -and
    $actualSha256 -eq $document.output.sha256 -and
    $document.status -eq "approved-for-one-test-installation" -and
    $document.device_specific -eq $true -and
    $document.transport.enabled -eq $true -and
    $document.transport.endpoint_configuration_required -ne $true -and
    @($document.transport.endpoint_priority).Count -ge 1 -and
    $document.validation.installation_allowed -eq $true -and
    $document.completeness.complete -eq $true -and
    @($document.completeness.missing_items).Count -eq 0
)
if (-not $complete) {
    throw "个人固件构建清单不满足安装条件"
}

(Get-Item -LiteralPath (Join-Path $repoRoot ($output -replace '/', '\\'))).IsReadOnly = $true
[PSCustomObject]@{
    result = "优化固件快速个人化完成"
    output = (Join-Path $repoRoot ($output -replace '/', '\\'))
    manifest = (Join-Path $repoRoot ($manifest -replace '/', '\\'))
    report = (Join-Path $repoRoot ($report -replace '/', '\\'))
    output_sha256 = $actualSha256
    full_tests_reused = $canReuseTests
    interaction_simulation_passed = $true
} | ConvertTo-Json
