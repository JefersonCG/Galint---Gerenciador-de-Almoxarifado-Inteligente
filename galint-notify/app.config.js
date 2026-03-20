export default {
  expo: {
    name: 'GalintNotify',
    slug: 'galint-notify',
    version: '1.0.0',
    orientation: 'portrait',
    userInterfaceStyle: 'dark',
    assetBundlePatterns: ['**/*'],
    android: {
      package: process.env.GALINT_NOTIFY_ANDROID_PACKAGE || 'com.galint.notify',
      permissions: ['POST_NOTIFICATIONS'],
    },
    plugins: ['expo-notifications'],
    extra: {
      eas: {
        projectId: process.env.EXPO_PUBLIC_GALINT_NOTIFY_PROJECT_ID || '',
      },
      defaultServerUrl: process.env.EXPO_PUBLIC_GALINT_NOTIFY_SERVER_URL || 'http://192.168.1.41:5000',
    },
  },
};