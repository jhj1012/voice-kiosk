# The kiosk for teammates who never use a terminal: started by "Start Kiosk.bat".
# Installs uv (which brings Python) the first time, builds the display if it is missing and
# Node.js is there, then runs the kiosk and opens the display. Closing this window stops it.
param([switch]$FullScreen)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = '음성 키오스크 (이 창을 닫으면 꺼져요)'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($path in "$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe",
                      "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe") {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Stop-WithMessage([string]$Message) {
    Write-Host ''
    Write-Host $Message -ForegroundColor Yellow
    exit 1
}

$uv = Find-Uv
if (-not $uv) {
    Write-Host '처음 실행이에요. 키오스크에 필요한 도구(uv)를 설치할게요. 1분쯤 걸려요.'
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Stop-WithMessage "uv를 설치하지 못했어요: $_`n인터넷 연결을 확인하고 다시 실행해 주세요."
    }
    $uv = Find-Uv
    if (-not $uv) { Stop-WithMessage 'uv를 설치하지 못했어요. 인터넷 연결을 확인하고 다시 실행해 주세요.' }
}

if (-not (Test-Path 'frontend\dist\index.html')) {
    if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
        Write-Host '화면 파일을 만들고 있어요...'
        npm.cmd --prefix frontend ci
        if ($LASTEXITCODE -eq 0) { npm.cmd --prefix frontend run build }
        if ($LASTEXITCODE -ne 0) { Stop-WithMessage '화면 파일을 만들지 못했어요. 위의 오류를 확인해 주세요.' }
    } else {
        Stop-WithMessage ('화면 파일(frontend\dist)이 없어요. README의 "1. 다운로드" 순서대로 ' +
            'Releases에서 voice-kiosk.zip을 받아 주세요.')
    }
}

Write-Host '키오스크를 시작해요. 처음에는 필요한 파일을 받느라 1~2분 걸릴 수 있어요.'
Write-Host '끄려면 이 창을 닫으세요.'
Write-Host ''
$open = if ($FullScreen) { '--kiosk' } else { '--open' }
& $uv run --no-dev python -m kiosk $open
if ($LASTEXITCODE -ne 0) { Stop-WithMessage '키오스크가 오류로 멈췄어요. 위의 메시지를 확인해 주세요.' }
