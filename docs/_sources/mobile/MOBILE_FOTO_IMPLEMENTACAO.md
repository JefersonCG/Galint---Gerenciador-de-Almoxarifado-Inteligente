# Implementação: Upload de Foto no Mobile

## ✅ Implementado

### Backend (Flask)
1. ✅ [galint_flask/models.py](galint_flask/models.py) - Adicionado campo `foto_path` ao modelo `Item`
2. ✅ [galint_flask/services/item_foto_service.py](galint_flask/services/item_foto_service.py) - Criado serviço de upload de fotos
3. ✅ [galint_flask/services/inventory.py](galint_flask/services/inventory.py) - Adicionado suporte ao campo `foto_path` em `create_item()` e `update_item()`
4. ✅ [galint_flask/views/api_mobile.py](galint_flask/views/api_mobile.py) - Rotas `/api/mobile/estoque` (POST e PUT) modificadas para aceitar `multipart/form-data`
5. ✅ [galint_flask/views/inventory.py](galint_flask/views/inventory.py) - View web atualizada para processar uploads de foto
6. ✅ [galint_flask/templates/inventory/form.html](galint_flask/templates/inventory/form.html) - Formulário web com campo de foto
7. ✅ [galint_flask/templates/inventory/list.html](galint_flask/templates/inventory/list.html) - Modal de detalhes exibindo foto do item
8. ✅ [scripts/add_foto_path_to_itens.py](scripts/add_foto_path_to_itens.py) - Script de migração do banco de dados executado

### Mobile (React Native)
1. ✅ [galint-mobile/src/screens/CadastroScreen.js](galint-mobile/src/screens/CadastroScreen.js) - Adicionado campo de foto com seleção de galeria/câmera
2. ✅ [galint-mobile/src/screens/EditarItemScreen.js](galint-mobile/src/screens/EditarItemScreen.js) - Adicionado campo de foto com preview da foto existente
3. ✅ [galint-mobile/src/services/api.js](galint-mobile/src/services/api.js) - Métodos `cadastrarItem()` e `atualizarItem()` modificados para enviar `FormData` quando há foto

## ⚠️ Pendências

### 1. Instalar Dependência no Mobile

A biblioteca `expo-image-picker` precisa ser instalada no projeto mobile:

```bash
cd galint-mobile
npx expo install expo-image-picker
```

### 2. Rebuild do APK

Após instalar a dependência, será necessário fazer rebuild do APK:

```bash
cd galint-mobile
npx expo prebuild
eas build --profile preview --platform android
```

### 3. Permissões no app.json

Verifique se as permissões de câmera e galeria estão configuradas no `galint-mobile/app.json`:

```json
{
  "expo": {
    "plugins": [
      [
        "expo-image-picker",
        {
          "photosPermission": "Precisamos de acesso à sua galeria para selecionar fotos.",
          "cameraPermission": "Precisamos de acesso à câmera para tirar fotos."
        }
      ]
    ]
  }
}
```

## 📋 Funcionalidades Implementadas

### 🎯 Cadastro de Item (Mobile)
- ✅ Botão "Adicionar Foto" com opções de câmera ou galeria
- ✅ Preview da imagem selecionada
- ✅ Opção de trocar ou remover foto antes de salvar
- ✅ Upload automático da foto ao cadastrar item
- ✅ Validação de tipo e tamanho (5MB máx, formatos: png, jpg, jpeg, webp, gif)

### 🎯 Edição de Item (Mobile)
- ✅ Exibição da foto existente (se houver)
- ✅ Opção de trocar foto existente
- ✅ Opção de remover foto
- ✅ Adição de foto se item não tinha
- ✅ Upload/remoção ao salvar

### 🎯 Cadastro/Edição Web
- ✅ Campo de upload de arquivo no formulário
- ✅ Preview da imagem atual ao editar
- ✅ Checkbox para remover foto existente
- ✅ Validação de formato e tamanho

### 🎯 Visualização
- ✅ Modal de detalhes do item exibe foto (web)
- ✅ Foto é armazenada em `static/uploads/itens/{codigo}_{timestamp}.{ext}`
- ✅ Caminho relativo salvo no banco: `uploads/itens/...`

## 🔒 Validações

### Backend
- Extensões permitidas: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`
- Tamanho máximo: 5 MB
- Nome seguro usando `werkzeug.utils.secure_filename`
- Timestamp no nome para evitar colisões

### Mobile
- Quality: 0.7 (compressão de imagem)
- Aspect ratio: 4:3 ao editar imagem
- Permissões solicitadas automaticamente

## 🚀 Teste Local

Para testar localmente:

1. **Backend (já rodando):**
   ```bash
   # Servidor Flask já está rodando em http://localhost:5000
   ```

2. **Mobile:**
   ```bash
   cd galint-mobile
   npx expo install expo-image-picker
   npx expo start
   ```

3. **Testar fluxo completo:**
   - Abrir app mobile
   - Ir para "Cadastrar Item"
   - Adicionar foto (câmera ou galeria)
   - Cadastrar item
   - Verificar no web se foto aparece no modal de detalhes

## 📝 Notas Técnicas

### Estrutura de Arquivos
```
static/
  uploads/
    itens/
      {codigo_item}_{timestamp}.{ext}
```

### Modelo de Dados
```python
class Item(Base):
    ...
    foto_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### API Endpoints Modificados

**POST /api/mobile/estoque**
- Aceita: `application/json` OU `multipart/form-data`
- Campos FormData: codigo_barras, descricao, categoria, marca, etc. + foto
- Resposta: `{ "id": "...", "message": "..." }`

**PUT /api/mobile/estoque/{codigo}**
- Aceita: `application/json` OU `multipart/form-data`
- Campos FormData: descricao, categoria, marca, etc. + foto + remover_foto
- Resposta: Item atualizado

## ✅ Checklist de Validação

- [x] Campo foto_path adicionado ao modelo
- [x] Serviço de upload criado e testado
- [x] Migração do banco executada
- [x] Rotas backend aceitam multipart/form-data
- [x] Upload funciona no formulário web
- [x] Preview da foto no modal web
- [x] Campo de foto no cadastro mobile
- [x] Campo de foto na edição mobile
- [x] API mobile envia FormData corretamente
- [ ] expo-image-picker instalado
- [ ] Rebuild do APK realizado
- [ ] Permissões configuradas no app.json
- [ ] Teste end-to-end realizado

## 🎉 Próximos Passos

1. Execute `cd galint-mobile && npx expo install expo-image-picker`
2. Configure permissões no app.json
3. Faça rebuild do APK
4. Teste o fluxo completo no dispositivo
