# PROPOSTA TÉCNICA: Rastreabilidade e Gestão Avançada de Estoque
## Sistema GALINT - Expansão do Módulo de Cadastro de Itens

---

## 📋 ANÁLISE TÉCNICA DA ESTRUTURA ATUAL

### Modelo de Dados Existente (Item)
```python
class Item(db.Model):
    codigo_item: str (PK)
    descricao: str
    unidade: str (default="Unidade")
    localizacao: str | None
    setor: str
    estoque_minimo: int
    nota_fiscal: str | None
    categoria: str
    marca: str | None
    numero_serie: str | None
    modelo: str | None
```

### Fluxo Atual de Cadastro
1. **View**: `inventory.py` → `create_item()` / `update_item()`
2. **Service**: `inventory_service.create_item(payload)`
3. **Notificação**: `TelegramService.notify_item_created(codigo)`

---

## 🎯 PROPOSTA DE IMPLEMENTAÇÃO

### 1. GERAÇÃO AUTOMÁTICA DE CÓDIGO DE BARRAS

#### Backend: Biblioteca e Geração
```python
# Adicionar ao requirements.txt
python-barcode==0.15.1
Pillow==10.2.0  # Já existe no projeto

# Novo arquivo: galint_flask/utils/barcode_generator.py
from barcode import Code128
from barcode.writer import ImageWriter
from io import BytesIO
from PIL import Image

def generate_barcode_image(code: str) -> bytes:
    """
    Gera imagem PNG do código de barras.
    Retorna bytes da imagem para armazenamento.
    """
    barcode_class = Code128(code, writer=ImageWriter())
    buffer = BytesIO()
    barcode_class.write(buffer, options={
        'module_width': 0.3,
        'module_height': 10.0,
        'quiet_zone': 2.5,
        'font_size': 10,
        'text_distance': 2.0,
        'write_text': True
    })
    buffer.seek(0)
    return buffer.getvalue()

def save_barcode_to_instance(codigo_item: str) -> str:
    """
    Salva imagem do código de barras em instance/barcodes/
    Retorna o caminho relativo.
    """
    from pathlib import Path
    from flask import current_app
    
    barcode_dir = Path(current_app.instance_path) / "barcodes"
    barcode_dir.mkdir(parents=True, exist_ok=True)
    
    img_bytes = generate_barcode_image(codigo_item)
    filepath = barcode_dir / f"{codigo_item}.png"
    
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    
    return f"barcodes/{codigo_item}.png"
```

#### Integração no Modelo
```python
# galint_flask/models.py - Adicionar ao Item
class Item(db.Model):
    # ... campos existentes ...
    barcode_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    
    def get_barcode_url(self) -> str | None:
        """Retorna URL para acessar a imagem do código de barras"""
        if self.barcode_image_path:
            return url_for('static', filename=self.barcode_image_path)
        return None
```

#### Migration SQL
```sql
-- Migration: add_barcode_to_items
ALTER TABLE itens ADD COLUMN barcode_image_path VARCHAR(255);

-- Gerar barcodes para itens existentes (executar via script Python)
-- Ver: scripts/generate_missing_barcodes.py
```

---

### 2. NOVOS CAMPOS DE RASTREABILIDADE

#### Extensão do Modelo (Migration)
```python
# galint_flask/models.py - Adicionar ao Item
class Item(db.Model):
    # Campos existentes...
    
    # Novos campos de rastreabilidade
    data_entrada: Mapped[date | None] = mapped_column(Date, nullable=True)
    lote: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_fabricacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Campos de unidade dinâmica
    tipo_embalagem: Mapped[str | None] = mapped_column(
        String(20), 
        nullable=True,
        comment="Lata, Balde, Rolo, Quilo, Pacote, Caixa, Unidade"
    )
    grandeza_referencia: Mapped[float | None] = mapped_column(
        Float, 
        nullable=True,
        comment="Valor de referência (Kg, Lt, Cm, M, etc)"
    )
    densidade: Mapped[float | None] = mapped_column(
        Float, 
        nullable=True,
        comment="g/mL - Para conversão Kg<->Lt"
    )
```

#### Migration SQL
```sql
-- Migration: add_traceability_fields
ALTER TABLE itens 
ADD COLUMN data_entrada DATE,
ADD COLUMN lote VARCHAR(50),
ADD COLUMN data_fabricacao DATE,
ADD COLUMN data_validade DATE,
ADD COLUMN tipo_embalagem VARCHAR(20),
ADD COLUMN grandeza_referencia FLOAT,
ADD COLUMN densidade FLOAT;

-- Índices para performance
CREATE INDEX idx_itens_lote ON itens(lote);
CREATE INDEX idx_itens_validade ON itens(data_validade) WHERE data_validade IS NOT NULL;
```

