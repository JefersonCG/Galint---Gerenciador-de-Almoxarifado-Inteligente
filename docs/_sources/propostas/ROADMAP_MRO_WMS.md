# ROADMAP: Evolução GALINT para MRO + WMS

> **Documento de Planejamento Estratégico**  
> Evolução do sistema GALINT de Almoxarifado Básico para plataforma completa de **MRO (Manutenção)** e **WMS (Gestão Avançada de Armazém)**

**Data:** 31 de Dezembro de 2025  
**Versão Atual:** 2.0 (Almoxarifado + Telegram + Mobile)  
**Versão Futura:** 3.0 (MRO + WMS Completo)

---

## 📊 Visão Geral da Evolução

### ✅ O que JÁ EXISTE (mantém 100%)

O GALINT atual possui funcionalidades sólidas de gestão de almoxarifado:

| Módulo | Status | Descrição |
|--------|--------|-----------|
| **Gestão de Itens** | ✅ Operacional | Cadastro, edição, exclusão com categorização |
| **Controle de Estoque** | ✅ Operacional | Entradas, saídas, saldo atual, estoque mínimo |
| **Movimentações** | ✅ Operacional | Registro de saídas com observações e devoluções |
| **Produtos Líquidos** | ✅ Operacional | Cálculo por frações (1/4, 1/2, 3/4) com densidade |
| **Usuários e Permissões** | ✅ Operacional | Admin, Padrão, setores com controle de acesso |
| **Relatórios** | ✅ Operacional | PDF, DOCX, XLSX - inventário e movimentações |
| **Materiais Danificados** | ✅ Operacional | Registro de avarias com autorização de descarte |
| **Notificações Telegram** | ✅ Operacional | Alertas de retirada de ferramentas em tempo real |
| **Menu Telegram Interativo** | ✅ Operacional | Menu por perfil (admin/setor) com consultas |
| **Backup Automático** | ✅ Operacional | PostgreSQL via pg_dump com gestão de backups |
| **App Mobile** | ✅ Operacional | React Native + Expo - CRUD de itens |
| **Dashboard** | ✅ Operacional | Indicadores por categoria, gráficos, alertas |
| **Rede Compartilhada** | ✅ Operacional | Link público protegido por token |

**Tecnologias:**
- Python 3.10.0 + Flask 3.0.3
- PostgreSQL + SQLAlchemy 2.0.45
- Telegram Bot API + APScheduler
- React Native (Expo SDK 51)
- Bootstrap 5.3

---

### 🔜 O que será ADICIONADO (funcionalidades futuras)

Expansão para níveis **MRO** (Manutenção) e **WMS** (Warehouse Management System) mantendo toda a base atual intacta.

---

## 🔧 MÓDULO MRO - Gestão de Manutenção

> **MRO:** Maintenance, Repair and Operations - Gestão completa de manutenção de equipamentos e ativos

### Funcionalidades Planejadas

#### 1. Gestão de Ativos/Equipamentos

**Objetivo:** Cadastrar e gerenciar equipamentos que necessitam manutenção

**Implementação:**
```python
# Novo modelo: galint_flask/models.py
class Equipamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    fabricante = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    numero_serie = db.Column(db.String(100))
    data_aquisicao = db.Column(db.Date)
    localizacao = db.Column(db.String(200))
    setor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    categoria_equipamento = db.Column(db.String(50))  # Elétrico, Mecânico, Hidráulico, etc.
    status = db.Column(db.String(20))  # Ativo, Manutenção, Inativo, Descartado
    foto = db.Column(db.String(500))
    documentacao = db.Column(db.Text)  # Manuais, diagramas (JSON)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
```

**Features:**
- ✨ Árvore hierárquica de ativos (Local → Setor → Equipamento → Componente)
- ✨ Upload de manuais e documentação técnica
- ✨ Foto do equipamento
- ✨ QR Code único por equipamento
- ✨ Histórico completo de vida útil

#### 2. Ordens de Serviço (OS)

**Objetivo:** Gerenciar solicitações e execução de manutenções

