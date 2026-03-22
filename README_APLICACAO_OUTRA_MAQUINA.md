# Aplicacao Em Outra Maquina

Este documento consolida o procedimento completo para replicar o estado atual do projeto em outra maquina com seguranca.

## Estado Atual

### Repositorio principal

- URL: https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
- Commit publicado: `41e1cea567b8470cb4eef18c8e44175f6d58e25c`

### Repositorio mobile

- Pasta local: `galint-mobile`
- Commit local atual: `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`
- Observacao: o mobile e um repositorio Git separado do principal.

### Problema real

O repositorio principal ja esta publicado, mas o mobile e um repositorio independente e, nesta maquina, nao possui remoto configurado. Por isso, em outra maquina, o principal pode ser baixado normalmente, mas o mobile nao sera reconstruido automaticamente apenas a partir do clone principal.

## Melhor Caminho

A melhor solucao e publicar o mobile em um repositorio proprio e, na outra maquina, clonar:

1. o repositorio principal
2. o repositorio do mobile

Se ainda nao existir um repositorio remoto para o mobile, crie um em:

- https://github.com/new

Exemplo de URL esperada para o mobile:

- https://github.com/SEU_USUARIO/galint-mobile.git

## Opcao 1: Via Repositorio Remoto Do Mobile

Use esta opcao se puder criar um repositorio GitHub proprio para o mobile.

### 1. Criar o repositorio do mobile

Acesse:

- https://github.com/new

Preencha assim:

1. Repository name: galint-mobile
2. Visibility: Private ou Public
3. Nao inicialize com README, .gitignore ou license

Ao final, voce tera uma URL parecida com esta:

- https://github.com/SEU_USUARIO/galint-mobile.git

### 2. Publicar o mobile nesta maquina

Na pasta do mobile, execute:

```powershell
cd "C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800\galint-mobile"
git remote add origin https://github.com/SEU_USUARIO/galint-mobile.git
git push -u origin master
```

Se o remoto `origin` ja existir e precisar ser substituido:

```powershell
cd "C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800\galint-mobile"
git remote remove origin
git remote add origin https://github.com/SEU_USUARIO/galint-mobile.git
git push -u origin master
```

### 3. Na outra maquina, baixar o repositorio principal

Use a URL real do principal:

```powershell
git clone https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
cd Galint---Gerenciador-de-Almoxarifado-Inteligente
git checkout 41e1cea567b8470cb4eef18c8e44175f6d58e25c
```

### 4. Na outra maquina, clonar o mobile dentro da pasta esperada

Ainda na raiz do projeto clonado:

```powershell
git clone https://github.com/SEU_USUARIO/galint-mobile.git galint-mobile
cd galint-mobile
git checkout 5829832d0ffb3f55c9e7b86da7c80040c7a52f9e
cd ..
```

### 5. Validar

```powershell
git rev-parse HEAD
git -C galint-mobile rev-parse HEAD
```

Resultado esperado:

1. Principal: `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
2. Mobile: `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`

## Opcao 2: Via Git Bundle

Use esta opcao se nao quiser criar um remoto do mobile agora.

### 1. Gerar o bundle do mobile nesta maquina

```powershell
cd "C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800\galint-mobile"
git bundle create ..\galint-mobile.bundle --all
```

Isso vai gerar o arquivo:

- `C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800\galint-mobile.bundle`

### 2. Copiar o bundle para a outra maquina

Pode ser por:

1. pendrive
2. rede local
3. OneDrive
4. Google Drive
5. WeTransfer

### 3. Na outra maquina, clonar o principal

```powershell
git clone https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
cd Galint---Gerenciador-de-Almoxarifado-Inteligente
git checkout 41e1cea567b8470cb4eef18c8e44175f6d58e25c
```

### 4. Restaurar o mobile a partir do bundle

Supondo o bundle em `C:\temp\galint-mobile.bundle`:

```powershell
git clone C:\temp\galint-mobile.bundle galint-mobile
cd galint-mobile
git checkout 5829832d0ffb3f55c9e7b86da7c80040c7a52f9e
cd ..
```

### 5. Validar

```powershell
git rev-parse HEAD
git -C galint-mobile rev-parse HEAD
```

## Opcao 3: Via Copia Direta Da Pasta Do Mobile

Use esta opcao se quiser replicar rapido entre duas maquinas, sem criar remoto.

### 1. Nesta maquina, copiar a pasta completa do mobile

Copie a pasta abaixo inteira, incluindo a pasta oculta `.git`:

- `C:\Users\Ronaldo\OneDrive\Desktop\GALINT_FLASK_COPIA_FULL_20251231_085800\galint-mobile`

### 2. Na outra maquina, clonar o principal

```powershell
git clone https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
cd Galint---Gerenciador-de-Almoxarifado-Inteligente
git checkout 41e1cea567b8470cb4eef18c8e44175f6d58e25c
```

### 3. Substituir a pasta do mobile

Depois do clone do principal, substitua a pasta `galint-mobile` pela copia completa trazida desta maquina.

### 4. Validar

```powershell
git -C galint-mobile rev-parse HEAD
```

Resultado esperado:

- `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`

## Qual Opcao Escolher

1. Melhor e mais limpa: Opcao 1
2. Sem criar repositorio remoto: Opcao 2
3. Mais rapida e direta entre duas maquinas: Opcao 3

## Checklist Final Na Outra Maquina

1. O principal foi clonado da URL correta:
   - https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
2. O principal esta no commit:
   - `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
3. A pasta `galint-mobile` existe dentro da raiz do projeto
4. O mobile esta no commit:
   - `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`

## Comandos Finais De Verificacao

Execute na outra maquina:

```powershell
git rev-parse HEAD
git -C galint-mobile rev-parse HEAD
```

Resultado esperado:

1. Principal: `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
2. Mobile: `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`

## Observacao Final

Enquanto o mobile nao tiver um remoto proprio, o repositorio principal continuara apontando para um commit do mobile que so existe localmente nesta maquina. Para eliminar esse risco de replicacao futura, a recomendacao e publicar o mobile em um repositorio Git separado.