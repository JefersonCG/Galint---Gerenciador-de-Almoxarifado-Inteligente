# README — Página Percentual Movimentos

## 1. Objetivo da página

A página **Percentual Movimentos** foi criada para transformar o histórico operacional do almoxarifado em um painel analítico legível, com foco em:

- percentualidade de retiradas e devoluções
- ranking de movimentações por funcionário
- ranking de itens mais retirados
- leitura temporal por blocos de 30 dias
- consolidação mensal de consumo
- previsão de risco de ruptura de materiais
- indicação do melhor momento para emitir o próximo pedido

Ela foi pensada para responder, dentro do próprio sistema, perguntas do tipo:

- quem mais movimenta materiais?
- quais itens saem mais?
- quanto do que sai retorna?
- qual material pode acabar antes?
- quando devo me antecipar e fazer o próximo pedido?

---

## 2. Localização da implementação

### Backend

- rota e lógica principal: `galint_flask/views/reports.py`
- blueprint: `reports`
- endpoint: `/relatorios/percentual-movimentos`

### Frontend

- template principal: `galint_flask/templates/reports/percentual_movimentos.html`
- entrada no menu lateral: `galint_flask/templates/sidebar_layout.html`

### Página institucional

- resumo funcional em: `galint_flask/templates/sobre.html`

---

## 3. Fontes de dados utilizadas

O painel trabalha com dados vindos das seguintes estruturas:

### 3.1 Saida

Tabela usada como **fonte canônica das retiradas exibidas no relatório**.

Campos relevantes:

- `codigo_item`
- `matricula`
- `data_saida`
- `quantidade`

Uso na página:

- retiradas de materiais
- retiradas de ferramentas
- rankings por funcionário
- rankings por item
- séries temporais de consumo

### 3.2 InventarioEvento

Tabela usada para eventos de retorno e ajustes.

Tipos relevantes:

- `devolucao_material`
- `devolucao_ferramenta`
- `devolucao`

Uso na página:

- devoluções de materiais
- devoluções de ferramentas
- cálculo da taxa de devolução
- consumo líquido por janela temporal

### 3.3 Item

Tabela usada para metadados do item e classificação de categoria.

Campos relevantes:

- `codigo_item`
- `descricao`
- `categoria`
- `estoque_minimo`

Uso na página:

- distinção entre material e ferramenta
- descrição exibida na UI
- leitura do ponto mínimo de estoque para recomendação de reposição

### 3.4 Usuario

Tabela usada para exibir nome do funcionário a partir da matrícula.

---

## 4. Regra de separação entre materiais e ferramentas

### Regra atual

A separação foi corrigida para usar a categoria do item:

- **ferramenta**: quando `Item.categoria` contém `Ferrament`
- **material**: todos os demais itens

### Problema antigo corrigido

Antes, havia uma lógica que considerava ferramenta quando `Saida.tipo_custodia` estivesse preenchido. Como esse campo possuía valor padrão em muitos casos, quase tudo acabava sendo tratado como ferramenta.

Esse erro gerava:

- materiais zerados no painel
- ferramentas infladas artificialmente
- leitura operacional incorreta

---

## 5. Regra de fonte canônica de retiradas

### Regra atual

Para o painel de Percentual Movimentos, a retirada exibida usa **Saida** como fonte principal.

### Motivo

No sistema, ferramentas podem aparecer tanto em `Saida` quanto em `RetiradaFerramenta`, dependendo do fluxo. Somar as duas fontes diretamente no relatório produzia duplicidade.

### Problema antigo corrigido

Foi identificada duplicidade nas retiradas de ferramentas porque o relatório anterior somava registros de:

- `Saida`
- `RetiradaFerramenta`

Essa soma inflava os totais e os rankings.

### Correção adotada

O relatório passou a:

- usar `Saida` para refletir a movimentação exibida ao usuário
- usar `InventarioEvento` para devoluções
- evitar dupla contagem no painel percentual

---

## 6. O que a página exibe

### 6.1 Cards de resumo

Os cards mostram:

