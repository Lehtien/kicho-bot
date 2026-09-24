[CmdletBinding()]
param(
    [string]$InstallRoot,
    [string]$ConfigPath,
    [string]$EnvFile,
    [string]$Workspace,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$exitCode = 1

try {
    if (-not $InstallRoot) {
        $InstallRoot = Join-Path $env:LOCALAPPDATA "kicho-bot"
    }
    $InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
    $uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $uvPath = $uvCommand.Source
    } else {
        $uvDirectory = Join-Path $InstallRoot "runtime\uv-0.12.5"
        $uvPath = Join-Path $uvDirectory "uv.exe"
        if (-not (Test-Path -LiteralPath $uvPath)) {
            Write-Host "Preparing uv (first run only)..."
            $architecture = $env:PROCESSOR_ARCHITEW6432
            if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
            switch ($architecture) {
                "AMD64" { $target = "x86_64-pc-windows-msvc" }
                "ARM64" { $target = "aarch64-pc-windows-msvc" }
                default { throw "Use 64-bit Windows (x64 or ARM64)." }
            }
            $asset = "uv-$target.zip"
            $release = "https://github.com/astral-sh/uv/releases/download/0.12.5"
            $temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("kicho-uv-" + [guid]::NewGuid().ToString("N"))
            New-Item -ItemType Directory -Path $temporary | Out-Null
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                $archive = Join-Path $temporary $asset
                $checksum = Join-Path $temporary "$asset.sha256"
                Invoke-WebRequest -UseBasicParsing -Uri "$release/$asset" -OutFile $archive
                Invoke-WebRequest -UseBasicParsing -Uri "$release/$asset.sha256" -OutFile $checksum
                $expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
                if ($expected -notmatch '^[0-9a-fA-F]{64}$' -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) {
                    throw "The uv download did not pass its checksum check. Please retry."
                }
                $expanded = Join-Path $temporary "expanded"
                Expand-Archive -LiteralPath $archive -DestinationPath $expanded
                $downloaded = Get-ChildItem -LiteralPath $expanded -Filter uv.exe -Recurse | Select-Object -First 1
                if (-not $downloaded) { throw "uv.exe was not found in the download." }
                New-Item -ItemType Directory -Force -Path $uvDirectory | Out-Null
                Copy-Item -LiteralPath $downloaded.FullName -Destination $uvPath
            } finally {
                Remove-Item -LiteralPath $temporary -Recurse -Force
            }
        }
    }
    $installer = Join-Path $PSScriptRoot "setup-desktop.py"
    $arguments = @("run", "--python", "3.11", "--frozen", "--script", $installer, "--uv", $uvPath, "--install-root", $InstallRoot)
    if ($ConfigPath) { $arguments += @("--config", $ConfigPath) }
    if ($EnvFile) { $arguments += @("--env-file", $EnvFile) }
    if ($Workspace) { $arguments += @("--workspace", $Workspace) }
    if ($NonInteractive) { $arguments += "--non-interactive" }
    & $uvPath @arguments
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host "Setup could not finish. Check your network connection and folder permissions, then run setup.cmd again."
}
exit $exitCode
