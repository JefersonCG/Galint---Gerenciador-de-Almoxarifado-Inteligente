# 🚀 Instalação do Sistema Telegram - GALINT

## ✅ Implementação Completa

O sistema de notificações Telegram foi **totalmente implementado** com sucesso!

---

## 📦 Próximos Passos para Ativar

### **1️⃣ Instalar Dependências (OBRIGATÓRIO)**

```powershell
# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Instalar novas dependências
pip install requests==2.32.3 APScheduler==3.10.4

# OU reinstalar tudo do requirements.txt
pip install -r requirements.txt
```

**Resultado esperado:**
```
Successfully installed requests-2.32.3 APScheduler-3.10.4
```

---

### **2️⃣ Executar Migrações do Banco de Dados**

**Migração 1: Estrutura principal do Telegram**

```powershell
# Com ambiente virtual ativado
python scripts\add_telegram_support.py
```

**Resultado esperado:**
```
🔄 Iniciando migração do banco de dados...
  → Adicionando campo 'local_servico' em 'saidas'...
    ✅ Campo 'local_servico' adicionado
  → Criando tabelas do sistema Telegram...
    ✅ Tabelas criadas com sucesso
    ✅ Tabela 'telegram_config' criada
    ✅ Tabela 'telegram_users' criada
    ✅ Tabela 'telegram_groups' criada
    ✅ Tabela 'telegram_notifications' criada
  → Criando configuração inicial do Telegram...
    ✅ Configuração inicial criada
```

**Migração 2: Cadastro automático de usuários**

```powershell
python scripts\add_telegram_conversations.py
```

**Resultado esperado:**
```
🔄 Criando tabela de conversações do Telegram...
  ✅ Tabela 'telegram_conversations' criada

✅ Migração concluída com sucesso!

📝 Agora o bot pode cadastrar usuários automaticamente:
  1. Usuário envia /start para o bot
  2. Bot pergunta o nome completo
  3. Bot pergunta a função/cargo
  4. Sistema busca automaticamente no banco
  5. Se encontrar match único, vincula automaticamente!
```

✅ Migração concluída com sucesso!
```

---

### **3️⃣ Reiniciar Servidor Flask**

```powershell
# Se estiver rodando, parar com Ctrl+C

