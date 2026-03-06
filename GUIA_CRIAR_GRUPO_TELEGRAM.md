# Guia: Como Criar Grupo do Telegram para Notificações GALINT

## Problema Resolvido
Atualmente, cada retirada está gerando 7 notificações (uma para cada usuário privilegiado).
Com um grupo, haverá apenas 1 notificação compartilhada por todos.

## Passo a Passo

### 1. Criar o Grupo no Telegram

1. Abra o Telegram
2. Clique em "Menu" (três linhas) → "Novo Grupo"
3. Nome sugerido: **"GALINT - Notificações"** ou **"Almoxarifado - Notificações"**
4. Adicione os membros que devem receber as notificações
5. Crie o grupo

### 2. Adicionar o Bot GALINT ao Grupo

1. No grupo recém-criado, clique em "Adicionar membros"
2. Procure pelo bot GALINT (nome do seu bot)
3. Adicione o bot ao grupo
4. **IMPORTANTE**: Torne o bot ADMINISTRADOR do grupo
   - Vá em Configurações do Grupo → Administradores
   - Adicione o bot como administrador
   - Dê permissão de "Enviar Mensagens"

### 3. Obter o chat_id do Grupo

Execute este script Python para descobrir o chat_id do grupo:

```bash
python scripts/get_telegram_group_id.py
```

O script mostrará o chat_id do grupo (será um número negativo, ex: -1001234567890)

### 4. Cadastrar o Grupo no Sistema

Acesse o sistema web GALINT:

1. Vá em **Configurações** → **Telegram** → **Grupos**
2. Clique em "Adicionar Grupo"
3. Preencha:
   - **Chat ID**: Cole o ID obtido no passo 3 (número negativo)
   - **Nome**: "Notificações Almoxarifado" (ou o nome que preferir)
   - **Descrição**: "Grupo para notificações de retiradas e alertas"
   - **Habilitado**: ✅ Sim
   - **Receber Retiradas**: ✅ Sim
   - **Receber Alertas**: ✅ Sim
4. Salve

### 5. Testar

Faça uma retirada de teste. Você verá:
- **ANTES**: 7 notificações individuais
- **DEPOIS**: 1 notificação no grupo

## Resultado Esperado

✅ **1 mensagem no grupo** ao invés de 7 mensagens individuais
✅ Todos os membros do grupo verão a mesma mensagem
✅ Redução drástica no número de notificações
✅ Histórico centrali organizado em um só lugar

## Outras Opções (menos recomendadas)

### Opção 2: Remover privilégios de alguns usuários

Se você não quiser que alguns usuários recebam todas as notificações:

1. Acesse o banco de dados ou sistema de usuários
2. Para usuários que não precisam receber TODAS as retiradas:
   - Remover `is_admin=1` OU
   - Alterar setor/cargo para não conter "SUPERVISOR" ou "ZELADOR"

### Opção 3: Desabilitar notificações de supervisão (não recomendado)

No sistema web:
1. Configurações → Telegram
2. Desmarcar "Notificar Supervisores"
3. **Desvantagem**: Ninguém receberá notificações de supervisão

---

**Recomendação Final**: Use a **Opção 1** (criar grupo). É a solução mais profissional e organizada!
