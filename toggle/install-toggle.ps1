[CmdletBinding()]
param(
    [switch]$NoShortcut
)

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'GalintToggle.vbs'
if (-not (Test-Path $scriptPath)) {
    throw "Inicializador oculto do botão não encontrado: $scriptPath"
}

if (-not $NoShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'GALINT.lnk'
    $iconPath = Join-Path $PSScriptRoot 'toggle.ico'
    $scriptHost = Join-Path $env:WINDIR 'System32\wscript.exe'
    if (-not (Test-Path $iconPath)) {
        throw "Ícone do botão não encontrado: $iconPath"
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $scriptHost
    $shortcut.Arguments = "//NoLogo `"$scriptPath`""
    $shortcut.WorkingDirectory = Split-Path -Parent $PSScriptRoot
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Description = 'Inicia ou para a aplicação GALINT e o polling do Telegram'
    $shortcut.Save()
    Write-Output "Atalho criado: $shortcutPath"
}

Write-Output "Inicializador oculto do botão: $scriptPath"