- retiradas de materiais
- devoluções de materiais
- retiradas de ferramentas
- devoluções de ferramentas
- quantidade de janelas de 30 dias calculadas
- quantidade de meses consolidados
- maior risco de ruptura identificado
- quantidade de itens elegíveis para previsão

### 6.2 Gráficos de percentualidade

Os gráficos mostram:

- movimentos totais
- ranking percentual de funcionários para materiais
- ranking percentual de funcionários para ferramentas
- materiais mais retirados
- ferramentas mais retiradas

### 6.3 Séries temporais

Foram adicionados dois blocos temporais:

- **Escalonamento em 30 dias**
- **Movimentações mensais**

### 6.4 Previsão de ruptura

A tabela de previsão mostra:

- saldo atual
- estoque mínimo
- média de consumo líquido por 30 dias
- intervalo de confiança de 95%
- probabilidade de ruptura em 30 dias
- classificação de risco
- previsão de ruptura
- data sugerida para o próximo pedido

---

## 7. Lógica das janelas sequenciais de 30 dias

### Regra implementada

Para cada material:

1. identificar a **primeira retirada** registrada
2. criar blocos consecutivos de 30 dias a partir dessa data
3. apurar em cada bloco:
   - retiradas do período
   - devoluções do período
   - consumo líquido do período
   - quantidade de movimentos do período

### Exemplo conceitual

Se a primeira retirada ocorreu em `20/12/2025`, os blocos ficam assim:

- bloco 1: `20/12/2025` a `18/01/2026`
- bloco 2: `19/01/2026` a `17/02/2026`
- bloco 3: `18/02/2026` a `19/03/2026`

Ou seja, o sistema não usa mês-calendário para esse cálculo. Ele usa blocos fixos de 30 dias encadeados desde o início real do histórico daquele item.

### Objetivo dessa abordagem

- preservar o ciclo real de consumo
- evitar distorção por cortes artificiais de mês
- aproximar a leitura da realidade operacional de uso

---

## 8. Lógica da consolidação mensal

Além das janelas sequenciais, a página também calcula consolidação mensal por competência `MM/AAAA`.

Em cada mês são acumulados:

- quantidade total retirada
- quantidade total devolvida
- consumo líquido do mês
- volume de movimentações do mês

Esse bloco serve para leitura gerencial mais tradicional e comparação entre meses.

---

## 9. Taxa de devolução

### Regra atual

A taxa de devolução por item é calculada por **quantidade**, e não por simples contagem de registros:

`taxa_devolucao = devolucoes_qty / retiradas_qty`

### Correção aplicada

Foi imposta limitação máxima de 100%:

`taxa_devolucao = min(1.0, devolucoes_qty / retiradas_qty)`

### Motivo

Contagem simples de eventos gerava distorções quando havia múltiplas devoluções parciais para uma mesma retirada.

---

## 10. Modelo de previsão de ruptura

### Escopo atual

A previsão atual é aplicada aos **materiais**.

### Etapas da previsão

Para cada material:

1. reunir o histórico de retiradas
2. reunir o histórico de devoluções
3. calcular o consumo líquido por janela de 30 dias
4. montar a série histórica de consumo líquido
5. calcular:
   - média de consumo por 30 dias
   - desvio padrão por 30 dias
   - intervalo de confiança de 95%
6. confrontar a demanda esperada com:
   - saldo atual
   - estoque mínimo

### Métricas geradas

- `media_30d`
- `desvio_padrao_30d`
- `ic95_baixo`
- `ic95_alto`
- `prob_ruptura_30d`
- `prob_repor_30d`
- `dias_para_ruptura`
- `dias_para_reposicao`
- `data_prevista_ruptura`
- `data_sugerida_pedido`

---

## 11. Confiança estatística de 95%

### O que a página faz

A página calcula um **intervalo de confiança estatística de 95%** para o consumo líquido esperado em 30 dias.

### O que isso significa

Significa que o modelo usa a dispersão do histórico para estimar uma faixa provável de demanda futura.

### O que isso não significa

Não significa promessa de 95% de precisão operacional real.

Isso seria tecnicamente irresponsável porque o consumo do almoxarifado depende de fatores externos como:

- obras e serviços emergenciais
- sazonalidade
- perdas e quebras
- devoluções fora do padrão
- mudanças de processo
- compras extraordinárias

