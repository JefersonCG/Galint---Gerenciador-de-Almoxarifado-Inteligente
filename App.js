import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Keyboard, Platform, View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import Constants from 'expo-constants';
import * as Application from 'expo-application';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import * as Updates from 'expo-updates';

import UpdateChecker from './src/services/updateChecker';
import ApiService from './src/services/api';
import { emitNotifyInboxChanged } from './src/services/notifyEvents';
import { heroPalette, loadSavedTheme, saveServerTheme } from './src/theme/heroTheme';
import GalintIntro from './src/components/GalintIntro';

const Stack = createNativeStackNavigator();
const navigationRef = createNavigationContainerRef();

// As telas são carregadas só depois da abertura: cada uma monta seus estilos ao ser carregada, e
// assim já pega as cores da Aparência (tema guardado ou recebido do servidor nesta abertura).
let screens = null;
function loadScreens() {
    if (!screens) {
        /* eslint-disable global-require */
        screens = {
            LoginScreen: require('./src/screens/LoginScreen').default,
            EstoqueScreen: require('./src/screens/EstoqueScreen').default,
            MovimentoScreen: require('./src/screens/MovimentoScreen').default,
            EntradaNFScreen: require('./src/screens/EntradaNFScreen').default,
            ScannerScreen: require('./src/screens/ScannerScreen').default,
            EditarItemScreen: require('./src/screens/EditarItemScreen').default,
            RetiradaScreen: require('./src/screens/RetiradaScreen').default,
            DevolverScreen: require('./src/screens/DevolverScreen').default,
            DocumentosFiscaisScreen: require('./src/screens/DocumentosFiscaisScreen').default,
            ConfigScreen: require('./src/screens/ConfigScreen').default,
            MenuScreen: require('./src/screens/MenuScreen').default,
            ProfileScreen: require('./src/screens/ProfileScreen').default,
            NotificationsScreen: require('./src/screens/NotificationsScreen').default,
            ReportsScreen: require('./src/screens/ReportsScreen').default,
            ReportsDailyScreen: require('./src/screens/ReportsDailyScreen').default,
            ReportsMonthlyScreen: require('./src/screens/ReportsMonthlyScreen').default,
            ReportsHistoryScreen: require('./src/screens/ReportsHistoryScreen').default,
            ReportsConsumptionScreen: require('./src/screens/ReportsConsumptionScreen').default,
        };
        /* eslint-enable global-require */
    }
    return screens;
}

Notifications.setNotificationHandler({
    handleNotification: async () => ({
        shouldPlaySound: true,
        shouldSetBadge: false,
        shouldShowBanner: true,
        shouldShowList: true,
    }),
});

function resolveExpoProjectId() {
    return Constants?.expoConfig?.extra?.eas?.projectId || Constants?.easConfig?.projectId || null;
}

// Permissão de aviso e canal do Android: valem para os alertas locais da tela inicial (aviso novo
// com o app aberto). O token de push depende do Firebase, que este APK não tem; se falhar, os
// alertas locais continuam funcionando.
async function prepareNotifications() {
    if (!Device.isDevice) {
        return { success: false, skipped: true, reason: 'physical_device_required' };
    }

    const permissionState = await Notifications.getPermissionsAsync();
    let finalStatus = permissionState.status;
    if (finalStatus !== 'granted') {
        const request = await Notifications.requestPermissionsAsync();
        finalStatus = request.status;
    }
    if (finalStatus !== 'granted') {
        return { success: false, skipped: true, reason: 'permission_denied' };
    }

    if (Platform.OS === 'android') {
        await Notifications.setNotificationChannelAsync('default', {
            name: 'Avisos do GALINT',
            importance: Notifications.AndroidImportance.MAX,
            vibrationPattern: [0, 250, 250, 250],
            lightColor: '#22d3ee',
            sound: 'default',
        });
    }

    const projectId = resolveExpoProjectId();
    const response = projectId
        ? await Notifications.getExpoPushTokenAsync({ projectId })
        : await Notifications.getExpoPushTokenAsync();

    await AsyncStorage.setItem('last_expo_push_token', response.data);
    return { success: true, token: response.data };
}

class AppErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, message: '' };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, message: error?.message || 'Erro inesperado' };
    }

    componentDidCatch(error, info) {
        console.warn('Erro capturado pelo ErrorBoundary:', error, info);
    }

    handleReload = async () => {
        try {
            await Updates.reloadAsync();
        } catch (reloadError) {
            console.warn('Falha ao recarregar:', reloadError);
        }
    };

    render() {
        if (!this.state.hasError) return this.props.children;

        return (
            <View style={styles.errorContainer}>
                <Text style={styles.errorTitle}>O app encontrou um problema</Text>
                <Text style={styles.errorText}>{this.state.message}</Text>
                <TouchableOpacity style={styles.errorButton} onPress={this.handleReload}>
                    <Text style={styles.errorButtonText}>Reabrir</Text>
                </TouchableOpacity>
            </View>
        );
    }
}

export default function App() {
    const [themeReady, setThemeReady] = useState(false);
    const [bootDone, setBootDone] = useState(false);
    const [introDone, setIntroDone] = useState(false);

    // Abertura: tema guardado → base do celular → servidor salvo → tema atual do servidor.
    useEffect(() => {
        let alive = true;
        (async () => {
            await loadSavedTheme();
            if (alive) setThemeReady(true);
            try {
                await ApiService.ensureLocalReady();
                const config = await ApiService.loadSavedConfig();
                if (config) {
                    const tema = await ApiService.getTema();
                    if (tema.success) await saveServerTheme(tema.tema, { applyNow: screens === null });
                }
            } catch (error) {
                console.warn('[App] Abertura sem servidor:', error?.message || error);
            }
            if (alive) setBootDone(true);
        })();
        return () => {
            alive = false;
        };
    }, []);

    useEffect(() => {
        const notificationReceivedSubscription = Notifications.addNotificationReceivedListener((event) => {
            emitNotifyInboxChanged({
                reason: 'push-received',
                data: event?.request?.content?.data || {},
            });
        });

        const notificationResponseSubscription = Notifications.addNotificationResponseReceivedListener((response) => {
            emitNotifyInboxChanged({
                reason: 'push-response',
                data: response?.notification?.request?.content?.data || {},
            });
            if (navigationRef.isReady()) {
                navigationRef.navigate('Notifications');
            }
        });

        UpdateChecker.start();

        (async () => {
            try {
                const result = await prepareNotifications();
                const authToken = await ApiService.getToken();
                if (result?.success && result.token && authToken) {
                    const registration = await ApiService.registerNotifyPushToken(result.token);
                    if (!registration?.success && !registration?.skipped) {
                        console.warn('[Push] Falha ao registrar token:', registration?.message || 'erro desconhecido');
                    }
                }
            } catch (error) {
                // Sem Firebase no APK o token não sai; os alertas locais seguem funcionando.
                console.warn('[Push] Sem token de push:', error?.message || error);
            }
        })();

        return () => {
            UpdateChecker.stop();
            notificationReceivedSubscription.remove();
            notificationResponseSubscription.remove();
        };
    }, []);

    if (!themeReady) {
        return <View style={{ flex: 1, backgroundColor: heroPalette.bg }} />;
    }

    if (!introDone) {
        return (
            <>
                <StatusBar style="light" backgroundColor={heroPalette.bg} />
                <GalintIntro ready={bootDone} onFinish={() => setIntroDone(true)} version={Application.nativeApplicationVersion} />
            </>
        );
    }

    return (
        <SafeAreaProvider>
            <AppNavigator />
        </SafeAreaProvider>
    );
}

