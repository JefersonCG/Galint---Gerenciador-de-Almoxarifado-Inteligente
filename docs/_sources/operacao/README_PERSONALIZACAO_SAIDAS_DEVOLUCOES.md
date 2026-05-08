# Plano de Estruturacao: Saidas e Devolucoes com Foto, Tela Espelho e Canais Externos

## Objetivo

Evoluir os fluxos de saida e devolucao para um padrao operacional mais visual, claro e reutilizavel, com foco em:

1. exibir foto e resumo do item durante o registro no sistema
2. preparar uma base de estado visual reaproveitavel para uma segunda tela voltada ao colaborador
3. padronizar os dados do evento para envio futuro ao Telegram e ao GalintNotify

## Estado atual do sistema

### O que ja existe

- O cadastro do item ja possui foto em `Item.foto_path`.
- A rota de detalhes do item em movimentacoes ja retorna `foto_path` e `foto_url`.
- A tela de saida usa `movements/saida.mako` com fluxo JS proprio e busca item em `/movimentos/item-info/<codigo>`.
- A tela de devolucao usa `movements/entrada.html` e hoje ainda trabalha com um layout mais simples.
- O Telegram ja possui servico consolidado e infraestrutura para envio de documentos; a camada de bot ja lida com upload/download de midia.

### Gargalos atuais

- Saidas e devolucoes mostram texto demais e contexto visual de menos.
- O colaborador nao ve claramente qual item esta sendo retirado ou devolvido.
- Nao existe ainda um estado operacional visual unico que possa ser espelhado para outro monitor ou enviado a canais externos.
- As telas de saida e devolucao ainda nao compartilham o mesmo padrao de experiencia visual.

## Diretriz de arquitetura

### Principio central

Antes de integrar Telegram, GalintNotify ou segundo monitor, o sistema web precisa gerar um estado operacional visual unico e coerente.

Esse estado deve representar, no minimo:

- tipo do movimento: saida ou devolucao
- codigo do item
- descricao
- categoria
- quantidade
- unidade exibida
- usuario responsavel
- local/finalidade, quando existir
- foto_url
- horario do evento ou da selecao atual

### Razao tecnica

Se cada canal construir a propria representacao, teremos divergencia visual e retrabalho. O web deve virar a fonte primaria do evento visual, e os demais canais apenas consumirem esse formato.

## Fases de implementacao

## Fase 1: Personalizacao visual dentro do sistema

### Objetivo

Adicionar foto e contexto visual nas telas de saida e devolucao, sem mudar regra de negocio nem notificacoes externas.

### Escopo

#### Saida

- Card de preview do item selecionado com:
  - foto
  - descricao
  - codigo
  - categoria
  - saldo
  - quantidade digitada
  - usuario atual
  - local do servico
- Miniatura da foto na lista de itens adicionados.
- Destaque do ultimo item adicionado para confirmar visualmente o que entrou na fila.

#### Saida fracionada

- Preview visual persistente fora do modal com:
  - foto
  - descricao
  - codigo
  - saldo total fracionado
  - quantidade pesada em foco
  - usuario atual
  - local do servico
- Reaproveitamento do mesmo estado visual no modal de pesagem e na futura tela espelho.

#### Devolucao

- Mesmo padrao de preview visual do item.
- Miniatura na lista de itens adicionados.
- Informacoes da devolucao com linguagem visual alinhada a saida.

#### Ferramentas

- Preview visual do item em retirada com:
  - foto
  - descricao
  - codigo
  - categoria
  - saldo
  - quantidade
  - matricula
  - local e observacao
- Miniatura da ferramenta na lista de itens adicionados.
- Compatibilidade com a futura tela espelho sem alterar a regra de custodia.

### Fora do escopo da Fase 1

- Telegram com foto
- GalintNotify com foto
- Segunda tela espelhada
- Persistencia de sessao operacional entre janelas
- WebSocket, SSE ou polling dedicado

### Resultado esperado

- Operador consegue validar visualmente o item antes de registrar.
- Colaborador ja passa a ver um fluxo mais claro no proprio monitor principal.
- A tela ganha base de dados e componentes para o espelhamento futuro.

## Fase 2: Tela espelho para segundo monitor

### Objetivo

Exibir em outra tela, voltada ao colaborador, o item que esta sendo retirado ou devolvido.

### Abordagem recomendada

Criar uma pagina espelho dedicada, sem controles administrativos, que mostre apenas:

- tipo de operacao
- foto grande do item
- descricao
- codigo
- quantidade
- unidade
- nome do colaborador
- status: aguardando, em conferência, registrado

