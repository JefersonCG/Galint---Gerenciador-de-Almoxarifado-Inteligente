# 📘 Guia Completo: Distribuir Certificado SSL em Rede Local

## 🎯 Objetivo
Este guia ensina como exportar e instalar o certificado SSL auto-assinado em todos os computadores da sua rede local, removendo o aviso "Não seguro" para todos os usuários.

---

## 📋 Visão Geral do Processo

```
┌─────────────────────────────────────────────────────────────┐
│  SERVIDOR (PC onde o Flask está rodando)                    │
│  1. Gerar certificado                                       │
│  2. Instalar como confiável                                 │
│  3. Exportar certificado                                    │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ (Copiar arquivo .cer)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  CLIENTES (Outros PCs da rede)                              │
│  4. Importar certificado em cada PC                        │
│  5. Testar acesso HTTPS                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🖥️ PARTE 1: NO SERVIDOR (PC com Flask)

### Passo 1: Gerar Certificado (se ainda não fez)

```powershell
# Abrir PowerShell na pasta do projeto
cd "C:\Users\LUIS\Desktop\GALINT FLASK"

# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Gerar certificado
python generate_cert_python.py
```

**Resultado esperado:**
```
✅ Certificado salvo em: certs\cert.pem
✅ Chave Privada salva em: certs\key.pem
```

---

### Passo 2: Instalar Certificado no Servidor

```powershell
# Executar como Administrador
# Botão direito no PowerShell → "Executar como administrador"

cd "C:\Users\LUIS\Desktop\GALINT FLASK"
.\trust_certificate.ps1
```

**O que esse script faz:**
- ✅ Adiciona o certificado aos "Certificados Raiz Confiáveis" do Windows
- ✅ Remove o aviso "Não seguro" neste computador
- ✅ Prepara o certificado para exportação

---

### Passo 3: Exportar Certificado para Distribuição

Existem **3 métodos** para exportar. Escolha o mais conveniente:

#### 📌 **MÉTODO A: Via Script PowerShell (RECOMENDADO - Mais Rápido)**

```powershell
# Executar como Administrador
cd "C:\Users\LUIS\Desktop\GALINT FLASK"

# Criar arquivo de exportação
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
$cert.Import((Resolve-Path "certs\cert.pem"))

$store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
$store.Open("ReadOnly")
$certToExport = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
$store.Close()

# Exportar para arquivo .cer
$exportPath = "certs\GALINT-SSL-Certificate.cer"
[System.IO.File]::WriteAllBytes($exportPath, $certToExport.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))

Write-Host "✅ Certificado exportado para: $exportPath" -ForegroundColor Green
Write-Host "📋 Copie este arquivo para os outros PCs da rede" -ForegroundColor Yellow
```

**Resultado:** Arquivo `certs\GALINT-SSL-Certificate.cer` criado

---

#### 📌 **MÉTODO B: Via Interface Gráfica (Mais Visual)**

1. **Abrir Gerenciador de Certificados:**
   - Pressione `Win + R`
   - Digite: `certlm.msc` (para máquina) ou `certmgr.msc` (para usuário)
   - Clique OK

2. **Localizar o Certificado:**
   - Expanda: **Certificados Raiz Confiáveis da Autoridade de Certificação**
   - Clique em: **Certificados**
   - Procure por: **localhost** ou **GALINT**

   ![Gerenciador de Certificados](https://i.imgur.com/example.png)

3. **Exportar:**
   - Clique direito no certificado → **Todas as Tarefas** → **Exportar...**
   - Clique **Avançar**
   - Selecione: **Não, não exportar a chave privada** ⚠️ IMPORTANTE!
   - Clique **Avançar**
   - Selecione: **X.509 codificado na base 64 (.CER)**
   - Clique **Avançar**
   - Salve como: `C:\Users\LUIS\Desktop\GALINT FLASK\certs\GALINT-SSL-Certificate.cer`
   - Clique **Avançar** → **Concluir**

4. **Confirmação:**
   ```
   ✅ "A exportação foi bem-sucedida"
   ```

---

#### 📌 **MÉTODO C: Via OpenSSL (Conversão Direta)**

Se você tiver OpenSSL instalado:

```powershell
cd "C:\Users\LUIS\Desktop\GALINT FLASK"

