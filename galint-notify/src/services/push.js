import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

import api from './api';

export async function bootstrapPush(session) {
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId || !session) {
    return null;
  }

  const permission = await Notifications.requestPermissionsAsync();
  if (permission.status !== 'granted') {
    return null;
  }

  const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
  if (tokenData?.data) {
    await api.registerPushToken(tokenData.data, 'expo');
  }
  return tokenData?.data || null;
}

export function listenForNotificationResponses(onOpen) {
  return Notifications.addNotificationResponseReceivedListener((response) => {
    const data = response?.notification?.request?.content?.data || {};
    const messageId = Number(data.messageId || data.message_id || 0) || null;
    onOpen(messageId);
  });
}