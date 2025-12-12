# GALINT Mobile - App Android para Almoxarifado

Aplicativo mobile para gerenciamento de almoxarifado com scanner de código de barras.

## 🚀 Instalação Rápida

### Método Automático (Recomendado)

1. Clique com botão direito em `instalar_e_rodar.ps1`
2. Selecione **"Executar com PowerShell"**
3. Aguarde instalação (3-5 minutos)
4. Escaneie o QR Code com o app **Expo Go**

### Método Manual

```powershell
npm install
npm start
```

## 📱 Funcionalidades

- ✅ **Login seguro** com teste de conexão
- ✅ **Scanner de código de barras** usando câmera
- ✅ **Cadastro de itens** direto pelo celular
- ✅ **Pesquisa no estoque** com filtros
- ✅ **Suporte HTTPS** com certificados auto-assinados
- ✅ **Cache offline** para trabalhar sem internet

## 📋 Pré-requisitos

### No Computador:
- Node.js 16+ ([Download](https://nodejs.org/))
- Servidor Flask rodando

### No Celular:
- Android com app **Expo Go** ([Play Store](https://play.google.com/store/apps/details?id=host.exp.exponent))
- Mesma rede Wi-Fi que o computador

## ⚙️ Configuração no App

Na primeira tela:

- **IP do Servidor:** `10.0.0.245`
- **Porta:** `5443` (HTTPS) ou `5000` (HTTP)
- **Usar HTTPS:** ✓ Ativado

Clique em **"Testar Conexão"** antes de fazer login.

## 📱 Estrutura do App

```
galint-mobile/
├── App.js                 # Ponto de entrada
├── src/
│   ├── screens/
│   │   ├── LoginScreen.js        # Tela de login e configuração
│   │   ├── EstoqueScreen.js      # Tela principal do estoque
│   │   ├── CadastroScreen.js     # Cadastro de itens
│   │   └── ScannerScreen.js      # Scanner de código de barras
│   ├── components/
│   │   ├── ItemCard.js           # Card de item do estoque
│   │   └── ConnectionTest.js     # Componente de teste de conexão
│   ├── services/
│   │   └── api.js                # Serviço de comunicação com backend
│   └── utils/
│       └── storage.js            # AsyncStorage para salvar configurações
├── package.json
└── app.json              # Configuração do Expo
```

## 🔌 Configuração do Servidor

No app, configure:
- **IP do Servidor:** `10.0.0.245` (ou IP do seu servidor)
- **Porta:** `5443` (HTTPS) ou `5000` (HTTP)
- **Protocolo:** Automático (tenta HTTPS primeiro)

## 🔐 Segurança

- Login usa autenticação do backend Flask
- Suporte a HTTPS (certificados auto-assinados são aceitos)
- Token de sessão armazenado localmente

## 📦 Tecnologias Utilizadas

- **React Native** - Framework mobile
- **Expo** - Plataforma de desenvolvimento
- **expo-camera** - Acesso à câmera
- **expo-barcode-scanner** - Scanner de códigos
- **axios** - Requisições HTTP
- **AsyncStorage** - Armazenamento local

## 🎨 Design

Interface minimalista com foco em:
- Facilidade de uso com uma mão
- Scanner rápido e preciso
- Feedback visual claro
- Modo offline (cache de dados)

## 📝 Licença

© 2025 GALINT - Gestão de Almoxarifado Integrada
