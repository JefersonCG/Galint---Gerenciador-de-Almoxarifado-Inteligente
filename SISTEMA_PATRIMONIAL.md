# 🔧 Sistema de Controle Patrimonial de Ferramentas - GALINT

## Visão Geral

O sistema GALINT agora possui um **controle patrimonial completo** para ferramentas, permitindo rastreabilidade total através de dois códigos independentes:

### 📊 Duplo Sistema de Código de Barras

1. **Código Original (EAN/Fábrica)**
   - Código de barras que vem do fabricante
   - Campo: `codigo_item` (código principal do item)
   - Uso: Identificação padrão, leitura por scanner
   - Exemplo: `7891234567890`

2. **Código Patrimonial/Interno** ⭐ NOVO
   - Etiqueta patrimonial interna da empresa
   - Campo: `codigo_patrimonial` (único no sistema)
   - Uso: Controle interno, rastreabilidade por colaborador
   - Exemplo: `PAT-001`, `FERR-2024-001`, `PARAF-123`

## Funcionalidades Implementadas

### ✅ 1. Cadastro de Ferramentas com Duplo Código

**Formulário de Cadastro** - [galint_flask/templates/inventory/form.html](galint_flask/templates/inventory/form.html#L508-L523)

Quando a categoria "Ferramentas" é selecionada:
- ☑️ Checkbox "Adicionar número de série e modelo"
- Campo **Número de Série** - Código do fabricante
- Campo **Código Patrimonial/Interno** ⭐ - Etiqueta interna (único)
- Campo **Modelo** - Modelo/versão do equipamento

**Características**:
- Código patrimonial é **único** no sistema (não pode repetir)
- Validação automática ao salvar
- Interface destacada (azul, monospace, negrito)
- Campos opcionais mas recomendados para ferramentas

### ✅ 2. Banco de Dados Atualizado

**Tabela: `itens`**
```sql
ALTER TABLE itens 
ADD COLUMN codigo_patrimonial VARCHAR(100) UNIQUE;
CREATE INDEX idx_itens_codigo_patrimonial ON itens(codigo_patrimonial);
```

**Nova Tabela: `ferramentas_em_uso`**
```sql
CREATE TABLE ferramentas_em_uso (
    id SERIAL PRIMARY KEY,
    codigo_item VARCHAR NOT NULL,
    codigo_patrimonial VARCHAR(100),
    matricula VARCHAR NOT NULL,
    data_retirada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_devolucao TIMESTAMP,
    observacao TEXT,
    saida_id INTEGER,
    status VARCHAR(20) DEFAULT 'EM_USO',
    FOREIGN KEY (codigo_item) REFERENCES itens(codigo_item),
    FOREIGN KEY (matricula) REFERENCIAS usuarios(matricula),
    FOREIGN KEY (saida_id) REFERENCES saidas(id_saida)
);
```

**Status possíveis**:
- `EM_USO` - Ferramenta atualmente com o colaborador
- `DEVOLVIDA` - Ferramenta devolvida
- `PERDIDA` - Ferramenta extraviada
- `DANIFICADA` - Ferramenta com problemas

### ✅ 3. Modelo de Dados

**Classe: `FerramentaEmUso`** - [galint_flask/models.py](galint_flask/models.py#L919-L957)

```python
class FerramentaEmUso(db.Model):
    """Registra ferramentas que estão em uso por colaboradores."""
    id: int
    codigo_item: str  # Código EAN/fábrica
    codigo_patrimonial: str  # Código interno
    matricula: str  # Quem está usando
    data_retirada: datetime
    data_devolucao: datetime | None
    observacao: str | None
    saida_id: int | None  # Vincula com registro de saída
    status: str  # EM_USO, DEVOLVIDA, PERDIDA, DANIFICADA
```

**Relacionamentos**:
- `item` → Item completo com todas as informações
- `usuario` → Colaborador que está usando
- `saida` → Registro da movimentação de saída

### ✅ 4. Validações e Segurança

**Unicidade do Código Patrimonial**
- Validação no backend ao salvar/atualizar
- Mensagem de erro clara se código já existe
- Permite null/vazio (opcional)

```python
# galint_flask/services/inventory.py
if codigo_patrimonial_clean:
    existing = Item.query.filter(
        Item.codigo_patrimonial == codigo_patrimonial_clean,
        Item.codigo_item != item.codigo_item
    ).first()
    if existing:
        raise ValueError(f"Código patrimonial '{codigo_patrimonial_clean}' já em uso")
```

## Casos de Uso

### 📦 1. Cadastro de Nova Ferramenta

**Cenário**: Chegou uma furadeira nova

1. **Scanner**: Ler código de barras do fabricante → `7891234567890`
2. **Formulário**: 
   - Descrição: "Furadeira Bosch GSB 13 RE"
   - Categoria: "Ferramentas"
   - ☑️ Adicionar número de série e modelo
3. **Campos adicionais**:
   - Número de Série: `BR20240115-001`
   - **Código Patrimonial**: `FURAD-001` ⭐
   - Modelo: `GSB 13 RE`
4. **Salvar** → Sistema valida unicidade do código patrimonial

**Resultado**:
- Item cadastrado com duplo código
- Pronto para rastreamento completo

### 🔨 2. Retirada de Ferramenta por Colaborador

**Cenário**: João precisa de uma furadeira

1. **Movimentação**: Registrar saída
2. **Sistema cria registro automático** em `ferramentas_em_uso`:
   - Código EAN: `7891234567890`
   - Código Patrimonial: `FURAD-001`
   - Colaborador: João (matrícula 12345)
   - Data: 05/02/2026 12:30
   - Status: `EM_USO`

**Rastreabilidade**:
- Histórico completo de quem está com cada ferramenta
- Consulta por código patrimonial
- Consulta por colaborador
- Alertas de não devolução

### 🔄 3. Devolução de Ferramenta

**Cenário**: João devolveu a furadeira

1. **Registrar devolução**
2. **Sistema atualiza registro**:
   - Data devolucao: 07/02/2026 16:00
   - Status: `DEVOLVIDA`
   - Ferramenta disponível novamente

### 🔍 4. Busca por Código Patrimonial

**Múltiplas formas de localizar**:

- Scanner patrimonial → Sistema identifica item
- Busca manual por código → Encontra ferramenta específica
- Relatório por colaborador → Lista todas suas ferramentas
- Relatório de pendências → Ferramentas não devolvidas

## Interface do Usuário

### Formulário de Cadastro

```
┌─────────────────────────────────────────┐
│ Categoria: [Ferramentas ▼]              │
│                                          │
│ ☑ Adicionar número de série e modelo    │
│                                          │
│ ┌────────────────────────────────────┐  │
│ │ Número de Série                    │  │
│ │ [SN123456_________________]        │  │
│ │ Número de série do fabricante      │  │
│ │                                    │  │
│ │ Código Patrimonial / Interno ⭐    │  │
│ │ [PAT-001__________________]        │  │
│ │ Etiqueta patrimonial interna       │  │
│ │                                    │  │
│ │ Modelo                             │  │
│ │ [GSB 13 RE________________]        │  │
│ │ Modelo ou versão do equipamento    │  │
│ └────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**Visual Highlights**:
- Código patrimonial em **azul**
- Fonte **monoespaçada** (melhor leitura)
- Texto em **negrito**
- Placeholder com exemplos

### API de Dados

**Item.to_dict()** agora inclui:
```json
{
    "codigo": "7891234567890",
    "descricao": "Furadeira Bosch GSB 13 RE",
    "categoria": "Ferramentas",
    "numero_serie": "BR20240115-001",
    "codigo_patrimonial": "FURAD-001",
    "modelo": "GSB 13 RE",
    ...
}
```

**FerramentaEmUso.to_dict()**:
```json
{
    "id": 1,
    "codigo_item": "7891234567890",
    "codigo_patrimonial": "FURAD-001",
    "matricula": "12345",
    "usuario_nome": "João Silva",
    "item_descricao": "Furadeira Bosch GSB 13 RE",
    "data_retirada": "2026-02-05T12:30:00",
    "data_devolucao": null,
    "status": "EM_USO"
}
```

## Fluxo de Trabalho Completo

```
┌────────────────┐
│ 1. CADASTRO    │
│ Furadeira nova │
│ EAN + Patrim.  │
└───────┬────────┘
        │
        ▼
┌────────────────┐      ┌──────────────────┐
│ 2. ESTOQUE     │      │ ferramentas_em_uso│
│ Ferramenta     │◄─────┤ vazia inicialmente│
│ disponível     │      └──────────────────┘
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ 3. RETIRADA    │
│ João pega      │
│ FURAD-001      │
└───────┬────────┘
        │
        ▼
┌────────────────┐      ┌──────────────────┐
│ 4. EM USO      │──────┤ Registro criado  │
│ João c/ ferram.│      │ Status: EM_USO   │
└───────┬────────┘      └──────────────────┘
        │
        ▼
┌────────────────┐      ┌──────────────────┐
│ 5. DEVOLUÇÃO   │──────┤ Registro atualiz.│
│ João devolve   │      │ Status: DEVOLVIDA│
└───────┬────────┘      └──────────────────┘
        │
        ▼
┌────────────────┐
│ 6. DISPONÍVEL  │
│ Ferramenta OK  │
│ para novo uso  │
└────────────────┘
```

## Relatórios e Consultas

### Consultas Disponíveis (Futuro)

1. **Por Ferramenta**
   - Histórico completo de uso
   - Quem usou e quando
   - Devoluções e pendências

2. **Por Colaborador**
   - Ferramentas atualmente em uso
   - Histórico de retiradas
   - Ferramentas não devolvidas

3. **Dashboard Patrimonial**
   - Total de ferramentas
   - Ferramentas em uso
   - Ferramentas disponíveis
   - Taxa de devolução
   - Itens perdidos/danificados

4. **Alertas**
   - Ferramentas não devolvidas há mais de X dias
   - Colaboradores com pendências
   - Ferramentas danificadas

## Instalação

O sistema já foi instalado! Execute:

```bash
.\.venv\Scripts\python.exe scripts/add_patrimonio_system.py
```

**Output**:
```
======================================================================
ADICIONANDO SISTEMA DE CÓDIGO PATRIMONIAL
======================================================================

[1/3] Adicionando campo codigo_patrimonial na tabela itens...
   [OK] Campo codigo_patrimonial adicionado

[2/3] Criando tabela ferramentas_em_uso...
   [OK] Tabela ferramentas_em_uso criada

[3/3] Adicionando indices de performance...
   [OK] Indices criados

======================================================================
[SUCESSO] SISTEMA DE CODIGO PATRIMONIAL INSTALADO!
======================================================================
```

## Próximas Melhorias

- [ ] Interface de gestão de ferramentas em uso
- [ ] Relatórios de rastreabilidade
- [ ] Scanner de código patrimonial (QR Code próprio)
- [ ] Alertas automáticos de não devolução
- [ ] Dashboard de controle patrimonial
- [ ] App mobile para leitura de códigos patrimoniais
- [ ] Geração de etiquetas patrimoniais (PDF/Impressão)
- [ ] Histórico fotográfico (antes/depois)
- [ ] Integração com manutenção preventiva

## Arquivos Modificados

1. ✅ [models.py](galint_flask/models.py) - Modelo Item + FerramentaEmUso
2. ✅ [inventory.py](galint_flask/services/inventory.py) - Validação unicidade
3. ✅ [form.html](galint_flask/templates/inventory/form.html) - Interface campos
4. ✅ [add_patrimonio_system.py](scripts/add_patrimonio_system.py) - Script migração

## Suporte

Para dúvidas ou problemas:
1. Verificar este documento
2. Consultar código-fonte comentado
3. Logs do sistema
4. Script de instalação

---

**Sistema desenvolvido para GALINT - Gestão de Almoxarifado Inteligente**
