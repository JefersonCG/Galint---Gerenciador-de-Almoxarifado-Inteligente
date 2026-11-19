# Botão GALINT

O alternador deslizante inicia e para o servidor de produção do GALINT na porta 5000, junto com o polling do Telegram integrado à aplicação. O toggle amarelo-canário segue o visual e as dimensões da janela da Central Publish. O PostgreSQL não é iniciado nem parado.

## Instalar

Execute no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\toggle\install-toggle.ps1
```

O instalador cria o atalho **GALINT** na Área de Trabalho com o mesmo ícone do toggle da Central Publish. O atalho usa um inicializador sem console para não abrir uma janela do PowerShell ou CMD. Ao fechar a janela, o servidor continua rodando, como no alternador do Central Publish.

O botão usa o ambiente virtual do projeto e as variáveis do `.env`, sem exibi-las na janela nem gravá-las em log. Ele reconhece o servidor do GALINT pela linha de comando: o Waitress com `galint_flask:create_app` na porta 5000, ligado por este botão ou pela tarefa "GALINT - inicio automatico", seja de qualquer cópia do projeto. Até 19/11/2026 ele só aceitava o Python do `.venv` da própria pasta, e o GALINT ligado pela cópia antiga do OneDrive aparecia como "porta 5000 ocupada" no botão do D:. Se a porta 5000 estiver ocupada por outro processo, o botão informa o conflito e não encerra esse processo.

## Sem janela (Painel de Sistemas)

A lógica de ligar, desligar e conferir fica no `GalintControle.ps1`. O `GalintToggle.ps1` carrega esse arquivo e só desenha a janela. O Painel de Sistemas, que junta os toggles da Central Publish, do Sublime Max SGP, da Pipocas do Biel e do GALINT numa janela só, roda o mesmo arquivo sem janela:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\toggle\GalintControle.ps1 -Acao status|ligar|desligar -Saida resultado.txt
```

O arquivo recebe `OK: ...` ou `FALHOU: ...` (só em ligar e desligar) e as linhas `ligado=`, `nivel=` e `texto=`. O código de saída é 0 quando deu certo e 2 quando falhou. Sem `-Saida`, o resultado sai na tela. O painel lê esse formato: não o mude sem ajustar o painel junto.

O atalho **GALINT** da Área de Trabalho foi apagado em 19/11/2026, porque o painel o substitui. Ao reinstalar o botão, use `install-toggle.ps1 -NoShortcut`. O `GalintToggle.vbs` continua abrindo a janela própria, e o painel a abre pelo botão direito no cartão do GALINT.
