# Liga, desliga e confere o servidor de produção do GALINT (waitress na porta 5000, com o polling do Telegram).
# É a lógica do botão GALINT sem a janela. Dois usos:
#   - o GalintToggle.ps1 carrega estas funções (dot-source) e desenha o toggle;
#   - o Painel de Sistemas roda este script sem janela:
#       powershell -NoProfile -ExecutionPolicy Bypass -File GalintControle.ps1 -Acao status|ligar|desligar -Saida <arquivo>
#     O arquivo recebe "OK: ..." ou "FALHOU: ..." (só em ligar/desligar) e as linhas ligado=, nivel= e texto=.
#     Código de saída: 0 deu certo, 2 falhou.
# O PostgreSQL não é iniciado nem parado.
param(
    [ValidateSet('status', 'ligar', 'desligar')]
    [string]$Acao,
    [string]$Saida
)

$ErrorActionPreference = 'Stop'

$script:projectRoot = Split-Path -Parent $PSScriptRoot
$projectParent = Split-Path -Parent $script:projectRoot
$projectGrandParent = Split-Path -Parent $projectParent
$script:pythonCandidates = @(
    (Join-Path $projectGrandParent '.venv\Scripts\python.exe'),
    (Join-Path $projectParent '.venv\Scripts\python.exe'),
    (Join-Path $script:projectRoot '.venv\Scripts\python.exe')
)

function Get-GalintProcesses {
    # O servidor do GALINT é o waitress com galint_flask:create_app na porta 5000, ligado por este botão ou pela tarefa
    # "GALINT - inicio automatico" (start_production.ps1), de qualquer cópia do projeto. Até 19/11/2026 só valia o
    # Python do .venv desta cópia: o GALINT ligado pela cópia antiga do OneDrive aparecia como "porta 5000 ocupada por
    # outro processo" no botão do D:, que também se recusava a desligá-lo.
    $allPythonProcesses = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine })
    $waitressProcesses = @($allPythonProcesses | Where-Object {
        $_.CommandLine.IndexOf('-m waitress', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine.IndexOf('galint_flask:create_app', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine -match '--port[= ]5000(?!\d)'
    })
    if ($waitressProcesses.Count -gt 0) {
        return $waitressProcesses
    }

    $listener = Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return @()
    }

    $portProcess = $allPythonProcesses | Where-Object { $_.ProcessId -eq $listener.OwningProcess } |
        Select-Object -First 1
    if (-not $portProcess -or $portProcess.CommandLine -notmatch '(^|\s|[\\/])app\.py(["\s]|$)') {
        return @()
    }

    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/health' -TimeoutSec 2
        if ($health.status -eq 'ok') {
            return @($portProcess)
        }
    }
    catch [System.Net.WebException] {
        return @()
    }

    return @()
}