### Decisão de produto adotada

A página deixa explícito que se trata de **confiança estatística**, e não garantia absoluta de acurácia.

---

## 12. Critério mínimo para item ser elegível à previsão

### Regra atual

O material só entra como elegível para previsão estatística quando possui **pelo menos 3 janelas de 30 dias**.

### Motivo

Com 1 ou 2 janelas, a série é curta demais e o risco calculado fica frágil ou enganoso.

### Efeito prático

Itens com pouco histórico aparecem auditados, mas não são promovidos automaticamente ao ranking de risco forte.

Na interface, esses casos aparecem como:

- confiança insuficiente
- acompanhamento manual recomendado

---

## 13. Auditoria embutida na página

Foi adicionada uma camada de auditoria visível ao usuário para evitar interpretação errada do painel.

Hoje a página informa:

- quantos materiais foram auditados
- quantos ficaram elegíveis para previsão
- quantos têm risco positivo calculado

Isso foi necessário porque um painel pode parecer vazio por dois motivos muito diferentes:

1. a lógica está errada
2. o histórico real ainda não é suficiente

A auditoria separa claramente esses dois cenários.

---

## 14. Correções realizadas durante a auditoria

### 14.1 Correção de classificação

Antes:

- materiais estavam sendo confundidos com ferramentas

Depois:

- classificação passou a respeitar a categoria do item

### 14.2 Correção de duplicidade

Antes:

- retiradas de ferramentas podiam ser infladas por soma de fontes diferentes

Depois:

- `Saida` foi mantida como fonte principal de retirada exibida

### 14.3 Correção de ortografia e acentuação

Foram revisados textos da página, incluindo:

- Devoluções
- Participação
- Funcionários
- Matrícula
- Movimentações
- Código
- Distribuição

### 14.4 Correção de previsões enganosas

Antes:

- itens com histórico mínimo apareciam com risco artificialmente alto

Depois:

- o modelo exige histórico mínimo
- a interface distingue amostra insuficiente de risco real

### 14.5 Correção visual dos gráficos vazios

Antes:

- gráficos podiam parecer vazios por receber listas dominadas por zero

Depois:

- o ranking de risco prioriza itens elegíveis e risco efetivo
- a tela mostra auditoria do volume elegível

---

## 15. Leitura operacional recomendada

### Para o almoxarifado

Usar a página para:

- acompanhar itens de maior saída
- entender devolução por item
- detectar risco de ruptura com antecedência
- decidir o melhor momento para reabastecer

### Para supervisão/gestão

Usar a página para:

- medir concentração de movimentações por funcionário
- avaliar comportamento de consumo por mês
- ver quais materiais exigem ação mais rápida
- comparar risco com estoque mínimo configurado

---

## 16. Limitações atuais

Apesar das melhorias, o modelo ainda possui limitações conhecidas:

- não considera prazo real de entrega por fornecedor
- não usa sazonalidade explícita por estação ou obra
- não separa consumo recorrente de consumo excepcional
- ainda não calcula lote econômico de compra
- ainda não considera calendário útil ou feriados

Esses pontos podem ser evoluídos futuramente.

---

## 17. Próximas evoluções recomendadas

### Evoluções de modelagem

- incorporar lead time por fornecedor
- usar janela recente ponderada com peso maior para os últimos ciclos
- separar consumo normal de eventos extraordinários
- calcular estoque de segurança adaptativo
- sugerir quantidade ideal de compra, não apenas data

### Evoluções de interface

- filtros por setor
- filtros por categoria
- horizonte configurável de previsão
- exportação da auditoria em XLSX/PDF
- alertas automáticos com base no risco

---

## 18. Resumo executivo

A página **Percentual Movimentos** deixou de ser apenas um painel visual de percentuais e passou a funcionar como um módulo analítico com quatro camadas:

1. leitura operacional de retiradas e devoluções
2. leitura temporal em 30 dias e por mês
3. leitura estatística com IC de 95%
4. leitura decisória para reposição e prevenção de ruptura

O resultado é um painel mais confiável, auditável e útil para tomada de decisão real no almoxarifado.