# Iniciar novamente
python app.py
```

**Verificar se não há erros:**
```
✓ Servidor deve iniciar normalmente
✓ Procurar linha: "APScheduler initialized" nos logs
```

---

### **4️⃣ Criar Bot no Telegram (5 minutos)**

1. **Abrir Telegram** (celular ou desktop)
2. **Buscar:** `@BotFather`
3. **Enviar:** `/newbot`
4. **Nome do bot:** `GALINT Almoxarifado`
5. **Username:** `galint_almoxarifado_bot` (ou outro disponível)
6. **Copiar o TOKEN** que o BotFather retorna (ex: `123456789:ABCdef...`)

---

### **5️⃣ Configurar no Sistema**

1. **Acessar:** http://localhost:5000/configuracoes
2. **Clicar:** Card "Telegram"
3. **Colar TOKEN** no campo indicado
4. **Marcar:** ☑️ "Ativado"
5. **Clicar:** "Salvar Configurações"
6. **Clicar:** "Testar Conexão"

**Resultado esperado:**
```
✅ Bot conectado! Username: @galint_almoxarifado_bot
```

---

### **6️⃣ Vincular Usuário de Teste**

1. **No Telegram:** Buscar `@galint_almoxarifado_bot`
2. **Enviar:** `/start`
3. **Bot responde com Chat ID** (ex: `123456789`)
4. **No sistema:** Voltar para `/configuracoes/telegram`
5. **Seção "Usuários Vinculados":**
   - Selecionar usuário (ex: seu próprio usuário admin)
   - Inserir Chat ID recebido
   - Clicar "+" para vincular

---

### **7️⃣ Criar Grupo de Supervisão (OPCIONAL)**

1. **No Telegram:**
   - Criar novo grupo: "Supervisão GALINT"
   - Adicionar o bot `@galint_almoxarifado_bot` como membro
   - Enviar qualquer mensagem no grupo (ex: "teste")

2. **No sistema:**
   - Seção "Grupos de Supervisão"
   - Nome: `Supervisão GALINT`
   - Chat ID: obter via bot ou API (geralmente começa com `-100`)
   - Clicar "+" para adicionar

---

### **8️⃣ Testar Sistema Completo**

#### **Teste 1: Mensagem Manual**
1. **No sistema:** Seção "Enviar Mensagem de Teste"
2. **Destinatário:** Selecionar seu usuário
3. **Mensagem:** `Testando notificação do GALINT 🔧`
4. **Clicar:** "Enviar"

**Resultado:** Mensagem deve chegar no seu Telegram!

#### **Teste 2: Retirada de Material**
1. **Cadastrar item de teste** (se não tiver):
   - Código: `TESTE-001`
   - Descrição: `Item de Teste`
   - **Categoria:** Escolha qualquer (Ferramentas, Material Elétrico, etc.)
   - Estoque: 10

2. **Registrar retirada:**
   - Menu: Movimentos → Saída
   - Código: `TESTE-001`
   - Quantidade: 1
   - **Local do Serviço:** `Teste do sistema no laboratório` (opcional)
   - Funcionário: (selecionar usuário vinculado)
   - Clicar: "Registrar Saída"

**Resultado:**
- ✅ Saída registrada com sucesso
- ✅ Você recebe mensagem no Telegram (personalizada por categoria):
  
  **Se for FERRAMENTA:**
  ```
  🔔 Retirada Registrada
  
  🔧 Item de Teste
  Quantidade: 1 un
  Serviço: Teste do sistema no laboratório
  
  ⚠️ Lembre-se de devolver ao final do expediente!
  ```
  
  **Se for OUTRO MATERIAL:**
  ```
  ✅ Retirada Confirmada
  
  ⚡ Item de Teste
  Quantidade: 1 un
  Finalidade: Teste do sistema no laboratório
  ```

- ✅ Grupo de supervisão recebe alerta com categoria e emoji

💡 **Dica:** Teste com diferentes categorias para ver mensagens personalizadas!

#### **Teste 3: Alerta Agendado**
1. **No sistema:** `/configuracoes/telegram`
2. **Clicar:** "Executar Alerta Agora"

**Resultado:**
- Se houver ferramentas não devolvidas → mensagem listando pendências
- Se não houver → nenhuma mensagem enviada (comportamento esperado)

---

## 🎯 Funcionalidades Implementadas

✅ **Cadastro Automático de Usuários:**
- Bot pergunta nome e função interativamente
- Busca automática no banco de dados
- Vinculação automática se encontrar match único
- Sem necessidade de administrador na maioria dos casos
- Ver documentação: [CADASTRO_AUTOMATICO_TELEGRAM.md](CADASTRO_AUTOMATICO_TELEGRAM.md)

✅ **Notificações Automáticas:**
- Retirada de **QUALQUER material** → mensagem para funcionário + grupo supervisão
- **TODOS os materiais** acionam notificação (Ferramentas, Elétrico, Líquidos, etc.)
- Mensagens personalizadas com **emojis por categoria** (🔧⚡💧📦)
- Campo "Local do Serviço" **opcional** para todos os materiais

✅ **Alertas Agendados:**
- Segunda a Sexta: 16:20
- Sábado: 11:00
- Lista ferramentas não devolvidas
- Horários configuráveis no painel

✅ **Painel Administrativo:**
- Configurar bot token
- Vincular usuários manualmente (quando necessário)
- Gerenciar grupos de supervisão
- Enviar mensagens de teste
- Executar alerta manualmente
- Visualizar histórico completo

✅ **Webhook com Respostas em Português:**
- Comandos `/start`, `/ajuda`, `/meuid` respondem em português
- Conversa interativa para cadastro automático
- Configuração simples via painel admin

✅ **Histórico de Notificações:**
- Data/hora de envio
- Destinatário e chat_id
- Tipo (retirada/alerta/teste)
- Status (enviado/falha)
- Mensagem completa
- Erros (se houver)

---

## 📁 Arquivos Criados/Modificados

### **Novos Arquivos:**
```
galint_flask/
  services/
    telegram_service.py          # Serviço de mensagens
    scheduler_service.py          # Agendamento APScheduler
  views/
    telegram_config.py            # Rotas admin
  templates/
    config_telegram.html          # Painel configuração
    config_telegram_historico.html # Histórico