# Converter PEM para CER (formato Windows)
openssl x509 -in certs\cert.pem -out certs\GALINT-SSL-Certificate.cer -outform DER

Write-Host "✅ Certificado exportado!" -ForegroundColor Green
```

---

### Passo 4: Compartilhar o Certificado na Rede

Escolha uma das opções:

#### **Opção A: Pasta Compartilhada (Recomendado)**

```powershell
# Criar pasta compartilhada
$sharePath = "C:\Users\LUIS\Desktop\GALINT FLASK\certs"
New-SmbShare -Name "GALINT-Cert" -Path $sharePath -ReadAccess "Everyone"

Write-Host "✅ Pasta compartilhada criada!" -ForegroundColor Green
Write-Host "📡 Acesso na rede: \\$env:COMPUTERNAME\GALINT-Cert" -ForegroundColor Cyan
Write-Host ""
Write-Host "Instrua os usuários a acessarem:" -ForegroundColor Yellow
Write-Host "   \\$env:COMPUTERNAME\GALINT-Cert\GALINT-SSL-Certificate.cer" -ForegroundColor Gray
```

#### **Opção B: E-mail**

```
📧 Envie o arquivo GALINT-SSL-Certificate.cer por e-mail
   com as instruções de instalação (veja PARTE 2)
```

#### **Opção C: Pen Drive / Servidor de Arquivos**

```
💾 Copie o arquivo GALINT-SSL-Certificate.cer para:
   - Pen Drive
   - Servidor de arquivos da empresa
   - OneDrive / Google Drive compartilhado
```

---

## 💻 PARTE 2: NOS CLIENTES (Outros PCs da Rede)

### 📥 Instruções para os Usuários Instalarem o Certificado

Envie estas instruções para cada usuário da rede:

---

### **MÉTODO 1: Instalação Rápida (Duplo Clique)**

1. **Obter o certificado:**
   - Acesse: `\\NOME-DO-SERVIDOR\GALINT-Cert\GALINT-SSL-Certificate.cer`
   - Ou abra o arquivo recebido por e-mail/pen drive

2. **Instalar:**
   - **Duplo clique** no arquivo `GALINT-SSL-Certificate.cer`
   - Clique em **Instalar Certificado...**
   - Selecione: **Computador Local** ⚠️ (precisa de Admin)
   - Clique **Avançar**
   - Selecione: **Colocar todos os certificados no repositório a seguir**
   - Clique **Procurar...**
   - Escolha: **Autoridades de Certificação Raiz Confiáveis**
   - Clique **OK** → **Avançar** → **Concluir**

3. **Aviso de Segurança:**
   - Aparecerá: "Deseja instalar este certificado?"
   - Clique **SIM**

4. **Confirmação:**
   ```
   ✅ "A importação foi bem-sucedida"
   ```

5. **Reiniciar Navegador:**
   - Feche TODOS os navegadores
   - Abra novamente
   - Acesse: `https://10.0.0.245:5443`
   - **🟢 Cadeado verde deve aparecer!**

---

### **MÉTODO 2: Via PowerShell (Para Admins de Rede)**

Para instalar em vários PCs automaticamente:

```powershell
# Executar como Administrador em cada PC cliente

# 1. Copiar certificado (se estiver em rede)
$certPath = "\\SERVIDOR\GALINT-Cert\GALINT-SSL-Certificate.cer"

# Ou se copiou localmente
# $certPath = "C:\Temp\GALINT-SSL-Certificate.cer"

# 2. Importar certificado
Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\LocalMachine\Root

Write-Host "✅ Certificado instalado com sucesso!" -ForegroundColor Green
Write-Host "🔄 Reinicie o navegador e acesse https://10.0.0.245:5443" -ForegroundColor Yellow
```