#### Geração Automática de Lote
```python
# galint_flask/utils/lote_generator.py
from datetime import datetime

def generate_lote(codigo_item: str, data_entrada: date) -> str:
    """
    Gera lote automático no formato: LOTE-YYYYMMDD-XXXX
    Onde XXXX são os últimos 4 dígitos do código do item.
    """
    suffix = codigo_item[-4:] if len(codigo_item) >= 4 else codigo_item.zfill(4)
    return f"LOTE-{data_entrada.strftime('%Y%m%d')}-{suffix}"

# Uso no service:
def create_item(payload: dict) -> str:
    # ...
    if not payload.get('lote') and payload.get('data_entrada'):
        payload['lote'] = generate_lote(
            payload['codigo'], 
            payload['data_entrada']
        )
```

---

### 3. LÓGICA DINÂMICA DE UNIDADES E GRANDEZAS

#### Mapeamento de Conversões
```python
# galint_flask/utils/unit_converter.py
from enum import Enum
from typing import Optional

class TipoEmbalagem(str, Enum):
    LATA = "Lata"
    BALDE = "Balde"
    ROLO = "Rolo"
    QUILO = "Quilo"
    PACOTE = "Pacote"
    CAIXA = "Caixa"
    UNIDADE = "Unidade"

class UnidadeGrandeza(str, Enum):
    KG = "Kg"
    LITRO = "Lt"
    CENTIMETRO = "Cm"
    METRO = "M"
    UNIDADE = "Unidade"

# Mapeamento de opções por tipo
OPCOES_POR_TIPO = {
    TipoEmbalagem.LATA: [UnidadeGrandeza.KG, UnidadeGrandeza.LITRO],
    TipoEmbalagem.BALDE: [UnidadeGrandeza.KG, UnidadeGrandeza.LITRO],
    TipoEmbalagem.ROLO: [UnidadeGrandeza.CENTIMETRO, UnidadeGrandeza.METRO],
    TipoEmbalagem.QUILO: [UnidadeGrandeza.KG],
    TipoEmbalagem.PACOTE: [UnidadeGrandeza.UNIDADE],
    TipoEmbalagem.CAIXA: [UnidadeGrandeza.UNIDADE],
    TipoEmbalagem.UNIDADE: [UnidadeGrandeza.UNIDADE],
}

def calcular_total_estoque(
    tipo_embalagem: str,
    grandeza: float,
    quantidade_embalagens: int,
    densidade: Optional[float] = None
) -> dict:
    """
    Calcula o total em estoque baseado no tipo de embalagem.
    
    Retorna:
        {
            'total_numerico': float,
            'unidade_display': str,
            'conversoes': dict  # conversões opcionais
        }
    """
    result = {
        'total_numerico': 0.0,
        'unidade_display': '',
        'conversoes': {}
    }
    
    if tipo_embalagem == TipoEmbalagem.LATA:
        # Ex: 5 latas de 2Kg cada = 10Kg total
        result['total_numerico'] = grandeza * quantidade_embalagens
        result['unidade_display'] = "Kg" if densidade is None else "Lt"
        
        if densidade:
            # Conversão Kg <-> Lt
            kg_total = result['total_numerico'] * densidade / 1000
            result['conversoes']['kg'] = round(kg_total, 2)
            result['conversoes']['litros'] = round(result['total_numerico'], 2)
    
    elif tipo_embalagem == TipoEmbalagem.ROLO:
        # Ex: 3 rolos de 50m cada = 150m total
        result['total_numerico'] = grandeza * quantidade_embalagens
        result['unidade_display'] = "M"
        result['conversoes']['cm'] = round(result['total_numerico'] * 100, 2)
    
    elif tipo_embalagem == TipoEmbalagem.PACOTE:
        # Ex: 5 pacotes de 20 unidades = 100 unidades
        result['total_numerico'] = grandeza * quantidade_embalagens
        result['unidade_display'] = "Unidades"
    
    elif tipo_embalagem == TipoEmbalagem.UNIDADE:
        # Valor direto
        result['total_numerico'] = quantidade_embalagens
        result['unidade_display'] = "Unidades"
    
    return result
```

