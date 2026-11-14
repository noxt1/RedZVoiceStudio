# Setup environment for voice cloning (XTTS-v2) on Windows.
#
#   powershell -ExecutionPolicy Bypass -File tools\setup_env.ps1
#
# NOTE: this file is intentionally ASCII-only. Windows PowerShell 5.1 reads
# .ps1 files as ANSI unless they have a UTF-8 BOM, and Cyrillic text in a
# BOM-less UTF-8 file breaks the parser ("TerminatorExpectedAtEndOfString").

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv_voice'

$py312 = 'C:\Users\cyril\AppData\Local\Programs\Python\Python312\python.exe'
if (-not (Test-Path $py312)) {
    Write-Host "Python 3.12 not found at $py312" -ForegroundColor Red
    Write-Host "Install Python 3.12 and update `$py312 in this script." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "Creating venv -> $venv" -ForegroundColor Cyan
    & $py312 -m venv $venv
}

$vp = "$venv\Scripts\python.exe"

Write-Host "Updating pip..." -ForegroundColor Cyan
& $vp -m pip install --quiet --disable-pip-version-check --upgrade pip

Write-Host "Installing torch (CUDA)..." -ForegroundColor Cyan
& $vp -m pip install --disable-pip-version-check "torch>=2.5" "torchaudio>=2.5" --index-url https://download.pytorch.org/whl/cu128

Write-Host "Installing coqui-tts..." -ForegroundColor Cyan
& $vp -m pip install --disable-pip-version-check "coqui-tts[codec]" six soundfile numpy lameenc scipy

Write-Host "Installing piper-tts (offline Mexican voice)..." -ForegroundColor Cyan
& $vp -m pip install --disable-pip-version-check piper-tts sounddevice

Write-Host "Installing faster-whisper (quality checks)..." -ForegroundColor Cyan
& $vp -m pip install --disable-pip-version-check faster-whisper

Write-Host "Installing speechbrain (voice similarity)..." -ForegroundColor Cyan
& $vp -m pip install --disable-pip-version-check speechbrain

Write-Host "Verifying..." -ForegroundColor Cyan
& $vp -c "import TTS, torch, torchaudio, soundfile; print('TTS', TTS.__version__, '| torch', torch.__version__, '| cuda', torch.cuda.is_available())"

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host "  python tools\voice_scanner.py"
Write-Host "  (record the prompts, then press the green button)"
