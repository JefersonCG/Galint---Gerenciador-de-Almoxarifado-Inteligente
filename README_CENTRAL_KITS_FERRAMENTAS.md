# Central de Kits de Ferramentas

## Visao geral

Este documento descreve a futura pagina operacional para controle absoluto de kits de ferramentas e EPI por colaborador.

O objetivo do modulo e transformar a bolsa Wonder em uma bolsa-chave auditavel. Cada bolsa passa a representar um kit real, vinculado a um colaborador, contendo ferramentas e itens adicionais que podem ser consultados, auditados, expandidos e relatados em PDF.

O sistema precisa responder, sem ambiguidade:

1. Quem esta com qual bolsa.
2. O que existe dentro da bolsa neste momento.
3. O que faz parte do kit padrao e o que foi agregado depois.
4. Qual e o valor total sob responsabilidade do colaborador.
5. O que foi perdido, quebrado, devolvido, substituido ou removido.
6. Quem autorizou cada alteracao.
7. Qual e o tipo de custodia atual.

---

## Nome recomendado do modulo

Nome recomendado para a pagina principal: **Central de Kits de Ferramentas**.

Nome recomendado para a acao principal: **Montar Kit**.

Nome recomendado para a bolsa Wonder dentro da regra de negocio: **Bolsa-chave**.

Essa nomenclatura deixa claro que:

1. A pagina principal e de gestao.
2. A montagem do kit e uma acao operacional.
3. A bolsa Wonder nao e um acessorio solto: ela e a referencia-mae do kit.

---

## Grupos-base de kits

O modulo deve nascer com dois grupos-base:

1. Eletricistas.
2. Manutencao Geral.

O grupo de Manutencao Geral cobre, inicialmente:

1. 1/2 oficial de manutencao.
2. Bombeiro hidraulico.
3. Oficial de manutencao.

Cada grupo pode ter um modelo-padrao de kit diferente.

---

## Raciocinio operacional

O kit nao deve ser tratado como vinte retiradas manuais separadas.

Ele deve ser tratado como uma operacao consolidada, com uma bolsa-chave e uma composicao interna.

Exemplo simplificado:

1. A bolsa Wonder do Antonio recebe um kit padrao de eletricista.
2. Esse kit contem vinte itens entre ferramentas e EPI.
3. O sistema registra uma operacao-pai do kit.
4. O sistema registra os itens-filhos da composicao.
5. O Telegram recebe uma notificacao consolidada da entrega do kit, e nao vinte mensagens independentes.

---

## Bolsa-chave

A bolsa Wonder tem dupla funcao:

1. Ela continua sendo um item de estoque/ferramenta.
2. Ela passa a ser a chave operacional do kit.

Em termos práticos, a bolsa-chave precisa permitir:

1. Identificar o kit de forma unica.
2. Abrir a tela do kit daquele colaborador.
3. Listar tudo que existe dentro da bolsa.
4. Relacionar fotos, valores, ocorrencias e historico.
5. Servir de ancora para auditoria patrimonial.

---

## Tipos de custodia

O modulo precisa suportar troca de tipo de custodia.

Tipos recomendados:

1. Diaria.
2. Permanente.
3. Temporaria especial.

Regra operacional inicial:

1. O kit pode ficar vinculado ao colaborador.
2. Mesmo assim, a devolucao diaria pode ser obrigatoria para determinados cenarios.
3. O tipo de custodia deve poder ser alterado com justificativa e auditoria.

---

## O que deve aparecer ao abrir a bolsa do Antonio

Ao abrir a bolsa do Antonio, o usuario precisa ver uma representacao digital completa do conteudo da bolsa.

Blocos principais:

1. Resumo da bolsa.
2. Conteudo atual.
3. Itens padrao do kit.
4. Itens extras agregados depois.
5. EPI vinculados.
6. Ocorrencias de perda e quebra.
7. Historico auditavel.
8. Gerador de PDF patrimonial.

---

## Resumo da bolsa

O cabecalho da bolsa deve exibir:

1. Nome do colaborador.
2. Matricula.
3. Grupo do kit.
4. Bolsa-chave vinculada.
5. Tipo de custodia atual.
6. Status do dia.
7. Quantidade total de itens.
8. Valor total do kit.
9. Ultima auditoria.
10. Pendencias criticas.

---

## Conteudo atual da bolsa

Cada item da bolsa deve mostrar:

1. Foto do item.
2. Descricao.
3. Codigo.
4. Categoria.
5. Quantidade.
6. Valor unitario congelado no contexto patrimonial.
7. Valor total daquele item dentro do kit.
8. Status do item.
9. Origem do item: padrao ou extra.

Status recomendados:

