# Script para adicionar certificado auto-assinado como confiavel no Windows
# ATENCAO: Execute como Administrador!

param(
    [string]$CertPath = "certs\cert.pem"
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ADICIONAR CERTIFICADO COMO CONFIAVEL" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Verificar se e administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "" 
    Write-Host "ERRO: Este script precisa ser executado como Administrador!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Clique com botao direito no PowerShell e escolha:" -ForegroundColor Yellow
    Write-Host "   'Executar como administrador'" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Verificar se certificado existe
if (-not (Test-Path $CertPath)) {
    Write-Host ""
    Write-Host "Certificado nao encontrado: $CertPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Execute primeiro:" -ForegroundColor Yellow
    Write-Host "   python generate_cert_python.py" -ForegroundColor Gray
    Write-Host ""
    Read-Host "Pressione Enter para sair"
    exit 1
}

Write-Host ""
Write-Host "Certificado: $CertPath" -ForegroundColor Gray
Write-Host ""

try {
    # Importar certificado
    Write-Host "Importando certificado..." -ForegroundColor Yellow
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
    $cert.Import((Resolve-Path $CertPath))
    
    Write-Host "   Subject: $($cert.Subject)" -ForegroundColor Gray
    Write-Host "   Issuer: $($cert.Issuer)" -ForegroundColor Gray
    Write-Host "   Valido ate: $($cert.NotAfter.ToString('dd/MM/yyyy'))" -ForegroundColor Gray
    
    # Abrir store de certificados raiz confiaveis
    Write-Host ""
    Write-Host "Abrindo armazenamento de certificados raiz..." -ForegroundColor Yellow
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
    $store.Open("ReadWrite")
    
    # Verificar se ja existe
    $existing = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    
    if ($existing) {
        Write-Host "   Certificado ja esta instalado!" -ForegroundColor Yellow
        Write-Host ""
        $response = Read-Host "Deseja reinstalar? (S/N)"
        
        if ($response -eq 'S' -or $response -eq 's') {
            $store.Remove($existing)
            Write-Host "   Certificado antigo removido" -ForegroundColor Gray
        }
        else {
            Write-Host ""
            Write-Host "Mantendo certificado existente" -ForegroundColor Green
            $store.Close()
            Read-Host "Pressione Enter para sair"
            exit 0
        }
    }
    
    # Adicionar certificado
    Write-Host ""
    Write-Host "Adicionando certificado como confiavel..." -ForegroundColor Yellow
    $store.Add($cert)
    $store.Close()
    
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "CERTIFICADO INSTALADO COM SUCESSO!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "O aviso 'Nao seguro' foi removido!" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "PROXIMOS PASSOS:" -ForegroundColor Yellow
    Write-Host "   1. Reinicie todos os navegadores abertos" -ForegroundColor Gray
    Write-Host "   2. Acesse: https://10.0.0.245:5443" -ForegroundColor Gray
    Write-Host "   3. O cadeado verde deve aparecer!" -ForegroundColor Gray
    Write-Host ""
    Write-Host "NOTA:" -ForegroundColor Yellow
    Write-Host "   - Isso funciona APENAS neste computador" -ForegroundColor Gray
    Write-Host "   - Outros PCs ainda verao o aviso" -ForegroundColor Gray
    Write-Host "   - Para distribuir para rede, veja GUIA_DISTRIBUICAO_CERTIFICADO.md" -ForegroundColor Gray
    Write-Host ""
    
}
catch {
    Write-Host ""
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host "Pressione Enter para sair..."
Read-Host
