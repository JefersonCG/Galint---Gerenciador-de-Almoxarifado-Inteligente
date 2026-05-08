# 🤖 Respostas em Português - Telegram Bot

## 📖 Problema

Por padrão, quando um usuário envia `/start` para o bot, o Telegram não responde automaticamente. Ou se configurado pelo BotFather, responde em inglês.

## ✅ Solução: Webhook

Configurando um **webhook**, o Flask recebe todos os comandos enviados ao bot e pode responder **em português** automaticamente!

---

## 🔧 Como Configurar

### **1️⃣ Requisitos**

- ✅ Servidor Flask **acessível pela internet** com **HTTPS**
- ✅ Bot já criado no @BotFather
- ✅ Token configurado no GALINT

### **2️⃣ Opções para ter HTTPS**

#### **Opção A: Ngrok (desenvolvimento/teste)**
```powershell
# Baixar ngrok: https://ngrok.com/download
# Executar:
ngrok http 5000

# Copiar a URL HTTPS gerada (ex: https://abc123.ngrok.io)
```

#### **Opção B: Servidor em nuvem (produção)**
- Heroku, AWS, Azure, DigitalOcean
- Certifique-se de ter certificado SSL válido

### **3️⃣ Configurar no Sistema**

1. **Acessar:** http://localhost:5000/configuracoes/telegram
2. **Seção:** "Respostas Automáticas em Português"
3. **Inserir URL:** `https://seu-servidor.com` (sem barra no final)
4. **Clicar:** "Configurar Webhook"

**Exemplo com ngrok:**
```
URL: https://abc123.ngrok-free.app
```

O sistema automaticamente adiciona: `/configuracoes/telegram/webhook`

**URL final enviada ao Telegram:**
```
https://abc123.ngrok-free.app/configuracoes/telegram/webhook
```

### **4️⃣ Testar**

1. **Abrir Telegram** no celular
2. **Buscar:** `@galint_almoxarifado_bot` (seu bot)
3. **Enviar:** `/start`

**Resultado esperado (EM PORTUGUÊS):**
```
👋 Olá, João!

Sou o assistente do GALINT - Sistema de Almoxarifado.

📱 Seu Chat ID: 123456789

Para receber notificações de retirada de materiais:
1️⃣ Copie o código acima
2️⃣ Informe ao administrador do sistema
3️⃣ Aguarde a vinculação com sua matrícula

✅ Após vinculado, você receberá alertas automáticos!
```

---

## 🎯 Comandos Disponíveis

| Comando | Descrição | Resposta |
|---------|-----------|----------|
| `/start` | Boas-vindas + Chat ID | Mensagem completa em português |
| `/ajuda` ou `/help` | Ajuda sobre o sistema | Lista de comandos e funcionalidades |
| `/meuid` | Apenas o Chat ID | Exibe código para vincular |

**Após vinculado (usuário/admin habilitado no sistema):**
- O webhook também processa as mesmas opções do modo polling (menus e comandos), incluindo **envio de relatório**.
- Para administradores, a opção **"Baixar Planilha Estoque Baixo"** envia a planilha (`.xlsx`) e, quando disponível, o PDF.

---

## 🔄 Fluxo Técnico

```
┌─────────────────────────────────────────────────────────┐
│  1. Usuário envia /start para @galint_almoxarifado_bot │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  2. Telegram API envia POST para:                       │
│     https://seu-servidor.com/configuracoes/telegram/webhook │
│                                                         │
│     JSON:                                               │
│     {                                                   │
│       "message": {                                      │
│         "text": "/start",                               │
│         "chat": {"id": 123456789},                      │
│         "from": {"first_name": "João"}                  │
│       }                                                 │
│     }                                                   │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  3. Flask processa (telegram_config.py - webhook())     │
│     - Identifica comando: /start                        │
│     - Extrai chat_id e first_name                       │
│     - Formata mensagem em PORTUGUÊS                     │
│     - Chama TelegramService.send_message()              │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  4. Bot responde para o usuário em PORTUGUÊS            │
└─────────────────────────────────────────────────────────┘
```

