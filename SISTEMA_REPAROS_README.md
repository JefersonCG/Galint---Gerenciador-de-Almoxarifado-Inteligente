# Sistema de Gerenciamento de Equipamentos em Reparo

## 📋 Visão Geral

Sistema completo de gerenciamento de equipamentos enviados para reparo, integrado ao GALINT. Permite rastrear todo o ciclo de vida de um reparo, desde o envio até o retorno, incluindo custos, prazos e fornecedores.

## ✨ Funcionalidades Implementadas

### 1. **Modelo de Dados** (`EquipamentoReparo`)
- Código do item em reparo (foreign key para `itens`)
- Responsável pelo envio (foreign key para `usuarios`)
- Datas: envio, retorno previsto e retorno real
- Problema descrito e solução aplicada
- Fornecedor/oficina responsável
- Custos: estimado e real
- Status do reparo com workflow definido
- Observações e histórico de atualizações

### 2. **Workflow de Status**
```
Aguardando Orçamento → Em Reparo → Concluído
                                 → Sem Conserto
```

**Estados disponíveis:**
- `aguardando_orcamento`: Equipamento aguardando avaliação e orçamento
- `em_reparo`: Reparo em andamento
- `concluido`: Reparo concluído com sucesso
- `sem_conserto`: Equipamento sem possibilidade de conserto

### 3. **Interface de Usuário**

#### **Página Principal** (`/reparos`)
- Dashboard com cards de estatísticas por status
- Filtros: status, busca por código/descrição/fornecedor
- Tabela completa com:
  - Informações do equipamento
  - Status visual (badges coloridos)
  - Dias em reparo (com alertas por cor)
  - Custos (estimado e real)
  - Ações rápidas

#### **Modal de Novo Reparo**
- Preenchimento rápido de dados
- Autocomplete inteligente para código de item
- Campos: código, problema, fornecedor, custo estimado, prazo, observações
- Validação automática

#### **Página de Detalhes** (`/reparos/<id>`)
- Visão completa do reparo
- Timeline de eventos
- Formulários para atualização (apenas admin/supervisor)
- Finalização de reparo com confirmação

### 4. **Integração com Sistema Existente**

#### **Lista de Estoque**
- Botão "Enviado para Reparo" em cada item (categoria Ferramentas/EPI/Material de EP)
- Ao clicar, redireciona para página de reparos com código pré-preenchido
- Modal abre automaticamente

#### **Sidebar**
- Novo link "Equipamentos em Reparo" com ícone de ferramenta
- Posicionado após "Auditar Ferramentas"

### 5. **API REST**

**Endpoints principais:**
- `GET /reparos` - Lista reparos com filtros
- `POST /reparos/novo` - Envia equipamento para reparo
- `GET /reparos/<id>` - Detalhes de um reparo
- `POST /reparos/<id>/atualizar` - Atualiza status e informações
- `POST /reparos/<id>/finalizar` - Finaliza reparo (concluído ou sem conserto)
- `GET /reparos/api/itens/autocomplete` - Autocomplete de itens
- `GET /reparos/api/stats` - Estatísticas de reparos

### 6. **Serviço de Negócio** (`ReparoService`)

**Métodos principais:**
```python
enviar_para_reparo(codigo_item, matricula_responsavel, problema_descrito, ...)
atualizar_status(reparo_id, novo_status, matricula_atualizador, ...)
finalizar_reparo(reparo_id, matricula_atualizador, status_final, ...)
listar_reparos(status=None, codigo_item=None, apenas_abertos=False, limit=100)
get_estatisticas() -> dict
buscar_reparos(termo_busca, limit=50)
```

### 7. **Permissões**
- Qualquer usuário autenticado pode **visualizar** reparos e **enviar** equipamentos
- Apenas **administradores** e **supervisores** podem:
  - Atualizar status de reparos
  - Finalizar reparos
  - Editar informações de custo e solução

## 🗄️ Banco de Dados

### Tabela `equipamentos_reparo`

```sql
CREATE TABLE equipamentos_reparo (
    id SERIAL PRIMARY KEY,
    codigo_item VARCHAR NOT NULL REFERENCES itens(codigo_item),
    matricula_responsavel VARCHAR(100) NOT NULL REFERENCES usuarios(id),
    data_envio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_retorno TIMESTAMP,
    prazo_previsto DATE,
    problema_descrito TEXT NOT NULL,
    solucao_aplicada TEXT,
    fornecedor_oficina VARCHAR(255),
    custo_estimado FLOAT,
    custo_real FLOAT,
    status VARCHAR(30) NOT NULL DEFAULT 'aguardando_orcamento',
    observacoes TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_por VARCHAR(100) REFERENCES usuarios(id)
);
```

**Índices criados:**
- `idx_equipamentos_reparo_codigo_item` (codigo_item)
- `idx_equipamentos_reparo_status` (status)
- `idx_equipamentos_reparo_matricula` (matricula_responsavel)
- `idx_equipamentos_reparo_data_envio` (data_envio DESC)

## 🚀 Como Usar

### 1. Aplicar Migração do Banco de Dados

Execute o script de migração:

```bash
# Ativar ambiente virtual
.\.venv\Scripts\activate

# Aplicar migração
python aplicar_migracao_reparos.py
```

Ou aplique manualmente:

