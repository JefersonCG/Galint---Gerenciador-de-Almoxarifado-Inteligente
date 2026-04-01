import 'react-native-reanimated';
import 'react-native-gesture-handler';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, Text, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import Constants from 'expo-constants';
import { StatusBar } from 'expo-status-bar';
import * as Notifications from 'expo-notifications';

import LoginScreen from './src/screens/LoginScreen';
import MessengerScreen from './src/screens/MessengerScreen';
import NotificationDetailScreen from './src/screens/NotificationDetailScreen';
import ReportsScreen from './src/screens/ReportsScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import ToolsScreen from './src/screens/ToolsScreen';
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

function AppShell({ navigation, route, session, onLogout, onServerSaved, highlightMessageId, onConsumedHighlight }) {
  const [activeScreen, setActiveScreen] = useState(route?.params?.screen || 'Messenger');

  const menuItems = [
    { key: 'Messenger', label: 'Messenger' },
    { key: 'Relatórios', label: 'Relatórios' },
    { key: 'Ferramentas', label: 'Ferramentas' },
    { key: 'Configurações', label: 'Configurações' },
  ];

  useEffect(() => {
    const requestedScreen = route?.params?.screen;
    if (requestedScreen) {
      setActiveScreen(requestedScreen);
    }
  }, [route?.params?.screen]);

  useEffect(() => {
    if (highlightMessageId) {
      setActiveScreen('Messenger');
    }
  }, [highlightMessageId]);

  let content = (
    <MessengerScreen
      navigation={navigation}
      session={session}
      highlightMessageId={highlightMessageId}
      onConsumedHighlight={onConsumedHighlight}
    />
  );

  if (activeScreen === 'Relatórios') {
    content = <ReportsScreen navigation={navigation} session={session} />;
  }

  if (activeScreen === 'Ferramentas') {
    content = <ToolsScreen navigation={navigation} session={session} />;
  }

  if (activeScreen === 'Configurações') {
    content = (
      <SettingsScreen
        navigation={navigation}
        session={session}
        onLogout={onLogout}
        onServerSaved={onServerSaved}
      />
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: palette.bg }}>
      <View style={{ paddingHorizontal: 16, paddingTop: 18, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: palette.border, backgroundColor: palette.panel }}>
        <Text style={{ color: palette.text, fontSize: 18, fontWeight: '800', marginBottom: 12 }}>GalintNotify</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {menuItems.map((item) => (
            <Pressable
              key={item.key}
              onPress={() => setActiveScreen(item.key)}
              style={{
                flex: 1,
                borderRadius: 999,
                paddingVertical: 10,
                paddingHorizontal: 12,
                backgroundColor: activeScreen === item.key ? palette.primary : palette.panelAlt,
                borderWidth: 1,
                borderColor: activeScreen === item.key ? palette.primary : palette.border,
                alignItems: 'center',
              }}
            >
              <Text style={{ color: activeScreen === item.key ? palette.bg : palette.text, fontWeight: '700', fontSize: 12 }}>{item.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      <View style={{ flex: 1 }}>{content}</View>
    </View>
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
    },
    async logout() {
      await api.logout();
      setSession(null);
      setHighlightMessageId(null);
    },
    async refreshServer() {
      const current = await api.restoreSession();
      setSession(current);
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
                <AppShell
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