#### Frontend - JavaScript Dinâmico
```javascript
// templates/inventory/form.html - Adicionar script

const tipoEmbalagemOpcoes = {
    'Lata': ['Kg', 'Lt'],
    'Balde': ['Kg', 'Lt'],
    'Rolo': ['Cm', 'M'],
    'Quilo': ['Kg'],
    'Pacote': ['Unidades por pacote'],
    'Caixa': ['Unidades por caixa'],
    'Unidade': ['Unidade']
};

function onTipoEmbalagemChange(tipoSelecionado) {
    const campoGrandeza = document.getElementById('campo-grandeza-container');
    const selectUnidade = document.getElementById('select-unidade-grandeza');
    const campoDensidade = document.getElementById('campo-densidade-container');
    
    if (!tipoSelecionado || tipoSelecionado === 'Unidade') {
        // Ocultar campos extras
        campoGrandeza.style.display = 'none';
        campoDensidade.style.display = 'none';
        return;
    }
    
    // Mostrar campo de grandeza
    campoGrandeza.style.display = 'block';
    
    // Preencher opções de unidade
    const opcoes = tipoEmbalagemOpcoes[tipoSelecionado] || [];
    selectUnidade.innerHTML = opcoes.map(u => 
        `<option value="${u}">${u}</option>`
    ).join('');
    
    // Mostrar densidade apenas para Lata/Balde
    if (['Lata', 'Balde'].includes(tipoSelecionado)) {
        campoDensidade.style.display = 'block';
    } else {
        campoDensidade.style.display = 'none';
    }
}

// Cálculo em tempo real
function calcularTotalEstoque() {
    const tipo = document.querySelector('input[name="tipo_embalagem"]:checked')?.value;
    const grandeza = parseFloat(document.getElementById('grandeza_referencia').value) || 0;
    const quantidade = parseInt(document.getElementById('saldo_atual').value) || 0;
    const densidade = parseFloat(document.getElementById('densidade').value) || null;
    
    // Chamar endpoint /api/calcular-estoque via AJAX
    fetch('/api/calcular-estoque', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tipo, grandeza, quantidade, densidade})
    })
    .then(r => r.json())
    .then(data => {
        document.getElementById('display-total').textContent = 
            `${data.total_numerico} ${data.unidade_display}`;
    });
}
```

---

### 4. BLOQUEIO DE CAMPO "SALDO EM ESTOQUE"

#### HTML Template Update
```html
<!-- templates/inventory/form.html -->
<div class="col-md-6">
    <label class="form-label">Saldo em estoque (unidades)</label>
    <input 
        type="number" 
        class="form-control" 
        name="saldo_atual" 
        value="{{ item.saldo if item else saldo_desejado or 0 }}"
        {% if item and not current_user.is_admin %}readonly disabled{% endif %}
        step="1"
        min="0">
    {% if item and not current_user.is_admin %}
    <small class="text-muted">
        <i class="bi bi-lock"></i> Apenas administradores podem editar o saldo após criação
    </small>
    {% endif %}
</div>
```

#### Backend Validation
```python
# galint_flask/views/inventory.py
@blueprint.post("/<codigo>/editar")
@login_required
def update_item(codigo: str):
    _require_admin()
    
    form = request.form
    saldo_raw = form.get("saldo_atual", "").strip()
    
    # Verificar se usuário está tentando alterar saldo sem ser admin
    if saldo_raw != "":
        prev_item = inventory_service.get_item(codigo)
        if prev_item and not current_user.is_admin:
            flash("Apenas administradores podem alterar o saldo em estoque.", "danger")
            return redirect(url_for("inventory.edit_item_form", codigo=codigo))
    
    # Continuar com update...
```

---

### 5. INTEGRAÇÃO COM RELATÓRIOS E TELEGRAM

#### Atualização de Relatórios
```python
# galint_flask/views/reports.py - Adicionar colunas nos PDFs
def _generate_item_report_pdf(...):
    # ...
    header = [
        "Data", "Hora", "Usuário", "Matrícula", "Qtd.", 
        "Lote", "Validade", "Período", "Observações"  # NOVOS
    ]
    
    for saida in saidas:
        # Buscar dados do lote do item
        item = Item.query.get(saida.codigo_item)
        
        data.append([
            # ...campos existentes...
            item.lote or "N/D",
            item.data_validade.strftime("%d/%m/%Y") if item.data_validade else "-",
            # ...
        ])
```

