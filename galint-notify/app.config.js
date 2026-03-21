export default {
  expo: {
    name: 'GalintNotify',
    slug: 'galint-notify',
    version: '1.0.0',
    icon: './galintnotify.png',
    orientation: 'portrait',
    userInterfaceStyle: 'dark',
    assetBundlePatterns: ['**/*'],
    android: {
      package: process.env.GALINT_NOTIFY_ANDROID_PACKAGE || 'com.galint.notify',
      permissions: ['POST_NOTIFICATIONS'],
      usesCleartextTraffic: true,
      adaptiveIcon: {
        foregroundImage: './galintnotify.png',
        backgroundColor: '#07111f',
      },
    },
    plugins: ['expo-notifications'],
    extra: {
      eas: {
        projectId: process.env.EXPO_PUBLIC_GALINT_NOTIFY_PROJECT_ID || '5289becd-f76f-451b-a24d-2385d9513da6',
      },
      defaultServerUrl: process.env.EXPO_PUBLIC_GALINT_NOTIFY_SERVER_URL || 'http://192.168.1.41:5000',
    },
  },
};