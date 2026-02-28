param(
    [int]$Port = 5000,
    [switch]$KillConflicts = $true
)

$ErrorActionPreference = 'Stop'

function Get-ListeningPids([int]$port) {
    $pattern = ":$port\s+.*LISTENING\s+(\d+)$"
    $lines = netstat -ano | Select-String -Pattern ":$port" -SimpleMatch -ErrorAction SilentlyContinue
    $pids = New-Object System.Collections.Generic.HashSet[int]

    foreach ($line in $lines) {
        $text = $line.ToString().Trim()
        $m = [regex]::Match($text, $pattern)
        if ($m.Success) {
            [void]$pids.Add([int]$m.Groups[1].Value)
        }
    }

    return $pids
}

function Is-PythonAppPy([int]$pid) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction Stop
        $cmd = $proc.CommandLine
        if (-not $cmd) { $cmd = "" }
        $cmd = $cmd.ToLowerInvariant()
        if ($cmd -match 'python' -and $cmd -match 'app\.py') {
            return $true
        }
    } catch {
        return $false
    }

    return $false
}

function Get-ParentPid([int]$pid) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction Stop
        if ($null -ne $proc.ParentProcessId) {
            return [int]$proc.ParentProcessId
        }
    } catch {
        return $null
    }
    return $null
}

$pids = Get-ListeningPids -port $Port
if ($pids.Count -gt 0) {
    foreach ($pid in $pids) {
        if (Is-PythonAppPy -pid $pid) {
            if ($KillConflicts) {
                Write-Host "[GALINT] Porta $Port em uso por python app.py (PID $pid). Finalizando..." -ForegroundColor Yellow
                $parentPid = Get-ParentPid -pid $pid
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue

                # Se este PID for um "filho" (ex.: launcher/venv), finalize o pai também.
                if ($null -ne $parentPid -and $parentPid -gt 0 -and (Is-PythonAppPy -pid $parentPid)) {
                    Write-Host "[GALINT] Finalizando também o processo pai (PID $parentPid)" -ForegroundColor Yellow
                    Stop-Process -Id $parentPid -Force -ErrorAction SilentlyContinue
                }
            } else {
                throw "Porta $Port já está em uso (PID $pid) por python app.py."
            }
        } else {
            throw "Porta $Port já está em uso por outro processo (PID $pid). Não vou finalizar automaticamente."
        }
    }

    Start-Sleep -Milliseconds 250
}

# Sobe o servidor pelo venv
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python do venv não encontrado em: $python"
}

Write-Host "[GALINT] Iniciando servidor via venv: $python app.py" -ForegroundColor Green
& $python "app.py"
