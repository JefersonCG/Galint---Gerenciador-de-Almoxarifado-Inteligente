# Guia Completo de Instalação - GALINT Mobile

## 📋 Índice

1. [Pré-requisitos](#pré-requisitos)
2. [Instalação no Computador](#instalação-no-computador)
3. [Instalação no Celular](#instalação-no-celular)
4. [Primeira Execução](#primeira-execução)
5. [Configuração do App](#configuração-do-app)
6. [Solução de Problemas](#solução-de-problemas)

---

## 🔧 Pré-requisitos

### No Computador:

1. **Node.js** (versão 16 ou superior)
   - Download: https://nodejs.org/
   - Instale a versão LTS (recomendada)
   - Após instalar, reinicie o PowerShell

2. **Servidor Flask** rodando
   - Certifique-se de que o servidor está ativo
   - URL: `https://10.0.0.245:5443` ou `http://10.0.0.245:5000`

### No Celular Android:

1. **App Expo Go**
   - Play Store: https://play.google.com/store/apps/details?id=host.exp.exponent
   - Instale e abra uma vez para configurar

2. **Mesma Rede Wi-Fi**
   - Conecte o celular na MESMA rede que o computador

---

## 💻 Instalação no Computador

### Método 1: Script Automático (RECOMENDADO)

1. Abra a pasta `galint-mobile` no explorador de arquivos

2. Localize o arquivo `instalar_e_rodar.ps1`

3. **Clique com botão direito** → **"Executar com PowerShell"**

4. Aguarde:
   - Verificação do Node.js ✓
   - Instalação de dependências (3-5 minutos)
   - Servidor de desenvolvimento iniciando

5. Um **QR Code** aparecerá no terminal

### Método 2: Manual

Abra PowerShell na pasta `galint-mobile`:

```powershell
# Navegar para a pasta
cd "C:\Users\LUIS\Desktop\GALINT FLASK\galint-mobile"

# Instalar dependências
npm install

# Iniciar servidor
npm start
```

Aguarde aparecer o QR Code.

---

## 📱 Instalação no Celular

### Passo 1: Baixar Expo Go

1. Abra a **Play Store** no Android
2. Pesquise por **"Expo Go"**
3. Instale o aplicativo
4. Abra o Expo Go uma vez para configurar

### Passo 2: Conectar ao App

1. Abra o app **Expo Go**

2. Toque em **"Scan QR code"**

3. Aponte a câmera para o **QR Code** que apareceu no computador

4. O app **GALINT** abrirá automaticamente!
   - Primeira execução pode demorar 30-60 segundos

---

## 🚀 Primeira Execução

### Tela de Login (Configuração)

Na primeira vez que abrir, você verá:

```
┌─────────────────────────────┐
│   Configuração do Servidor  │
├─────────────────────────────┤
│                             │
│  IP do Servidor:            │
│  [10.0.0.245        ]       │
│                             │
│  Porta:                     │
│  [5443              ]       │
│                             │
│  □ Usar HTTPS               │
│                             │
│  [Testar Conexão]           │
│                             │
└─────────────────────────────┘
```

### Preencha:

1. **IP do Servidor:** `10.0.0.245`
2. **Porta:** `5443` (HTTPS) ou `5000` (HTTP)
3. **Usar HTTPS:** ✓ Marque a caixa
4. Clique em **"Testar Conexão"**

### Se aparecer "Conexão OK!":

5. Digite suas **credenciais** de login
6. Marque **"Lembrar de mim"** (opcional)
7. Clique em **"Entrar"**

---

## ⚙️ Configuração do App

### Tela de Estoque

Após fazer login, você verá a lista de itens:

- **Pesquisar:** Campo de busca no topo
- **Atualizar:** Arraste para baixo para recarregar
- **Scanner:** Botão flutuante (câmera) no canto
- **Cadastrar:** Botão + para adicionar item

### Scanner de Código de Barras

1. Toque no botão de **câmera** (flutuante)
2. Permita acesso à câmera se solicitado
3. Aponte para o código de barras
4. O app detecta automaticamente e busca o item
5. Se encontrado: mostra detalhes
6. Se não encontrado: abre tela de cadastro

### Cadastrar Novo Item

1. Via scanner ou botão "+"
2. Preencha:
   - Código de barras (preenchido se via scanner)
   - Descrição do item
   - Categoria
   - Quantidade inicial
   - Unidade (UN, CX, KG, etc.)
   - Localização
   - Marca (opcional)
3. Clique em **"Cadastrar"**

---

## 🔧 Solução de Problemas

### ❌ "Node.js não encontrado"

**Problema:** Script diz que Node.js não está instalado.

**Solução:**
1. Baixe Node.js: https://nodejs.org/
2. Instale a versão LTS
3. Reinicie o PowerShell
4. Execute novamente

---

### ❌ "Cannot connect to Metro"

**Problema:** App não consegue conectar ao servidor de desenvolvimento.

**Solução:**
```powershell
# Limpar cache e reiniciar
npm start -c
```

---

### ❌ "Network request failed"

**Problema:** App não conecta ao servidor Flask.

**Soluções:**

1. **Verificar servidor Flask:**
   ```powershell
   # Deve estar rodando em nova janela
   python app.py
   ```

2. **Testar conexão manual:**
   - Abra navegador no celular
   - Digite: `https://10.0.0.245:5443`
   - Deve carregar a página do GALINT

3. **Verificar rede Wi-Fi:**
   - Celular e computador na MESMA rede
   - Verifique configurações de IP

4. **Tentar HTTP:**
   - Use porta `5000` (HTTP)
   - Desmarque "Usar HTTPS"

---

### ❌ QR Code não aparece

**Problema:** Terminal não mostra QR Code.

**Soluções:**

1. Pressione **`w`** no terminal
   - Abre navegador com QR Code

2. Pressione **`i`** no terminal
   - Mostra URL para digitar manualmente no Expo Go

3. Reiniciar:
   ```powershell
   # Ctrl+C para parar
   # Depois:
   npm start
   ```

---

### ❌ "Permissão de câmera negada"

**Problema:** Scanner não funciona.

**Solução:**
1. Vá em **Configurações** do Android
2. **Apps** → **Expo Go**
3. **Permissões** → **Câmera** → **Permitir**
4. Reinicie o app

---

### ❌ App demora muito para carregar

**Problema:** Primeira execução lenta.

**Normal:**
- Primeira vez pode demorar 1-2 minutos
- Expo baixa dependências no celular
- Aguarde até aparecer a tela de login

**Se continuar lento:**
```powershell
# Limpar cache
npm start -c
```

---

### ❌ "Token inválido" ao fazer login

**Problema:** Credenciais não aceitas.

**Soluções:**

1. Verificar IP/porta corretos
2. Testar conexão antes de fazer login
3. Verificar se usuário existe no sistema
4. Tentar outro usuário

---

## 📞 Verificações Finais

Antes de usar, confirme:

- [ ] Node.js instalado (versão 16+)
- [ ] Expo Go instalado no Android
- [ ] Servidor Flask rodando
- [ ] Celular e PC na mesma rede Wi-Fi
- [ ] Firewall liberando portas 5000/5443
- [ ] QR Code visível no terminal
- [ ] App abrindo no Expo Go

---

## 🎓 Dicas de Uso

1. **Mantenha o servidor rodando:** Não feche a janela do Flask

2. **Evite troca de rede:** Mude para rede móvel desconecta

3. **Use HTTPS:** Mais seguro, especialmente em rede compartilhada

4. **Cache automático:** App funciona offline após carregar dados

5. **Scanner em boa luz:** Câmera precisa de iluminação adequada

---

## 🎉 Tudo Pronto!

Agora você pode:

- ✅ Pesquisar itens no almoxarifado
- ✅ Escanear códigos de barras
- ✅ Cadastrar novos produtos
- ✅ Consultar estoque em tempo real
- ✅ Trabalhar offline (com cache)

**Desenvolvido para GALINT - © 2025**
