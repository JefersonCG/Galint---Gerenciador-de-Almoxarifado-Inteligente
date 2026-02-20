# 📘 README — Publicando Sistema Flask com Cloudflare Tunnel

Este documento explica como publicar um sistema **Flask rodando localmente** na internet usando **Cloudflare Tunnel**, sem abrir portas no roteador.

---

## 📌 Visão Geral

Com o Cloudflare Tunnel, seu sistema Flask continua rodando localmente e passa a ser acessível por um domínio com HTTPS.

Fluxo:

```
Servidor Local (Flask)
        │
   cloudflared
        │
   Cloudflare
        │
     Usuários
```

### Benefícios

- ✅ Não precisa abrir portas
- ✅ HTTPS automático
- ✅ Proteção contra ataques
- ✅ Pode usar autenticação
- ✅ Domínio próprio

---

## 📋 Requisitos

Antes de começar, você precisa:

- Ter um domínio (ex: meusistema.com.br)
- Criar uma conta gratuita no Cloudflare
- Ter o Flask funcionando localmente (ex: localhost:5000)
- Ter acesso ao servidor (Windows ou Linux)

---

## 🔧 Passo 1 — Criar Conta no Cloudflare

1. Acesse: https://dash.cloudflare.com
2. Crie sua conta
3. Adicione seu domínio
4. Aponte o DNS para o Cloudflare (conforme instruções do painel)

---

## 🔧 Passo 2 — Instalar o Cloudflared

### Windows

Baixe em:
https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

Instale normalmente.

---

### Linux (Debian/Ubuntu)

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

---

## 🔧 Passo 3 — Fazer Login no Cloudflare

No terminal:

```bash
cloudflared tunnel login
```

O navegador será aberto para autorização.

---

## 🔧 Passo 4 — Criar o Tunnel

```bash
cloudflared tunnel create flask-system
```

Guarde o **ID do Tunnel**, pois será usado depois.

---

## 🔧 Passo 5 — Configurar o Tunnel

Crie o arquivo de configuração:

### Linux

```bash
nano ~/.cloudflared/config.yml
```

### Windows

Crie em:

```
C:\Users\SEU_USUARIO\.cloudflared\config.yml
```

---

### Conteúdo do Arquivo

Substitua pelos seus dados:

```yaml
tunnel: SEU_ID_DO_TUNNEL
credentials-file: /home/user/.cloudflared/SEU_ID_DO_TUNNEL.json

ingress:
  - hostname: sistema.seudominio.com
    service: http://localhost:5000
  - service: http_status:404
```

> ⚠️ No Windows, ajuste o caminho do `credentials-file`.

---

## 🔧 Passo 6 — Criar DNS Automaticamente

```bash
cloudflared tunnel route dns flask-system sistema.seudominio.com
```

Isso cria o apontamento no Cloudflare.

---

## 🔧 Passo 7 — Iniciar o Tunnel

```bash
cloudflared tunnel run flask-system
```

Após isso, seu sistema ficará disponível em:

```
https://sistema.seudominio.com
```

---

## 🚀 Rodando Flask em Produção (Recomendado)

Evite usar apenas `flask run` em produção.

Use Gunicorn:

```bash
gunicorn app:app --bind 0.0.0.0:5000
```

Estrutura comum:

```
app.py
requirements.txt
venv/
```

---

## 🔐 Segurança (Muito Importante)

Recomendações:

- Ativar Cloudflare Access
- Limitar usuários por e-mail
- Criar autenticação no sistema
- Usar HTTPS (já incluso)

Isso evita acesso indevido.

---

## 📦 Observação Sobre "Compilar"

Flask não é compilado como APK.

Formas de rodar:

- Script Python
- Gunicorn
- Executável com PyInstaller (Windows)

O Cloudflare Tunnel funciona em todos os casos.

---

## 📊 Arquitetura Recomendada

Para uso profissional:

```
Flask
Gunicorn
Banco de Dados
Cloudflare Tunnel
Domínio
```

---

## 🛠️ Problemas Comuns

### ❌ Site não abre

Verifique:

- Flask está rodando?
- Porta correta?
- Tunnel ativo?
- DNS configurado?

---

### ❌ Erro 502 / 504

Normalmente indica:

- Flask parado
- Porta errada
- Firewall bloqueando

---

## 📞 Suporte

Se tiver problemas:

1. Verifique os logs do cloudflared
2. Teste local: http://localhost:5000
3. Confirme o DNS no painel Cloudflare

---

## ✅ Conclusão

Com esse método, você pode:

- Publicar seu sistema local
- Manter segurança
- Evitar custos de hospedagem
- Acessar de qualquer lugar

Ideal para sistemas internos, condomínios, almoxarifado e gestão.

---

📌 Documento criado para uso em projetos Flask com Cloudflare Tunnel.