---

### **MÉTODO 3: Via Política de Grupo (GPO) - Rede Windows Server**

Para ambientes corporativos com Active Directory:

#### **No Servidor de Domínio:**

1. **Abrir Console de Gerenciamento de Política de Grupo:**
   ```
   Win + R → gpmc.msc
   ```

2. **Criar/Editar GPO:**
   - Clique direito em seu domínio → **Criar uma GPO neste domínio e fornecer um link aqui**
   - Nome: `Certificado GALINT SSL`
   - Clique direito → **Editar**

3. **Configurar Distribuição:**
   ```
   Configuração do Computador
     └─ Políticas
         └─ Configurações do Windows
             └─ Configurações de Segurança
                 └─ Políticas de Chave Pública
                     └─ Autoridades de Certificação Raiz Confiáveis
   ```

4. **Importar Certificado:**
   - Clique direito em **Autoridades de Certificação Raiz Confiáveis**
   - **Importar...**
   - Selecione: `GALINT-SSL-Certificate.cer`
   - Concluir

5. **Aplicar GPO:**
   ```powershell
   # Em cada PC cliente ou aguardar atualização automática
   gpupdate /force
   ```

---

## 🔍 VERIFICAÇÃO E TESTES

### No PC Cliente, após instalar o certificado:

#### **Teste 1: Verificar Instalação**

```powershell
# Abrir PowerShell
certutil -store Root | Select-String -Pattern "GALINT|localhost" -Context 2,2
```

**Resultado esperado:**
```
✅ Certificado encontrado no armazenamento Raiz
```

---

#### **Teste 2: Acessar via Navegador**

1. **Abrir navegador (Chrome/Edge/Firefox)**
2. **Acessar:** `https://10.0.0.245:5443`
3. **Verificar cadeado:** 🟢 Deve estar verde/seguro

**Antes:**
```
⚠️ Não seguro | https://10.0.0.245:5443
```

**Depois:**
```
🔒         | https://10.0.0.245:5443
```

---

#### **Teste 3: Ver Detalhes do Certificado**

1. **Clicar no cadeado** 🔒 na barra de endereços
2. **Clicar em:** "Conexão é segura"
3. **Clicar em:** "Certificado é válido"
4. **Verificar:**
   - ✅ Emitido para: `localhost` ou `10.0.0.245`
   - ✅ Emitido por: `GALINT`
   - ✅ Válido até: (data de expiração)

---

## 🛠️ SOLUÇÃO DE PROBLEMAS

### ❌ Problema: "O certificado não é confiável"

**Causa:** Certificado não foi instalado em "Certificados Raiz Confiáveis"

**Solução:**
```powershell
# Verificar onde está instalado
certutil -store My | Select-String -Pattern "localhost"
certutil -store Root | Select-String -Pattern "localhost"

# Se estiver em 'My', mover para 'Root'
# Desinstalar e reinstalar seguindo MÉTODO 1
```

---

### ❌ Problema: "Aviso ainda aparece após instalar"

**Causa:** Navegador em cache ou certificado errado

**Solução:**
1. Feche TODOS os navegadores (verifique no Gerenciador de Tarefas)
2. Limpe cache do navegador:
   - Chrome/Edge: `Ctrl + Shift + Del` → Limpar dados de navegação
3. Reinicie o computador
4. Teste novamente

---

### ❌ Problema: "Acesso negado ao instalar"

**Causa:** Sem permissões de administrador

**Solução:**
```powershell
# Executar PowerShell como Administrador
# Botão direito → "Executar como administrador"
```

---

### ❌ Problema: "Certificado expirado"

**Causa:** Certificado auto-assinado expirou (válido por 1 ano)

**Solução:**
```powershell
# No SERVIDOR, gerar novo certificado
cd "C:\Users\LUIS\Desktop\GALINT FLASK"
.\.venv\Scripts\Activate.ps1
python generate_cert_python.py

# Repetir todo o processo de distribuição
```

---