**Implementação:**
```python
class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_os = db.Column(db.String(50), unique=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamento.id'))
    tipo = db.Column(db.String(20))  # Preventiva, Corretiva, Preditiva
    prioridade = db.Column(db.String(20))  # Baixa, Média, Alta, Crítica
    status = db.Column(db.String(20))  # Aberta, Agendada, Em Andamento, Concluída, Cancelada
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    descricao_problema = db.Column(db.Text)
    descricao_solucao = db.Column(db.Text)
    data_abertura = db.Column(db.DateTime, default=datetime.utcnow)
    data_agendamento = db.Column(db.DateTime)
    data_inicio = db.Column(db.DateTime)
    data_conclusao = db.Column(db.DateTime)
    tempo_parada = db.Column(db.Integer)  # minutos
    custo_estimado = db.Column(db.Numeric(10, 2))
    custo_real = db.Column(db.Numeric(10, 2))
    checklist = db.Column(db.JSON)
```

**Features:**
- ✨ Workflow de aprovação (solicitação → aprovação → execução)
- ✨ Checklist de tarefas por tipo de manutenção
- ✨ Registro de horas trabalhadas
- ✨ Vinculação automática de peças consumidas (integra com estoque atual)
- ✨ Fotos antes/depois
- ✨ Assinatura digital do solicitante e executor
- ✨ Notificações Telegram em cada mudança de status

#### 3. Planos de Manutenção Preventiva

**Objetivo:** Programar manutenções recorrentes automaticamente

**Implementação:**
```python
class PlanoManutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamento.id'))
    nome = db.Column(db.String(200))
    descricao = db.Column(db.Text)
    tipo_periodicidade = db.Column(db.String(20))  # Tempo, Uso
    intervalo_dias = db.Column(db.Integer)
    intervalo_horas_uso = db.Column(db.Integer)
    ultima_execucao = db.Column(db.Date)
    proxima_execucao = db.Column(db.Date)
    ativo = db.Column(db.Boolean, default=True)
    checklist_template = db.Column(db.JSON)
    pecas_necessarias = db.Column(db.JSON)  # Lista de itens do almoxarifado
```

**Features:**
- ✨ Geração automática de OS preventivas
- ✨ Notificação antecipada (7, 3, 1 dia antes)
- ✨ Programação baseada em tempo (dias, semanas, meses)
- ✨ Programação baseada em uso (horas, km, ciclos)
- ✨ Template de checklist reutilizável
- ✨ Reserva automática de peças do almoxarifado

#### 4. Registro de Falhas e Análise

**Implementação:**
```python
class FalhaEquipamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipamento_id = db.Column(db.Integer, db.ForeignKey('equipamento.id'))
    data_falha = db.Column(db.DateTime)
    tipo_falha = db.Column(db.String(50))  # Elétrica, Mecânica, Software, etc.
    gravidade = db.Column(db.String(20))  # Leve, Moderada, Grave, Crítica
    descricao = db.Column(db.Text)
    causa_raiz = db.Column(db.Text)
    acao_corretiva = db.Column(db.Text)
    tempo_parada = db.Column(db.Integer)  # minutos
    custo_parada = db.Column(db.Numeric(10, 2))
```

**Features:**
- ✨ Análise de causa raiz (5 porquês, Ishikawa)
- ✨ Histórico de falhas por equipamento
- ✨ Padrões de falhas (relatórios)

#### 5. KPIs e Dashboards MRO

**Indicadores Calculados:**
- 📊 **MTBF** (Mean Time Between Failures) - Tempo médio entre falhas
- 📊 **MTTR** (Mean Time To Repair) - Tempo médio de reparo
- 📊 **OEE** (Overall Equipment Effectiveness) - Eficiência global do equipamento
- 📊 **Custo de manutenção** por equipamento/período
- 📊 **Taxa preventiva vs corretiva**
- 📊 **Disponibilidade** de equipamentos
- 📊 **Backlog** de OS (abertas vs concluídas)

**Visualizações:**
- 📈 Gráfico de evolução de falhas
- 📈 Mapa de calor de equipamentos críticos
- 📈 Timeline de manutenções realizadas
- 📈 Comparativo custo orçado vs real

---

## 📦 MÓDULO WMS - Warehouse Management System

> **WMS:** Sistema avançado de gestão de armazém com endereçamento, lotes e rastreabilidade

### Funcionalidades Planejadas

#### 1. Sistema de Endereçamento

**Objetivo:** Localização precisa de cada item no almoxarifado

