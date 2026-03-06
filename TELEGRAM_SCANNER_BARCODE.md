# 📸 SCANNER DE CÓDIGO DE BARRAS VIA TELEGRAM

## 🎯 Visão Geral

Sistema completo para fazer retiradas de materiais via Telegram usando **scanner de código de barras**.

### ✨ Funcionalidades Implementadas

1. **📸 Escanear Código de Barras** - Tire foto e envie para o bot
2. **🔍 Processamento Automático** - Leitura inteligente com pré-processamento
3. **📊 Busca de Item** - Localização automática no banco de dados
4. **📤 Confirmar Retirada** - Botões interativos para confirmar
5. **🔒 Sistema de Permissões** - Controle de quem pode fazer retiradas

---

## 🚀 Como Usar (Usuário Final)

### 1️⃣ **Obter Permissão**
Entre em contato com o administrador para habilitar retiradas via Telegram.

### 2️⃣ **Iniciar Scanner**
```
/scanear
```
O bot enviará instruções detalhadas.

### 3️⃣ **Tirar Foto do Código**
- ✅ Foto bem iluminada
- ✅ Código em foco
- ✅ Sem reflexos
- ✅ Código inteiro visível

### 4️⃣ **Enviar Foto**
Apenas envie a foto no chat do bot (sem comando adicional).

### 5️⃣ **Aguardar Processamento**
```
🔍 Processando imagem...
⏳ Aguarde um momento...
```

### 6️⃣ **Confirmar Retirada**
```
✅ DISPONÍVEL
🔧 CHAVE PHILLIPS 1/4
━━━━━━━━━━━━━━━

🏷️ Código: FER-0234
📂 Categoria: Ferramentas
📍 Localização: Prateleira A3
📊 Estoque Atual: 15 un

[📤 Fazer Retirada] [📊 Ver Detalhes]
```

---

## ⚙️ Configuração (Administrador)

### 📦 **1. Instalar Bibliotecas**

Execute no terminal:
```bash
C:\.venv\Scripts\python.exe -m pip install pyzbar opencv-python-headless==4.8.1.78
```

**Dependências necessárias:**
- `pyzbar` - Leitura de códigos de barras
- `opencv-python-headless` - Processamento de imagens
- `pillow` - Manipulação de imagens (já instalado)

### 🗄️ **2. Executar Migration**

Execute no terminal:
```bash
C:\.venv\Scripts\python.exe -m flask db upgrade
```

Ou execute manualmente:
```bash
C:\.venv\Scripts\python.exe -c "from galint_flask import create_app; from galint_flask.extensions import db; from migrations.versions.add_telegram_withdrawal_permission import upgrade; app = create_app(); app.app_context().push(); upgrade()"
```

### 🔧 **3. Habilitar Usuários**

1. Acesse **Configurações → Telegram**
2. Na tabela **Usuários Vinculados**, localize o usuário
3. Ative o switch na coluna **🔧 Retiradas**
4. Ícone muda de 🎥 (cinza) para 📸 (verde)

### ✅ **4. Verificar Instalação**

Execute:
```bash
C:\.venv\Scripts\python.exe -c "from galint_flask.utils.barcode_photo_processor import BarcodePhotoProcessor; print('✅ Scanner disponível!' if BarcodePhotoProcessor.is_available() else '❌ Bibliotecas faltando:', BarcodePhotoProcessor.get_missing_libraries())"
```

---

## 🏗️ Arquitetura Técnica

### 📁 **Arquivos Criados/Modificados**

```
galint_flask/
├── models.py                          # ✅ Adicionado campo can_withdraw_via_telegram
├── utils/
│   └── barcode_photo_processor.py    # ✅ NOVO - Processamento de fotos
├── services/
│   └── telegram_service.py           # ✅ Handlers de foto e /scanear
├── views/
│   └── telegram_config.py            # ✅ Rota toggle-withdrawal
└── templates/
    └── telegram/
        └── config.html                # ✅ Interface de permissões

migrations/versions/
└── add_telegram_withdrawal_permission.py  # ✅ NOVO - Migration

requirements.txt                       # ✅ Bibliotecas adicionadas
```

### 🔄 **Fluxo de Processamento**

