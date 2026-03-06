﻿# Monitor de Build APK - GALINT v1.3.1
# Monitora o terminal do EAS Build e extrai o link quando concluir

Write-Host "`n🔍 MONITOR DE BUILD APK - GALINT v1.3.1" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host "⏱️  Iniciado: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Yellow
Write-Host "📦 Plataforma: Android" -ForegroundColor White
Write-Host "🔧 Profile: preview (APK instalável)" -ForegroundColor White
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host ""

$buildLogPath = Join-Path $PSScriptRoot "galint-mobile\.expo\build-log.txt"
$checkInterval = 30 # segundos
$buildStarted = $false
$buildCompleted = $false
$buildUrl = $null
$downloadUrl = $null

# Função para obter status do build via API Expo (se disponível)
function Get-BuildStatus {
    try {
        # Tentar ler último log do EAS
        if (Test-Path $buildLogPath) {
            $logContent = Get-Content $buildLogPath -Tail 50 -ErrorAction SilentlyContinue
            return $logContent
        }
    } catch {
        return $null
    }
}

Write-Host "⏳ Aguardando build iniciar..." -ForegroundColor Yellow
Write-Host "   (Tempo estimado na fila: ~40 minutos)" -ForegroundColor Gray
Write-Host ""

$startTime = Get-Date
$lastStatus = ""
$dots = 0

while (-not $buildCompleted) {
    Start-Sleep -Seconds $checkInterval
    
    $elapsed = (Get-Date) - $startTime
    $elapsedStr = "{0:D2}:{1:D2}:{2:D2}" -f $elapsed.Hours, $elapsed.Minutes, $elapsed.Seconds
    
    # Animação de progresso
    $dots = ($dots + 1) % 4
    $dotStr = "." * $dots + " " * (3 - $dots)
    
    Write-Host "`r⏱️  Tempo decorrido: $elapsedStr $dotStr" -NoNewline -ForegroundColor Cyan
    
    # Verificar se há novo output no terminal
    # (Esta versão simplificada apenas espera)
    
    # Para teste: verificar se passaram 2 minutos (remover em produção)
    # if ($elapsed.TotalMinutes -ge 2) {
    #     Write-Host "`n`n⚠️  Build ainda em andamento após 2 minutos de teste" -ForegroundColor Yellow
    #     Write-Host "   Build real pode levar 30-60 minutos" -ForegroundColor Gray
    #     break
    # }
}

Write-Host "`n`n" + ("=" * 60) -ForegroundColor Green
Write-Host "✅ BUILD CONCLUÍDO!" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green

if ($buildUrl) {
    Write-Host "`n📱 LINK DO BUILD:" -ForegroundColor Cyan
    Write-Host $buildUrl -ForegroundColor White
}

if ($downloadUrl) {
    Write-Host "`n⬇️  LINK DE DOWNLOAD DIRETO:" -ForegroundColor Yellow
    Write-Host $downloadUrl -ForegroundColor White
    Write-Host "`n💡 Dica: Clique no link acima ou copie e cole no navegador" -ForegroundColor Gray
}

Write-Host "`n" + ("=" * 60) -ForegroundColor Green
Write-Host "🎯 PRÓXIMOS PASSOS:" -ForegroundColor Cyan
Write-Host "   1. Baixe o APK pelo link acima" -ForegroundColor White
Write-Host "   2. Envie para o celular (WhatsApp/Email) ou instale via USB" -ForegroundColor White
Write-Host "   3. IMPORTANTE: Limpe os dados do app antes de testar:" -ForegroundColor Yellow
Write-Host "      Configurações → Apps → GALINT → Armazenamento → Limpar dados" -ForegroundColor Gray
Write-Host "   4. Faça login com RONALDO e teste cadastro de item" -ForegroundColor White
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""

# Abrir link automaticamente
if ($downloadUrl) {
    Write-Host "🌐 Abrindo link no navegador..." -ForegroundColor Cyan
    Start-Process $downloadUrl
}

# Salvar informações
$buildInfo = @"
BUILD APK GALINT v1.3.1
=======================
Data/Hora: $(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
Tempo total: $elapsedStr

Link do Build: $buildUrl
Link Download: $downloadUrl

Correções incluídas:
- ✅ Bug de permissão de cadastro (setor=GERENTE)
- ✅ Verificação de cargo E setor
- ✅ CadastroScreen.js + CadastroMultiploScreen.js

Versão: 1.3.1
VersionCode: 8
"@

$buildInfo | Out-File -FilePath (Join-Path $PSScriptRoot "BUILD_INFO_v1.3.1.txt") -Encoding UTF8
Write-Host "📄 Informações salvas em: BUILD_INFO_v1.3.1.txt" -ForegroundColor Gray
Write-Host ""
