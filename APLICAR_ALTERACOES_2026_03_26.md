# Aplicação das alterações de 26/03/2026

Este pacote consolida as mudanças operacionais e de interface feitas hoje no GALINT.

## 1. Suporte a Bombona

- O tipo de embalagem Bombona foi incluído no backend, templates web, fluxo de movimentação, documentos fiscais, Telegram e app mobile.
- O comportamento esperado para Bombona é o mesmo de recipientes líquidos fracionáveis, com suporte a litros e, quando aplicável, kg.

## 2. Padronização dos itens 5L

- Arquivo: scripts/migrations/manual/aplicar_migracao_bombona_5l.py
- Finalidade: localizar itens líquidos de 5L e normalizar para tipo_embalagem_novo = bombona.

### Como aplicar em outro ambiente

1. Ative o ambiente virtual do projeto.
2. Garanta acesso ao banco correto da instância.
3. Execute:

```powershell
.\.venv\Scripts\python.exe scripts\migrations\manual\aplicar_migracao_bombona_5l.py
```

4. Valide os itens atualizados na tela de estoque.

## 3. Ajustes de interface e cadastro

- Correção de contraste no modal de detalhes do inventário.
- Correção de legibilidade dos campos de data no formulário de item.
- Sugestão automática de Bombona quando a descrição do item indicar 5L.
- Correção do campo de saldo bloqueado para não truncar valores decimais no POST.

## 4. Correção de validação de saldo na edição de item

- A validação passou a respeitar o modo anterior do estoque.
- Alterar litragem, embalagem ou metadados não deve mais disparar falso erro de alteração de saldo quando o saldo operacional não foi editado.

## 5. Regularização documental feita hoje

- Item regularizado: 7899710007767
- NFs envolvidas: 1113587 e 2344855
- Resultado final aplicado neste ambiente: saldo corrigido para 307 unidades.

### Observação importante

- Essa regularização foi aplicada diretamente no banco deste ambiente e nao faz parte de um script versionado permanente.
- Para repetir em outro banco, primeiro confirme se o cenário é o mesmo: a NF 1113587 precisa estar refletida por ajuste manual indevido e a 2344855 precisa estar pendente sem entrada vinculada.
- Nao reaplique cegamente em bases diferentes sem conferência prévia dos saldos e dos itens documentais.

## 6. Ordem recomendada de deploy

1. Atualizar o código da aplicação web.
2. Atualizar o submódulo galint-mobile.
3. Executar a migração de Bombona 5L, se a base ainda nao estiver normalizada.
4. Validar cadastro, movimentações e documentos fiscais.
5. Somente se houver o mesmo problema documental do item 7899710007767, repetir a regularização de dados com conferência manual.