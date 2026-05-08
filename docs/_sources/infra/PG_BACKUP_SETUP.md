# Configurando pg_dump para o GALINT

Se o GALINT acusa que o comando `pg_dump` não foi encontrado, siga estes passos para apontar o caminho corretamente.

## 1. Confirme onde está o `pg_dump`

- Normalmente o binário fica em `C:\Program Files\PostgreSQL\<versão>\bin\pg_dump.exe`.
- Abra o Explorer e navegue até essa pasta.
- Copie o caminho completo incluindo o `pg_dump.exe`.

## 2. Defina a variável de ambiente `BACKUP_PG_DUMP`

1. Abra o menu Iniciar e pesquise por **"variáveis de ambiente"**.
2. Clique em **"Editar as variáveis de ambiente do sistema"**.
3. Clique em **"Variáveis de ambiente…"**.
4. Em _Variáveis de usuário para_ `LUIS`, clique em **"Novo…"** (ou selecione `BACKUP_PG_DUMP` e clique em "Editar").
   - Nome: `BACKUP_PG_DUMP`
   - Valor: `C:\Program Files\PostgreSQL\15\bin\pg_dump.exe` (ajuste conforme a sua versão)
5. Clique em **OK** em todas as janelas.

## 3. (Opcional, recomendado) adicione `pg_dump` ao PATH

1. Ainda na janela de variáveis, selecione a variável `Path` em _Variáveis do sistema_ e clique em **Editar**.
2. Clique em **Novo** e cole o diretório: `C:\Program Files\PostgreSQL\15\bin`
3. Clique em **OK** para salvar.

## 4. Reinicie o servidor e o navegador

- Feche o terminal onde o Flask está rodando e abra outro (reabra o terminal do projeto). Reative a virtualenv e rode `python app.py` novamente.
- Recarregue a página do GALINT no navegador.

A mensagem de erro deve desaparecer e o backup passará a funcionar.
