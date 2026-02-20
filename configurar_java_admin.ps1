# Script para configurar JAVA_HOME e PATH (requer execução como Administrador)

$javaPath = "C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot"

Write-Host "Configurando JAVA_HOME para: $javaPath" -ForegroundColor Cyan

# Configurar JAVA_HOME
[Environment]::SetEnvironmentVariable("JAVA_HOME", $javaPath, "Machine")

# Adicionar ao PATH
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($currentPath -notlike "*$javaPath\bin*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$javaPath\bin", "Machine")
    Write-Host "✓ PATH atualizado com sucesso" -ForegroundColor Green
} else {
    Write-Host "✓ PATH já contém o diretório do Java" -ForegroundColor Yellow
}

Write-Host "`n✓ Configuração concluída!" -ForegroundColor Green
Write-Host "Reinicie o VS Code para que as alterações tenham efeito." -ForegroundColor Yellow

# Verificar
Write-Host "`nVerificando instalação:" -ForegroundColor Cyan
& "$javaPath\bin\java.exe" -version