```
┌─────────────┐
│   USUÁRIO   │
│ Tira foto   │
└──────┬──────┘
       │
       ↓
┌──────────────────────┐
│   TELEGRAM BOT API   │
│ Recebe foto          │
│ Retorna file_id      │
└──────┬───────────────┘
       │
       ↓
┌────────────────────────────┐
│ BarcodePhotoProcessor      │
│ 1. Download foto           │
│ 2. Pré-processamento       │
│    • Grayscale             │
│    • CLAHE (contraste)     │
│    • Gaussian blur         │
│    • Binarização adaptativa│
│ 3. Decodificação (pyzbar)  │
└──────┬─────────────────────┘
       │
       ↓
┌────────────────────┐
│ telegram_service   │
│ 1. Valida permissão│
│ 2. Busca item no BD│
│ 3. Formata mensagem│
│ 4. Envia com botões│
└────────────────────┘
```

### 🔒 **Sistema de Permissões**

**Banco de Dados:**
```sql
ALTER TABLE telegram_users 
ADD COLUMN can_withdraw_via_telegram BOOLEAN 
DEFAULT FALSE 
NOT NULL;
```

**Verificação:**
```python
can_withdraw, telegram_user = TelegramService._can_user_withdraw_via_telegram(chat_id)

if not can_withdraw:
    return "❌ Permissão negada"
```

---

## 🔧 **Comandos Disponíveis**

| Comando | Descrição | Permissão |
|---------|-----------|-----------|
| `/scanear` | Instruções para escanear código | Retirada habilitada |
| `/start` | Menu principal | Todos |
| `/estoque <código>` | Buscar item manualmente | Todos |
| `/ajuda` | Ajuda do sistema | Todos |

---

## 📊 **Formatos de Código de Barras Suportados**

Através da biblioteca **pyzbar**, o sistema suporta:

- ✅ **CODE128** (padrão do sistema)
- ✅ CODE39
- ✅ CODE93
- ✅ EAN-8
- ✅ EAN-13
- ✅ UPC-A
- ✅ UPC-E
- ✅ QR Code
- ✅ Data Matrix
- ✅ PDF417

---

## 🐛 **Troubleshooting**

### ❌ "Bibliotecas necessárias não instaladas"

**Solução:**
```bash
pip install pyzbar opencv-python-headless
```

### ❌ "Nenhum código de barras detectado"

**Causas comuns:**
- 📷 Foto desfocada
- 🌑 Pouca iluminação
- 💡 Reflexo no código
- ✂️ Código parcialmente visível

**Solução:**
- Tire nova foto com melhor iluminação
- Aproxime mais do código
- Evite reflexos e sombras

### ❌ "Permissão Negada"

**Solução:**
1. Verifique se usuário está vinculado
2. Administrador deve habilitar permissão
3. Campo `can_withdraw_via_telegram = TRUE`

### ❌ "Campo can_withdraw_via_telegram não existe"

**Solução:**
```bash
# Executar migration
python -m flask db upgrade
```

---

## 🎯 **Melhores Práticas**

### Para Administradores:
1. ✅ Habilite apenas usuários treinados
2. ✅ Monitore uso inicial
3. ✅ Mantenha códigos de barras atualizados
4. ✅ Verifique qualidade das etiquetas

### Para Usuários:
1. ✅ Use `/scanear` para ver dicas
2. ✅ Tire fotos com boa iluminação
3. ✅ Mantenha foco no código
4. ✅ Confirme item antes de retirar

---

## 📈 **Vantagens do Sistema**

| Vantagem | Benefício |
|----------|-----------|
| 🚀 **Rapidez** | Retirada em segundos |
| 🎯 **Precisão** | Zero erros de digitação |
| 📱 **Mobilidade** | Funciona em qualquer celular |
| 🔒 **Segurança** | Controle de permissões |
| 📊 **Rastreamento** | Histórico completo |
| 💰 **Economia** | Reduz tempo de atendimento |

---

## 🔄 **Próximas Funcionalidades**

### 🚧 Em Desenvolvimento:
- [ ] Retirada de múltiplos itens
- [ ] Devolução via Telegram
- [ ] Histórico de retiradas do usuário
- [ ] QR Code com informações completas
- [ ] Scanner offline (PWA)

---

## 📞 **Suporte**

Em caso de problemas:

1. **Verifique logs:** `log/actions.log`
2. **Teste conexão:** Botão "Testar Conexão"
3. **Valide permissões:** Interface web
4. **Consulte documentação:** Este arquivo

---

## ✅ **Checklist de Instalação**

- [ ] Bibliotecas instaladas (`pyzbar`, `opencv-python-headless`)
- [ ] Migration executada
- [ ] Campo `can_withdraw_via_telegram` existe no banco
- [ ] Usuários habilitados na interface web
- [ ] Teste realizado com foto de código de barras
- [ ] Comando `/scanear` funcionando

---

**🎉 Sistema pronto para uso!**

Última atualização: {{ date }}
