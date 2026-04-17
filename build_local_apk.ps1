Param(
    [string]$ShortPath = '',
    [string]$OutputDir = '',
    [switch]$SkipNpmInstall,
    [switch]$InstallConnectedDevice
)

$ErrorActionPreference = 'Stop'

try {
    if ($PSScriptRoot) {
        Set-Location -Path $PSScriptRoot
    }
}
catch {
}

try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
}
catch {
}

function Write-Step {
    param([string]$Message)

    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-ExistingPath {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if (-not $candidate) {
            continue
        }
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

function Resolve-FirstGlobPath {
    param([string[]]$Patterns)

    foreach ($pattern in $Patterns) {
        if (-not $pattern) {
            continue
        }
        $match = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    return $null
}

$projectRoot = (Get-Location).Path

if (-not $ShortPath) {
    $ShortPath = Join-Path $env:SystemDrive 'gm-src'
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $projectRoot 'build-output'
}

$nodeVer = '20.19.6'
$nodeHome = Join-Path $env:USERPROFILE "tools\node-v$nodeVer-win-x64"
if (Test-Path $nodeHome) {
    $env:Path = "$nodeHome;$env:Path"
}

try {
    $nodeVersion = (& node -v | Out-String).Trim()
}
catch {
    throw 'Node.js não encontrado. Instale o Node 20 e tente novamente.'
}

$javaExecutable = Resolve-ExistingPath @(
    $(if ($env:JAVA_HOME) { Join-Path $env:JAVA_HOME 'bin\java.exe' })
     (Join-Path $env:USERPROFILE 'tools\jdk-17\bin\java.exe')
)
if (-not $javaExecutable) {
    $javaExecutable = Resolve-FirstGlobPath @(
        'C:\Program Files\Eclipse Adoptium\jdk-17*\bin\java.exe',
        'C:\Program Files\Microsoft\jdk-17*\bin\java.exe',
        'C:\Program Files\Java\jdk-17*\bin\java.exe',
        'C:\Program Files\Android\Android Studio\jbr\bin\java.exe'
    )
}
if (-not $javaExecutable) {
    try {
        $javaExecutable = (Get-Command java -ErrorAction Stop).Source
    }
    catch {
    }
}
if (-not $javaExecutable) {
    throw 'Java não encontrado. Instale o JDK 17 e tente novamente.'
}

$env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $javaExecutable)
$env:Path = "$(Join-Path $env:JAVA_HOME 'bin');$env:Path"
$javaVersion = (Get-Item $javaExecutable).VersionInfo.ProductVersion
if (-not $javaVersion) {
    $javaVersion = Split-Path -Leaf $env:JAVA_HOME
}

$sdkRoot = Resolve-ExistingPath @(
    $env:ANDROID_SDK_ROOT,
    $env:ANDROID_HOME,
    (Join-Path $env:LOCALAPPDATA 'Android\Sdk')
)
if (-not $sdkRoot) {
    throw 'Android SDK não encontrado. Defina ANDROID_SDK_ROOT/ANDROID_HOME ou instale o SDK em %LOCALAPPDATA%\Android\Sdk.'
}

$requiredPaths = @(
    (Join-Path $sdkRoot 'platform-tools\adb.exe'),
    (Join-Path $sdkRoot 'platforms\android-36'),
    (Join-Path $sdkRoot 'build-tools\36.0.0'),
    (Join-Path $sdkRoot 'cmake\3.22.1\bin\cmake.exe'),
    (Join-Path $sdkRoot 'ndk\27.1.12297006')
)

$missingPaths = @($requiredPaths | Where-Object { -not (Test-Path $_) })
if ($missingPaths.Count -gt 0) {
    $missingList = ($missingPaths | ForEach-Object { " - $_" }) -join [Environment]::NewLine
    throw "Android SDK incompleto. Instale os componentes abaixo antes de rodar o build local:`n$missingList"
}

$env:ANDROID_SDK_ROOT = $sdkRoot
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_NDK_HOME = Join-Path $sdkRoot 'ndk\27.1.12297006'

Write-Step "Node em uso: $nodeVersion"
Write-Step "Java em uso: $javaVersion"
Write-Step "Android SDK: $sdkRoot"
Write-Step "Preparando cópia curta em $ShortPath"

if (Test-Path $ShortPath) {
    Remove-Item -Recurse -Force $ShortPath
}
New-Item -ItemType Directory -Path $ShortPath -Force | Out-Null

$excludeDirs = @(
    (Join-Path $projectRoot 'node_modules'),
    (Join-Path $projectRoot '.git'),
    (Join-Path $projectRoot '.expo'),
    (Join-Path $projectRoot 'build-output'),
    (Join-Path $projectRoot 'android\.cxx'),
    (Join-Path $projectRoot 'android\.gradle'),
    (Join-Path $projectRoot 'android\build'),
    (Join-Path $projectRoot 'android\app\build'),
    (Join-Path $projectRoot 'ios\build')
)

$robocopyArgs = @(
    $projectRoot,
    $ShortPath,
    '/MIR',
    '/R:2',
    '/W:1',
    '/NFL',
    '/NDL',
    '/NJH',
    '/NJS',
    '/NP',
    '/XD'
) + $excludeDirs

& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "Falha ao copiar o projeto para o caminho curto. Robocopy exit code: $LASTEXITCODE"
}

Set-Location $ShortPath

if (-not $SkipNpmInstall) {
    Write-Step 'Rodando npm install na cópia curta'
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
        throw 'npm install falhou na cópia curta.'
    }
}

$androidDir = Join-Path $ShortPath 'android'
$gradlew = Join-Path $androidDir 'gradlew.bat'
if (-not (Test-Path $gradlew)) {
    throw "Gradle wrapper não encontrado em $gradlew"
}

Write-Step 'Executando Gradle release com new architecture desligada'
Push-Location $androidDir
try {
    & $gradlew clean assembleRelease -PnewArchEnabled=false --no-daemon
    if ($LASTEXITCODE -ne 0) {
        throw 'Gradle retornou erro ao montar o release.'
    }
}
finally {
    Pop-Location
}

$builtApk = Join-Path $ShortPath 'android\app\build\outputs\apk\release\app-release.apk'
if (-not (Test-Path $builtApk)) {
    throw "APK final não encontrado em $builtApk"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$finalApk = Join-Path $OutputDir "galint-mobile-local-$timestamp.apk"
Copy-Item $builtApk $finalApk -Force

Write-Step "APK copiado para $finalApk"

if ($InstallConnectedDevice) {
    $adbPath = Join-Path $sdkRoot 'platform-tools\adb.exe'
    $connectedDevices = @(
        & $adbPath devices |
            Select-Object -Skip 1 |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -match '\tdevice$' }
    )

    if ($connectedDevices.Count -eq 0) {
        throw 'Nenhum dispositivo ADB conectado para instalar o APK.'
    }

    Write-Step 'Instalando APK no dispositivo conectado'
    & $adbPath install -r $finalApk
    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao instalar o APK via ADB.'
    }
}

Write-Host ''
Write-Host "Build local concluída com sucesso." -ForegroundColor Green
Write-Host "APK final: $finalApk" -ForegroundColor Green