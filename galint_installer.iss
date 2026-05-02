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