#### Notificação Telegram Enriquecida
```python
# galint_flask/services/telegram_service.py
@staticmethod
def notify_item_created(codigo_item: str) -> None:
    item = db.session.get(Item, codigo_item)
    if not item:
        return
    
    message = f"""
🆕 <b>Novo Item Cadastrado</b>

📦 <b>Produto:</b> {item.descricao}
🔢 <b>Código:</b> {item.codigo_item}
📊 <b>Lote:</b> {item.lote or "N/D"}
📅 <b>Data Entrada:</b> {item.data_entrada.strftime("%d/%m/%Y") if item.data_entrada else "N/D"}
📅 <b>Fabricação:</b> {item.data_fabricacao.strftime("%d/%m/%Y") if item.data_fabricacao else "N/D"}
⏰ <b>Validade:</b> {item.data_validade.strftime("%d/%m/%Y") if item.data_validade else "Indeterminado"}
📦 <b>Tipo:</b> {item.tipo_embalagem or "Unidade"}
📏 <b>Unidade:</b> {item.unidade}
🏷️ <b>Categoria:</b> {item.categoria}
"""
    
    if item.barcode_image_path:
        # Enviar imagem do código de barras
        TelegramService._notify_admins_with_photo(
            message, 
            item.barcode_image_path
        )
    else:
        TelegramService._notify_admins(message)
```

---

## 📱 MOBILE: CONSIDERAÇÕES REACT NATIVE

### Componentes Nativos
```jsx
// galint-mobile/src/screens/ItemFormScreen.js
import DateTimePicker from '@react-native-community/datetimepicker';

export default function ItemFormScreen() {
  const [tipoEmbalagem, setTipoEmbalagem] = useState('Unidade');
  const [dataEntrada, setDataEntrada] = useState(new Date());
  const [showDatePicker, setShowDatePicker] = useState(false);
  
  return (
    <ScrollView style={styles.container}>
      {/* Data de Entrada - Obrigatório */}
      <Text style={styles.label}>Data de Entrada *</Text>
      <TouchableOpacity onPress={() => setShowDatePicker(true)}>
        <TextInput 
          value={dataEntrada.toLocaleDateString('pt-BR')}
          editable={false}
          style={styles.input}
        />
      </TouchableOpacity>
      
      {showDatePicker && (
        <DateTimePicker
          value={dataEntrada}
          mode="date"
          display="default"
          onChange={(event, date) => {
            setShowDatePicker(false);
            if (date) setDataEntrada(date);
          }}
        />
      )}
      
      {/* Radio Buttons - Tipo Embalagem */}
      <Text style={styles.label}>Tipo de Embalagem</Text>
      <RadioButton.Group 
        onValueChange={setTipoEmbalagem} 
        value={tipoEmbalagem}
      >
        <RadioButton.Item label="Lata" value="Lata" />
        <RadioButton.Item label="Balde" value="Balde" />
        <RadioButton.Item label="Rolo" value="Rolo" />
        {/* ... */}
      </RadioButton.Group>
      
      {/* Campos condicionais baseados no tipo */}
      {tipoEmbalagem !== 'Unidade' && (
        <TextInput
          label="Grandeza de Referência"
          keyboardType="numeric"
          style={styles.input}
        />
      )}
      
      {/* Bloqueio de saldo para não-admins */}
      <TextInput
        label="Saldo em Estoque"
        keyboardType="numeric"
        editable={isNewItem || isAdmin}
        style={[
          styles.input,
          !isAdmin && !isNewItem && styles.inputDisabled
        ]}
      />
    </ScrollView>
  );
}
```

---

## 🚀 PLANO DE IMPLEMENTAÇÃO

### Fase 1: Backend (2-3 dias)
1. ✅ Criar migrations para novos campos
2. ✅ Implementar gerador de lote automático
3. ✅ Implementar gerador de código de barras
4. ✅ Atualizar `inventory_service.create_item()` e `update_item()`
5. ✅ Criar API `/api/calcular-estoque` para conversões

### Fase 2: Frontend Web (2 dias)
1. ✅ Atualizar formulário com novos campos
2. ✅ Implementar JavaScript de cálculo dinâmico
3. ✅ Adicionar datepickers (usar biblioteca existente)
4. ✅ Implementar lógica de bloqueio de saldo
5. ✅ Adicionar exibição de código de barras

### Fase 3: Mobile (1-2 dias)
1. ✅ Atualizar tela de cadastro
2. ✅ Integrar DateTimePicker nativo
3. ✅ Implementar RadioButton.Group
4. ✅ Sincronizar API com novos campos

