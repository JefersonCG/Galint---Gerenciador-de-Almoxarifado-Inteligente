# Changelog - GALINT Mobile

Todas as mudanças notáveis do aplicativo GALINT Mobile serão documentadas neste arquivo.

## [2.6.1] - 2026-11-27 (código 31, c81fef9)

### Adicionado
- **Comandos de voz.** Pedido do usuário: "eu falo 'Retirada lâmpada bolbo 9w kian 6 unidades' e ele abre em retirada com o material que pedi e a quantidade".
  - **A 1ª palavra diz a ação:**
    - Retirada: "retirada", "retirar", "tirar", "dar saída";
    - Devolução: "devolução", "devolver";
    - Alteração (a conferência do item): "alteração", "alterar", "conferir", "contagem", "ajustar".
  - **A quantidade vem no fim**, com a unidade: "6 unidades", "3 peças", "2 caixas", "2 rolos", "meia lata", "uma lata e meia". Também vale "quantidade 4". O "9w" do meio é do material.
  - **Só a ação** ("retirada", "devolução") abre a tela.
  - **Abre direto** quando um item está claramente à frente. Exemplos: a lâmpada da Kian com 6 unidades; "dar saída bucha de redução 50 x 25 3 peças".
  - **Com mais de um item parecido**, a lista aparece com a faixa do comando (ex.: "📤 Retirada · 6 unidades", ✕ cancela) e o toque no item faz o comando.
  - **Sem palavra de comando**, a fala é só busca, como na 2.6.0. Assim "cano 6 metros" não vira quantidade.
- **Toque no item da lista da tela inicial** pergunta: Retirada, Devolução ou Alteração.
  - Zerado: a Retirada aparece apagada e avisa "Estoque zerado".
  - Quem só tem uma opção (gerência: Alteração) vai direto, como antes.
- **App só de retirada** (supervisão e zeladoria): 🎤 grande embaixo dos três botões, com os mesmos comandos (sem Alteração).
- **Retirada:** o 🎤 da própria tela também entende a quantidade ("luva 25 6 unidades").
  - Um item claramente à frente abre direto.
  - Senão, a quantidade vai para o item tocado na lista. Digitar no campo descarta a quantidade falada.
- **Como a quantidade entra:**
  - Retirada (`quantidadeDaFala` em `utils/filaSaidaConta.js`):
    - item com embalagem sai na unidade dita;
    - "2 litros" de tinta que só sai em lata inteira avisa e fica 1;
    - "2 e meio" avisa "dê esta saída no site", porque a Retirada do app só tira inteiro.
  - Devolução (`quantidadeFaladaDevolucao` em `utils/devolucaoConta.js`):
    - lata de 18 L volta em latas;
    - "2 caixas" de item com 100 por caixa = 200;
    - unidade que não dá para converter deixa o campo como era.

## [2.6.0] - 2026-11-27 (código 30, 9fae526)

### Adicionado
- **Retirada e pesquisa de material por voz (🎤)**, na busca da tela inicial e no "Código ou nome" da Retirada.
  - **Escuta:** a do próprio Android em pt-BR (módulo nativo `GalintVoz`, sem biblioteca nova).
  - **Busca (`utils/buscaFalada.js`):**
    - código ditado: "0265" e "0 2 6 5";
    - números por extenso: "dois e meio" = 2,5;
    - unidades faladas: "20 amperes" = "20A", "2 milímetros" = "2MM";
    - abreviação e plural: "adaptador" acha "ADAP.", "redução" acha "RED";
    - erro pequeno do reconhecimento: "wasco" acha "WESCO".
  - **Zerados:** aparecem marcados "ZERADO". Na Retirada não entram na saída.
  - **Mesma busca para texto digitado.**

## [2.5.2] - 2026-11-26 (código 29, b464567)

### Corrigido
- **Formulários limpos depois de registrar saída e devolução** (pedido do usuário).
  - Retirada: local, quem retira, código, item, quantidade, embalagem e custódia voltam vazios. O celular não guarda mais o local e a pessoa da saída anterior; só a fila do que falhou.
  - Devolução: "Concluir" volta para a tela Devolução (rota `Devolucao`). Antes abria a tela antiga "Movimento" por cima, e o formulário preenchido ficava embaixo.
  - Custódia do dia: a seleção é limpa a cada baixa (`resetKey` no `DailyCustodyPanel`).
  - Será que temos!?: voltando de "Retirar", a câmera abre limpa.

## [2.5.1] - 2026-11-26 (código 28, d79cac0)

### Adicionado
- **"Será que temos!?" mostra que a foto foi tirada.** Origem: "a pessoa não sabe se tirou ou não".
  - No toque: vibração, flash branco e ampulheta girando.
  - Foto tirada: a imagem congela e uma tartaruga anda na trilha, com "Procurando…" ou "Preparando a busca…".
  - Só `Animated` nativo, sem biblioteca nova.

## [2.5.0] - 2026-11-26 (código 27, 9dcb676)

### Adicionado
- **Retirada única para todos:** a tela da Fila de saída virou a Retirada.
  - "Dar saída" com um item sai direto, sem pergunta; "Mais um item" guarda e abre o leitor.
  - O campo busca por código ou nome na base do celular, sem os zerados.
  - O leitor com modo de retirada abre esta tela.
- **Devolução em botão próprio:** `MovimentoScreen` fixa na aba Devolução, com leitura de código e baixa de várias ferramentas da custódia.
- **"Será que temos!?" (SeraQueTemosScreen):**
  - foto → itens parecidos (DINOv2 + OpenCLIP no servidor), com foto e saldo;
  - tocar confirma, e a foto vira referência do item; com saldo, aparece "Retirar";
  - no ☰ com contorno na cor do sistema.
- **App só de retirada** (marca `app_so_retirada` do usuário, vinda no login): três botões na tela inicial e menu sem Conferência, Painel, Configurações, Relatórios e "Atualizar a base agora".
- **WhatsApp:** saída de vários itens numa mensagem só, com a foto de cada item (`GalintShare.shareManyToWhatsApp`, `ACTION_SEND_MULTIPLE` com `ClipData`).

### Alterado
- **Menu ☰:** sem as dicas embaixo de cada item.
- **Avisos:** abrir a tela marca todos como lidos; saiu o "Marcar todos".
- **Base do celular:** lista inteira a cada 10 min (antes 30). A pergunta "o que mudou?" continua a cada 15 s.

## [2.4.1] - 2026-11-26 (código 26, f5268a0)

### Adicionado
- **Devolução reconhece ferramenta, fracionado ou unitário** (`GET /api/mobile/devolucao/tipo/<codigo>`).
  - Lata pela metade: botões ¼ ½ ¾ 1, com a conta ao vivo ("½ lata = 9 L").
  - Contas em `utils/devolucaoConta.js`.

### Publicação
- **Pasta:** o APK vai para `D:\Jeferson dos Santos\Projetos\GALINT 08.04.2026\instance\apks\` como `GALINT-<versão>-codigo<código>-<rótulo>.apk`. Um `.txt` com o mesmo nome, sem BOM, vira a nota.
- **Atualização:** os celulares com 2.2.4 ou mais se atualizam sozinhos ao abrir o app.
- **Compilação:** em `C:\gm-src`, ver `README.md` do GALINT.

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
