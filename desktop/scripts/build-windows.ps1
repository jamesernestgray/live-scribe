#
# build-windows.ps1 — Build Live Scribe desktop app for Windows.
#
# Usage:
#   .\desktop\scripts\build-windows.ps1 [-Debug]
#
# Output:
#   desktop\tauri\target\release\bundle\msi\Live Scribe_*.msi
#   desktop\tauri\target\release\bundle\nsis\Live Scribe_*-setup.exe
#

param(
    [switch]$Debug
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$TauriDir = Join-Path $ProjectRoot "desktop\tauri"

$DebugFlag = ""
$BuildType = "release"
if ($Debug) {
    $DebugFlag = "--debug"
    $BuildType = "debug"
}

Write-Host "=== Live Scribe Desktop — Windows Build ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Project root: $ProjectRoot"
Write-Host "  Tauri dir:    $TauriDir"
Write-Host "  Build type:   $BuildType"
Write-Host ""

# ── Prerequisites ────────────────────────────────────────────────────

Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check Rust
try {
    $rustVersion = & rustc --version 2>&1
    Write-Host "  [OK] Rust: $rustVersion"
} catch {
    Write-Host "  [ERROR] Rust not found. Install from https://rustup.rs" -ForegroundColor Red
    exit 1
}

# Check Cargo
try {
    & cargo --version | Out-Null
    Write-Host "  [OK] Cargo found"
} catch {
    Write-Host "  [ERROR] Cargo not found." -ForegroundColor Red
    exit 1
}

# Check Tauri CLI
try {
    $tauriVersion = & cargo tauri --version 2>&1
    Write-Host "  [OK] Tauri CLI: $tauriVersion"
} catch {
    Write-Host "  [ERROR] cargo-tauri not found. Install with: cargo install tauri-cli" -ForegroundColor Red
    exit 1
}

# Check Python
try {
    $pythonVersion = & python3 --version 2>&1
    Write-Host "  [OK] Python: $pythonVersion"
} catch {
    try {
        $pythonVersion = & python --version 2>&1
        Write-Host "  [OK] Python: $pythonVersion (note: using 'python' instead of 'python3')"
    } catch {
        Write-Host "  [ERROR] Python not found." -ForegroundColor Red
        exit 1
    }
}

# Check WebView2 (required on Windows)
$webview2Key = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE69B7F}"
if (Test-Path $webview2Key) {
    Write-Host "  [OK] WebView2 Runtime installed"
} else {
    Write-Host "  [WARNING] WebView2 Runtime may not be installed." -ForegroundColor Yellow
    Write-Host "           Download from: https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    Write-Host "           (NSIS installer can bundle it automatically)"
}

Write-Host ""

# ── Build ────────────────────────────────────────────────────────────

Write-Host "Building Live Scribe desktop app..." -ForegroundColor Yellow
Write-Host ""

Set-Location $TauriDir

if ($Debug) {
    & cargo tauri build --debug
} else {
    & cargo tauri build
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "=== Build Failed ===" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host ""

$BundleDir = Join-Path $TauriDir "target\release\bundle"
if (Test-Path $BundleDir) {
    Write-Host "Output files:"
    $msiDir = Join-Path $BundleDir "msi"
    if (Test-Path $msiDir) {
        Write-Host "  MSI: $msiDir"
        Get-ChildItem $msiDir | ForEach-Object { Write-Host "    $($_.Name) ($([math]::Round($_.Length/1MB, 1)) MB)" }
    }
    $nsisDir = Join-Path $BundleDir "nsis"
    if (Test-Path $nsisDir) {
        Write-Host "  NSIS: $nsisDir"
        Get-ChildItem $nsisDir | ForEach-Object { Write-Host "    $($_.Name) ($([math]::Round($_.Length/1MB, 1)) MB)" }
    }
} else {
    Write-Host "Bundle directory: $BundleDir"
}