## 📊 CHECKLIST DE IMPLANTAÇÃO

### No Servidor:
- [ ] Certificado gerado (`certs\cert.pem` e `certs\key.pem`)
- [ ] Certificado instalado localmente (executou `trust_certificate.ps1`)
- [ ] Certificado exportado (`certs\GALINT-SSL-Certificate.cer`)
- [ ] Arquivo compartilhado na rede ou distribuído
- [ ] Servidor HTTPS rodando (`python scripts/tests/test_https_adhoc.py`)

### Em Cada PC Cliente:
- [ ] Arquivo `.cer` copiado/acessado
- [ ] Certificado instalado em "Certificados Raiz Confiáveis"
- [ ] Navegadores reiniciados
- [ ] Testado acesso a `https://10.0.0.245:5443`
- [ ] Cadeado verde visível 🔒

---

## 🔄 MANUTENÇÃO E RENOVAÇÃO

### Quando renovar o certificado:

1. **Antes de expirar** (certificado válido por 365 dias)
2. **Quando mudar o IP do servidor**
3. **Quando mudar o domínio/hostname**

### Processo de renovação:

```powershell
# 1. Remover certificado antigo (em todos os PCs)
certutil -delstore Root "Thumbprint-do-Certificado-Antigo"

# 2. Gerar novo certificado no servidor
python generate_cert_python.py

# 3. Repetir processo de distribuição
# (Exportar e instalar nos clientes)
```

---

## 💡 DICAS IMPORTANTES

### ✅ Boas Práticas:

1. **Documentar a data de expiração** do certificado
2. **Criar lembrete** para renovar 1 mês antes
3. **Manter backup** do arquivo `.cer` exportado
4. **Testar em 1 PC** antes de distribuir para toda rede
5. **Criar guia visual** com screenshots para usuários finais

### ⚠️ Avisos de Segurança:

1. **NUNCA exporte a chave privada** (`key.pem`) - apenas o certificado público
2. **Apenas para redes locais** - não use certificados auto-assinados na Internet
3. **Certificados auto-assinados NÃO são válidos** fora da sua rede
4. **Para produção na Internet**, use Let's Encrypt ou CA comercial

---

## 📞 SUPORTE

### Comandos Úteis para Diagnóstico:

```powershell
# Listar todos os certificados raiz
certutil -store Root

# Verificar certificado específico
certutil -store Root | Select-String -Pattern "GALINT" -Context 5,5

# Ver detalhes de um arquivo .cer
certutil -dump "GALINT-SSL-Certificate.cer"

# Testar conexão SSL
Test-NetConnection -ComputerName 10.0.0.245 -Port 5443

# Ver certificado de um site via PowerShell
$url = "https://10.0.0.245:5443"
$req = [System.Net.WebRequest]::Create($url)
try { $req.GetResponse() } catch { $_.Exception.InnerException.Certificate }
```

---

## 📚 RECURSOS ADICIONAIS

- **Gerenciador de Certificados:** `Win + R` → `certmgr.msc`
- **Console MMC Personalizado:** `mmc` → Adicionar Snap-in → Certificados
- **Documentação Microsoft:** [Gerenciar Certificados](https://docs.microsoft.com/windows/security/threat-protection/windows-firewall/import-certificate)
- **Let's Encrypt (Produção):** Ver arquivo `setup_letsencrypt.md`

---

## ✅ RESUMO EXECUTIVO

### Para Distribuir Certificado na Rede Local:

1. **Servidor:** Execute `.\trust_certificate.ps1` como admin
2. **Servidor:** Exporte certificado (Método A, B ou C)
3. **Servidor:** Compartilhe arquivo `.cer` na rede
4. **Clientes:** Duplo clique em `.cer` → Instalar em "Raiz Confiáveis"
5. **Clientes:** Reiniciar navegador
6. **Teste:** Acessar `https://10.0.0.245:5443` → 🟢 Cadeado verde

---

**✨ Com isso, todos os usuários da sua rede terão acesso HTTPS seguro sem avisos! ✨**
