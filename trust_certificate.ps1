# Script para adicionar certificado auto-assinado como confiável no Windows
# ATENÇÃO: Execute como Administrador!

param(
    [string]$CertPath = "certs\cert.pem"
)

Write-Host "="*60 -ForegroundColor Cyan
Write-Host "🔒 ADICIONAR CERTIFICADO COMO CONFIÁVEL" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan

# Verificar se é administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "" 
    Write-Host "❌ ERRO: Este script precisa ser executado como Administrador!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Clique com botão direito no PowerShell e escolha:" -ForegroundColor Yellow
    Write-Host "   'Executar como administrador'" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# Verificar se certificado existe
if (-not (Test-Path $CertPath)) {
    Write-Host ""
    Write-Host "❌ Certificado não encontrado: $CertPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Execute primeiro:" -ForegroundColor Yellow
    Write-Host "   python generate_cert_python.py" -ForegroundColor Gray
    Write-Host ""
    pause
    exit 1
}

Write-Host ""
Write-Host "📁 Certificado: $CertPath" -ForegroundColor Gray
Write-Host ""

try {
    # Importar certificado
    Write-Host "📥 Importando certificado..." -ForegroundColor Yellow
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
    $cert.Import((Resolve-Path $CertPath))
    
    Write-Host "   Subject: $($cert.Subject)" -ForegroundColor Gray
    Write-Host "   Issuer: $($cert.Issuer)" -ForegroundColor Gray
    Write-Host "   Válido até: $($cert.NotAfter.ToString('dd/MM/yyyy'))" -ForegroundColor Gray
    
    # Abrir store de certificados raiz confiáveis
    Write-Host ""
    Write-Host "🔓 Abrindo armazenamento de certificados raiz..." -ForegroundColor Yellow
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
    $store.Open("ReadWrite")
    
    # Verificar se já existe
    $existing = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    
    if ($existing) {
        Write-Host "   ⚠️  Certificado já está instalado!" -ForegroundColor Yellow
        Write-Host ""
        $response = Read-Host "Deseja reinstalar? (S/N)"
        
        if ($response -eq 'S' -or $response -eq 's') {
            $store.Remove($existing)
            Write-Host "   🗑️  Certificado antigo removido" -ForegroundColor Gray
        }
        else {
            Write-Host ""
            Write-Host "✅ Mantendo certificado existente" -ForegroundColor Green
            $store.Close()
            pause
            exit 0
        }
    }
    
    # Adicionar certificado
    Write-Host ""
    Write-Host "➕ Adicionando certificado como confiável..." -ForegroundColor Yellow
    $store.Add($cert)
    $store.Close()
    
    Write-Host ""
    Write-Host "="*60 -ForegroundColor Green
    Write-Host "✅ CERTIFICADO INSTALADO COM SUCESSO!" -ForegroundColor Green
    Write-Host "="*60 -ForegroundColor Green
    Write-Host ""
    Write-Host "🎉 O aviso 'Não seguro' foi removido!" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "⚠️  PRÓXIMOS PASSOS:" -ForegroundColor Yellow
    Write-Host "   1. Reinicie todos os navegadores abertos" -ForegroundColor Gray
    Write-Host "   2. Acesse: https://10.0.0.245:5443" -ForegroundColor Gray
    Write-Host "   3. O cadeado verde deve aparecer!" -ForegroundColor Gray
    Write-Host ""
    Write-Host "📝 NOTA:" -ForegroundColor Yellow
    Write-Host "   - Isso funciona APENAS neste computador" -ForegroundColor Gray
    Write-Host "   - Outros PCs ainda verão o aviso" -ForegroundColor Gray
    Write-Host "   - Para distribuir para rede, exporte o certificado:" -ForegroundColor Gray
    Write-Host "     certmgr.msc → Certificados Raiz Confiáveis → Exportar" -ForegroundColor Gray
    Write-Host ""
    
}
catch {
    Write-Host ""
    Write-Host "❌ ERRO: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host "Pressione qualquer tecla para sair..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