// O Android desenha o app atrás da barra de navegação (edge-to-edge): sem este recuo, o botão
// "Registrar Saída", a busca da tela inicial e os botões do leitor ficavam escondidos atrás
// dela (prints do usuário em 21/11/2026). O recuo vale para todas as telas.
function AppNavigator() {
    const insets = useSafeAreaInsets();
    const S = loadScreens();

    return (
        <AppErrorBoundary>
            {/* Regra do usuário (21/11/2026): teclado só aberto enquanto se digita; trocou de tela, fecha. */}
            <NavigationContainer ref={navigationRef} onStateChange={() => Keyboard.dismiss()}>
                <StatusBar style="light" backgroundColor={heroPalette.bgAlt} />
                <Stack.Navigator
                    initialRouteName="Login"
                    screenOptions={({ navigation, route }) => ({
                        headerStyle: {
                            backgroundColor: heroPalette.bgAlt,
                        },
                        headerTintColor: '#fff',
                        headerTitleStyle: {
                            fontWeight: 'bold',
                            color: heroPalette.text,
                        },
                        contentStyle: {
                            backgroundColor: heroPalette.bg,
                            paddingBottom: insets.bottom,
                        },
                        headerLeft: () => {
                            if (route.name === 'Login' || route.name === 'Estoque') return null;
                            if (!navigation.canGoBack()) return null;
                            return (
                                <TouchableOpacity
                                    onPress={() => navigation.goBack()}
                                    style={{ paddingHorizontal: 8 }}
                                >
                                    <Text style={{ color: '#fff', fontWeight: '700' }}>← Voltar</Text>
                                </TouchableOpacity>
                            );
                        },
                    })}
                >
                    <Stack.Screen name="Login" component={S.LoginScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="Estoque" component={S.EstoqueScreen} options={{ title: 'GALINT', headerBackVisible: false }} />
                    <Stack.Screen name="Movimento" component={S.MovimentoScreen} options={{ title: 'Movimento de material' }} />
                    <Stack.Screen name="EntradaNF" component={S.EntradaNFScreen} options={{ title: 'Lançar entrada' }} />
                    {/* Em espera desde a 2.2.0 (config/features.js): a rota fica, o menu não mostra. */}
                    <Stack.Screen name="DocumentosFiscais" component={S.DocumentosFiscaisScreen} options={{ title: 'Documentos Fiscais' }} />
                    <Stack.Screen name="Scanner" component={S.ScannerScreen} options={{ title: 'Escanear Código', headerTransparent: true }} />
                    <Stack.Screen name="EditarItem" component={S.EditarItemScreen} options={{ title: 'Editar Item' }} />
                    <Stack.Screen name="Retirada" component={S.RetiradaScreen} options={{ title: 'Retirar Material' }} />
                    <Stack.Screen name="Devolver" component={S.DevolverScreen} options={{ title: 'Devolução' }} />
                    <Stack.Screen name="Config" component={S.ConfigScreen} options={{ title: 'Configurações' }} />
                    <Stack.Screen name="Menu" component={S.MenuScreen} options={{ title: 'Painel' }} />
                    <Stack.Screen name="Profile" component={S.ProfileScreen} options={{ title: 'Perfil do Usuário' }} />
                    <Stack.Screen name="Notifications" component={S.NotificationsScreen} options={{ title: 'Avisos' }} />
                    <Stack.Screen name="Reports" component={S.ReportsScreen} options={{ title: 'Relatórios' }} />
                    <Stack.Screen name="ReportsDaily" component={S.ReportsDailyScreen} options={{ title: 'Relatório Diário' }} />
                    <Stack.Screen name="ReportsMonthly" component={S.ReportsMonthlyScreen} options={{ title: 'Relatório Mensal' }} />
                    <Stack.Screen name="ReportsConsumption" component={S.ReportsConsumptionScreen} options={{ title: 'Consumo Analítico' }} />
                    <Stack.Screen name="ReportsHistory" component={S.ReportsHistoryScreen} options={{ title: 'Histórico de Relatórios' }} />
                </Stack.Navigator>
            </NavigationContainer>
        </AppErrorBoundary>
    );
}

const styles = StyleSheet.create({
    errorContainer: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.bg,
        padding: 24,
    },
    errorTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 8,
        textAlign: 'center',
    },
    errorText: {
        fontSize: 14,
        color: heroPalette.textMuted,
        textAlign: 'center',
        marginBottom: 16,
    },
    errorButton: {
        backgroundColor: heroPalette.primaryStrong,
        paddingVertical: 10,
        paddingHorizontal: 20,
        borderRadius: 8,
    },
    errorButtonText: {
        color: heroPalette.bg,
        fontWeight: '600',
    },
});