scripts/
  add_telegram_support.py        # Migração banco

Documentação/
  README.md                      # Guia completo (seção Telegram)
  SETUP_AMBIENTE_DEV.md          # Setup desenvolvimento
  INSTALACAO_TELEGRAM.md         # Este arquivo
```

### **Arquivos Modificados:**
```
galint_flask/
  models.py                      # + TelegramConfig, TelegramUser, TelegramGroup, TelegramNotification
                                 # + Saida.local_servico
  __init__.py                    # + Inicialização scheduler
  views/__init__.py              # + Registro blueprint telegram_config
  views/movements.py             # + Integração notificações
  services/inventory.py          # + Suporte local_servico
  templates/config.html          # + Card Telegram
  templates_mako/movements/saida.mako # + Campo Local do Serviço

requirements.txt                 # + requests, APScheduler
```

---

## 🔍 Verificação de Instalação

Execute este checklist para garantir que tudo está funcionando:

- [ ] Dependências instaladas (`pip list` mostra requests e APScheduler)
- [ ] Migração executada sem erros
- [ ] Servidor Flask inicia sem erros
- [ ] Logs mostram "APScheduler initialized"
- [ ] Página `/configuracoes/telegram` carrega normalmente
- [ ] Bot criado no Telegram via @BotFather
- [ ] Token configurado no sistema
- [ ] Teste de conexão retorna sucesso
- [ ] Pelo menos 1 usuário vinculado
- [ ] Mensagem de teste enviada e recebida
- [ ] Retirada de ferramenta aciona notificação
- [ ] Campo "Local do Serviço" aparece no formulário de saída
- [ ] Campo obrigatório para categoria Ferramentas

---

## ❓ Troubleshooting Rápido

### **Erro: ModuleNotFoundError: No module named 'requests'**
**Solução:**
```powershell
pip install requests APScheduler
```

### **Erro: "Bot não conectado"**
**Causas:**
1. Token incorreto → Verificar se copiou token completo do @BotFather
2. Sem internet → Verificar conexão
3. Firewall bloqueando → Liberar api.telegram.org porta 443

### **Erro: "Campo local_servico não existe"**
**Solução:**
```powershell
python scripts\add_telegram_support.py
```

### **Mensagem não chega no Telegram**
**Verificar:**
1. Usuário bloqueou o bot? → Desbloquear e enviar /start
2. Chat ID correto? → Conferir vinculação
3. Bot ativado? → Verificar checkbox "Ativado" no painel
4. Ver histórico → Checar mensagem de erro

### **Alerta agendado não dispara**
**Verificar:**
1. Servidor Flask está rodando? → Manter rodando
2. Checkbox "Alertas agendados habilitados" marcado?
3. Horário configurado correto?
4. Testar com "Executar Alerta Agora"

---

## 📚 Documentação Completa

Para informações detalhadas, consulte:

- **[README.md](README.md)** - Documentação geral do GALINT (inclui seção "Telegram")
- **[SETUP_AMBIENTE_DEV.md](SETUP_AMBIENTE_DEV.md)** - Setup ambiente desenvolvimento

---

## 🎉 Pronto!

Sistema Telegram totalmente funcional e integrado ao GALINT!

**Em caso de dúvidas:**
1. Consultar [README.md](README.md) (seção "Troubleshooting" e "Telegram")
2. Verificar logs do Flask no terminal
3. Checar histórico de notificações em `/configuracoes/telegram/historico`

**Desenvolvido para GALINT - Sistema de Gestão de Almoxarifado Integrada**  
*Notificações em tempo real para rastreabilidade total de ferramentas* 🔧📱
