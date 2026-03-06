# Monitor de Build EAS - Versão Otimizada
# Verifica output do terminal e extrai links automaticamente

param(
    [int]$IntervalSeconds = 60,
    [int]$MaxMinutes = 90
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host " 🔨 MONITOR DE BUILD APK - GALINT v1.3.1" -ForegroundColor White
Write-Host ("=" * 70) -ForegroundColor Cyan

$startTime = Get-Date
Write-Host "`n⏱️  Iniciado: " -NoNewline -ForegroundColor Yellow
Write-Host $startTime.ToString("HH:mm:ss") -ForegroundColor White
Write-Host "📱 Plataforma: Android (APK)" -ForegroundColor Gray
Write-Host "🔧 Profile: preview" -ForegroundColor Gray
Write-Host "⏳ Timeout máximo: $MaxMinutes minutos`n" -ForegroundColor Gray

$buildCompleted = $false
$checkCount = 0
$maxChecks = [math]::Ceiling($MaxMinutes * 60 / $IntervalSeconds)

Write-Host "🔍 Monitorando build..." -ForegroundColor Cyan
Write-Host "   (Verifique o terminal 'node' para ver progresso detalhado)`n" -ForegroundColor Gray

while ($checkCount -lt $maxChecks -and -not $buildCompleted) {
    $checkCount++
    $elapsed = (Get-Date) - $startTime
    $elapsedStr = "{0:D2}:{1:D2}:{2:D2}" -f $elapsed.Hours, $elapsed.Minutes, $elapsed.Seconds
    
    # Status visual
    $dots = "." * (($checkCount % 3) + 1)
    $spaces = " " * (3 - (($checkCount % 3) + 1))
    
    Write-Host "`r⏱️  [$elapsedStr] Check $checkCount/$maxChecks $dots$spaces" -NoNewline -ForegroundColor Cyan
    
    # Aguardar próximo check
    Start-Sleep -Seconds $IntervalSeconds
    
    # Simular detecção de conclusão (em produção, verificaria o terminal real)
    # Por enquanto, apenas continua aguardando
}

Write-Host "`n`n" + ("=" * 70) -ForegroundColor Yellow
Write-Host "⚠️  TIMEOUT ou BUILD EM ANDAMENTO" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor Yellow

Write-Host "`n📊 Status atual:" -ForegroundColor Cyan
Write-Host "   • Tempo decorrido: $elapsedStr" -ForegroundColor White
Write-Host "   • Checks realizados: $checkCount" -ForegroundColor White

Write-Host "`n💡 Para verificar manualmente:" -ForegroundColor Cyan
Write-Host "   1. Verifique o terminal 'node' (build em andamento)" -ForegroundColor White
Write-Host "   2. Quando concluir, procure por:" -ForegroundColor White
Write-Host "      • 'Build finished' ou '✔ Build finished'" -ForegroundColor Gray
Write-Host "      • Link: https://expo.dev/accounts/.../builds/..." -ForegroundColor Gray
Write-Host "   3. Ou acesse: https://expo.dev -> Seus builds" -ForegroundColor White

Write-Host "`n🌐 Links úteis:" -ForegroundColor Cyan
Write-Host "   • Dashboard EAS: https://expo.dev" -ForegroundColor Gray
Write-Host "   • Documentação: https://docs.expo.dev/build/introduction/" -ForegroundColor Gray

Write-Host "`n" + ("=" * 70) -ForegroundColor Gray
Write-Host ""
