# GALINT no Pendrive com Python Portatil

Este modo usa o proprio pendrive para carregar o codigo e o runtime Python, sem rebuild do executavel a cada alteracao. O banco PostgreSQL continua fora do pendrive.

## Modelo adotado

1. O codigo do GALINT fica clonado no pendrive com Git.
2. O Python portatil fica em portable_runtime/python.
3. O ambiente do projeto fica em .venv_portable.
4. O banco de dados continua em PostgreSQL na maquina ou em um servidor da rede.
5. A multijanela auxiliar fica desligada por padrao para o sistema trabalhar sempre em uma unica janela.

## Estrutura recomendada no pendrive

```text
GALINT_USB/
  GALINT/
    .git/
    app.py
    requirements.txt
    .env.portable
    portable_runtime/
      python/
        python.exe
    .venv_portable/
    scripts/
      setup_portable_usb.ps1
      start_portable_usb.ps1
      update_portable_usb.ps1
```

## Importante sobre o Python portatil

Use um Python Windows completo com pip e venv. Nao use o pacote embeddable minimo da Python Software Foundation, porque ele costuma falhar com dependencias compiladas e com criacao de venv.

## Setup inicial no pendrive

1. Copie o repositorio para uma pasta dedicada no pendrive.
2. Coloque o Python portatil em portable_runtime/python/python.exe.
3. Rode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_portable_usb.ps1
```

4. Edite o arquivo .env.portable com a conexao PostgreSQL correta.

## Iniciar o sistema no pendrive

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_portable_usb.ps1
```

Esse script sobe o GALINT com Waitress em producao e mantem a configuracao de janela unica.

## Atualizar sem empacotar novamente

Sempre que o codigo mudar, no pendrive rode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_portable_usb.ps1
```

Esse fluxo faz:

1. git pull --ff-only
2. pip install -r requirements.txt
3. python app.py upgrade

Depois basta iniciar novamente com start_portable_usb.ps1.

## O pendrive precisa estar limpo?

Nao. Ele nao precisa estar zerado. O que importa e:

1. Ter uma pasta dedicada para o GALINT.
2. Ter espaco livre suficiente. O recomendado e pelo menos 8 GB livres.
3. Preferir NTFS ou exFAT.
4. Evitar guardar outros arquivos soltos dentro da pasta do repositorio.

## Observacao operacional

Se o pendrive for removido durante uso, voce pode corromper logs, uploads em andamento ou o proprio repositório Git. O modelo mais seguro continua sendo rodar o GALINT em uma maquina fixa da rede e usar o pendrive apenas como kit de distribuicao/recuperacao.