**Implementação:**
```python
class Endereco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True)  # A01-B03-N2-P5
    corredor = db.Column(db.String(10))
    prateleira = db.Column(db.String(10))
    nivel = db.Column(db.String(10))
    posicao = db.Column(db.String(10))
    tipo = db.Column(db.String(20))  # Picking, Estoque, Quarentena, Expedição
    capacidade_peso_kg = db.Column(db.Numeric(10, 2))
    capacidade_volume_m3 = db.Column(db.Numeric(10, 3))
    ocupado = db.Column(db.Boolean, default=False)
    bloqueado = db.Column(db.Boolean, default=False)
    
class ItemEndereco(db.Model):
    """Relacionamento entre Item e Endereço (um item pode estar em vários endereços)"""
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    endereco_id = db.Column(db.Integer, db.ForeignKey('endereco.id'))
    lote_id = db.Column(db.Integer, db.ForeignKey('lote.id'))
    quantidade = db.Column(db.Numeric(10, 3))
    data_entrada = db.Column(db.DateTime, default=datetime.utcnow)
```

**Features:**
- ✨ Nomenclatura padrão: **CORREDOR-PRATELEIRA-NIVEL-POSIÇÃO**
- ✨ Mapa visual 3D do almoxarifado
- ✨ Sugestão automática de endereço no recebimento (otimização)
- ✨ Tipos de endereço (picking rápido, estoque profundo, quarentena)
- ✨ Controle de capacidade (peso e volume)
- ✨ Bloqueio/desbloqueio de posições

#### 2. Controle de Lotes

**Objetivo:** Rastreabilidade completa com número de lote e validade

**Implementação:**
```python
class Lote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_lote = db.Column(db.String(100), unique=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    data_fabricacao = db.Column(db.Date)
    data_validade = db.Column(db.Date)
    fornecedor = db.Column(db.String(200))
    nota_fiscal = db.Column(db.String(50))
    quantidade_original = db.Column(db.Numeric(10, 3))
    quantidade_atual = db.Column(db.Numeric(10, 3))
    status = db.Column(db.String(20))  # Normal, Bloqueado, Vencido, Recall
    observacao = db.Column(db.Text)
```

**Features:**
- ✨ Controle FIFO/FEFO/LIFO configurável por item
- ✨ Alerta automático de vencimento (Telegram)
- ✨ Bloqueio de lote (quarentena)
- ✨ Rastreamento bidirecional (origem → destino)
- ✨ Recall de produtos (notificação massiva)
- ✨ Relatório de produtos próximos ao vencimento

#### 3. Recebimento Estruturado

**Objetivo:** Processo completo desde agendamento até conferência

**Implementação:**
```python
class Recebimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True)
    fornecedor = db.Column(db.String(200))
    nota_fiscal = db.Column(db.String(50))
    data_agendamento = db.Column(db.DateTime)
    data_recebimento = db.Column(db.DateTime)
    status = db.Column(db.String(20))  # Agendado, Em Conferência, Conferido, Armazenado
    usuario_recebimento_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    observacao = db.Column(db.Text)
    
class ItemRecebimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recebimento_id = db.Column(db.Integer, db.ForeignKey('recebimento.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    quantidade_esperada = db.Column(db.Numeric(10, 3))
    quantidade_recebida = db.Column(db.Numeric(10, 3))
    lote_numero = db.Column(db.String(100))
    divergencia = db.Column(db.Boolean, default=False)
    motivo_divergencia = db.Column(db.String(200))
    endereco_id = db.Column(db.Integer, db.ForeignKey('endereco.id'))
```

**Features:**
- ✨ Pré-recebimento (agendamento)
- ✨ Conferência NF vs físico com registro de divergências
- ✨ Inspeção de qualidade (checklist)
- ✨ Impressão automática de etiquetas com código de barras
- ✨ Sugestão de endereço otimizada
- ✨ Foto de carga recebida

#### 4. Movimentações Internas e Picking

**Implementação:**
```python
class TransferenciaInterna(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    lote_id = db.Column(db.Integer, db.ForeignKey('lote.id'))
    endereco_origem_id = db.Column(db.Integer, db.ForeignKey('endereco.id'))
    endereco_destino_id = db.Column(db.Integer, db.ForeignKey('endereco.id'))
    quantidade = db.Column(db.Numeric(10, 3))
    motivo = db.Column(db.String(100))  # Reabastecimento, Reorganização, etc.
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    data_transferencia = db.Column(db.DateTime, default=datetime.utcnow)

class Separacao(db.Model):
    """Picking - separação de itens para saída"""
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    separador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    status = db.Column(db.String(20))  # Pendente, Em Separação, Conferida, Expedida
    prioridade = db.Column(db.String(20))
    data_solicitacao = db.Column(db.DateTime)
    data_inicio_separacao = db.Column(db.DateTime)
    data_conclusao = db.Column(db.DateTime)
    rota_sugerida = db.Column(db.JSON)  # Sequência otimizada de endereços
```