1. Em posse.
2. Devolvido.
3. Perdido.
4. Quebrado.
5. Em reposicao.
6. Em analise.

---

## Ferramentas e EPI no mesmo kit

O kit nao deve aceitar apenas ferramentas.

Ele deve aceitar qualquer item elegivel do estoque, inclusive:

1. Ferramentas manuais.
2. Ferramentas eletricas.
3. Bolsa Wonder.
4. Calca.
5. Bota.
6. Oculos.
7. Protetor auricular.
8. Luvas.
9. Demais EPI cadastrados no estoque.

O criterio correto nao e categoria fixa. O criterio correto e:

**item permitido em composicao de kit**.

---

## Agregar mais ferramentas e EPI

Ao abrir a bolsa do Antonio, o sistema precisa permitir adicionar mais itens.

Essa acao deve permitir:

1. Buscar item no estoque.
2. Validar saldo disponivel.
3. Definir quantidade.
4. Marcar se o item e extra operacional ou se passou a integrar o padrao daquela bolsa.
5. Registrar motivo da agregacao.
6. Auditar quem executou a acao.

---

## Operacao consolidada de kit

O kit deve registrar uma operacao-pai e varios itens-filhos.

Isso vale para:

1. Montagem inicial.
2. Entrega do kit.
3. Devolucao diaria.
4. Reentrega.
5. Agregacao de novo item.
6. Remocao de item.
7. Reposicao de item perdido.
8. Substituicao por quebra.

Beneficios:

1. Uma notificacao consolidada.
2. Um lote auditavel.
3. Uma linha do tempo coerente.
4. Relatorio PDF confiavel.

---

## PDF patrimonial da bolsa

Cada bolsa deve ter geracao de PDF completa.

O relatorio deve conter:

1. Dados do colaborador.
2. Dados da bolsa-chave.
3. Grupo do kit.
4. Tipo de custodia atual.
5. Data e hora de emissao.
6. Conteudo atual da bolsa.
7. Itens padrao.
8. Itens extras.
9. Valor unitario por item.
10. Valor total por item.
11. Valor total consolidado da bolsa.
12. Itens perdidos.
13. Itens quebrados.
14. Itens removidos.
15. Linha do tempo das ultimas alteracoes.
16. Nome do administrador que gerou o PDF.

Importante:

O PDF deve usar o valor do item no momento do evento patrimonial relevante, e nao recalcular apenas pelo preco atual do cadastro.

---

## Modal de perdeu

Quando o administrador ou operador registrar perda, o modal deve exigir:

1. Item afetado.
2. Quantidade.
3. Motivo.
4. Data da ocorrencia.
5. Responsavel pelo registro.
6. Observacao complementar.
7. Acao de destino.

Acoes de destino recomendadas:

1. Baixa patrimonial.
2. Reposicao pendente.
3. Analise administrativa.

---

## Modal de quebrou

Quando o item quebrar ou for danificado, o modal deve exigir:

1. Item afetado.
2. Quantidade.
3. Motivo.
4. Descricao do dano.
5. Foto obrigatoria da quebra ou do avariado.
6. Responsavel pelo registro.
7. Data e hora.
8. Destino do item.

Destinos recomendados:

1. Enviar para reparo.
2. Baixar como perda tecnica.
3. Manter em analise.
4. Substituir imediatamente.

---

## Auditoria rigorosa

Tudo que ocorrer na pagina precisa ser auditavel.

Eventos minimos:

1. Criacao de modelo de kit.
2. Edicao da composicao do modelo.
3. Criacao de bolsa-kit.
4. Vinculo da bolsa ao colaborador.
5. Mudanca de tipo de custodia.
6. Entrega inicial do kit.
7. Devolucao diaria.
8. Reentrega.
9. Agregacao de item extra.
10. Remocao de item.
11. Registro de perda.
12. Registro de quebra.
13. Reposicao.
14. Geracao de PDF.
15. Auditoria fisica da bolsa.

Cada evento deve registrar:

1. Quem fez.
2. Quando fez.
3. Qual bolsa foi afetada.
4. Qual colaborador estava vinculado.
5. Qual item foi afetado.
6. Quantidade.
7. Valor congelado no evento.
8. Estado anterior.
9. Estado posterior.
10. Motivo da alteracao.

---

## Perguntas que o modulo precisa responder

1. Quem esta com esta bolsa agora.
2. O que existe dentro da bolsa agora.
3. O que faz parte do kit padrao.
4. O que foi agregado posteriormente.
5. Qual o valor total atual sob responsabilidade do colaborador.
6. O que foi perdido.
7. O que foi quebrado.
8. O que esta em reposicao.
9. O que diverge do kit padrao.
10. Quem alterou a composicao por ultimo.

---

## Pagina principal do modulo

A Central de Kits de Ferramentas deve ter duas camadas:

