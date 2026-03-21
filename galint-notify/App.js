import 'react-native-reanimated';
import 'react-native-gesture-handler';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, Text, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createDrawerNavigator } from '@react-navigation/drawer';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import * as Notifications from 'expo-notifications';

import LoginScreen from './src/screens/LoginScreen';
import MessengerScreen from './src/screens/MessengerScreen';
import NotificationDetailScreen from './src/screens/NotificationDetailScreen';
import ReportsScreen from './src/screens/ReportsScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import api from './src/services/api';
import { palette } from './src/theme';
import { bootstrapPush, listenForNotificationResponses } from './src/services/push';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

const Drawer = createDrawerNavigator();
const Stack = createNativeStackNavigator();

const navTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: palette.bg,
    card: palette.panel,
    text: palette.text,
    border: palette.border,
    primary: palette.primary,
  },
};

function DrawerShell({ session, onLogout, onServerSaved, highlightMessageId, onConsumedHighlight }) {
  return (
    <Drawer.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: palette.panel },
        headerTintColor: palette.text,
        sceneContainerStyle: { backgroundColor: palette.bg },
        drawerStyle: { backgroundColor: palette.panel },
        drawerActiveTintColor: palette.primary,
        drawerInactiveTintColor: palette.muted,
      }}
    >
      <Drawer.Screen name="Messenger" options={{ title: 'Messenger' }}>
        {(props) => (
          <MessengerScreen
            {...props}
            session={session}
            highlightMessageId={highlightMessageId}
            onConsumedHighlight={onConsumedHighlight}
          />
        )}
      </Drawer.Screen>
      <Drawer.Screen name="Relatórios">
        {(props) => <ReportsScreen {...props} session={session} />}
      </Drawer.Screen>
      <Drawer.Screen name="Configurações">
        {(props) => <SettingsScreen {...props} session={session} onLogout={onLogout} onServerSaved={onServerSaved} />}
      </Drawer.Screen>
    </Drawer.Navigator>
  );
}

export default function App() {
  const navigationRef = useRef(null);
  const [booting, setBooting] = useState(true);
  const [session, setSession] = useState(null);
  const [highlightMessageId, setHighlightMessageId] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function bootstrap() {
      try {
        const restored = await api.restoreSession();
        if (mounted) {
          setSession(restored);
        }
      } catch (error) {
        Alert.alert('GalintNotify', error.message || 'Falha ao carregar sessão');
      } finally {
        if (mounted) setBooting(false);
      }
    }

    bootstrap();
    const sub = listenForNotificationResponses((messageId) => {
      setHighlightMessageId(messageId || null);
      if (navigationRef.current && messageId) {
        navigationRef.current.navigate('App', { screen: 'Messenger' });
      }
    });

    return () => {
      mounted = false;
      sub.remove();
    };
  }, []);

  const actions = useMemo(() => ({
    async login({ matricula, senha }) {
      const nextSession = await api.login({ matricula, senha });
      setSession(nextSession);
      await bootstrapPush(nextSession);
    },
    async logout() {
      await api.logout();
      setSession(null);
      setHighlightMessageId(null);
    },
    async refreshServer() {
      const current = await api.restoreSession();
      setSession(current);
      if (current) {
        await bootstrapPush(current);
      }
    },
  }), []);

  if (booting) {
    return (
      <View style={{ flex: 1, backgroundColor: palette.bg, alignItems: 'center', justifyContent: 'center' }}>
        <StatusBar style="light" />
        <ActivityIndicator color={palette.primary} size="large" />
        <Text style={{ color: palette.text, marginTop: 12 }}>Inicializando GalintNotify...</Text>
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <NavigationContainer ref={navigationRef} theme={navTheme}>
        <StatusBar style="light" />
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          {!session ? (
            <Stack.Screen name="Login">
              {(props) => <LoginScreen {...props} onLogin={actions.login} />}
            </Stack.Screen>
          ) : (
            <Stack.Screen name="App">
              {(props) => (
                <DrawerShell
                  {...props}
                  session={session}
                  onLogout={actions.logout}
                  onServerSaved={actions.refreshServer}
                  highlightMessageId={highlightMessageId}
                  onConsumedHighlight={() => setHighlightMessageId(null)}
                />
              )}
            </Stack.Screen>
          )}
          <Stack.Screen name="NotificationDetail" component={NotificationDetailScreen} options={{ headerShown: true, title: 'Detalhes da notificação', headerStyle: { backgroundColor: palette.panel }, headerTintColor: palette.text }} />
        </Stack.Navigator>
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}