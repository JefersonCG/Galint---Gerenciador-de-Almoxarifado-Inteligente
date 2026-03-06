# Sistema de Backup com Progresso e Logout Automático

## 🎯 Funcionalidades Implementadas

### 1. **Barra de Progresso em Tempo Real**
- Mostra visualmente o andamento da operação (0-100%)
- Atualização a cada 500ms via polling
- Mensagens descritivas de cada etapa

### 2. **Execução em Background**
- Backup e restauração rodam em threads separadas
- Não bloqueia o servidor durante a operação
- Sistema de tracking via arquivo JSON temporário

### 3. **Logout Automático Após Conclusão**
- Após sucesso, aguarda 2 segundos
- Exibe mensagem "Deslogando..."
- Redireciona automaticamente para tela de login
- **Motivo**: Restauração altera dados críticos do banco; logout garante que sessões antigas não causem inconsistência

### 4. **Feedback Visual Aprimorado**
- ✅ **Sucesso**: Barra verde com mensagem de conclusão
- ❌ **Erro**: Barra vermelha com descrição do problema
- 🔄 **Em andamento**: Barra azul animada

## 🔧 Arquitetura Técnica

### Backend
1. **`BackupService`** (`galint_flask/services/backup.py`)
   - `create_backup_background(operation_id)` - Cria backup em thread
   - `restore_backup_background(operation_id, backup_name)` - Restaura em thread
   - `read_status(operation_id)` - Retorna status atual
   - Callbacks de progresso em pontos-chave (5%, 10%, 20%, 40%, 80%, 100%)

2. **Rotas** (`galint_flask/views/pages.py`)
   - `POST /configuracoes/backup` - Inicia backup, retorna `operation_id`
   - `POST /configuracoes/restaurar` - Inicia restauração, retorna `operation_id`
   - `GET /configuracoes/backup/status/<operation_id>` - Polling de status

### Frontend
1. **Template** (`galint_flask/templates/config_backup.html`)
   - Container de progresso (oculto por padrão)
   - JavaScript para interceptar submits
   - Polling automático a cada 500ms
   - Lógica de logout após sucesso

## 📊 Etapas de Progresso

### Criação de Backup
```
5%   → Preparando backup...
10%  → Localizando pg_dump...
20%  → Conectando ao PostgreSQL...
40%  → Executando pg_dump (exportando dados)...
80%  → Verificando resultado...
100% → Backup concluído!
```

### Restauração de Backup
```
5%   → Preparando restauração...
10%  → Localizando psql...
20%  → Conectando ao PostgreSQL...
40%  → Executando psql (importando dados)...
80%  → Verificando resultado...
100% → Restauração concluída!
```

## 🚀 Como Usar

1. Acesse **Configurações → Backup**
2. Para **criar backup**:
   - Clique em "Gerar backup agora"
   - Acompanhe a barra de progresso
   - Aguarde logout automático
3. Para **restaurar**:
   - Selecione um backup da lista
   - Clique em "Restaurar banco de dados"
   - Confirme a operação
   - Acompanhe a barra de progresso
   - Aguarde logout automático

## 🔐 Segurança

- **Apenas administradores** podem criar/restaurar backups
- Confirmação obrigatória antes de restaurar
- Logout automático previne uso de dados em cache inconsistentes
- Status temporário armazenado em `instance/backup_status_*.json`
- Arquivos de status limpáveis via `BackupService.cleanup_status()`

## ⚙️ Configuração Avançada

### Timeouts
- `GALINT_BACKUP_TIMEOUT_SECONDS` (padrão: 120s) - Timeout do subprocess pg_dump/psql
- `GALINT_PG_CONNECT_TIMEOUT_SECONDS` (padrão: 10s) - Timeout de conexão
- `GALINT_PG_LOCK_TIMEOUT_MS` (padrão: 5000ms) - Timeout de lock
- `GALINT_PG_STATEMENT_TIMEOUT_MS` (padrão: 60000ms) - Timeout de statement

### Polling
- Intervalo atual: 500ms (ajustável no JavaScript)
- Recomendado: 300-1000ms

## 🐛 Troubleshooting

### Operação trava em 40%
- Pode haver lock/sessão idle no Postgres
- Use: `python scripts/terminate_idle_in_tx.py`

### Erro "psql não encontrado"
- Instale PostgreSQL client tools
- Configure `BACKUP_PSQL` com caminho completo

### Barra não atualiza
- Verifique console do navegador (F12)
- Confirme que rota `/configuracoes/backup/status/<id>` está acessível

## 📝 Notas de Desenvolvimento

- Threads daemon: não bloqueiam shutdown do servidor
- Status JSON: formato simples, fácil de estender
- Sem dependências extras (não usa WebSocket/SSE)
- Compatível com qualquer navegador moderno (Fetch API)