1. Lista de kits por colaborador.
2. Detalhe da bolsa do colaborador.

Na lista principal, cada card precisa mostrar:

1. Nome do colaborador.
2. Matricula.
3. Grupo do kit.
4. Tipo de custodia.
5. Bolsa-chave.
6. Quantidade de itens.
7. Valor total.
8. Alertas de perda, quebra ou divergencia.

---

## Tela de detalhe da bolsa

### Blocos recomendados

1. Cabecalho do kit.
2. Conteudo atual da bolsa.
3. Itens padrao.
4. Itens extras.
5. Ocorrencias criticas.
6. Linha do tempo auditavel.
7. Botao de gerar PDF.

### Acoes recomendadas

1. Adicionar ferramenta.
2. Adicionar EPI.
3. Trocar tipo de custodia.
4. Registrar devolucao.
5. Registrar perda.
6. Registrar quebra.
7. Substituir item.
8. Auditar bolsa.

---

## Notificacoes

O modulo deve notificar de forma consolidada.

Regras:

1. Uma entrega de kit gera uma notificacao consolidada.
2. Uma devolucao do kit gera uma notificacao consolidada.
3. Uma agregacao em lote gera uma notificacao consolidada.
4. Perda e quebra geram notificacoes individuais de ocorrencia critica.

---

## Desenho funcional da Central de Kits

```text
CENTRAL DE KITS DE FERRAMENTAS

[ Filtros ] [ Grupo ] [ Custodia ] [ Alertas ] [ Busca por colaborador ]

+----------------------------------------------------------------------------------+
| ANTONIO | Kit Eletricista | Bolsa Wonder BW-014 | Custodia: Diaria | R$ 4.820,00 |
| 24 itens | 2 alertas | Ultima auditoria: 01/04/2026 17:40                         |
| [ Abrir bolsa ] [ Gerar PDF ] [ Auditar ] [ Trocar custodia ]                    |
+----------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------+
| JOSE    | Kit Manutencao Geral | Bolsa Wonder BW-022 | Custodia: Permanente      |
| 19 itens | sem alertas | Ultima auditoria: 01/04/2026 18:05                       |
| [ Abrir bolsa ] [ Gerar PDF ] [ Auditar ] [ Trocar custodia ]                    |
+----------------------------------------------------------------------------------+
```

---

## Desenho da bolsa do Antonio

```text
KIT DE ANTONIO

+----------------------------------------------------------------------------------+
| Antonio | Matricula 12345 | Kit Eletricista | Bolsa Wonder BW-014 | Diaria       |
| 24 itens | Valor total R$ 4.820,00 | 1 perda | 1 quebra | PDF | Auditoria       |
+----------------------------------------------------------------------------------+

+-----------------------------------+  +-------------------------------------------+
| CONTEUDO DA BOLSA                 |  | OCORRENCIAS CRITICAS                     |
| foto | item | qtd | valor | status|  | perdido | quebrado | reposicao | auditoria |
| foto | item | qtd | valor | status|  | modal perdeu | modal quebrou | foto dano  |
| foto | item | qtd | valor | status|  +-------------------------------------------+
+-----------------------------------+

+----------------------------------------------------------------------------------+
| ITENS EXTRAS E EPI                                                              |
| bota | oculos | luva | protetor auricular | item extra operacional               |
| [ Adicionar ferramenta ] [ Adicionar EPI ] [ Remover ]                          |
+----------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------+
| LINHA DO TEMPO AUDITAVEL                                                        |
| 02/04 07:10 - Kit entregue                                                      |
| 02/04 09:20 - Oculos agregados                                                  |
| 02/04 15:40 - Alicate quebrado com foto anexada                                 |
| 02/04 17:30 - PDF gerado por administrador                                       |
+----------------------------------------------------------------------------------+
```

---

## Fluxo de operacao consolidada

```text
MODELO DE KIT
      |
      v
BOLSA-CHAVE WONDER
      |
      v
COMPOSICAO DO KIT
      |
      v
ATRIBUICAO AO COLABORADOR
      |
      v
OPERACAO CONSOLIDADA DE ENTREGA
      |
      v
AUDITORIA + HISTORICO + PDF + OCORRENCIAS
```

---

## Resultado esperado

Quando este modulo estiver pronto, abrir a bolsa do Antonio deve equivaler a abrir um prontuario patrimonial completo do kit dele.

O sistema deve mostrar, em uma unica tela:

1. O que ele tem agora.
2. O que ele ja teve.
3. O que entrou depois.
4. O que perdeu.
5. O que quebrou.
6. Quanto vale.
7. Quem registrou cada mudanca.

Esse e o conceito de controle absoluto buscado para a Central de Kits de Ferramentas.