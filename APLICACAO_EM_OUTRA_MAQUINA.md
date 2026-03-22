# Aplicacao Em Outra Maquina

Este documento consolida o procedimento seguro para replicar o estado atual deste workspace em outra maquina.

## Estado Atual Confirmado Nesta Maquina

### Repositorio principal

- URL: https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
- Branch: master
- Commit aplicado localmente e publicado: `41e1cea567b8470cb4eef18c8e44175f6d58e25c`

### Repositorio mobile

- Pasta local: `galint-mobile`
- Branch local: `master`
- Commit local atual confirmado: `eeb95ead8022151c842e2a1c0109b8573d057d5e`
- Observacao: o mobile e um repositorio Git separado do principal e, neste clone, nao possui remoto configurado.

## Situacao Especial Do Vínculo Com O Mobile

O commit `41e1cea567b8470cb4eef18c8e44175f6d58e25c` do repositorio principal registra a pasta `galint-mobile` como um gitlink apontando para o commit:

- `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`

Porem, neste workspace atual:

1. a pasta `galint-mobile` esta em `eeb95ead8022151c842e2a1c0109b8573d057d5e`
2. o commit `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e` nao existe neste clone local do mobile
3. nao existe `origin` configurado no repositorio mobile
4. nao existe `.gitmodules` configurado no repositorio principal

Em outras palavras: o principal pode ser clonado normalmente do GitHub, mas o estado exato do mobile precisa ser levado separadamente desta maquina.

## Melhor Caminho Hoje

Com o estado atual confirmado, a forma mais segura de replicar em outra maquina e:

1. clonar o repositorio principal do GitHub
2. fixar o principal no commit `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
3. copiar o mobile desta maquina usando bundle ou copia direta da pasta com `.git`
4. fixar o mobile no commit real disponivel nesta maquina: `eeb95ead8022151c842e2a1c0109b8573d057d5e`

## Opcao 1: Via Git Bundle Do Mobile

Use esta opcao se quiser transportar o repositorio mobile sem criar remoto agora.

### 1. Gerar o bundle do mobile nesta maquina

Na raiz do projeto atual:

```powershell
git -C galint-mobile bundle create galint-mobile.bundle --all
```

Isso vai gerar o arquivo:

- `galint-mobile.bundle`

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

Supondo o bundle copiado para `C:\temp\galint-mobile.bundle`:

```powershell
git clone C:\temp\galint-mobile.bundle galint-mobile
git -C galint-mobile checkout eeb95ead8022151c842e2a1c0109b8573d057d5e
```

### 5. Validar

```powershell
git rev-parse HEAD
git -C galint-mobile rev-parse HEAD
```

Resultado esperado:

1. Principal: `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
2. Mobile: `eeb95ead8022151c842e2a1c0109b8573d057d5e`

## Opcao 2: Via Copia Direta Da Pasta Do Mobile

Use esta opcao se quiser replicar rapido entre duas maquinas sem depender de remoto.

### 1. Nesta maquina, copiar a pasta completa do mobile

Copie a pasta abaixo inteira, incluindo a pasta oculta `.git`:

- `galint-mobile`

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
git rev-parse HEAD
git -C galint-mobile rev-parse HEAD
```

Resultado esperado:

1. Principal: `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
2. Mobile: `eeb95ead8022151c842e2a1c0109b8573d057d5e`

## O Que Ainda Falta Para Fechar Isso De Forma Limpa

Para eliminar esse risco de replicacao futura, o ideal e publicar o mobile em um repositorio Git proprio e depois:

1. configurar `origin` no repositorio `galint-mobile`
2. publicar a branch `master` do mobile
3. adicionar `.gitmodules` corretamente no principal, se a intencao for tratar o mobile como submodulo de fato
4. ou remover o gitlink do principal e passar a tratar `galint-mobile` apenas como pasta comum fora do versionamento do repositorio principal

## Checklist Final Na Outra Maquina

1. O principal foi clonado da URL correta:
   - https://github.com/JefersonCG/Galint---Gerenciador-de-Almoxarifado-Inteligente.git
2. O principal esta no commit:
   - `41e1cea567b8470cb4eef18c8e44175f6d58e25c`
3. A pasta `galint-mobile` existe dentro da raiz do projeto
4. O mobile esta no commit:
   - `eeb95ead8022151c842e2a1c0109b8573d057d5e`

## Observacao Final

O gitlink do principal ainda referencia `5829832d0ffb3f55c9e7b86da7c80040c7a52f9e`, mas esse commit nao esta disponivel neste clone local do mobile. Portanto, a replicacao segura hoje deve usar o estado real confirmado nesta maquina, que e `eeb95ead8022151c842e2a1c0109b8573d057d5e`, ate que o repositorio mobile seja publicado ou recuperado com esse commit antigo.