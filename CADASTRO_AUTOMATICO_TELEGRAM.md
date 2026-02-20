# 🤖 Cadastro Automático via Bot Telegram

## 📱 Como Funciona o Novo Sistema

Agora o bot **pergunta o nome e a função** do usuário e faz o cadastro **automaticamente**, sem precisar do administrador!

---

## 🎯 Fluxo Completo de Cadastro

### **1️⃣ Usuário Inicia Conversa**

**No Telegram:**
1. Buscar: `@galint_almoxarifado_bot`
2. Clicar em "INICIAR" ou enviar `/start`

**Bot responde:**
```
👋 Olá, João!

Sou o assistente do GALINT - Sistema de Almoxarifado.

Vou te ajudar a se cadastrar automaticamente! 🚀

📝 Por favor, digite seu nome completo:
(exatamente como está cadastrado no sistema)
```

---

### **2️⃣ Usuário Envia Nome**

**Exemplo:** Usuário digita: `João da Silva`

**Bot responde:**
```
✅ Nome registrado: João da Silva

💼 Agora digite sua função/cargo:
(ex: Eletricista, Pedreiro, Auxiliar, Supervisor, etc.)
```

---

### **3️⃣ Usuário Envia Função/Cargo**

**Exemplo:** Usuário digita: `Eletricista`

**Bot busca automaticamente no banco de dados**

---

## ✅ Cenários Possíveis

### **🎉 Cenário 1: CADASTRO AUTOMÁTICO (1 match)**

Se o sistema encontrar **exatamente 1 pessoa** com esse nome e cargo:

```
🎉 Cadastro realizado com sucesso!

✅ Você foi vinculado automaticamente:

👤 Nome: João da Silva
🆔 Matrícula: 0001234567890
💼 Cargo: Eletricista
🏢 Setor: Manutenção

🔔 A partir de agora você receberá:
• Notificações de retirada de materiais
• Lembretes de devolução de ferramentas

✨ Tudo pronto! Não precisa fazer mais nada.
```

**✅ USUÁRIO JÁ ESTÁ CADASTRADO E RECEBENDO NOTIFICAÇÕES!**

---

### **⚠️ Cenário 2: MÚLTIPLOS CADASTROS (2+ matches)**

Se existem várias pessoas com nomes parecidos:

```
⚠️ Encontrei múltiplos cadastros similares:

• João da Silva - Eletricista (Mat: 0001234567890)
• João Silva Santos - Eletricista (Mat: 0009876543210)
• João Pedro Silva - Auxiliar Elétrico (Mat: 0005555444433)

Por favor, entre em contato com o administrador do sistema 
e informe:

🆔 Seu Chat ID: 999888777
📝 Nome: João da Silva
💼 Cargo: Eletricista

O administrador fará a vinculação manual.
```

**→ Administrador acessa `/configuracoes/telegram/` e vincula manualmente**

---

### **❌ Cenário 3: NÃO ENCONTRADO**

Se não existe ninguém cadastrado com esse nome/cargo:

```
❌ Não encontrei seu cadastro no sistema.

Verifique se digitou corretamente:
📝 Nome: João da Silva
💼 Cargo: Eletricista

Se os dados estão corretos, entre em contato com o 
administrador e informe:

🆔 Seu Chat ID: 999888777

💡 Você pode tentar novamente enviando /start
```

**→ Administrador pode:**
- Cadastrar o funcionário no sistema primeiro
- Ou vincular manualmente com o Chat ID

---

## 🔍 Como o Sistema Busca?

### **Busca Inteligente:**

1. **Nome:** busca parcial, não precisa ser exato
   - ✅ "João Silva" encontra "João da Silva Santos"
   - ✅ "Maria" encontra "Maria dos Santos"
   - ✅ Case insensitive: "JOÃO" = "joão" = "João"

2. **Cargo:** também busca parcial
   - ✅ "Eletricista" encontra "Eletricista Predial"
   - ✅ "Pedreiro" encontra "Pedreiro Master"

