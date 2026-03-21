import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

import api from './api';

function isExpoGo() {
  return Constants.executionEnvironment === 'storeClient' || Constants.appOwnership === 'expo';
}

export async function bootstrapPush(session) {
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!session) {
    return { supported: false, skippedReason: 'Sessão indisponível.' };
  }

  if (!projectId) {
    return { supported: false, skippedReason: 'Project ID do Expo não configurado.' };
  }

  if (isExpoGo()) {
    return {
      supported: false,
      skippedReason: 'Push nativo foi desativado no Expo Go. Use o APK do GalintNotify para registrar notificações.',
    };
  }

  try {
    const permission = await Notifications.requestPermissionsAsync();
    if (permission.status !== 'granted') {
      return { supported: false, skippedReason: 'Permissão de notificação não concedida.' };
    }

    const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
    if (tokenData?.data) {
      await api.registerPushToken(tokenData.data, 'expo');
    }
    return { supported: true, token: tokenData?.data || null };
  } catch (error) {
    return {
      supported: false,
      skippedReason: error?.message || 'Falha ao registrar o push neste dispositivo.',
    };
  }
}

export function listenForNotificationResponses(onOpen) {
  return Notifications.addNotificationResponseReceivedListener((response) => {
    const data = response?.notification?.request?.content?.data || {};
    const messageId = Number(data.messageId || data.message_id || 0) || null;
    onOpen(messageId);
  });
}