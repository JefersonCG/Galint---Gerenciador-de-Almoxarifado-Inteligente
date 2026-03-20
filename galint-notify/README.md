# GalintNotify

App Expo separado para inbox de notificações do GALINT, com login, push Android, feed sem digitação e compartilhamento de relatórios.

## Stack escolhida

- Expo Push para entrega rápida de push Android
- Inbox persistente no backend via `/api/notify`
- Compartilhamento via `expo-sharing`
- Download de arquivos via `expo-file-system`

## Variáveis de ambiente

Não commitar segredos. Para build e execução, use variáveis no ambiente local/EAS:

- `EXPO_PUBLIC_GALINT_NOTIFY_PROJECT_ID`: Project ID do Expo/EAS usado por `expo-notifications`
- `EXPO_PUBLIC_GALINT_NOTIFY_SERVER_URL`: URL padrão do backend GALINT
- `GALINT_NOTIFY_ANDROID_PACKAGE`: package Android do app

Exemplo PowerShell:

```powershell
$env:EXPO_PUBLIC_GALINT_NOTIFY_PROJECT_ID="seu-project-id"
$env:EXPO_PUBLIC_GALINT_NOTIFY_SERVER_URL="http://192.168.1.41:5000"
$env:GALINT_NOTIFY_ANDROID_PACKAGE="com.galint.notify"
```

## Instalação

```powershell
cd galint-notify
npm install
npx expo start
```

## Build APK com EAS

```powershell
cd galint-notify
npx eas login
npx eas build --platform android --profile preview
```

## Fluxo funcional

1. Login em `/api/notify/login`
2. Registro do Expo Push Token em `/api/notify/push/register`
3. Inbox em `/api/notify/inbox`
4. Marcação de leitura em `/api/notify/inbox/<id>/read`
5. Relatórios em `/api/notify/reports` e `/api/notify/reports/<id>/download`

## Observações operacionais

- O app usa drawer menu como os “3 traços” para Messenger, Relatórios e Configurações.
- Ao tocar no push, o app abre o Messenger e destaca a mensagem correspondente.
- O backend continua usando Telegram como canal alternativo; o failover é decidido no Notification Router do Flask.
- Expo Push não exige segredo no app nem no backend para o envio básico via endpoint público da Expo.