**Features:**
- ✨ Roteirização automática (caminho mais curto)
- ✨ Picking guiado por app mobile (endereço → endereço)
- ✨ Wave picking (consolidação de pedidos)
- ✨ Conferência com código de barras
- ✨ Reabastecimento automático (ponto de pedido por endereço)

#### 5. Inventário Cíclico

**Objetivo:** Contagens programadas sem parar operação

**Implementação:**
```python
class InventarioCiclico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True)
    data_programada = db.Column(db.Date)
    tipo = db.Column(db.String(20))  # Por Endereço, Por Categoria, Curva ABC
    status = db.Column(db.String(20))  # Agendado, Em Contagem, Recontagem, Concluído
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    
class ContagemInventario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario_ciclico.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    endereco_id = db.Column(db.Integer, db.ForeignKey('endereco.id'))
    lote_id = db.Column(db.Integer, db.ForeignKey('lote.id'))
    quantidade_sistema = db.Column(db.Numeric(10, 3))
    quantidade_contada = db.Column(db.Numeric(10, 3))
    divergencia = db.Column(db.Numeric(10, 3))
    contador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    data_contagem = db.Column(db.DateTime)
    recontagem = db.Column(db.Boolean, default=False)
```

**Features:**
- ✨ Programação automática por curva ABC
- ✨ Contagem por endereço (blind count - sem ver sistema)
- ✨ Processo de recontagem automático para divergências >5%
- ✨ Ajuste de estoque com auditoria
- ✨ Acurácia de inventário (KPI)
- ✨ App mobile para contagem offline

#### 6. Serialização e Rastreamento

**Implementação:**
```python
class Serial(db.Model):
    """Para itens que necessitam controle individual (ferramentas, equipamentos)"""
    id = db.Column(db.Integer, primary_key=True)
    numero_serie = db.Column(db.String(100), unique=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'))
    lote_id = db.Column(db.Integer, db.ForeignKey('lote.id'))
    endereco_id = db.Column(db.Integer, db.ForeignKey('endereco.id'))
    status = db.Column(db.String(20))  # Disponível, Em Uso, Manutenção, Baixado
    usuario_atual_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    data_ultima_movimentacao = db.Column(db.DateTime)
```

**Features:**
- ✨ Número de série único por unidade
- ✨ Rastreamento individual (quem está usando agora)
- ✨ Histórico completo de movimentações
- ✨ Integração com notificações de ferramentas (já existe)

#### 7. Indicadores WMS

**KPIs Calculados:**
- 📊 **Acurácia de inventário** (%)
- 📊 **Giro de estoque** (turnover) por item/categoria
- 📊 **Tempo médio de recebimento**
- 📊 **Tempo médio de separação** (picking)
- 📊 **Taxa de ocupação** do armazém (%)
- 📊 **Curva ABC** dinâmica
- 📊 **Itens sem movimentação** (slow-moving)
- 📊 **Taxa de avarias** no recebimento

---

## 🚀 Roadmap de Implementação

### **FASE 1: Fundação WMS (3 meses)**

**Prioridade: Alta**

| Sprint | Funcionalidade | Esforço | Status |
|--------|----------------|---------|--------|
| 1.1 | Sistema de Endereçamento | 2 semanas | 🔜 Planejado |
| 1.2 | Controle de Lotes | 2 semanas | 🔜 Planejado |
| 1.3 | Recebimento Estruturado | 2 semanas | 🔜 Planejado |
| 1.4 | Transferências Internas | 1 semana | 🔜 Planejado |
| 1.5 | Inventário Cíclico | 3 semanas | 🔜 Planejado |
| 1.6 | Dashboards WMS | 2 semanas | 🔜 Planejado |

**Entregáveis:**
- ✅ Modelos de dados WMS
- ✅ Telas de cadastro de endereços
- ✅ Processo de recebimento completo
- ✅ Tela de inventário cíclico
- ✅ Relatórios WMS

---

### **FASE 2: MRO Básico (3 meses)**

**Prioridade: Alta**

