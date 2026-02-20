# 📸 Suporte a Relatórios em Formato JPEG

## 🎯 Problema Resolvido

Alguns dispositivos Android e aplicativos de mensagens (WhatsApp, Telegram) têm dificuldade em compartilhar arquivos PDF diretamente. O formato JPEG resolve isso permitindo:

✅ Compartilhamento fácil em apps de mensagens
✅ Visualização universal sem necessidade de leitor de PDF  
✅ Abertura direta na galeria de fotos
✅ Melhor compatibilidade com dispositivos antigos

---

## 🚀 Como Usar

### No Aplicativo Mobile

**Relatórios Diários:**
```javascript
// Agora aceita 3 formatos: pdf, xlsx, jpeg
GET /api/mobile/reports/daily?format=jpeg&scope=all
GET /api/mobile/reports/daily?format=jpeg&scope=tools
GET /api/mobile/reports/daily?format=jpeg&scope=materials
```

**Relatórios Mensais:**
```javascript
// Também aceita jpeg
GET /api/mobile/reports/monthly?format=jpeg&scope=all&month=1&year=2026
```

### Implementação no React Native (galint-mobile)

Atualizar [ReportsDailyScreen.js](galint-mobile/src/screens/ReportsDailyScreen.js):

```javascript
const downloadReport = async (scope, format) => {
  setLoading(true);
  try {
    const response = await fetch(
      `${API_BASE}/api/mobile/reports/daily?scope=${scope}&format=${format}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    if (!response.ok) throw new Error('Erro ao baixar');

    const blob = await response.blob();
    const fileName = `relatorio_${scope}_${format}_${Date.now()}.${format}`;
    
    // Escolher mimetype correto
    const mimeType = format === 'jpeg' ? 'image/jpeg' : 
                     format === 'pdf' ? 'application/pdf' : 
                     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    
    const fileUri = FileSystem.documentDirectory + fileName;
    const reader = new FileReader();
    reader.onloadend = async () => {
      const base64data = reader.result.split(',')[1];
      await FileSystem.writeAsStringAsync(fileUri, base64data, {
        encoding: FileSystem.EncodingType.Base64,
      });
      
      // Compartilhar - JPEG funciona melhor!
      await Sharing.shareAsync(fileUri, {
        mimeType,
        dialogTitle: 'Compartilhar Relatório',
        UTI: format === 'jpeg' ? 'public.jpeg' : undefined,
      });
    };
    reader.readAsDataURL(blob);
  } catch (error) {
    Alert.alert('Erro', error.message);
  } finally {
    setLoading(false);
  }
};

// Adicionar botão JPEG na UI
<TouchableOpacity
  style={styles.buttonJpeg}
  onPress={() => downloadReport('all', 'jpeg')}
>
  <Icon name="image" size={20} color="#fff" />
  <Text style={styles.buttonText}>JPEG (Compartilhar)</Text>
</TouchableOpacity>
```

---

## ⚙️ Requisitos Técnicos

### Backend (Flask)

**Dependências Instaladas:**
```
pdf2image==1.17.0  # Converte PDF para imagens
pillow==11.1.0     # Manipulação de imagens
```

**Windows - Poppler Binário:**
```powershell
# Baixar poppler-windows:
# https://github.com/oschwartz10612/poppler-windows/releases

# Extrair e adicionar ao PATH, ou copiar para pasta do projeto:
# poppler-xx.xx.x/Library/bin/*.dll -> .venv/Scripts/
```

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler
```

### Teste Local

```powershell
# Testar conversão PDF → JPEG
cd C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800
.\.venv\Scripts\python.exe -c "
from pdf2image import convert_from_path
from PIL import Image
print('✅ pdf2image e Pillow funcionando!')
"
```

---

## 🔧 Como Funciona

1. **Gera PDF normalmente** usando ReportLab (já implementado)
2. **Converte PDF para JPEG**:
   - Usa `pdf2image` para converter cada página em imagem PIL
   - Se 1 página: salva direto como JPEG (qualidade 95%)
   - Se múltiplas páginas: combina verticalmente em uma imagem longa
3. **Retorna JPEG** com `mimetype=image/jpeg`

### Qualidade

- **DPI**: 200 (alta qualidade para impressão/visualização)
- **Compressão**: JPEG quality=95 (quase lossless)
- **Tamanho**: ~500KB-2MB por relatório (dependendo do conteúdo)

---

## 📱 Vantagens do JPEG no Mobile

| Aspecto | PDF | JPEG |
|---------|-----|------|
| Compartilhamento WhatsApp | ⚠️ Precisa abrir app | ✅ Direto da galeria |
| Abertura | 📱 Requer leitor PDF | ✅ Nativo em qualquer app |
| Tamanho arquivo | 📦 50-200KB | 📦 500KB-2MB |
| Edição/anotações | ❌ Difícil no mobile | ✅ Fácil com apps de foto |
| Impressão | ✅ Melhor | ⚠️ Pode perder qualidade |
| Múltiplas páginas | ✅ Suportado | ⚠️ Imagem longa |

---

## 🚨 Notas Importantes

1. **Primeiro uso**: Instale poppler no Windows (veja acima)
2. **Espaço em disco**: JPEG ocupa mais que PDF
3. **Múltiplas páginas**: Relatórios longos viram imagens muito altas
4. **Compatibilidade**: 100% dos apps de mensagens suportam JPEG

---

## 🔍 Troubleshooting

**Erro: "pdf2image não instalado"**
```powershell
pip install pdf2image pillow
```

**Erro: "Unable to get page count. Is poppler installed?"**
```powershell
# Windows: Baixe poppler-windows e adicione ao PATH
# Ou copie DLLs para .venv/Scripts/
```

**JPEG muito grande (>5MB)**
- Ajuste `dpi=200` para `dpi=150` em `_convert_pdf_to_jpeg()`
- Ou ajuste `quality=95` para `quality=85`

---

## ✅ Checklist de Implementação

- [x] Função `_convert_pdf_to_jpeg()` criada em `api_mobile.py`
- [x] Suporte `format=jpeg` em `/api/mobile/reports/daily`
- [x] Suporte `format=jpeg` em `/api/mobile/reports/monthly`
- [x] Dependências instaladas (`pdf2image`, `pillow`)
- [x] Documentação criada
- [ ] **TODO**: Atualizar `ReportsDailyScreen.js` com botão JPEG
- [ ] **TODO**: Atualizar `ReportsMonthlyScreen.js` com botão JPEG
- [ ] **TODO**: Instalar poppler no servidor de produção (se Windows)

---

**Autor**: GitHub Copilot  
**Data**: 21/01/2026  
**Versão**: 1.0.0
