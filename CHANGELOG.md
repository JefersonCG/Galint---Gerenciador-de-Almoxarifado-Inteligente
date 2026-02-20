# Changelog - GALINT Mobile

Todas as mudanças notáveis do aplicativo GALINT Mobile serão documentadas neste arquivo.

## [1.3.0] - 2026-01-31

### ✨ Adicionado
- **Sistema de Rastreabilidade Completo**
  - Campo "Data de Entrada" com DatePicker
  - Campo "Data de Fabricação" com DatePicker
  - Campo "Data de Validade" com contador de dias regressivo
  - Alerta visual quando produto está próximo do vencimento (≤30 dias)
  - Lote gerado automaticamente pelo backend (formato LOTE-YYYYMMDD-XXXX)
  - Barcode gerado automaticamente como PNG Code128

- **Unidades Dinâmicas de Conversão**
  - Seletor de tipo de embalagem (Lata, Rolo, Pacote, Caixa)
  - Campo "Grandeza de Referência" com labels dinâmicos
  - Campo "Densidade" para conversão Kg↔Lt (apenas para Latas)
  - Preview em tempo real de conversões:
    - Lata: Unidades → Kg → Litros
    - Rolo: Unidades → Metros → Centímetros
    - Pacote/Caixa: Embalagens → Unidades totais

- **Design Soft Depth (UI/UX)**
  - Página única contínua sem cards pesados
  - Sombras suaves e profundidade visual
  - Campos condicionais com destaque dinâmico
  - Animações de entrada suave (slideDown, fadeIn)
  - Responsividade mobile-first
  - Cores e espaçamentos consistentes

### 🔧 Corrigido
- Problema de permissão para administradores cadastrarem itens
- Validação de `is_admin` agora normalizada (boolean, int, string)
- Sincronização de token JWT mais robusta
- Debug logs detalhados para troubleshooting de autenticação

### 📝 Melhorado
- Formulário de cadastro reorganizado em 4 seções lógicas:
  1. Identificação
  2. Classificação
  3. Rastreabilidade (NOVO)
  4. Unidades Dinâmicas (NOVO)
- Feedback visual aprimorado (conversões, validade, estados)
- Validações client-side mais inteligentes

### 🔄 Mudanças no Backend (Requeridas)
- Endpoint `/api/mobile/estoque` agora aceita:
  - `data_entrada` (string ISO date)
  - `data_fabricacao` (string ISO date)
  - `data_validade` (string ISO date)
  - `tipo_embalagem` (string: Lata, Rolo, Pacote, Caixa)
  - `grandeza_referencia` (float)
  - `densidade` (float)
- Geração automática de `lote` e `barcode_image_path` no backend

## [1.2.2] - 2026-01-XX

### 🔧 Corrigido
- Estabilidade geral
- Sincronização offline

## [1.2.0] - 2025-12-XX

### ✨ Adicionado
- Modo offline com fila de sincronização
- Cadastro múltiplo de itens
- Scanner de código de barras otimizado

### 🔧 Corrigido
- Crashes durante entrada de dados
- Timeouts de rede

## [1.1.0] - 2025-11-XX

### ✨ Adicionado
- Painel de relatórios
- Devolução de ferramentas e materiais
- Notificações push

### 🔧 Corrigido
- Layout responsivo
- Performance em listas grandes

## [1.0.0] - 2025-10-XX

### ✨ Lançamento Inicial
- Login/Autenticação JWT
- Listagem de estoque
- Cadastro de itens
- Retirada de materiais
- Configurações

---

## Legendas

- ✨ Adicionado - Novas funcionalidades
- 🔧 Corrigido - Bugs resolvidos
- 📝 Melhorado - Melhorias existentes
- 🔄 Mudanças - Alterações não retrocompatíveis
- 🗑️ Removido - Funcionalidades descontinuadas
- 🔒 Segurança - Vulnerabilidades corrigidas

---

**Formato:** Baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)
**Versionamento:** [Semantic Versioning](https://semver.org/)
