# Recebimento de NF-e pela SEFAZ

## Configuração

1. Acesse **Documentos Fiscais → Recebimento SEFAZ** com perfil administrador.
2. Informe o CNPJ destinatário e a UF do estabelecimento.
3. Envie o certificado digital A1 no formato `.PFX` ou `.P12` e sua senha.
4. Selecione produção ou homologação e ative a consulta automática.
5. Reinicie o GALINT após instalar uma versão que inclua esta integração.

O GALINT valida o arquivo antes de salvar e criptografa o certificado e a senha usando a chave secreta persistente da instalação (`SECRET_KEY`). Mantenha essa chave protegida e junto do processo seguro de backup; sem ela, os dados criptografados não poderão ser recuperados. Não envie certificados por e-mail ou registre a senha em arquivos do projeto.

## Consulta e conferência

A consulta é feita pelo serviço oficial de Distribuição DF-e, com controle do NSU e intervalo mínimo de uma hora. Consultas mais frequentes podem ser recusadas pela SEFAZ por consumo indevido. A rotina começa após o GALINT iniciar e continua em intervalos horários enquanto a integração estiver ativa.

As notas encontradas aparecem na caixa de entrada SEFAZ e também podem ser localizadas pela busca global. Quando o XML completo estiver disponível, o GALINT apresenta os principais campos e os itens da nota, além de permitir baixar o XML original. O GALINT não lança automaticamente itens no estoque nem envia eventos de manifestação. Dependendo das regras fiscais e da manifestação do destinatário, a SEFAZ pode fornecer apenas o resumo da nota; o XML completo fica disponível conforme as regras do serviço.

Notas recebidas pela SEFAZ permanecem separadas da movimentação de estoque até conferência. Para notas não localizadas, administradores podem criar um rascunho pela busca global, preencher os dados essenciais e seguir para a tela fiscal para incluir e conferir os itens.