3. **Match único:** só cadastra automaticamente se encontrar **1 única pessoa**
   - Se encontrar 0 → pede para falar com admin
   - Se encontrar 2+ → mostra lista e pede para falar com admin
   - Se encontrar 1 → **CADASTRA AUTOMATICAMENTE! 🎉**

---

## 🛠️ Comandos Disponíveis

| Comando | O que faz |
|---------|-----------|
| `/start` | Inicia cadastro automático (conversa interativa) |
| `/ajuda` ou `/help` | Mostra ajuda em português |
| `/meuid` | Mostra apenas o Chat ID (para cadastro manual) |

---

## 👨‍💼 Cadastro Manual (Administrador)

**Quando usar:**
- Múltiplos cadastros encontrados
- Nenhum cadastro encontrado
- Usuário prefere não usar o sistema automático

**Como fazer:**

1. **Funcionário envia Chat ID:**
   - Enviar `/meuid` para o bot
   - Copiar o número que aparece

2. **Administrador acessa:**
   - `http://localhost:5000/configuracoes/telegram/`
   - Seção "Usuários Vinculados"
   - Seleciona matrícula do funcionário
   - Cola o Chat ID
   - Clica no botão ➕

---

## 🔄 Usuário Já Cadastrado

Se o usuário já está vinculado e envia `/start`:

```
✅ Você já está cadastrado!

👤 Nome: João da Silva
🆔 Matrícula: 0001234567890
💼 Cargo: Eletricista

🔔 Você já recebe notificações automáticas!
```

**Não cria conversa duplicada nem pede dados novamente.**

---

## 📊 Exemplo Completo de Conversa

```
👤 Usuário: /start

🤖 Bot: Olá! Digite seu nome completo:

👤 Usuário: Maria dos Santos

🤖 Bot: ✅ Nome registrado: Maria dos Santos
         Agora digite sua função/cargo:

👤 Usuário: Auxiliar de Limpeza

🤖 Bot: 🎉 Cadastro realizado com sucesso!
         
         ✅ Você foi vinculado automaticamente:
         
         👤 Nome: Maria dos Santos
         🆔 Matrícula: 0002233445566
         💼 Cargo: Auxiliar de Limpeza
         🏢 Setor: Limpeza
         
         🔔 A partir de agora você receberá:
         • Notificações de retirada de materiais
         • Lembretes de devolução de ferramentas
         
         ✨ Tudo pronto! Não precisa fazer mais nada.
```

---

## 🎯 Vantagens do Sistema Automático

✅ **Rápido:** cadastro em 30 segundos  
✅ **Fácil:** só responder 2 perguntas  
✅ **Automático:** não precisa do administrador  
✅ **Seguro:** só vincula se encontrar match único  
✅ **Inteligente:** busca flexível por nome parcial  
✅ **Confiável:** registra tudo no banco de dados  

---

## ❓ FAQ - Perguntas Frequentes

**P: E se eu errar o nome?**  
R: Envie `/start` novamente que o sistema reseta a conversa.

**P: O nome precisa ser exatamente igual ao cadastro?**  
R: Não! A busca é parcial. "João Silva" encontra "João da Silva Santos".

**P: E se eu não souber meu cargo exato?**  
R: Digite algo parecido (ex: "eletricista", "pedreiro"). Se não der match, o admin vincula manual.

**P: Quanto tempo demora?**  
R: Uns 30 segundos. Duas perguntas e pronto!

**P: Precisa de internet?**  
R: Sim, o Telegram precisa de conexão.

**P: O administrador vê minhas mensagens?**  
R: Não. Só o bot vê. O admin só vê o resultado final do cadastro.

---

## 🔧 Configuração Técnica (Administrador)

### **Tabela Criada:**
- `telegram_conversations` - armazena estado das conversas

### **Estados Possíveis:**
- `awaiting_name` - aguardando nome do usuário
- `awaiting_cargo` - aguardando função/cargo
- `completed` - conversa finalizada

### **Limpeza Automática:**
- Conversas são deletadas após conclusão (sucesso ou erro)
- Comandos `/start` resetam conversas antigas

---

**🚀 Sistema pronto para uso! Divulgue o bot para os funcionários e deixe eles se cadastrarem sozinhos!**