| Sprint | Funcionalidade | Esforço | Status |
|--------|----------------|---------|--------|
| 2.1 | Cadastro de Equipamentos | 2 semanas | 🔜 Planejado |
| 2.2 | Ordens de Serviço | 3 semanas | 🔜 Planejado |
| 2.3 | Workflow de Aprovação | 2 semanas | 🔜 Planejado |
| 2.4 | Planos de Manutenção | 2 semanas | 🔜 Planejado |
| 2.5 | Registro de Falhas | 1 semana | 🔜 Planejado |
| 2.6 | Dashboards MRO | 2 semanas | 🔜 Planejado |

**Entregáveis:**
- ✅ Modelos de dados MRO
- ✅ Telas de gestão de equipamentos
- ✅ Processo completo de OS
- ✅ Planos preventivos com geração automática
- ✅ KPIs MRO (MTBF, MTTR, OEE)

---

### **FASE 3: Mobilidade Avançada (2 meses)**

**Prioridade: Média**

| Sprint | Funcionalidade | Esforço | Status |
|--------|----------------|---------|--------|
| 3.1 | App: Recebimento com Barcode | 2 semanas | 🔜 Planejado |
| 3.2 | App: Picking Guiado | 2 semanas | 🔜 Planejado |
| 3.3 | App: Inventário Offline | 2 semanas | 🔜 Planejado |
| 3.4 | App: OS em Campo | 2 semanas | 🔜 Planejado |

**Entregáveis:**
- ✅ Módulo WMS no app mobile
- ✅ Módulo MRO no app mobile
- ✅ Sincronização offline
- ✅ Câmera para QR Code e código de barras

---

### **FASE 4: Integrações e APIs (2 meses)**

**Prioridade: Média**

| Sprint | Funcionalidade | Esforço | Status |
|--------|----------------|---------|--------|
| 4.1 | API REST Completa | 3 semanas | 🔜 Planejado |
| 4.2 | Webhooks | 1 semana | 🔜 Planejado |
| 4.3 | Integração ERP (SAP, TOTVS) | 3 semanas | 🔜 Planejado |
| 4.4 | Exportação BI (Power BI, Superset) | 1 semana | 🔜 Planejado |

**Entregáveis:**
- ✅ Documentação Swagger/OpenAPI
- ✅ Endpoints RESTful completos
- ✅ Autenticação JWT
- ✅ Webhook de eventos

---

### **FASE 5: Automação e IA (3 meses)**

**Prioridade: Baixa (futuro)**

| Sprint | Funcionalidade | Esforço | Status |
|--------|----------------|---------|--------|
| 5.1 | Previsão de Demanda (ML) | 3 semanas | 🔮 Futuro |
| 5.2 | Previsão de Falhas (ML) | 3 semanas | 🔮 Futuro |
| 5.3 | Otimização de Rotas (IA) | 2 semanas | 🔮 Futuro |
| 5.4 | Chatbot Telegram Avançado | 2 semanas | 🔮 Futuro |
| 5.5 | IoT - Sensores de Equipamentos | 2 semanas | 🔮 Futuro |

**Entregáveis:**
- ✅ Modelos de Machine Learning
- ✅ Dashboard preditivo
- ✅ Alertas proativos

---

## 📐 Arquitetura da Expansão

### Estrutura de Diretórios (nova organização)

