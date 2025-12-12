# 🚀 Guia Rápido de Instalação - GALINT Mobile

## 📱 Pré-requisitos

Antes de começar, certifique-se de ter instalado:

1. **Node.js** (versão 16 ou superior)
   - Download: https://nodejs.org/
   - Verifique: `node --version`

2. **Expo Go** no seu smartphone Android
   - Play Store: https://play.google.com/store/apps/details?id=host.exp.exponent

## ⚡ Instalação Rápida

### Passo 1: Abrir terminal na pasta do projeto

```powershell
cd "C:\Users\LUIS\Desktop\GALINT FLASK\galint-mobile"
```

### Passo 2: Instalar dependências

```powershell
npm install
```

Aguarde alguns minutos (baixa ~500MB de pacotes)

### Passo 3: Iniciar o servidor de desenvolvimento

```powershell
npm start
```

### Passo 4: Executar no smartphone

1. Um QR Code aparecerá no terminal
2. Abra o **Expo Go** no seu Android
3. Toque em **"Scan QR Code"**
4. Aponte a câmera para o QR Code
5. O app abrirá automaticamente!

## 🔧 Configuração Inicial no App

1. **IP do Servidor:** `10.0.0.245`
2. **Porta:** `5443` (HTTPS) ou `5000` (HTTP)
3. **Usar HTTPS:** Ativado
4. Clique em **"Testar Conexão"**
5. Se OK, faça login com suas credenciais

## 🎯 Funcionalidades

- ✅ Scanner de código de barras
- ✅ Cadastro rápido de itens
- ✅ Pesquisa no estoque
- ✅ Offline-first (dados em cache)

## 🛠️ Comandos Úteis

```powershell
# Iniciar desenvolvimento
npm start

# Limpar cache (se houver problemas)
npm start -c

# Rodar em emulador Android (requer Android Studio)
npm run android
```

## 📝 Observações Importantes

### Mesma Rede Wi-Fi
O smartphone e o servidor Flask devem estar na **mesma rede Wi-Fi** para comunicação local.

### Firewall
Certifique-se de que o firewall do Windows permite conexões na porta 5000/5443.

### HTTPS
Certificados auto-assinados são aceitos automaticamente no app.

## ❓ Problemas Comuns

### "Cannot connect to Metro"
```powershell
# Solução: Limpar cache
npm start -c
```

### "Network request failed"
- Verifique se o servidor Flask está rodando
- Confirme IP e porta corretos
- Teste com HTTP primeiro (porta 5000)

### QR Code não aparece
```powershell
# Solução: Pressione 'w' no terminal para abrir no navegador
# Ou escaneie manualmente o link exibido
```

## 📱 Build para Produção (Opcional)

Para gerar APK instalável:

```powershell
# Instalar EAS CLI
npm install -g eas-cli

# Fazer build
eas build --platform android --profile preview
```

## 🎉 Pronto!

Agora você tem um app mobile completo para gerenciar o almoxarifado!

---

**Desenvolvido para GALINT - © 2025**
