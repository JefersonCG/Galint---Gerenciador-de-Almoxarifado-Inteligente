# Script para gerar certificados SSL auto-assinados para desenvolvimento

Write-Host "=== Gerando Certificados SSL Auto-Assinados ===" -ForegroundColor Cyan

$certDir = "certs"
if (-Not (Test-Path $certDir)) {
    New-Item -ItemType Directory -Path $certDir | Out-Null
    Write-Host "Diretório 'certs' criado." -ForegroundColor Green
}

# Gerar certificado auto-assinado usando OpenSSL (se disponível) ou alternativa PowerShell
$certPath = Join-Path $certDir "cert.pem"
$keyPath = Join-Path $certDir "key.pem"

# Verificar se OpenSSL está disponível
$opensslAvailable = Get-Command openssl -ErrorAction SilentlyContinue

if ($opensslAvailable) {
    Write-Host "Usando OpenSSL para gerar certificados..." -ForegroundColor Yellow
    
    openssl req -x509 -newkey rsa:4096 -nodes `
        -out $certPath `
        -keyout $keyPath `
        -days 365 `
        -subj "/C=BR/ST=Estado/L=Cidade/O=GALINT/OU=Dev/CN=localhost"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Certificados gerados com sucesso!" -ForegroundColor Green
        Write-Host "  Certificado: $certPath" -ForegroundColor Gray
        Write-Host "  Chave: $keyPath" -ForegroundColor Gray
    } else {
        Write-Host "Erro ao gerar certificados com OpenSSL." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "OpenSSL não encontrado. Usando método alternativo do PowerShell..." -ForegroundColor Yellow
    
    # Criar certificado auto-assinado usando PowerShell (apenas Windows)
    $cert = New-SelfSignedCertificate `
        -DnsName "localhost", "127.0.0.1", "10.0.0.245" `
        -CertStoreLocation "cert:\LocalMachine\My" `
        -NotAfter (Get-Date).AddYears(1) `
        -KeyAlgorithm RSA `
        -KeyLength 4096
    
    # Exportar certificado e chave
    $password = ConvertTo-SecureString -String "galint2024" -Force -AsPlainText
    
    $pfxPath = Join-Path $certDir "cert.pfx"
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $password | Out-Null
    
    # Converter PFX para PEM (requer OpenSSL - informar usuário)
    Write-Host "`nCertificado PFX criado em: $pfxPath" -ForegroundColor Green
    Write-Host "Para converter para PEM (necessário para Flask), instale OpenSSL:" -ForegroundColor Yellow
    Write-Host "  1. Baixe: https://slproweb.com/products/Win32OpenSSL.html" -ForegroundColor Gray
    Write-Host "  2. Execute este script novamente" -ForegroundColor Gray
    Write-Host "`nOu use o seguinte comando manualmente:" -ForegroundColor Yellow
    Write-Host "  openssl pkcs12 -in $pfxPath -out $certPath -nodes -nokeys" -ForegroundColor Gray
    Write-Host "  openssl pkcs12 -in $pfxPath -out $keyPath -nodes -nocerts" -ForegroundColor Gray
}

Write-Host "`n=== AVISO DE SEGURANÇA ===" -ForegroundColor Red
Write-Host "Certificados auto-assinados são APENAS para desenvolvimento!" -ForegroundColor Yellow
Write-Host "Para produção, use certificados válidos (Let's Encrypt, etc.)" -ForegroundColor Yellow