```
GALINT_FLASK_COPIA_FULL_20251231_085800/
│
├── galint_flask/
│   ├── __init__.py                 # ✅ Mantém (factory)
│   ├── models.py                   # 🔄 Expande (novos models)
│   ├── config.py                   # ✅ Mantém
│   ├── extensions.py               # ✅ Mantém
│   │
│   ├── views/                      # Rotas Flask
│   │   ├── __init__.py             # ✅ Mantém
│   │   ├── items.py                # ✅ Mantém (atual)
│   │   ├── saidas.py               # ✅ Mantém (atual)
│   │   ├── entradas.py             # ✅ Mantém (atual)
│   │   ├── users.py                # ✅ Mantém (atual)
│   │   ├── reports.py              # ✅ Mantém (atual)
│   │   ├── mro.py                  # 🆕 NOVO - Módulo MRO
│   │   ├── os.py                   # 🆕 NOVO - Ordens de Serviço
│   │   ├── equipamentos.py         # 🆕 NOVO - Gestão de Ativos
│   │   ├── wms.py                  # 🆕 NOVO - WMS Principal
│   │   ├── enderecos.py            # 🆕 NOVO - Endereçamento
│   │   ├── lotes.py                # 🆕 NOVO - Controle de Lotes
│   │   ├── recebimento.py          # 🆕 NOVO - Recebimento
│   │   ├── picking.py              # 🆕 NOVO - Separação
│   │   └── inventario.py           # 🆕 NOVO - Inventário Cíclico
│   │
│   ├── services/                   # Lógica de negócio
│   │   ├── telegram_service.py     # ✅ Mantém (atual)
│   │   ├── notification_service.py # ✅ Mantém (atual)
│   │   ├── scheduler_service.py    # ✅ Mantém (atual)
│   │   ├── mro_service.py          # 🆕 NOVO - Lógica MRO
│   │   ├── os_service.py           # 🆕 NOVO - Gestão de OS
│   │   ├── wms_service.py          # 🆕 NOVO - Lógica WMS
│   │   ├── endereco_service.py     # 🆕 NOVO - Sugestão de endereço
│   │   ├── lote_service.py         # 🆕 NOVO - FIFO/FEFO
│   │   └── inventario_service.py   # 🆕 NOVO - Contagens
│   │
│   ├── api/                        # 🆕 NOVO - API REST
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── items.py
│   │   │   ├── mro.py
│   │   │   ├── wms.py
│   │   │   └── auth.py
│   │   └── schemas.py
│   │
│   ├── templates/                  # Templates Jinja2
│   │   ├── base.html               # ✅ Mantém
│   │   ├── mro/                    # 🆕 NOVO
│   │   │   ├── equipamentos.html
│   │   │   ├── os_lista.html
│   │   │   ├── os_form.html
│   │   │   └── dashboard_mro.html
│   │   └── wms/                    # 🆕 NOVO
│   │       ├── enderecos.html
│   │       ├── lotes.html
│   │       ├── recebimento.html
│   │       ├── picking.html
│   │       └── dashboard_wms.html
│   │
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   │   ├── mro.js              # 🆕 NOVO
│   │   │   └── wms.js              # 🆕 NOVO
│   │   └── img/
│   │
│   └── migrations/                 # Alembic
│       └── versions/
│           ├── xxx_initial.py      # ✅ Existe
│           ├── xxx_add_mro.py      # 🆕 NOVO
│           └── xxx_add_wms.py      # 🆕 NOVO
│
├── galint-mobile/                  # React Native
│   ├── src/
│   │   ├── screens/
│   │   │   ├── mro/                # 🆕 NOVO
│   │   │   │   ├── OSListScreen.js
│   │   │   │   └── OSFormScreen.js
│   │   │   └── wms/                # 🆕 NOVO
│   │   │       ├── PickingScreen.js
│   │   │       ├── InventoryScreen.js
│   │   │       └── ReceivingScreen.js
│   │   └── services/
│   │       ├── mroApi.js           # 🆕 NOVO
│   │       └── wmsApi.js           # 🆕 NOVO
│   │
│   └── package.json                # 🔄 Adiciona dependências
│
├── scripts/
│   ├── generate_test_data_mro.py   # 🆕 NOVO
│   └── generate_test_data_wms.py   # 🆕 NOVO
│
├── requirements.txt                # 🔄 Adiciona dependências
├── README.md                       # 🔄 Atualiza
└── ROADMAP_MRO_WMS.md              # 🆕 NOVO (este arquivo)
```

---

## 🔌 Novas Dependências

### Backend (adicionar ao `requirements.txt`)

```txt
# IA e Machine Learning (Fase 5)
scikit-learn==1.3.0
pandas==2.1.0
numpy==1.24.0

# Tarefas Assíncronas
celery==5.3.0
redis==5.0.0

# API REST Avançada
flask-restx==1.1.0
marshmallow==3.20.0
apispec==6.3.0

# Geração de Códigos de Barras (adicional)
python-zpl==0.1.0  # Impressoras Zebra
reportlab==4.4.7  # Já existe

# Otimização de Rotas
networkx==3.1
```

### Frontend Mobile (adicionar ao `package.json`)

```json
{
  "dependencies": {
    "expo-barcode-scanner": "~13.0.0",
    "expo-camera": "~15.0.0",
    "react-native-qrcode-svg": "^6.2.0",
    "react-native-maps": "^1.7.1"
  }
}
```

---

## 💾 Migração de Dados

### Estratégia de Migração

**Princípio:** Zero downtime, dados existentes intactos