---

## 🚨 Solução de Problemas

### **Bot não responde ao /start**

1. **Verificar webhook configurado:**
   - Enviar comando para o bot: `/getWebhookInfo` (não funciona com bots de terceiros)
   - OU testar diretamente no navegador: `https://api.telegram.org/bot<SEU_TOKEN>/getWebhookInfo`

2. **Logs do Flask:**
   ```powershell
   # Verificar se chegou requisição POST
   # Deve aparecer: POST /configuracoes/telegram/webhook
   ```

3. **Testar webhook manualmente:**
   ```powershell
   curl -X POST https://seu-servidor.com/configuracoes/telegram/webhook -H "Content-Type: application/json" -d '{"message":{"text":"/start","chat":{"id":123},"from":{"first_name":"Teste"}}}'
   ```

### **Bot responde em inglês**

- Webhook NÃO está configurado
- Está usando resposta padrão do BotFather
- **Solução:** Configurar webhook conforme instruções acima

### **Erro: "URL inválida"**

- Telegram exige **HTTPS** (não aceita HTTP simples)
- URL deve ser acessível publicamente
- **Solução:** Usar ngrok ou servidor com SSL

### **Webhook configurado mas não funciona**

1. Remover webhook antigo:
   - No sistema: Clicar "Remover Webhook"
   - Aguardar 5 segundos
   - Configurar novamente

2. Verificar firewall/porta do servidor

3. Testar se URL está acessível:
   ```powershell
   curl https://seu-servidor.com/configuracoes/telegram/webhook
   # Deve retornar: {"ok": true}
   ```

---

## 🔒 Segurança

### **Validação de Origem**

A rota `/webhook` é **pública** (sem `@login_required`) para permitir que o Telegram envie dados.

**Riscos:**
- Qualquer pessoa pode enviar POST para `/webhook`

**Recomendações para produção:**

1. **Validar IP de origem** (IPs do Telegram):
```python
TELEGRAM_IPS = [
    "149.154.160.0/20",
    "91.108.4.0/22"
]
```

2. **Validar secret token** (adicionar parâmetro secreto na URL):
```python
# Webhook URL: https://servidor.com/configuracoes/telegram/webhook?secret=abc123

@bp.route("/webhook", methods=["POST"])
def webhook():
    secret = request.args.get("secret")
    if secret != "abc123":  # Guardar em variável de ambiente
        return jsonify({"ok": False}), 403
    # ... resto do código
```

---

## 📊 Monitoramento

### **Ver requisições do webhook:**
```python
# Adicionar log em telegram_config.py webhook():
logger.info(f"Webhook recebido: {update}")
```

### **Histórico de mensagens:**
- Acessar: `/configuracoes/telegram/historico`
- Mostra todas mensagens enviadas (incluindo respostas de comandos)

---

## 💡 Desenvolvimento Local

### **Usar ngrok temporariamente:**

1. **Terminal 1 - Flask:**
   ```powershell
   python app.py
   ```

2. **Terminal 2 - Ngrok:**
   ```powershell
   ngrok http 5000
   ```

3. **Copiar URL HTTPS** do ngrok (ex: `https://abc123.ngrok-free.app`)

4. **Configurar no sistema:**
   - Acessar: /configuracoes/telegram
   - Webhook URL: `https://abc123.ngrok-free.app`
   - Salvar

5. **Testar no Telegram:** `/start`

⚠️ **Atenção:** Toda vez que reiniciar ngrok, a URL muda. Precisa reconfigurar o webhook!

---

## 🎓 Referências

- **Telegram Bot API:** https://core.telegram.org/bots/api
- **Webhooks:** https://core.telegram.org/bots/api#setwebhook
- **Ngrok:** https://ngrok.com/docs

