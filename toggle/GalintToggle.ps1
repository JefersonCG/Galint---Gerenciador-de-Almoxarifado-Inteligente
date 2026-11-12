$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:projectRoot = Split-Path -Parent $PSScriptRoot
$projectParent = Split-Path -Parent $script:projectRoot
$projectGrandParent = Split-Path -Parent $projectParent
$script:pythonCandidates = @(
    (Join-Path $projectGrandParent '.venv\Scripts\python.exe'),
    (Join-Path $projectParent '.venv\Scripts\python.exe'),
    (Join-Path $script:projectRoot '.venv\Scripts\python.exe')
)
$script:busy = $false
$script:running = $false
$script:hover = $false
$script:position = 0.0
$script:target = 0.0
$script:pulse = 0.0
$script:progressText = ''
$script:lastOperationError = ''
$script:errorUntil = [DateTime]::MinValue
$script:timerTicks = 0
$script:track = [Drawing.RectangleF]::new([single]132, [single]55, [single]216, [single]90)
$script:bgColor = [Drawing.Color]::FromArgb(11, 18, 32)
$script:trackOff = [Drawing.Color]::FromArgb(59, 66, 82)
$script:trackOn = [Drawing.Color]::FromArgb(255, 239, 0)

function Get-GalintProcesses {
    $pythonPaths = @($script:pythonCandidates | Where-Object { Test-Path $_ } | ForEach-Object { [IO.Path]::GetFullPath($_) })
    $allPythonProcesses = @(Get-CimInstance -ClassName Win32_Process | Where-Object {
        ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and
        $_.ExecutablePath -and $_.CommandLine
    })
    $waitressProcesses = @($allPythonProcesses | Where-Object {
        ($pythonPaths -contains [IO.Path]::GetFullPath($_.ExecutablePath)) -and
        $_.CommandLine.IndexOf('-m waitress', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.CommandLine.IndexOf('galint_flask:create_app', [StringComparison]::OrdinalIgnoreCase) -ge 0
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

function Update-GalintStatus {
    $previousText = $script:statusLabel.Text
    $previousColor = $script:statusLabel.ForeColor
    $previousTarget = $script:target
    try {
        $script:running = @(Get-GalintProcesses).Count -gt 0
        $script:target = if ($script:running) { 1.0 } else { 0.0 }
        if ($script:running) {
            $script:statusLabel.Text = 'No ar: aplicação web e polling do Telegram'
            $script:statusLabel.ForeColor = [Drawing.Color]::FromArgb(74, 222, 128)
        }
        elseif (Test-GalintPort) {
            $script:statusLabel.Text = 'Porta 5000 ocupada por outro processo'
            $script:statusLabel.ForeColor = [Drawing.Color]::FromArgb(248, 113, 113)
        }
        else {
            $script:statusLabel.Text = 'GALINT parado'
            $script:statusLabel.ForeColor = [Drawing.Color]::FromArgb(148, 163, 184)
        }
    }
    catch {
        $script:statusLabel.Text = "Falha ao verificar: $($_.Exception.Message)"
        $script:statusLabel.ForeColor = [Drawing.Color]::FromArgb(248, 113, 113)
    }

    if ($script:statusLabel.Text -ne $previousText -or
        $script:statusLabel.ForeColor -ne $previousColor -or
        $script:target -ne $previousTarget) {
        $script:form.Invalidate()
    }
}

function Start-Galint {
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

    $script:statusLabel.Text = 'Aguardando o servidor iniciar...'
    [Windows.Forms.Application]::DoEvents()
    for ($second = 0; $second -lt 90; $second++) {
        if ((Test-GalintPort) -and @(Get-GalintProcesses).Count -gt 0) {
            return 'GALINT no ar em http://localhost:5000.'
        }
        $server.Refresh()
        if ($server.HasExited) {
            throw "O servidor encerrou durante a inicialização (código $($server.ExitCode)). Verifique o ambiente e o banco de dados."
        }
        if ($second -gt 0 -and $second % 10 -eq 0) {
            $script:statusLabel.Text = 'Aguardando o GALINT iniciar...'
        }
        [Windows.Forms.Application]::DoEvents()
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
        Stop-Process -Id $process.ProcessId -Force
    }
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        if (@(Get-GalintProcesses).Count -eq 0) {
            return 'GALINT parado. O PostgreSQL continua em execução.'
        }
        Start-Sleep -Seconds 1
    }
    throw 'O processo do GALINT não encerrou no tempo esperado.'
}

$script:form = New-Object Windows.Forms.Form
$doubleBuffered = $script:form.GetType().GetProperty(
    'DoubleBuffered',
    [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::NonPublic)
if (-not $doubleBuffered) { throw 'Não foi possível habilitar o desenho sem cintilação da janela.' }
$doubleBuffered.SetValue($script:form, $true, $null)
$script:form.Text = 'GALINT'
$script:form.ClientSize = New-Object Drawing.Size(480, 210)
$script:form.FormBorderStyle = [Windows.Forms.FormBorderStyle]::FixedSingle
$script:form.MaximizeBox = $false
$script:form.MinimizeBox = $false
$script:form.StartPosition = [Windows.Forms.FormStartPosition]::CenterScreen
$script:form.AutoScaleMode = [Windows.Forms.AutoScaleMode]::None
$script:form.BackColor = $script:bgColor
$script:form.KeyPreview = $true
$script:form.Icon = New-Object Drawing.Icon((Join-Path $PSScriptRoot 'toggle.ico'))

$script:statusLabel = [PSCustomObject]@{
    Text = ''
    ForeColor = [Drawing.Color]::FromArgb(148, 163, 184)
}

$script:form.Add_Paint({
    param($sender, $eventArgs)
    $graphics = $eventArgs.Graphics
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear($script:bgColor)

    $titleFont = New-Object Drawing.Font('Segoe UI Semibold', 17, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $bodyFont = New-Object Drawing.Font('Segoe UI', 13.5, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $smallFont = New-Object Drawing.Font('Segoe UI', 10, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $footerFont = New-Object Drawing.Font('Segoe UI', 10, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $labelFont = New-Object Drawing.Font('Segoe UI Semibold', 16, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $busyFont = New-Object Drawing.Font('Segoe UI Semibold', 12, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $center = New-Object Drawing.StringFormat
    $center.Alignment = [Drawing.StringAlignment]::Center
    $center.LineAlignment = [Drawing.StringAlignment]::Center
    $titleBrush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(229, 231, 235))
    $footerBrush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(100, 116, 139))
    [Drawing.RectangleF]$titleRect = [Drawing.RectangleF]::new([single]0, [single]10, [single]480, [single]30)
    $graphics.DrawString('GALINT', $titleFont, $titleBrush, $titleRect, $center)

    $trackColor = [Drawing.Color]::FromArgb(
        [int]($script:trackOff.R + ($script:trackOn.R - $script:trackOff.R) * $script:position),
        [int]($script:trackOff.G + ($script:trackOn.G - $script:trackOff.G) * $script:position),
        [int]($script:trackOff.B + ($script:trackOn.B - $script:trackOff.B) * $script:position))
    if ($script:busy) {
        $blend = 0.55 + 0.25 * [Math]::Sin($script:pulse)
        $trackColor = [Drawing.Color]::FromArgb(
            [int]($trackColor.R + (255 - $trackColor.R) * $blend),
            [int]($trackColor.G + (239 - $trackColor.G) * $blend),
            [int]($trackColor.B + (0 - $trackColor.B) * $blend))
    }
    elseif ($script:hover) {
        $trackColor = [Drawing.Color]::FromArgb(
            [int]($trackColor.R + (255 - $trackColor.R) * 0.06),
            [int]($trackColor.G + (255 - $trackColor.G) * 0.06),
            [int]($trackColor.B + (255 - $trackColor.B) * 0.06))
    }

    $trackPath = New-Object Drawing.Drawing2D.GraphicsPath
    $radius = $script:track.Height / 2
    $diameter = $radius * 2
    $trackPath.AddArc($script:track.X, $script:track.Y, $diameter, $diameter, 180, 90)
    $trackPath.AddArc($script:track.Right - $diameter, $script:track.Y, $diameter, $diameter, 270, 90)
    $trackPath.AddArc($script:track.Right - $diameter, $script:track.Bottom - $diameter, $diameter, $diameter, 0, 90)
    $trackPath.AddArc($script:track.X, $script:track.Bottom - $diameter, $diameter, $diameter, 90, 90)
    $trackPath.CloseFigure()
    $trackBrush = New-Object Drawing.SolidBrush($trackColor)
    $graphics.FillPath($trackBrush, $trackPath)

    $thumbSize = $script:track.Height - 14
    [Drawing.RectangleF]$leftLabel = [Drawing.RectangleF]::new(
        [single]($script:track.X + 12), [single]$script:track.Y,
        [single]($script:track.Width - $thumbSize - 31), [single]$script:track.Height)
    [Drawing.RectangleF]$rightLabel = [Drawing.RectangleF]::new(
        [single]($script:track.X + $thumbSize + 19), [single]$script:track.Y,
        [single]($script:track.Width - $thumbSize - 31), [single]$script:track.Height)
    $onAlpha = [int](255 * $script:position)
    $offAlpha = [int](210 * (1 - $script:position))
    $onBrush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb($onAlpha, 15, 23, 42))
    $offBrush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb($offAlpha, 226, 232, 240))
    $onText = if ($script:busy -and $script:target -gt 0) { 'LIGANDO' } else { 'LIGADO' }
    $offText = if ($script:busy -and $script:target -le 0) { 'DESLIGANDO' } else { 'DESLIGADO' }
    $currentLabelFont = if ($script:busy) { $busyFont } else { $labelFont }
    $graphics.DrawString($onText, $currentLabelFont, $onBrush, $leftLabel, $center)
    $graphics.DrawString($offText, $currentLabelFont, $offBrush, $rightLabel, $center)

    $thumbX = $script:track.X + 7 + ($script:track.Width - 14 - $thumbSize) * $script:position
    [Drawing.RectangleF]$thumb = [Drawing.RectangleF]::new(
        [single]$thumbX, [single]($script:track.Y + 7), [single]$thumbSize, [single]$thumbSize)
    $shadowBrush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(70, 0, 0, 0))
    $thumbBrush = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(248, 250, 252))
    $graphics.FillEllipse($shadowBrush, ($thumb.X + 0.5), ($thumb.Y + 3), $thumb.Width, $thumb.Height)
    $graphics.FillEllipse($thumbBrush, $thumb)

    if ($script:busy) {
        $message = $script:progressText
        $messageColor = [Drawing.Color]::FromArgb(255, 239, 0)
    }
    else {
        $message = $script:statusLabel.Text
        $messageColor = $script:statusLabel.ForeColor
    }
    $statusBrush = New-Object Drawing.SolidBrush($messageColor)
    $statusFont = if ($message.Length -gt 58) { $smallFont } else { $bodyFont }
    [Drawing.RectangleF]$statusRect = [Drawing.RectangleF]::new([single]14, [single]152, [single]452, [single]36)
    $graphics.DrawString($message, $statusFont, $statusBrush, $statusRect, $center)
    [Drawing.RectangleF]$footerRect = [Drawing.RectangleF]::new([single]0, [single]192, [single]480, [single]14)
    $graphics.DrawString('Aplicação + Telegram  ·  PostgreSQL não é alterado', $footerFont, $footerBrush, $footerRect, $center)

    $titleFont.Dispose()
    $bodyFont.Dispose()
    $smallFont.Dispose()
    $footerFont.Dispose()
    $labelFont.Dispose()
    $busyFont.Dispose()
    $center.Dispose()
    $titleBrush.Dispose()
    $footerBrush.Dispose()
    $trackPath.Dispose()
    $trackBrush.Dispose()
    $onBrush.Dispose()
    $offBrush.Dispose()
    $shadowBrush.Dispose()
    $thumbBrush.Dispose()
    $statusBrush.Dispose()
})

$script:form.Add_MouseMove({
    param($sender, $eventArgs)
    [Drawing.PointF]$mousePosition = [Drawing.PointF]::new([single]$eventArgs.X, [single]$eventArgs.Y)
    $inside = $script:track.Contains($mousePosition)
    if ($script:hover -ne ($inside -and -not $script:busy)) {
        $script:hover = $inside -and -not $script:busy
        $script:form.Cursor = if ($script:hover) { [Windows.Forms.Cursors]::Hand } else { [Windows.Forms.Cursors]::Default }
        $script:form.Invalidate()
    }
})
$script:form.Add_MouseLeave({
    $script:hover = $false
    $script:form.Cursor = [Windows.Forms.Cursors]::Default
    $script:form.Invalidate()
})
function Invoke-GalintToggle {
    if ($script:busy) { return }
    $script:busy = $true
    $script:target = if ($script:running) { 0.0 } else { 1.0 }
    $script:progressText = if ($script:running) { 'Parando o servidor GALINT...' } else { 'Iniciando o GALINT...' }
    [Windows.Forms.Application]::DoEvents()
    try {
        if ($script:running) {
            $null = Stop-Galint
        }
        else {
            $null = Start-Galint
        }
        $script:lastOperationError = ''
    }
    catch {
        $script:lastOperationError = $_.Exception.Message
        $script:errorUntil = (Get-Date).AddSeconds(20)
        [Windows.Forms.MessageBox]::Show($script:form, $_.Exception.Message, 'GALINT', 'OK', 'Warning') | Out-Null
    }
    finally {
        $script:busy = $false
        $script:progressText = ''
        Update-GalintStatus
        if ($script:lastOperationError) {
            $script:statusLabel.Text = $script:lastOperationError
            $script:statusLabel.ForeColor = [Drawing.Color]::FromArgb(248, 113, 113)
            $script:form.Invalidate()
        }
    }
}

$script:form.Add_MouseClick({
    param($sender, $eventArgs)
    [Drawing.PointF]$mousePosition = [Drawing.PointF]::new([single]$eventArgs.X, [single]$eventArgs.Y)
    if ($eventArgs.Button -eq [Windows.Forms.MouseButtons]::Left -and $script:track.Contains($mousePosition) -and -not $script:busy) {
        Invoke-GalintToggle
    }
})
$script:form.Add_KeyDown({
    param($sender, $eventArgs)
    if (($eventArgs.KeyCode -eq [Windows.Forms.Keys]::Space -or $eventArgs.KeyCode -eq [Windows.Forms.Keys]::Enter) -and -not $script:busy) {
        $eventArgs.Handled = $true
        Invoke-GalintToggle
    }
})

$timer = New-Object Windows.Forms.Timer
$timer.Add_Tick({
    $dirty = $false
    $difference = $script:target - $script:position
    if ([Math]::Abs($difference) -gt 0.004) {
        $script:position += $difference * 0.22
        $dirty = $true
    }
    elseif ($script:position -ne $script:target) {
        $script:position = $script:target
        $dirty = $true
    }
    if ($script:busy) {
        $script:pulse += 0.09
        $dirty = $true
    }
    if ($dirty) {
        $script:form.Invalidate()
    }
    if (-not $script:busy -and $script:timerTicks % 133 -eq 0 -and (Get-Date) -ge $script:errorUntil) {
        $script:lastOperationError = ''
        Update-GalintStatus
    }
    $script:timerTicks++
})
$timer.Interval = 15
$timer.Start()
$script:form.Add_FormClosing({
    if ($script:busy) {
        $_.Cancel = $true
    }
})
Update-GalintStatus
$script:form.Invalidate()
[Windows.Forms.Application]::Run($script:form)
$timer.Dispose()