1. **Modelos Novos**
   - Criados via migrations Alembic
   - Não afetam tabelas existentes

2. **Modelos Expandidos**
   - Adicionar colunas via `ALTER TABLE`
   - Valores default para registros antigos
   - Exemplo:
   ```sql
   ALTER TABLE item ADD COLUMN endereco_principal_id INTEGER;
   ALTER TABLE item ADD COLUMN controle_lote BOOLEAN DEFAULT FALSE;
   ```

3. **Dados de Teste**
   - Scripts Python para popular:
     - Endereços fictícios
     - Equipamentos de exemplo
     - OS de teste

---

## 📊 Estimativa de Esforço Total

| Fase | Duração | Complexidade | Equipe Sugerida |
|------|---------|--------------|-----------------|
| Fase 1: WMS Base | 3 meses | Alta | 2 devs backend + 1 frontend |
| Fase 2: MRO Base | 3 meses | Alta | 2 devs backend + 1 frontend |
| Fase 3: Mobile | 2 meses | Média | 1 dev mobile |
| Fase 4: APIs | 2 meses | Média | 1 dev backend + 1 analista |
| Fase 5: IA/IoT | 3 meses | Muito Alta | 1 dev IA + 1 dev IoT |
| **TOTAL** | **13 meses** | - | **Equipe completa** |

**Estimativa com 1 desenvolvedor fullstack:** 18-24 meses

---

## 🎯 Critérios de Sucesso

### KPIs do Projeto

| Métrica | Meta |
|---------|------|
| **Acurácia de Inventário** | > 98% |
| **Redução de tempo de picking** | -30% |
| **Disponibilidade de Equipamentos** | > 95% |
| **Taxa de Manutenção Preventiva** | > 70% |
| **MTTR (Tempo Médio de Reparo)** | < 2 horas |
| **Ocupação do Armazém** | 75-85% |
| **Adoção por Usuários** | > 90% |
| **Satisfação (NPS)** | > 8.0 |

---

## 🛡️ Compatibilidade e Garantias

### ✅ Garantias de Compatibilidade

1. **Zero Breaking Changes**
   - Toda funcionalidade atual permanece funcionando
   - Usuários não são forçados a usar novos módulos
   - Rotas antigas mantidas (backward compatibility)

2. **Migração Gradual**
   - MRO e WMS são **opcionais**
   - Ativação por configuração (feature flags)
   - Treinamento antes do rollout

3. **Rollback Seguro**
   - Cada fase tem ponto de rollback
   - Backups automáticos antes de migrations
   - Logs detalhados de todas mudanças

4. **Testes**
   - Cobertura de testes > 80%
   - Testes de regressão obrigatórios
   - Ambiente de homologação separado

---

## 📞 Próximos Passos Sugeridos

### Ações Imediatas

1. **Validação de Requisitos**
   - [ ] Entrevistas com usuários-chave
   - [ ] Mapear processos atuais de manutenção
   - [ ] Levantar necessidades específicas de WMS

2. **Prototipação**
   - [ ] Mockups de telas MRO
   - [ ] Mockups de telas WMS
   - [ ] Aprovação do layout

3. **Preparação Técnica**
   - [ ] Setup de ambiente de desenvolvimento
   - [ ] Definição de convenções de código
   - [ ] Pipeline CI/CD

4. **Planejamento Detalhado**
   - [ ] Sprint planning (Fase 1)
   - [ ] Definição de user stories
   - [ ] Estimativa refinada

---

## 📚 Referências e Normas

- **ISO 55000** - Gestão de Ativos
- **ISO 9001** - Gestão da Qualidade
- **NBR 5462** - Confiabilidade e Manutenabilidade
- **CMMS Best Practices** - Guia de melhores práticas
- **WMS Implementation Guide** - Metodologia de implantação

---

## 📝 Controle de Versões deste Documento

| Versão | Data | Autor | Mudanças |
|--------|------|-------|----------|
| 1.0 | 31/12/2025 | Sistema | Documento inicial de roadmap |

---

**Documento Vivo:** Este roadmap será atualizado conforme o projeto evolui.

---

> **Nota:** Este é um planejamento estratégico. A implementação real dependerá de:
> - Prioridades de negócio
> - Disponibilidade de recursos
> - Feedback de usuários
> - Validação técnica durante desenvolvimento

**Para discutir qualquer aspecto deste roadmap, entre em contato com a equipe de desenvolvimento.**