function Test-GalintPort {
    $client = New-Object Net.Sockets.TcpClient
    $pending = $null
    try {
        $pending = $client.BeginConnect('127.0.0.1', 5000, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($pending)
        return $true
    }
    catch [Net.Sockets.SocketException] {
        return $false
    }
    finally {
        if ($pending) { $pending.AsyncWaitHandle.Close() }
        $client.Close()
    }
}

function Get-GalintEstado {
    # As frases que a janela e o painel mostram. Nivel: 0 parado, 1 no ar, 3 erro.
    if (@(Get-GalintProcesses).Count -gt 0) {
        return [PSCustomObject]@{ Ligado = $true; Nivel = 1; Texto = 'No ar: aplicação web e polling do Telegram' }
    }
    if (Test-GalintPort) {
        return [PSCustomObject]@{ Ligado = $false; Nivel = 3; Texto = 'Porta 5000 ocupada por outro processo' }
    }
    return [PSCustomObject]@{ Ligado = $false; Nivel = 0; Texto = 'GALINT parado' }
}

function Start-Galint {
    # Progresso: chamado a cada segundo da espera, com um texto novo ou $null (a janela usa para não travar).
    param([scriptblock]$Progresso = { param($texto) })

    if (@(Get-GalintProcesses).Count -gt 0) {
        return 'O GALINT já está no ar.'
    }
    if (Test-GalintPort) {
        throw 'A porta 5000 está ocupada por outro processo. Ele não foi alterado.'
    }

    $python = $script:pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $python) {
        throw 'Python do ambiente virtual não encontrado. Verifique a pasta .venv.'
    }

    $savedEnvironment = @{}
    $envFile = Join-Path $script:projectRoot '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
            if ($line -match '^\s*([^#][^=]+)=(.+)$') {
                $name = $matches[1].Trim()
                if (-not $savedEnvironment.ContainsKey($name)) {
                    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
                }
                [Environment]::SetEnvironmentVariable($name, $matches[2].Trim(), 'Process')
            }
        }
    }

    foreach ($setting in @{
        FLASK_ENV = 'production'
        GALINT_TELEGRAM_KEEP_WEBHOOK = 'false'
        GALINT_TELEGRAM_POLLING = 'true'
    }.GetEnumerator()) {
        if (-not $savedEnvironment.ContainsKey($setting.Key)) {
            $savedEnvironment[$setting.Key] = [Environment]::GetEnvironmentVariable($setting.Key, 'Process')
        }
        [Environment]::SetEnvironmentVariable($setting.Key, $setting.Value, 'Process')
    }

    try {
        $server = Start-Process -FilePath $python `
            -ArgumentList @('-u', '-m', 'waitress', '--host=0.0.0.0', '--port=5000', '--call', 'galint_flask:create_app') `
            -WorkingDirectory $script:projectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput 'NUL' -RedirectStandardError '\\.\NUL'
    }
    finally {
        foreach ($name in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
        }
    }

    $null = & $Progresso 'Aguardando o servidor iniciar...'
    for ($second = 0; $second -lt 90; $second++) {
        if ((Test-GalintPort) -and @(Get-GalintProcesses).Count -gt 0) {
            return 'GALINT no ar em http://localhost:5000.'
        }
        $server.Refresh()
        if ($server.HasExited) {
            throw "O servidor encerrou durante a inicialização (código $($server.ExitCode)). Verifique o ambiente e o banco de dados."
        }
        if ($second -gt 0 -and $second % 10 -eq 0) {
            $null = & $Progresso 'Aguardando o GALINT iniciar...'
        }
        else {
            $null = & $Progresso $null
        }
        Start-Sleep -Seconds 1
    }
    throw 'O GALINT não respondeu na porta 5000 em 90 segundos.'
}

function Stop-Galint {
    $processes = @(Get-GalintProcesses)
    if ($processes.Count -eq 0) {
        if (Test-GalintPort) {
            throw 'A porta 5000 está ocupada por um processo não identificado como GALINT. Ele não foi encerrado.'
        }
        return 'O GALINT já está parado.'
    }

    foreach ($process in $processes) {
        # O python do .venv abre o Python instalado como filho e o leva junto ao fechar: o filho pode já ter saído.
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        }
        catch {
            if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) { throw }
        }
    }
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        if (@(Get-GalintProcesses).Count -eq 0) {
            return 'GALINT parado. O PostgreSQL continua em execução.'
        }
        Start-Sleep -Seconds 1
    }
    throw 'O processo do GALINT não encerrou no tempo esperado.'
}

# Sem -Acao (dot-source pelo GalintToggle.ps1): só define as funções acima.
if ($Acao) {
    $linhas = New-Object System.Collections.Generic.List[string]
    $codigo = 0
    try {
        if ($Acao -eq 'ligar') { $linhas.Add('OK: ' + (Start-Galint)) }
        elseif ($Acao -eq 'desligar') { $linhas.Add('OK: ' + (Stop-Galint)) }
    }
    catch {
        $linhas.Add('FALHOU: ' + $_.Exception.Message)
        $codigo = 2
    }
    try {
        $estado = Get-GalintEstado
        $linhas.Add("ligado=$($estado.Ligado)")
        $linhas.Add("nivel=$($estado.Nivel)")
        $linhas.Add("texto=$($estado.Texto)")
    }
    catch {
        $linhas.Add('ligado=False')
        $linhas.Add('nivel=3')
        $linhas.Add("texto=Falha ao verificar: $($_.Exception.Message)")
        if ($Acao -eq 'status') { $codigo = 2 }
    }
    $conteudo = ($linhas -join "`r`n") + "`r`n"
    if ($Saida) {
        [IO.File]::WriteAllText($Saida, $conteudo, (New-Object Text.UTF8Encoding $false))
    }
    else {
        $conteudo
    }
    exit $codigo
}
