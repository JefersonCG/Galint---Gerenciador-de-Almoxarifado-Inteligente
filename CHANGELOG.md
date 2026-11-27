# Changelog - GALINT Mobile

Todas as mudanças notáveis do aplicativo GALINT Mobile serão documentadas neste arquivo.

## [2.7.1] - 2026-11-27 (código 34)

### Adicionado
- **🎤 na câmera.** Pedido do usuário: "quando clico em + um item no apk ele deveria dar a opção do microfone na câmera".
  - O leitor aberto pela Retirada ("Mais um item", "Ler código") ou pelo "Ler código" da Devolução ganha o botão "Falar".
  - A fala volta para a tela que abriu o leitor e segue a mesma busca do 🎤 dela: material, quantidade, quem e local.

### Mudado
- **A escuta não fecha numa pausa de 2 s.** Pedido do usuário: "tem como aumentar o tempo de intervalo quando se fala, pois 2 segundos sem falar ele já fecha".
  - Antes: a janela de voz do Google, que encerra sozinha na pausa e ignora o pedido de esperar mais.
  - Agora: escuta própria do app (`components/EscutaVoz.js` e `GalintVoz.comecar` no módulo nativo), sem a janela do Google.
    - Quando o reconhecedor do Android fecha um trecho na pausa, ela recomeça na hora e junta o texto.
    - Termina com 4 s sem fala (8 s antes da primeira palavra) ou no botão "Pronto"; ✕ cancela.
    - O texto aparece enquanto a pessoa fala.
  - Na primeira vez, o app pede a permissão do microfone.
  - Sem a permissão, ou sem o reconhecedor do Android, volta para a janela do Google.

## [2.7.0] - 2026-11-27 (código 33, 994b829)

### Adicionado
- **Login pelo nome, depois a senha, depois a digital.** Pedido do usuário para os celulares da supervisão e da zeladoria: "só terá um campo de digite seu nome; eles digitam, aparece outro campo digite sua senha; após a senha, se houver leitor de biometria vai pedir a biometria, se não ele já acessa o GALINT".
  - Um campo "Digite seu nome". O campo "Digite sua senha" aparece quando o nome é digitado.
  - O nome pode ser só o primeiro, sem acento ("isaias" acha ISAÍAS). Dois primeiros nomes iguais pedem o nome completo e mostram a lista.
  - Quem tem plantão confirma com a digital depois da senha. Sem leitor, ou sem digital cadastrada no celular, entra direto.
  - Celular dividido pela equipe:
    - não há entrada só pela digital;
    - o cofre da digital é apagado no login;
    - o nome não fica guardado para o próximo.
  - Quem não tem plantão entra como antes, com a opção "Entrar com digital".
- **Fim do plantão.** Pedido do usuário: "todos eles são plantonista 12 por 36, pegam de 07h às 19h; sempre que encerrar essa carga horária o sistema deslogará o usuário, para ninguém usar o usuário dele".
  - O plantão é marcado em Usuários no site, com os campos "Plantão __ às __". Já vem 07:00–19:00 para quem tem "App só de retirada".
  - O login só passa dentro do plantão, a partir de 30 min antes do início. Fora dele: "Fora do seu plantão (07h às 19h)."
  - No fim do plantão, o app sai sozinho e mostra "Plantão encerrado.".
  - O servidor também recusa todo pedido depois do fim, mesmo com o app aberto ou desatualizado.
  - Servidor: GALINT 5c4344ae. Vale depois de religar o GALINT.

### Mudado
- Avisos de login sem "(HTTP 403)"; só erro do servidor mostra o código.
- Sai o texto "Depois de entrar com a senha, você pode ligar a entrada pela digital" (tela limpa).

## [2.6.2] - 2026-11-27 (código 32, 132b65d)

### Adicionado
- **Quem retira ou devolve e o local, ditos no comando.** Pedido do usuário: "Retirada por/para Gláucia de 5 papel toalhas interfolhas para local das áreas comuns e banheiros".
  - O nome e o local vão para a tela seguinte, também quando o material aparece numa lista e a pessoa escolhe o item.
  - "por/para <nome>" logo depois da ação vai até a quantidade. Também vale no fim da frase ("… para Gláucia"), mas só com nome do cadastro.
  - "local …" vai até o fim da frase.
  - Nomes falados: "Rafael" acha RAPHAEL, "Luiz" acha LUÍZ, "Isaias" acha ISAÍAS. Duas pessoas parecidas (dois JÚLIOs) abrem a lista já com o nome dito.
  - Quem não escolhe quem retira (fora administrador e gerente) recebe o aviso "A retirada fica no seu nome".
  - A Devolução não tem campo de local; o local dito é ignorado lá.
- **Quantidade antes do material:** "de 5 papel toalhas". "20 amperes" e "50 x 25" continuam sendo do material.
- **"5 pacotes ou 5 unidades?"** quando a unidade não é dita e o item tem embalagem (papel toalha: pacote com 1.000). Vale na Retirada e na Devolução.
- **Comando "custódia":** "custódia furadeira", "com quem está a trena", "custódia da Gláucia", ou "custódia" sozinha para ver todas.
  - Abre a tela Custódia: ferramenta, com quem está, desde quando, dias, local, PERMANENTE e ATRASADA.
  - O item da lista que é ferramenta ganha a opção 🧰 Custódia.
  - Rota nova do servidor `/api/mobile/custodia` (GALINT 024e0d56), com a mesma conta da página Custódia do site. Vale depois de religar o GALINT; antes disso, a tela avisa "Custódia indisponível agora".

### Corrigido
- **Devolução limpa.** Pedido do usuário: "remove essas informações de custódia daqui, deixe limpo".
  - A tela tem só "Ler código" e "Código, nome ou 🎤", a mesma busca da Retirada.
  - A baixa de várias ferramentas da custódia do dia continua no site.
- **"Concluir" da devolução volta para onde a devolução começou.** Antes ia sempre para a tela Devolução, que abria por cima da tela inicial com a custódia do dia. Relato do usuário: "após uma devolução, o apk abriu essa página".
- **Devolução recusada diz o motivo** (servidor 024e0d56).
  - Antes: "não há retirada pendente para este material". Exemplo: a LUVA CORRER SOLDA 25MM, cuja única retirada já tinha voltado.
  - Agora: "Já devolvida: a última retirada (1 unidade, ISAQUE GABRIEL, 07/08/2026) voltou em 04/09/2026."
  - Devolução feita por outra pessoa abate a retirada de quem retirou, como o site.

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
