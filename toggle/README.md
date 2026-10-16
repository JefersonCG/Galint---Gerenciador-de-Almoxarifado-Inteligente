# Botão GALINT

O alternador deslizante inicia e para o servidor de produção do GALINT na porta 5000, junto com o polling do Telegram integrado à aplicação. O toggle amarelo-canário segue o visual e as dimensões da janela da Central Publish. O PostgreSQL não é iniciado nem parado.

## Instalar

Execute no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\toggle\install-toggle.ps1
```

O instalador cria o atalho **GALINT** na Área de Trabalho com o mesmo ícone do toggle da Central Publish. O atalho usa um inicializador sem console para não abrir uma janela do PowerShell ou CMD. Ao fechar a janela, o servidor continua rodando, como no alternador do Central Publish.

O botão usa o ambiente virtual do projeto e as variáveis do `.env`, sem exibi-las na janela nem gravá-las em log. Ele reconhece o servidor Waitress deste GALINT pela localização do Python e pela linha de comando. Se a porta 5000 estiver ocupada por outro processo, informa o conflito e não encerra esse processo.
