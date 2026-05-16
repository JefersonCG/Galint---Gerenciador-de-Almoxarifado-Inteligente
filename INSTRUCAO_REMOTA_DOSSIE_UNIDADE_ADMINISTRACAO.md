# Instrucao remota: Dossie Vivo da Unidade

Esta instrucao registra a visao combinada para a continuidade do modulo de Administracao condominial. O objetivo nao e criar apenas uma ficha cadastral bonita: o card de cada unidade no dashboard deve virar a porta de entrada para um dossie operacional completo da unidade.

## Objetivo principal

No dashboard da Administracao, ao visualizar um edificio, cada unidade deve aparecer como um card compacto, semelhante ao mapa visual de unidades. Ao clicar em uma unidade, o sistema deve abrir um modal grande ou painel lateral expandido com todos os dados relevantes daquela unidade, sem obrigar o usuario a sair do dashboard para procurar a pessoa em outra tela.

Esse dossie deve concentrar tudo que o sistema souber sobre a unidade, o proprietario, moradores, acessos, historico, manutencao, reservas, cobrancas e eventos registrados.

## Conceito de produto

Chamar internamente de Dossie Vivo da Unidade.

O dossie deve ser:

- consultivo, para a administracao localizar informacoes rapidamente;
- operacional, permitindo editar vinculos e registrar acoes;
- historico, mantendo rastreabilidade de tudo que aconteceu;
- auditavel, especialmente nas partes de cobrancas, multas e LGPD.

## Fluxo esperado

1. Usuario entra no dashboard da Administracao.
2. Seleciona ou visualiza um edificio/bloco.
3. Clica no card da unidade, por exemplo 1001.
4. Abre um modal grande com o dossie completo.
5. O usuario consulta, edita ou registra acoes sem precisar abrir o cadastro tradicional.

## Estrutura recomendada do dossie

### 1. Cabecalho fixo

Mostrar sempre no topo:

- edificio/bloco;
- numero da unidade;
- status da unidade: vaga, ocupada, alugada, em obra, pendente ou outro status futuro;
- proprietario atual;
- ocupante principal atual, quando houver;
- resumo financeiro: regular, pendente, em analise;
- contadores rapidos: moradores, veiculos, pets, funcionarios, pendencias.

### 2. Resumo cadastral

Dados principais da unidade e do titular:

- proprietario pessoa fisica ou juridica;
- CPF/CNPJ, RG, CNH quando aplicavel;
- contatos;
- dados da unidade;
- vaga ou estacionamento livre;
- IPTU, RGI e matricula do imovel;
- anexos/documentos.

### 3. Pessoas vinculadas

Separar vinculos por tipo:

- proprietario;
- locatario;
- moradores;
- dependentes;
- funcionarios domesticos;
- prestadores recorrentes;
- responsaveis autorizados.

Importante: ao remover alguem, nao apagar o historico. Encerrar o vinculo com data, motivo e usuario responsavel. Exemplo: "Maria trabalhou na unidade de 2024 a 2026".

### 4. Veiculos, pets e acessos

Concentrar:

- veiculos cadastrados;
- placa, modelo, cor, tipo e vaga;
- CNH do condutor quando fizer sentido;
- pets cadastrados;
- observacoes de portaria;
- restricoes, autorizacoes e regras de acesso.

### 5. Ocupacao e aluguel da unidade

Esta parte e sobre o aluguel da unidade/apartamento em si, nao sobre salao de festas ou outros espacos comuns.

Deve permitir registrar:

- proprietario mora na unidade;
- unidade alugada;
- unidade disponivel para aluguel;
- historico de locatarios;
- periodo de contrato;
- imobiliaria ou responsavel;
- responsavel financeiro;
- data de entrada e saida.

### 6. Reservas e locacoes de espacos comuns

Separar da locacao da unidade. Aqui entram espacos do condominio, como:

- salao de festas;
- churrasqueira;
- piscina, se houver regra de reserva;
- quadra;
- sala multiuso;
- vagas extras;
- outros espacos configuraveis.

Registrar datas, valores, caucao, status, cancelamento, ocorrencias e vistoria quando existir.

### 7. Cobrancas, taxas e multas

Esta aba precisa ser muito bem planejada. Nao implementar calculos definitivos sem as regras reais do condominio.

Direcao esperada:

- criar uma calculadora/motor de cobrancas e multas;
- permitir tipo: taxa, multa, ressarcimento, reserva, reparo, advertencia convertida em multa;
- permitir categoria: estacionamento irregular, barulho, obra irregular, dano em area comum, atraso, reserva de espaco ou outra;
- ter valor base;
- percentual de multa;
- juros por dia ou mes;
- multa fixa ou percentual;
- reincidencia;
- data da ocorrencia;
- data de vencimento;
- dias de atraso;
- desconto autorizado;
- responsavel pela aprovacao;
- anexos/provas;
- previa antes de gerar a cobranca.

Obrigatorio: mostrar memoria de calculo. Exemplo:

```text
Valor base: R$ 200,00
Multa 10%: R$ 20,00
Juros por atraso: R$ 4,30
Total: R$ 224,30
```

Nada deve sair como numero magico. Toda cobranca deve ser auditavel, com regra, formula, usuario, data e origem.

### 8. Historico geral / timeline

Criar uma linha do tempo unificada da unidade. Deve mostrar tudo que aconteceu em ordem cronologica, incluindo:

- morador entrou;
- morador saiu;
- funcionario foi vinculado;
- funcionario foi removido;
- veiculo cadastrado;
- visitante entrou;
- visita tecnica realizada;
- reforma solicitada;
- manutencao executada;
- material do almoxarifado saiu para aquele bloco/unidade;
- multa criada;
- cobranca paga;
- espaco comum reservado;
- ocorrencia registrada;
- documento anexado.

### 9. Acoes rapidas

Dentro do dossie, disponibilizar acoes contextuais:

- adicionar morador;
- adicionar funcionario;
- encerrar vinculo;
- cadastrar veiculo;
- cadastrar pet;
- registrar visita;
- abrir manutencao;
- registrar ocorrencia;
- gerar taxa, multa ou cobranca;
- reservar espaco comum;
- anexar documento.

As acoes devem respeitar permissao de usuario, LGPD e auditoria.

## Cuidados tecnicos

- Nao apagar historico ao remover pessoa, veiculo, funcionario ou vinculo; encerrar o vinculo.
- Dados sensiveis devem respeitar permissao e mascaramento.
- O modal nao deve carregar tudo de forma pesada se houver muitos eventos; usar abas e carregamento sob demanda quando necessario.
- O dashboard deve continuar rapido.
- O card da unidade pode usar cor/status para indicar ocupado, vago, pendente, alugado ou em obra.
- O dossie deve funcionar como centro operacional, nao apenas como visualizacao.

## Prioridade sugerida

1. Criar clique no card da unidade abrindo modal/painel do dossie.
2. Mostrar resumo cadastral com os dados ja existentes no cadastro de morador/proprietario.
3. Adicionar abas: Resumo, Pessoas, Veiculos/Pets, Ocupacao, Historico, Cobrancas.
4. Implementar timeline basica com eventos ja existentes no sistema.
5. Depois evoluir reservas de espacos comuns.
6. Deixar cobrancas/multas preparadas, mas nao fechar formula ate receber as regras reais.

## Decisao importante

A parte de cobrancas, taxas e multas deve ficar em aberto ate o alinhamento das regras reais. Quando as regras forem passadas, implementar com logica matematica rigorosa, memoria de calculo e aprovacao antes de gerar qualquer valor oficial.