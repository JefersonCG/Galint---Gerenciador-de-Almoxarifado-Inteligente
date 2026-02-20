# 🏷️ SISTEMA DE CÓDIGO PATRIMONIAL - IMPLEMENTAÇÃO COMPLETA

## ✅ Status: IMPLEMENTADO E FUNCIONAL

---

## 📋 Visão Geral

Sistema de rastreamento patrimonial com relacionamento **1-para-muitos** entre itens e códigos patrimoniais.

### Conceito

```
1 Item (EAN/SKU) → MÚLTIPLOS Códigos Patrimoniais (unidades físicas)

Exemplo:
  Item: Furadeira Bosch 7891234567890
    ├── PAT-001 (disponível)
    ├── PAT-002 (em uso - João Silva)
    ├── PAT-003 (manutenção)
    ├── ...
    └── PAT-020 (disponível)
```

---

## 🗄️ Estrutura do Banco de Dados

### Tabela: `patrimonio_ferramentas`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER PK | Identificador único |
| `codigo_patrimonial` | VARCHAR(100) UNIQUE | Código patrimonial (ex: PAT-001) |
| `codigo_item` | VARCHAR(50) FK | Referência ao item (EAN/SKU) |
| `status` | VARCHAR(20) | disponivel \| em_uso \| manutencao \| baixado |
| `matricula` | VARCHAR(20) FK | Usuário atual (se em_uso) |
| `data_criacao` | TIMESTAMP | Data de criação do código |
| `observacao` | TEXT | Observações adicionais |

**Índices criados:**
- `idx_patrimonio_codigo_item` - Busca por item
- `idx_patrimonio_status` - Filtro por status
- `idx_patrimonio_matricula` - Busca por usuário
- `idx_patrimonio_codigo` - Busca por código patrimonial

### Tabela: `ferramentas_em_uso` (histórico)

Mantida para rastreamento completo de uso ao longo do tempo.

---

## 🔧 Arquivos Criados/Modificados

### 1. Migração do Banco
- **Arquivo:** `scripts/migrate_patrimonio_correto.py`
- **Função:** Remove campo `codigo_patrimonial` da tabela `itens` e cria tabela `patrimonio_ferramentas`
- **Como usar:**
  ```bash
  .\.venv\Scripts\python.exe scripts/migrate_patrimonio_correto.py
  ```

### 2. Modelos (models.py)
- **Modificado:** Removido campo `codigo_patrimonial` da classe `Item`
- **Adicionado:** Nova classe `PatrimonioFerramenta` com relacionamento correto
- **Mantido:** Classe `FerramentaEmUso` para histórico

### 3. Serviço de Gestão
- **Arquivo:** `galint_flask/services/patrimonio_service.py`
- **Classe:** `PatrimonioService`

#### Métodos Disponíveis:

```python
# Adicionar códigos em lote
PatrimonioService.adicionar_codigos_lote(
    codigo_item='7891234567890',
    prefixo='PAT',
    quantidade=20,
    numero_inicial=1
)
# Gera: PAT-001, PAT-002, ..., PAT-020

# Listar disponíveis
codigos = PatrimonioService.listar_disponiveis('7891234567890')

# Listar todos (qualquer status)
todos = PatrimonioService.listar_todos('7891234567890')

# Atribuir a usuário
PatrimonioService.atribuir_a_usuario('PAT-005', '12345')

# Devolver
PatrimonioService.devolver('PAT-005')

# Histórico de uso
historico = PatrimonioService.historico_uso('PAT-005')

# Estatísticas
stats = PatrimonioService.estatisticas_item('7891234567890')
# Retorna: {total: 20, disponivel: 15, em_uso: 3, manutencao: 2, baixado: 0}

# Alterar status
PatrimonioService.alterar_status('PAT-001', 'manutencao', 'Motor queimado')

# Deletar código
PatrimonioService.deletar_codigo('PAT-999')  # Só se não estiver em uso
```

### 4. Views/Rotas
- **Arquivo:** `galint_flask/views/patrimonio.py`
- **Blueprint:** `/patrimonio`

#### Rotas Disponíveis:

| Rota | Método | Descrição |
|------|--------|-----------|
| `/patrimonio/item/<codigo_item>` | GET | Lista todos códigos do item |
| `/patrimonio/adicionar-lote` | POST | Adiciona códigos em lote |
| `/patrimonio/disponiveis/<codigo_item>` | GET | API: códigos disponíveis |
| `/patrimonio/atribuir` | POST | Atribui código a usuário |
| `/patrimonio/devolver` | POST | Devolve código |
| `/patrimonio/historico/<codigo>` | GET | Histórico completo |
| `/patrimonio/alterar-status` | POST | Altera status |
| `/patrimonio/deletar/<codigo>` | DELETE | Remove código |
| `/patrimonio/buscar/<codigo>` | GET | API: busca código |
| `/patrimonio/estatisticas/<codigo_item>` | GET | API: estatísticas |

### 5. Templates HTML

#### 5.1. Lista de Códigos
- **Arquivo:** `galint_flask/templates/patrimonio/listar.html`
- **Acesso:** Via `/patrimonio/item/<codigo_item>`
- **Recursos:**
  - Cards de estatísticas (Total, Disponível, Em Uso, Manutenção)
  - Tabela completa de códigos com filtros
  - Modal para adicionar códigos em lote
  - Ações: Ver histórico, Alterar status, Deletar

#### 5.2. Histórico de Uso
- **Arquivo:** `galint_flask/templates/patrimonio/historico.html`
- **Acesso:** Via `/patrimonio/historico/<codigo_patrimonial>`
- **Recursos:**
  - Timeline visual de uso
  - Quem usou, quando retirou, quando devolveu
  - Status atual do código

