param(
    [string]$RustdeskSrc = $env:RUSTDESK_SRC,
    [string]$ZipPassword = $env:ZIP_PASSWORD,
    [string]$SecretKey = $env:SECRET_KEY
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not $RustdeskSrc) {
    Write-Host "Set -RustdeskSrc or RUSTDESK_SRC to your rustdesk source path."
    exit 1
}
if (-not (Test-Path $RustdeskSrc)) {
    Write-Host "RUSTDESK_SRC not found: $RustdeskSrc"
    exit 1
}

if (-not $ZipPassword) {
    $ZipPassword = ([System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N"))
}
if (-not $SecretKey) {
    $SecretKey = ([System.Guid]::NewGuid().ToString("N") + [System.Guid]::NewGuid().ToString("N"))
}

$toolsDir = Join-Path $repoRoot "tools"
New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null

$cloudflared = Join-Path $toolsDir "cloudflared.exe"
if (-not (Test-Path $cloudflared)) {
    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Write-Host "Downloading cloudflared..."
    Invoke-WebRequest -Uri $downloadUrl -OutFile $cloudflared
}

$logFile = Join-Path $repoRoot "cloudflared.log"
if (Test-Path $logFile) {
    Remove-Item $logFile -Force
}

Start-Process $cloudflared -ArgumentList "tunnel --url http://127.0.0.1:8000 --no-autoupdate" -RedirectStandardOutput $logFile -RedirectStandardError $logFile | Out-Null

$publicUrl = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "https://[a-z0-9-]+\\.trycloudflare\\.com") {
            $publicUrl = $matches[0]
            break
        }
    }
}

if (-not $publicUrl) {
    Write-Host "Failed to get tunnel URL. Check $logFile."
    exit 1
}

$env:GENURL = $publicUrl
$env:ZIP_PASSWORD = $ZipPassword
$env:SECRET_KEY = $SecretKey
$env:LOCAL_BUILD = "true"
$env:LOCAL_BUILD_PLATFORM = "windows"
$env:RUSTDESK_SRC = $RustdeskSrc

$envFile = Join-Path $repoRoot ".env.local"
@"
SECRET_KEY=$SecretKey
ZIP_PASSWORD=$ZipPassword
GENURL=$publicUrl
LOCAL_BUILD=true
LOCAL_BUILD_PLATFORM=windows
RUSTDESK_SRC=$RustdeskSrc
"@ | Set-Content -Path $envFile -Encoding ascii

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "python not found in PATH."
    exit 1
}

$venv = Join-Path $repoRoot ".venv"
if (-not (Test-Path $venv)) {
    python -m venv $venv
}

$pythonExe = Join-Path $venv "Scripts\\python.exe"
& $pythonExe -m pip install -r (Join-Path $repoRoot "requirements.txt")
& $pythonExe (Join-Path $repoRoot "manage.py") migrate

Write-Host "Public URL: $publicUrl"
Write-Host "Starting server..."
& $pythonExe (Join-Path $repoRoot "manage.py") runserver 0.0.0.0:8000