### Modo 1: Mesmo computador, dois monitores

Implementacao recomendada para a primeira versao:

- abrir uma segunda janela do navegador em rota dedicada
- sincronizar estado com `BroadcastChannel` ou evento de `localStorage`
- sem dependencia imediata de backend para streaming

### Modo 2: Outro dispositivo ou outra maquina

Implementacao posterior:

- criar `operation_session_id`
- armazenar estado atual no backend
- usar polling curto ou SSE para atualizacao da tela espelho

### Riscos

- espelhamento local e simples funciona bem para o mesmo PC
- para outro dispositivo, ja exige controle de sessao, expiracao e seguranca de acesso

## Fase 3: Evento operacional unificado

### Objetivo

Padronizar o payload que representara a retirada ou devolucao para qualquer canal.

### Contrato proposto

```json
{
  "event_type": "saida",
  "event_id": "uuid-ou-id-composto",
  "created_at": "2026-03-28T12:34:56Z",
  "item": {
    "codigo": "7898505140030",
    "descricao": "COPO DESCARTAVEL 200ML",
    "categoria": "Material/Uso geral",
    "foto_url": "/static/uploads/items/7898505140030.jpg"
  },
  "movement": {
    "quantidade": 1,
    "unidade": "pacote",
    "observacao": null
  },
  "actor": {
    "matricula": "123",
    "nome": "Fulano"
  },
  "context": {
    "local_servico": "Bloco 5",
    "source": "sistema_web"
  }
}
```

### Beneficio

Com esse contrato:

- a tela espelho consome o mesmo objeto
- o Telegram consome o mesmo objeto
- o GalintNotify consome o mesmo objeto
- o sistema mantem consistencia entre todos os canais

## Fase 4: Telegram com foto

### Objetivo

Enviar notificacao operacional com imagem do item e legenda resumida.

### Estrategia

- implementar `send_photo` no servico Telegram, em paralelo ao `send_document`
- usar `foto_path` local ou URL publica segura
- enviar legenda padronizada com:
  - tipo do movimento
  - item
  - quantidade
  - usuario
  - local

### Observacoes

- se a imagem for apenas local, pode ser enviada por upload multipart
- se houver URL publica estavel, pode ser enviada por URL
- o envio com foto deve ser opcional e tolerante a falhas

## Fase 5: GalintNotify com foto

### Objetivo

Levar o mesmo evento operacional visual para o app/servico de notificacao interno.

### Requisito previo

GalintNotify precisa aceitar payload com `foto_url` ou binario/midia referenciada.

### Recomendacao

Nao integrar antes de o contrato do evento estar estabilizado no sistema web.

## Sequencia recomendada de implementacao

1. Fase 1: preview e foto em saida e devolucao
2. consolidacao do estado visual compartilhado em JS
3. Fase 2: tela espelho local para dois monitores no mesmo PC
4. Fase 3: contrato de evento operacional unificado
5. Fase 4: Telegram com foto
6. Fase 5: GalintNotify com foto

## Viabilidade tecnica

### Foto no sistema

- Viabilidade: alta
- Risco: baixo
- Dependencia: ja atendida

### Segundo monitor no mesmo computador

- Viabilidade: alta
- Risco: medio
- Dependencia: tela espelho e sincronizacao de estado

### Segundo monitor em outro dispositivo

- Viabilidade: media
- Risco: medio para alto
- Dependencia: sessao operacional persistida e atualizacao em tempo real

### Telegram com foto

- Viabilidade: alta
- Risco: medio
- Dependencia: metodo de envio de foto e padrao de legenda

### GalintNotify com foto

- Viabilidade: media
- Risco: medio
- Dependencia: contrato de payload e suporte do consumidor

## Entregaveis da Fase 1

- Tela de saida com preview visual e foto
- Tela de saida fracionada com preview visual e foto
- Tela de devolucao com preview visual e foto
- Tela de retirada de ferramentas com preview visual e foto
- Miniatura nas linhas dos itens adicionados
- Estado JS preparado para reaproveitamento em tela espelho
- Validacao manual e renderizacao via app

## Criterios de aceite da Fase 1

- Ao selecionar ou adicionar item, a foto aparece no preview
- A lista de itens mostra miniatura quando existir foto
- Se nao houver foto, aparece placeholder consistente
- Nenhuma regra de estoque e movimentacao muda
- O fluxo atual de registro continua funcionando

## Observacao operacional

Para testes iniciais, a foto ficara apenas dentro do sistema. Telegram e GalintNotify entram depois que a representacao visual estiver estabilizada e aprovada no uso diario.