### Fase 4: Integração (1 dia)
1. ✅ Atualizar relatórios (PDF/Excel)
2. ✅ Enriquecer notificações Telegram
3. ✅ Gerar barcodes retroativos (script)
4. ✅ Testes end-to-end

### Fase 5: Validações (1 dia)
1. ✅ Alertas de validade próxima
2. ✅ Relatório de lotes vencidos
3. ✅ Dashboard de rastreabilidade

---

## 💡 RECOMENDAÇÕES ADICIONAIS

### 1. Alertas Inteligentes de Validade
```python
# Criar job agendado diário
@scheduler.schedule_daily(hour=8, minute=0)
def alert_expiring_items():
    """Alerta itens com validade próxima (30 dias)"""
    expiring = Item.query.filter(
        Item.data_validade.between(
            date.today(),
            date.today() + timedelta(days=30)
        )
    ).all()
    
    if expiring:
        message = "⚠️ <b>Itens com validade próxima:</b>\n\n"
        for item in expiring:
            dias = (item.data_validade - date.today()).days
            message += f"• {item.descricao} - {dias} dias\n"
        
        TelegramService._notify_admins(message)
```

### 2. Relatório de Rastreabilidade
```python
# Novo endpoint para auditoria
@blueprint.get("/rastreabilidade/<lote>")
@login_required
def rastreabilidade_lote(lote: str):
    """Mostra todo histórico de movimentação de um lote"""
    itens = Item.query.filter_by(lote=lote).all()
    
    historico = []
    for item in itens:
        historico.extend([
            {
                'tipo': 'entrada',
                'data': e.data_entrada,
                'quantidade': e.quantidade,
                'usuario': e.usuario.nome
            }
            for e in item.entradas
        ])
        historico.extend([
            {
                'tipo': 'saida',
                'data': s.data_saida,
                'quantidade': s.quantidade,
                'usuario': s.usuario.nome
            }
            for s in item.saidas
        ])
    
    return render_template('rastreabilidade.html', lote=lote, historico=historico)
```

### 3. QR Code Adicional para Lote
```python
# Gerar QR Code contendo JSON com dados do lote
import qrcode
import json

def generate_lote_qrcode(item: Item) -> bytes:
    """Gera QR Code com dados completos do lote para auditoria"""
    data = {
        'lote': item.lote,
        'produto': item.descricao,
        'codigo': item.codigo_item,
        'fabricacao': item.data_fabricacao.isoformat() if item.data_fabricacao else None,
        'validade': item.data_validade.isoformat() if item.data_validade else None,
        'categoria': item.categoria
    }
    
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(json.dumps(data))
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()
```

---

## 📊 ESTIMATIVA DE ESFORÇO

| Fase | Horas | Prioridade |
|------|-------|-----------|
| Backend (Models + Migrations) | 8h | Alta |
| Gerador de Lote/Barcode | 4h | Alta |
| Frontend Web (Forms) | 12h | Alta |
| JavaScript Dinâmico | 6h | Média |
| Mobile (React Native) | 10h | Média |
| Relatórios + Telegram | 6h | Média |
| Testes + Validação | 8h | Alta |
| **TOTAL** | **54h** | - |

---

## ✅ CHECKLIST DE ENTREGA

- [ ] Migrations executadas sem erro
- [ ] Todos os itens possuem código de barras
- [ ] Lote gerado automaticamente quando vazio
- [ ] Campos de data funcionando com datepicker
- [ ] Cálculo de unidades/grandezas correto
- [ ] Saldo bloqueado para não-admins em edição
- [ ] Relatórios exibindo novos campos
- [ ] Telegram notificando com dados completos
- [ ] Mobile sincronizado com backend
- [ ] Documentação atualizada

---

**Ronaldo, esta é minha sugestão técnica completa.**

**Principais destaques:**
1. ✅ Geração automática de lote no formato `LOTE-YYYYMMDD-XXXX`
2. ✅ Biblioteca `python-barcode` para gerar imagens PNG
3. ✅ JavaScript para calcular totais dinamicamente no frontend
4. ✅ Bloqueio de campo com validação backend + frontend
5. ✅ Componentes nativos no React Native (DateTimePicker)
6. ✅ Integração completa com relatórios e Telegram

**Posso começar imediatamente pela Fase 1 (Backend)?** Isso inclui criar as migrations, implementar o gerador de lote e o gerador de código de barras. Após sua aprovação, prossigo com as demais fases.