```bash
psql -U seu_usuario -d galint_db -f migrations/add_equipamentos_reparo.sql
```

### 2. Reiniciar o Servidor

```bash
# Parar o servidor (Ctrl+C)
# Iniciar novamente
python app.py
```

### 3. Acessar o Sistema

1. Faça login no GALINT
2. Acesse "Equipamentos em Reparo" no menu lateral
3. Clique em "Enviar para Reparo" para registrar um novo reparo
4. Use os filtros para encontrar reparos específicos
5. Clique em "Ver" para acessar detalhes e atualizar status

### 4. Enviar Item do Estoque para Reparo

1. Acesse "Estoque" no menu
2. Localize o item (Ferramenta/EPI/Material de EP)
3. Clique no botão "Enviado para Reparo" (amarelo)
4. Preencha os dados no modal que abre automaticamente
5. Confirme o envio

## 📊 Exemplos de Uso

### Cenário 1: Enviar Ferramenta para Reparo
1. Furadeira parou de funcionar
2. Operador registra problema: "Motor não liga, cheiro de queimado"
3. Envia para "Oficina ABC" com prazo de 7 dias
4. Status: "Aguardando Orçamento"

### Cenário 2: Atualizar Status (Supervisor)
1. Oficina enviou orçamento: R$ 350,00
2. Supervisor atualiza para "Em Reparo"
3. Adiciona observação: "Aprovado orçamento, prazo confirmado"

### Cenário 3: Finalizar Reparo
1. Equipamento retornou após 5 dias
2. Supervisor finaliza com status "Concluído"
3. Informa solução: "Substituído motor e rolamento"
4. Custo real: R$ 340,00
5. Sistema registra data/hora de retorno automaticamente

## 🎨 Interface Visual

### Cards de Estatísticas
- **Aguardando Orçamento** - Badge amarelo 🟡
- **Em Reparo** - Badge azul 🔵
- **Concluído** - Badge verde 🟢
- **Sem Conserto** - Badge vermelho 🔴

### Indicadores de Tempo
- **0-15 dias** - Badge cinza (normal)
- **16-30 dias** - Badge amarelo (atenção)
- **31+ dias** - Badge vermelho (crítico)

## 🔧 Arquitetura Técnica

### Arquivos Criados/Modificados

**Novos arquivos:**
- `galint_flask/services/reparo_service.py` - Lógica de negócio
- `galint_flask/views/reparo.py` - Rotas HTTP
- `galint_flask/templates/reparo/list.html` - Listagem
- `galint_flask/templates/reparo/detalhes.html` - Detalhes
- `migrations/add_equipamentos_reparo.sql` - Migração SQL
- `aplicar_migracao_reparos.py` - Script de migração

**Arquivos modificados:**
- `galint_flask/models.py` - Adicionado modelo `EquipamentoReparo`
- `galint_flask/views/__init__.py` - Registrado blueprint `reparo`
- `galint_flask/templates/sidebar_layout.html` - Link no menu
- `galint_flask/templates_mako/sidebar_layout.mako` - Link no menu (Mako)
- `galint_flask/templates/inventory/list.html` - Botão "Enviado para Reparo"

### Dependências
- Flask 3.x
- SQLAlchemy (ORM)
- Bootstrap 5 (UI)
- Bootstrap Icons
- PostgreSQL

## 📈 Métricas e Relatórios

O sistema coleta automaticamente:
- Quantidade de reparos por status
- Custo total de reparos
- Tempo médio de reparo
- Reparos em aberto vs. finalizados

**Endpoint de estatísticas:**
```javascript
GET /reparos/api/stats

Resposta:
{
  "total": 45,
  "aguardando_orcamento": 5,
  "em_reparo": 12,
  "concluido": 25,
  "sem_conserto": 3,
  "abertos": 17,
  "custo_total": 15680.50
}
```

## 🔐 Segurança

- Autenticação obrigatória para todos os endpoints
- Permissões diferenciadas (usuário vs admin/supervisor)
- Foreign keys garantem integridade referencial
- Validação de dados no backend e frontend
- Auditoria: quem criou, quem atualizou, quando

## 🚨 Tratamento de Erros

- Validação de campos obrigatórios
- Verificação de existência de itens e usuários
- Rollback automático em caso de falha
- Mensagens de erro amigáveis para o usuário
- Logging de todas as operações

## 🎯 Próximas Melhorias (Sugestões)

1. **Notificações**
   - Alertar supervisor quando prazo estiver próximo
   - Notificar via Telegram quando reparo concluído

2. **Relatórios**
   - Relatório de custos mensais
   - Ranking de fornecedores por prazo/custo
   - Equipamentos mais problemáticos

3. **Anexos**
   - Upload de fotos do problema
   - Anexar orçamentos em PDF
   - Nota fiscal do reparo

4. **Histórico**
   - Rastrear todas as alterações de status
   - Timeline visual com marcos importantes

5. **Dashboard**
   - Gráficos de tendências
   - Comparativo mensal
   - Análise por categoria de equipamento

## 📞 Suporte

Em caso de dúvidas ou problemas:
1. Verifique os logs em `galint_flask/logs/`
2. Consulte este README
3. Revise o código-fonte (bem documentado)

---

**Desenvolvido por:** Engenheiro Sênior
**Data:** 14 de fevereiro de 2026
**Versão:** 1.0.0