---

## 🚀 Como Usar

### Passo 1: Executar Migração

```bash
.\.venv\Scripts\python.exe scripts/migrate_patrimonio_correto.py
```

### Passo 2: Cadastrar Item (Normal)

Cadastre o item normalmente no sistema (ex: Furadeira Bosch, código 7891234567890).

### Passo 3: Adicionar Códigos Patrimoniais

1. Acesse: `/patrimonio/item/7891234567890`
2. Clique em "Adicionar Códigos em Lote"
3. Preencha:
   - **Prefixo:** PAT
   - **Número Inicial:** 1
   - **Quantidade:** 20
4. Salve → Sistema cria PAT-001 a PAT-020

### Passo 4: Retirada de Ferramenta

Quando um colaborador retirar:

```python
# No código de saída, após registrar a saída:
PatrimonioService.atribuir_a_usuario('PAT-005', matricula_colaborador)
```

### Passo 5: Devolução

Quando devolver:

```python
PatrimonioService.devolver('PAT-005')
```

---

## 🎯 Fluxo Completo de Uso

### Cenário Real: 20 Furadeiras Bosch

```
1. ENTRADA NO ESTOQUE
   ├─ Cadastrar item: Furadeira Bosch (7891234567890)
   ├─ Registrar entrada: 20 unidades
   └─ Criar códigos patrimoniais: PAT-001 a PAT-020

2. RETIRADA (João Silva)
   ├─ João retira 1 furadeira
   ├─ Sistema mostra códigos disponíveis
   ├─ Selecionar: PAT-005
   └─ Status: PAT-005 = em_uso (João Silva)

3. DURANTE O USO
   ├─ Consultar: Quem está com PAT-005? → João Silva
   ├─ Consultar: João tem quais ferramentas? → PAT-005, PAT-012
   └─ Histórico de PAT-005: Usado por João desde 05/02/2026

4. DEVOLUÇÃO
   ├─ João devolve PAT-005
   ├─ Status: PAT-005 = disponivel
   └─ Histórico atualizado: Usado por João de 05/02 a 08/02

5. MANUTENÇÃO
   ├─ PAT-003 apresenta defeito
   ├─ Alterar status: manutencao
   └─ Observação: "Motor queimado - enviar para reparo"

6. RELATÓRIOS
   ├─ Estatísticas do item:
   │   ├─ Total: 20
   │   ├─ Disponível: 15
   │   ├─ Em uso: 3
   │   ├─ Manutenção: 2
   │   └─ Baixado: 0
   └─ Histórico de cada unidade individual
```

---

## 📊 Benefícios da Implementação

### ✅ Rastreabilidade Total
- Cada unidade física tem código único
- Histórico completo de quem usou, quando e por quanto tempo
- Identificação de unidades problemáticas (sempre em manutenção)

### ✅ Controle Preciso
- Sabe exatamente onde está cada unidade
- Controle de quantas ferramentas cada colaborador tem
- Identificação de perdas/extravios

### ✅ Manutenção Facilitada
- Marca unidades específicas como "em manutenção"
- Rastreia histórico de problemas por unidade
- Decisão de quando baixar patrimônio

### ✅ Relatórios Gerenciais
- Taxa de utilização por ferramenta
- Colaboradores que mais usam cada tipo
- Tempo médio de uso
- Ferramentas subutilizadas

---

## 🔗 Integração com Sistema Existente

### Compatibilidade

O sistema patrimonial **NÃO quebra** funcionalidades existentes:

- ✅ Entradas continuam funcionando normalmente
- ✅ Saídas sem código patrimonial continuam funcionando
- ✅ Relatórios existentes não são afetados

### Uso Opcional

O sistema patrimonial é **OPCIONAL**:
- Itens sem códigos patrimoniais funcionam normalmente
- Apenas ferramentas que precisam de rastreamento individual usam códigos

---

## 🛠️ Próximas Melhorias Sugeridas

1. **Interface de Saída Integrada**
   - Ao registrar saída de ferramenta, mostrar códigos disponíveis
   - Selecionar código patrimonial específico
   - Atribuir automaticamente ao colaborador

2. **Alertas de Devolução**
   - Notificar colaborador se ferramenta não devolvida em X dias
   - Enviar lembretes via Telegram

3. **Relatórios Avançados**
   - PDF de histórico por código patrimonial
   - Relatório de ferramentas não devolvidas
   - Ranking de colaboradores por tempo de uso

4. **QR Code por Unidade**
   - Gerar QR Code para cada código patrimonial
   - Facilitar identificação física da ferramenta

5. **App Mobile**
   - Leitura de QR Code para retirada/devolução
   - Consulta rápida de status

---

## 📝 Notas Técnicas

### Banco de Dados
- Sistema funciona com **PostgreSQL** e **SQLite**
- Usa dialect detection para SQL compatível
- Transações com rollback automático em caso de erro

### Performance
- Índices criados para otimizar consultas frequentes
- Queries otimizadas com joins apropriados
- Cache pode ser adicionado no futuro

### Segurança
- Login obrigatório em todas as rotas (`@login_required`)
- Validação de dados em todos os endpoints
- Proteção contra SQL injection (SQLAlchemy ORM)

---

## ✨ Resumo

Sistema **COMPLETO e FUNCIONAL** de gestão patrimonial com:
- ✅ Banco de dados migrado
- ✅ Modelos atualizados
- ✅ Serviço de gestão completo
- ✅ Rotas e APIs funcionais
- ✅ Interfaces web profissionais
- ✅ Documentação completa

**Pronto para produção! 🚀**
