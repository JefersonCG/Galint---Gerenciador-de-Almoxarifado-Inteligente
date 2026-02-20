# 📱 GALINT Mobile - Gestão de Almoxarifado em Campo

> **Aplicativo móvel profissional para controle de estoque com relatórios corporativos integrados**

[![Expo SDK](https://img.shields.io/badge/Expo-54.0.0-blue.svg)](https://expo.dev/)
[![React Native](https://img.shields.io/badge/React%20Native-0.81.5-61DAFB.svg)](https://reactnative.dev/)
[![EAS Build](https://img.shields.io/badge/EAS%20Build-Ready-green.svg)](https://expo.dev/eas)

---

## 🎯 Visão Geral

O **GALINT Mobile** é um aplicativo nativo Android desenvolvido com React Native/Expo que revoluciona a operação de almoxarifado ao trazer **autonomia completa** para o campo. Conectado ao servidor Flask via API REST, oferece funcionalidades empresariais que eliminam a dependência de computadores para tarefas críticas do dia-a-dia.

### 🚀 Diferenciais de Mercado

#### 1. **Sistema de Relatórios Corporativos Móvel**
- **Primeira solução mobile** com geração de relatórios PDF/XLSX profissionais
- Cabeçalho corporativo padronizado (empresa, CNPJ, endereço)
- Filtros avançados: diário/mensal, por escopo (ferramentas/materiais/geral)
- **Compartilhamento direto** via WhatsApp, email, drive (expo-sharing)
- **Uso offline**: relatórios salvos localmente após download

🔥 **Diferencial único**: Enquanto apps de estoque tradicionais exigem acesso web para relatórios, o GALINT Mobile gera documentos auditáveis **diretamente no celular** do operador.

#### 2. **Menu de Navegação Centralizado**
- Arquitetura moderna: Home → Menu → Funcionalidades
- **Perfil de Usuário**: Visualização completa de dados (nome, matrícula, cargo, telefone, Telegram)
- **Configurações**: API server, timeouts, modo debug
- **Relatórios**: Hub dedicado para acesso rápido a análises

🔥 **Diferencial**: UX profissional semelhante a apps bancários, não apenas "listagens de estoque".

#### 3. **Controle Granular de Permissões**
- **Restrição por perfil**: Apenas Admin/Manager podem cadastrar/editar itens
- Operadores visualizam e retiram, gerentes controlam cadastro
- Validação no frontend (React) e backend (Flask)

🔥 **Diferencial**: Governança robusta evitando cadastros incorretos por usuários sem treinamento.

#### 4. **Filtros Interativos por Categoria**
- **Cards clicáveis** com ícones visuais (🔧 🏗️ ⚡ 🔩)
- Filtro instantâneo ao tocar categoria
- Resumo quantitativo: total de itens por categoria

🔥 **Diferencial**: Navegação tátil otimizada para uso com luvas ou em movimento.

#### 5. **Integração Total com Backend Corporativo**
- Sincronização bidirecional: alterações refletem em tempo real
- **TimeService**: timestamps sincronizados via atomic clocks (worldtimeapi.org)
- Autenticação JWT com tokens temporais seguros
- API RESTful documentada com 15+ endpoints

🔥 **Diferencial**: Arquitetura enterprise-grade, não apenas um "app simples de estoque".

---

## ✨ Funcionalidades Principais

### 📊 **Relatórios Avançados** *(Novidade v1.2.0)*

#### Relatórios Diários
- **Escopos disponíveis**:
  - 🔧 Ferramentas (apenas categorias com "ferramenta")
  - 🏗️ Materiais (exclusão de ferramentas)
  - 📦 Geral (todos os itens)
- **Formatos**: PDF (impressão/assinatura) e XLSX (análise/edição)
- **Conteúdo**:
  - Listagem completa de retiradas do dia
  - Código reduzido (5 dígitos) para economia de espaço
  - Data compacta: `19/1/26 - 18h41m`
  - Marca, quantidade, usuário, observações
  - **Marcação de devoluções**: flag visual "⚠️ DEVOLUÇÃO" quando aplicável
  - Footer com timestamp de geração

#### Relatórios Mensais
- **Seleção de período**: Chips para 12 meses + 4 anos
- **Mesmos escopos e formatos** do relatório diário
- Resumo por categoria incluído (aba separada no XLSX)
- Ideal para auditorias e prestação de contas

#### Compartilhamento
- **expo-sharing**: integração nativa com Android Share Sheet
- Envio direto para: WhatsApp, Gmail, Drive, Slack, etc.
- Arquivo mantido localmente: acesso offline pós-download

### 📱 **Menu Centralizado** *(Novidade v1.2.0)*

Acessível via botão ⚙️ na tela de Estoque:

#### 👤 Perfil de Usuário
- Nome completo
- Matrícula funcional
- Cargo
- Telefone
- ID Telegram (se configurado)
- Badges visuais: Admin/Manager/Operador

#### ⚙️ Configurações
- URL do servidor API
- Timeout de requisições
- Modo debug (para troubleshooting)
- Cache de autenticação

#### 📈 Relatórios
- Acesso rápido a Daily/Monthly
- Histórico de downloads recentes (planejado)

### 📦 **Gestão de Estoque**

#### Visualização
- **Cards de categoria clicáveis** com filtro imediato
- Lista de itens: código, descrição, quantidade, localização
- Indicadores visuais: estoque baixo (⚠️), zerado (🔴)
- Busca textual em tempo real

#### Movimentações
- **Retirada**: quantidade, observação, confirmação
- **Devolução**: 
  - Ferramentas: gera evento "devolução_ferramenta" 
  - Materiais: gera evento "devolucao_material"
  - Descrição obrigatória do que foi devolvido
  - Integração com InventarioEvento para auditoria
- **Entrada**: NF, fornecedor, quantidade (admin/manager)

#### Cadastro *(Admin/Manager apenas)*
- Formulário completo: código, descrição, categoria, marca, unidade
- Localização física, estoque mínimo
- Validações: duplicidade, campos obrigatórios
- Upload de foto (planejado)

### 🔐 **Autenticação e Segurança**

- Login via matrícula ou Telegram ID
- **Tokens JWT** com expiração configurável
- AsyncStorage para persistência segura
- Logout com limpeza de cache
- Revalidação automática em chamadas API

---

## 🏗️ Arquitetura Técnica

### Stack Tecnológico

```
Frontend:
├── React Native 0.81.5
├── Expo SDK 54.0.0
├── React Navigation 6.x (native stack)
├── expo-file-system 17.0.1 (download de arquivos)
├── expo-sharing 13.0.1 (compartilhamento nativo)
└── AsyncStorage (persistência local)

Backend Integration:
├── Axios (HTTP client)
├── JWT Authentication
└── REST API (15 endpoints)

Build & Deploy:
├── EAS Build (APK nativo)
├── EAS Update (OTA updates)
└── PowerShell automation scripts
```

### Fluxo de Dados

```
Mobile App (React Native)
    ↓ HTTP/JWT
Flask REST API (galint_flask/views/api_mobile.py)
    ↓ SQLAlchemy
PostgreSQL Database
    ↑ Queries
TelegramService (geração de relatórios)
    → ReportLab (PDF) / OpenPyXL (XLSX)
    → expo-file-system (salvar local)
    → expo-sharing (compartilhar)
```

### Estrutura do Projeto

```
galint-mobile/
├── App.js                    # Navigator principal
├── src/
│   ├── screens/
│   │   ├── LoginScreen.js       # Autenticação
│   │   ├── EstoqueScreen.js     # Lista + filtros por categoria
│   │   ├── MenuScreen.js        # Hub de navegação (novo)
│   │   ├── ProfileScreen.js     # Perfil do usuário (novo)
│   │   ├── ReportsScreen.js     # Hub de relatórios (novo)
│   │   ├── ReportsDailyScreen.js   # Relatório diário (novo)
│   │   ├── ReportsMonthlyScreen.js # Relatório mensal (novo)
│   │   ├── CadastroScreen.js    # Cadastro (admin/manager)
│   │   ├── RetiradaScreen.js    # Retirada de item
│   │   └── DevolucaoScreen.js   # Devolução
│   └── services/
│       └── api.js               # Client Axios + helpers
├── eas.json                  # Perfis de build
├── app.json                  # Config Expo
└── build_apk.ps1            # Script automático de build
```

---

## 📥 Instalação e Deploy

### Desenvolvimento (Expo Go)

```powershell
# Na pasta galint-mobile
npm install
npm start

# No celular: Expo Go → Scan QR Code
```

### Produção (APK Nativo)

**Build automatizado via EAS:**

```powershell
.\build_apk.ps1 -Profile "preview" -ExpoToken "SEU_TOKEN_EXPO"
```

**O que o script faz:**
1. Verifica Node.js v20.19.6
2. `npm install` (dependências)
3. `eas build -p android --profile preview`
4. Gera APK assinado com credenciais Expo

**Resultado:**
- APK disponível em: `https://expo.dev/accounts/{account}/projects/galint-mobile/builds/{id}`
- Instalação direta via download no celular

### OTA Updates (Over-The-Air)

Para atualizar JavaScript/UI **sem rebuild**:

```powershell
cd galint-mobile
npx eas-cli update --channel preview --message "Descrição da atualização"
```

⚠️ **Limitação**: Apenas código JS. Para mudanças em dependências nativas (expo-file-system, expo-sharing), é necessário **rebuild do APK**.

---

## 🔄 Atualizações Recentes (v1.2.0)

### 🆕 Janeiro 2026 - Módulo de Relatórios Corporativos

**Backend (Flask):**
- ✅ Novos endpoints: `/api/mobile/reports/daily` e `/api/mobile/reports/monthly`
- ✅ Parâmetros: `scope` (all/tools/materials), `format` (pdf/xlsx), `month`, `year`
- ✅ Cabeçalho corporativo padronizado em todos os PDFs
- ✅ Footer com timestamp sincronizado (TimeService)
- ✅ Paginação: 25 itens/página em relatórios impressos
- ✅ Filtro de devoluções: apenas ferramentas marcadas no relatório
- ✅ `galint_flask/services/telegram_reports.py`: novos métodos generate_daily_xlsx(), generate_monthly_pdf_report()

**Mobile:**
- ✅ MenuScreen: navegação centralizada (Perfil, Config, Relatórios)
- ✅ ProfileScreen: exibição completa de dados do usuário
- ✅ ReportsScreen: hub de acesso a Daily/Monthly
- ✅ ReportsDailyScreen: 3 escopos × 2 formatos = 6 botões de download
- ✅ ReportsMonthlyScreen: seleção de mês/ano + download/share
- ✅ Integração expo-file-system (download) + expo-sharing (compartilhamento)
- ✅ EstoqueScreen: categoria cards agora clicáveis para filtro
- ✅ CadastroScreen: restrição admin/manager com validação useEffect

**Segurança:**
- ✅ Permissões: isAdminOrManager() valida cargo/is_admin/is_manager
- ✅ Alert + goBack() quando usuário sem permissão tenta acessar cadastro

**Impacto no Uso Diário:**
- 🎯 **Autonomia**: Operadores geram relatórios no campo sem PC
- 🎯 **Agilidade**: Compartilhamento instantâneo para WhatsApp/email
- 🎯 **Governança**: Restrições impedem cadastros indevidos
- 🎯 **Rastreabilidade**: Todo relatório tem timestamp + user + escopo

---

## 🆚 Comparação com Concorrentes

| Funcionalidade | GALINT Mobile | Apps Tradicionais |
|---|---|---|
| **Relatórios no celular** | ✅ PDF/XLSX nativos | ❌ Apenas web |
| **Compartilhamento direto** | ✅ WhatsApp/email | ❌ Download + upload manual |
| **Filtros por escopo** | ✅ 3 níveis (tools/mat/all) | ⚠️ Limitado |
| **Cabeçalho corporativo** | ✅ CNPJ + logo + endereço | ❌ Genérico |
| **Permissões granulares** | ✅ Admin/Manager/Operador | ⚠️ Apenas on/off |
| **Menu centralizado** | ✅ UX moderna | ❌ Tabs simples |
| **Perfil de usuário** | ✅ Completo | ❌ Apenas nome |
| **Sincronização tempo** | ✅ Atomic clocks API | ❌ Relógio local |
| **Devolução rastreável** | ✅ Tipo + descrição | ⚠️ Simples entrada |
| **OTA Updates** | ✅ Expo Updates | ❌ Requer APK |

---

## 🔧 Configuração Avançada

### Variáveis de Ambiente (Backend)

Necessárias para funcionamento completo:

```powershell
$env:GALINT_DATABASE_URI = 'postgresql://user:pass@10.0.0.245:5432/galint_db'
$env:GALINT_SECRET_KEY = 'chave-segura-256-bits'
$env:GALINT_TELEGRAM_POLLING = 'true'  # Se usar Telegram
$env:GALINT_TELEGRAM_OUTBOX_ENABLED = 'true'
```

### API Endpoints Utilizados

```
POST   /api/mobile/login           # Autenticação
GET    /api/mobile/estoque         # Lista itens
GET    /api/mobile/categorias      # Categorias únicas
POST   /api/mobile/retirada        # Registrar saída
POST   /api/mobile/devolucao       # Devolução ferramenta
POST   /api/mobile/devolucao_material  # Devolução material
GET    /api/mobile/reports/daily   # Relatório diário (PDF/XLSX)
GET    /api/mobile/reports/monthly # Relatório mensal (PDF/XLSX)
POST   /api/mobile/cadastro        # Novo item (admin)
GET    /api/mobile/health          # Health check
```

Documentação completa: [API_ENDPOINTS.md](API_ENDPOINTS.md)

---

## 🐛 Troubleshooting

### Tela Branca após OTA Update

**Causa:** Dependências nativas (`expo-file-system`, `expo-sharing`) não podem ser entregues via OTA.

**Solução:**
```powershell
# Gerar novo APK completo
.\build_apk.ps1 -Profile "preview" -ExpoToken "..."
```

### Network Error ao Baixar Relatório

**Causa:** Token JWT expirado ou servidor inacessível.

**Solução:**
1. Verificar conectividade: abrir `http://10.0.0.245:5000/api/mobile/health` no navegador do celular
2. Fazer logout e login novamente para renovar token
3. Conferir timeout em ConfigScreen (padrão: 30s)

### Permissão Negada ao Compartilhar

**Causa:** App sem permissão de armazenamento (Android 10+).

**Solução:**
1. Configurações → Apps → GALINT → Permissões
2. Ativar "Armazenamento"
3. No Android 11+, usar Scoped Storage (já implementado via expo-sharing)

### Categoria não Filtra

**Causa:** SearchQuery não sendo aplicado no useEffect.

**Solução:** Verificar [EstoqueScreen.js](src/screens/EstoqueScreen.js#L45) método `handleCategoriaPress()`.

---

## 📚 Documentação Adicional

- [GUIA_COMPLETO.md](GUIA_COMPLETO.md) - Instalação passo-a-passo
- [API_ENDPOINTS.md](API_ENDPOINTS.md) - Documentação da API REST
- [OTA_EAS_UPDATE.md](OTA_EAS_UPDATE.md) - Sistema de updates
- [INSTALACAO.md](INSTALACAO.md) - Setup ambiente dev

---

## 🤝 Suporte e Contato

**Sistema:** GALINT - Gestão de Almoxarifado Integrado  
**Versão:** 1.2.0 (Janeiro 2026)  
**Runtime:** Expo SDK 54 / React Native 0.81.5  

**Desenvolvedor:** [Sua Empresa]  
**Repositório:** [Privado]  

---

## 📄 Licença

Propriedade privada. Todos os direitos reservados.

---

**🚀 GALINT Mobile - Gestão Profissional, Autonomia Total**
