# The kiosk for teammates who never use a terminal: started by "Start Kiosk.bat".
# Installs uv (which brings Python) the first time, builds the display if it is missing and
# Node.js is there, then runs the kiosk and opens the display. Closing this window stops it.
# -Phone ("Start Kiosk (phone).bat"): an Android phone is the screen, microphone and speaker;
# this window shows the address to open on the phone.
# -Usb ("Start Kiosk (USB).bat"): the same over a USB cable, no Wi-Fi on the phone: adb (Android's
# debugging tool, downloaded once into tools\) forwards the phone's 127.0.0.1:8766 to this laptop
# and opens Chrome there. The phone needs USB debugging on (README).
param([switch]$FullScreen, [switch]$Phone, [switch]$Usb)

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

$PhonePort = 8766
$AdbZip = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'

function Find-Adb {
    foreach ($path in 'tools\platform-tools\adb.exe',
                      "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe") {
        if (Test-Path $path) { return (Resolve-Path $path).Path }
    }
    $command = Get-Command adb -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

function Install-Adb {
    Write-Host '처음 실행이에요. USB 연결에 필요한 도구(adb, Google의 Android 도구)를 받을게요.'
    $zip = Join-Path $env:TEMP 'voice-kiosk-platform-tools.zip'
    try {
        Invoke-WebRequest $AdbZip -OutFile $zip -UseBasicParsing
        New-Item -ItemType Directory -Force tools | Out-Null
        Expand-Archive $zip -DestinationPath tools -Force
    } catch {
        Stop-WithMessage "adb를 받지 못했어요: $_`n인터넷 연결을 확인하고 다시 실행해 주세요."
    } finally {
        Remove-Item $zip -ErrorAction SilentlyContinue
    }
}

function Invoke-Adb([string]$Adb) {
    # adb prints notes like "* daemon not running; starting now" on stderr: in Windows PowerShell
    # that is an error, which stops this script ($ErrorActionPreference). Not here.
    $ErrorActionPreference = 'Continue'
    & $Adb @args 2>$null
}

function Get-PhoneState([string]$Adb) {
    # The first device's state: device (ready), unauthorized (allow on the phone), offline, or none.
    $line = Invoke-Adb $Adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\t' } |
        Select-Object -First 1
    if (-not $line) { return 'none' }
    return ($line -split '\t')[1].Trim()
}

function Wait-Phone([string]$Adb) {
    $said = ''
    while (($state = Get-PhoneState $Adb) -ne 'device') {
        if ($state -ne $said) {
            $said = $state
            if ($state -eq 'unauthorized') {
                Write-Host '화면 기기에 "USB 디버깅을 허용하시겠습니까?"가 떠 있어요. "이 컴퓨터에서 항상 허용"에 체크하고 허용을 눌러 주세요.' -ForegroundColor Yellow
            } else {
                Write-Host '화면 기기를 USB 케이블로 노트북에 연결해 주세요. (처음이면 README의 "USB로 연결하기"에서 USB 디버깅 켜기)' -ForegroundColor Yellow
            }
        }
        Start-Sleep -Seconds 1
    }
}

# While the kiosk runs: forwards the port again after the cable was plugged in again (adb forgets
# it), and opens Chrome on the phone once the kiosk answers. Chrome reuses its tab (the app id).
$UsbWatch = {
    param([string]$Adb, [int]$Port)
    $url = "https://127.0.0.1:$Port/"
    $opened = $false
    while ($true) {
        $ready = (& $Adb get-state 2>$null) -eq 'device'
        if ($ready -and -not ((& $Adb reverse --list 2>$null) -match "tcp:$Port")) {
            & $Adb reverse "tcp:$Port" "tcp:$Port" | Out-Null
        }
        if ($ready -and -not $opened) {
            $client = New-Object Net.Sockets.TcpClient
            try { $client.Connect('127.0.0.1', $Port); $listening = $true } catch { $listening = $false }
            $client.Close()
            if ($listening) {
                & $Adb shell am start -a android.intent.action.VIEW -d $url `
                    -e com.android.browser.application_id voice-kiosk com.android.chrome | Out-Null
                $opened = $true
            }
        }
        Start-Sleep -Seconds 2
    }
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
if ($Usb) {
    $adb = Find-Adb
    if (-not $adb) { Install-Adb; $adb = Find-Adb }
    if (-not $adb) { Stop-WithMessage 'adb를 찾지 못했어요. tools 폴더를 지우고 다시 실행해 주세요.' }
    Invoke-Adb $adb start-server | Out-Null
    Wait-Phone $adb
    Invoke-Adb $adb reverse "tcp:$PhonePort" "tcp:$PhonePort" | Out-Null
    Write-Host "USB 연결 완료. 화면 기기의 Chrome에 https://127.0.0.1:$PhonePort 이 저절로 열려요." -ForegroundColor Green
    Write-Host '처음이면 "연결이 비공개로 설정되어 있지 않습니다" → 고급 → 이동. (아래에 나오는 Wi-Fi 주소는 쓰지 않아요)'
    Write-Host ''
    $watch = Start-Job -ScriptBlock $UsbWatch -ArgumentList $adb, $PhonePort
    try {
        & $uv run --no-dev python -m kiosk --phone
    } finally {
        Stop-Job $watch -ErrorAction SilentlyContinue
        Remove-Job $watch -Force -ErrorAction SilentlyContinue
        Invoke-Adb $adb reverse --remove "tcp:$PhonePort" | Out-Null
    }
} elseif ($Phone) {
    Write-Host '휴대폰 모드: 노트북과 화면 기기를 같은 Wi-Fi(핫스팟)에 연결해 두세요. 화면 기기에서 열 주소가 아래에 나와요.'
    Write-Host ''
    & $uv run --no-dev python -m kiosk --phone
} else {
    $open = if ($FullScreen) { '--kiosk' } else { '--open' }
    & $uv run --no-dev python -m kiosk $open
}
if ($LASTEXITCODE -ne 0) { Stop-WithMessage '키오스크가 오류로 멈췄어요. 위의 메시지를 확인해 주세요.' }
