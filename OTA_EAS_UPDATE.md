# OTA (EAS Update) — GALINT Mobile

Este projeto está configurado para receber atualizações OTA (Over-The-Air) via **EAS Update** a partir do próximo build.

## O que muda

- O APK/App Bundle passa a vir com `expo-updates` embutido.
- Depois do app instalado, dá para publicar alterações de JavaScript/Assets suportados via `eas update`.
- **Mudanças nativas** (ex.: permissões, plugins nativos, versões do React Native/Expo, etc.) continuam exigindo novo build.

## Pré-requisitos (na sua máquina)

- Node.js + npm (para rodar `eas`/`expo` localmente)
- Expo CLI via `npx expo ...`
- EAS CLI instalado: `npm i -g eas-cli`

## Build já com canal

O `eas.json` define canais:

- `development` → channel `development`
- `preview` → channel `preview`
- `production` → channel `production`

## Publicar uma atualização OTA

Exemplo (canal preview):

- `eas update --channel preview --message "Correção: maiúsculo no blur"`

Exemplo (produção):

- `eas update --channel production --message "Hotfix: ajustes de UI"`

## Observações importantes

- As atualizações OTA só aplicam em builds com **runtimeVersion** compatível.
- Aqui usamos `runtimeVersion.policy = appVersion` (do `app.json`).
  - Se você trocar `expo.version` (ex.: 1.1.0 → 1.1.1), updates OTA antigos não vão mais aplicar nesse novo binário.
