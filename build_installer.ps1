# Script para criar instalador do GALINT com Inno Setup
# Uso: .\build_installer.ps1

$ErrorActionPreference = "Stop"

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "   GALINT - Build Instalador" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path "dist\GALINT\GALINT.exe")) {
    Write-Host "ERRO: Executavel nao encontrado!" -ForegroundColor Red
    Write-Host "Execute primeiro: .\build_executable.ps1" -ForegroundColor Yellow
    exit 1
}

$innoSetupCandidates = @()
if ($env:GALINT_ISCC_PATH) {
    $innoSetupCandidates += $env:GALINT_ISCC_PATH
}

$innoSetupCommand = Get-Command iscc -ErrorAction SilentlyContinue
if ($innoSetupCommand) {
    $innoSetupCandidates += $innoSetupCommand.Source
}

$innoSetupCandidates += @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ }

$innoSetupExe = $innoSetupCandidates |
    Select-Object -Unique |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $innoSetupExe) {
    Write-Host "ERRO: Inno Setup nao encontrado!" -ForegroundColor Red
    Write-Host "" 
    Write-Host "Instale Inno Setup:" -ForegroundColor Yellow
    Write-Host "  https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
    Write-Host "" 
    Write-Host "Apos a instalacao, adicione ao PATH ou defina GALINT_ISCC_PATH:" -ForegroundColor Yellow
    Write-Host "  C:\Program Files (x86)\Inno Setup 6\ISCC.exe" -ForegroundColor Cyan
    exit 1
}

Write-Host "Usando Inno Setup em: $innoSetupExe" -ForegroundColor DarkGray

$version = Get-Content "version.txt" -ErrorAction SilentlyContinue
if (-not $version) {
    $version = "1.0.0"
}

Write-Host "Criando script de instalacao..." -ForegroundColor Green

$innoScript = @'
; GALINT Instalador
; Gerado automaticamente

#define MyAppName "GALINT"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Sua Empresa"
#define MyAppURL "https://seu-site.com.br"
#define MyAppExeName "GALINT.exe"

[Setup]
AppId={{GALINT-MRO-WMS}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
ChangesAssociations=yes
OutputDir=dist\installers
OutputBaseFilename=GALINT-Setup-v{#MyAppVersion}
SetupIconFile=galint_flask\static\img\galint-icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\GALINT\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.galintetq\OpenWithProgids"; ValueType: string; ValueName: "GALINT.LabelLayout"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\GALINT.LabelLayout"; ValueType: string; ValueName: ""; ValueData: "Layout do Editor de Etiquetas do GALINT"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\GALINT.LabelLayout\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\GALINT.LabelLayout\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" open-layout-file ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: string;
begin
  if CurStep = ssPostInstall then begin
    DataDir := ExpandConstant('{commonappdata}\GALINT');
    if not DirExists(DataDir) then begin
      CreateDir(DataDir);
      CreateDir(DataDir + '\database');
      CreateDir(DataDir + '\uploads');
      CreateDir(DataDir + '\backups');
      CreateDir(DataDir + '\logs');
    end;
  end;
end;
'@

$innoScript = $innoScript -replace '#define MyAppVersion "1.0.0"', "#define MyAppVersion `"$version`""

$innoScript | Out-File -FilePath "galint_installer.iss" -Encoding UTF8
New-Item -ItemType Directory -Force -Path "dist\installers" | Out-Null

Write-Host "Compilando instalador..." -ForegroundColor Green
& $innoSetupExe "galint_installer.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: O compilador do Inno Setup retornou codigo $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

$installerPath = "dist\installers\GALINT-Setup-v$version.exe"
if (Test-Path $installerPath) {
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host "   INSTALADOR CRIADO COM SUCESSO" -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Instalador:" -ForegroundColor Cyan
    Write-Host "  $installerPath" -ForegroundColor White
    Write-Host ""

    $size = (Get-Item $installerPath).Length / 1MB
    Write-Host "Tamanho: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "ERRO: Falha ao criar instalador!" -ForegroundColor Red
    exit 1
}
