import 'react-native-gesture-handler';
import React, { useEffect, useMemo, useState } from 'react';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Alert, Platform, View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import * as Updates from 'expo-updates';

import LoginScreen from './src/screens/LoginScreen';
import EstoqueScreen from './src/screens/EstoqueScreen';
import ScannerScreen from './src/screens/ScannerScreen';
import EditarItemScreen from './src/screens/EditarItemScreen';
import RetiradaScreen from './src/screens/RetiradaScreen';
import DevolverScreen from './src/screens/DevolverScreen';
import DocumentosFiscaisScreen from './src/screens/DocumentosFiscaisScreen';
import ConfigScreen from './src/screens/ConfigScreen';
import MenuScreen from './src/screens/MenuScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import NotificationsScreen from './src/screens/NotificationsScreen';
import ReportsScreen from './src/screens/ReportsScreen';
import ReportsDailyScreen from './src/screens/ReportsDailyScreen';
import ReportsMonthlyScreen from './src/screens/ReportsMonthlyScreen';
import ReportsHistoryScreen from './src/screens/ReportsHistoryScreen';
import ReportsConsumptionScreen from './src/screens/ReportsConsumptionScreen';
import UpdateChecker from './src/services/updateChecker';
import ApiService from './src/services/api';
import { initOfflineDb } from './src/services/offlineDb'; // Inicializar DB
import { emitNotifyInboxChanged } from './src/services/notifyEvents';
import { heroPalette } from './src/theme/heroTheme';

const Stack = createNativeStackNavigator();
const navigationRef = createNavigationContainerRef();

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

async function getExpoPushToken() {
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
            name: 'default',
            importance: Notifications.AndroidImportance.MAX,
            vibrationPattern: [0, 250, 250, 250],
            lightColor: '#0d6efd',
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
    const [isReady, setIsReady] = useState(false);
    const [progress, setProgress] = useState(0);

    useEffect(() => {
        // Inicializar Banco de Dados Offline
        initOfflineDb().catch(err => console.error("Erro ao iniciar DB:", err));

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

        // Inicia o sistema de verificação automática de atualizações
        console.log('[App] Iniciando UpdateChecker...');
        UpdateChecker.start();

        let unsubscribeNet;
        try {
            // Carrega NetInfo de forma segura
            // eslint-disable-next-line global-require
            const NetInfo = require('@react-native-community/netinfo');
            unsubscribeNet = NetInfo.addEventListener((state) => {
                const online = state?.isConnected && state?.isInternetReachable !== false;
                if (online) {
                    ApiService.syncPendingOps().catch(() => {});
                }
            });
        } catch (error) {
            // Sem NetInfo disponível, não registra listener
        }

        ApiService.loadSavedConfig()
            .then(async (config) => {
                if (!config) return;
                const authToken = await ApiService.getToken();
                if (!authToken) return;

                const pushTokenResult = await getExpoPushToken();
                if (!pushTokenResult?.success || !pushTokenResult?.token) {
                    return;
                }

                const registrationResult = await ApiService.registerNotifyPushToken(pushTokenResult.token);
                if (!registrationResult?.success && !registrationResult?.skipped) {
                    console.warn('[Push] Falha ao registrar token:', registrationResult?.message || 'erro desconhecido');
                }
            })
            .catch((error) => {
                console.warn('[Push] Falha na inicialização automática:', error?.message || error);
            });

        // Cleanup ao desmontar
        return () => {
            console.log('[App] Parando UpdateChecker...');
            UpdateChecker.stop();
            if (unsubscribeNet) unsubscribeNet();
            notificationReceivedSubscription.remove();
            notificationResponseSubscription.remove();
        };
    }, []);

    useEffect(() => {
        let progressInterval;
        let readyTimeout;

        progressInterval = setInterval(() => {
            setProgress((prev) => {
                if (prev >= 0.92) return prev;
                return Math.min(prev + 0.06, 0.92);
            });
        }, 180);

        readyTimeout = setTimeout(() => {
            setProgress(1);
            setIsReady(true);
        }, 1600);

        return () => {
            if (progressInterval) clearInterval(progressInterval);
            if (readyTimeout) clearTimeout(readyTimeout);
        };
    }, []);

    const progressPercent = useMemo(() => Math.round(progress * 100), [progress]);

    if (!isReady) {
        return (
            <View style={styles.splashContainer}>
                <Text style={styles.splashTitle}>GALINT</Text>
                <Text style={styles.splashSubtitle}>Sistema de almoxarifado</Text>
                
                <View style={styles.progressContainer}>
                    <View style={styles.progressTrack}>
                        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((index) => {
                            const isActive = progressPercent >= (index + 1) * 10;
                            return (
                                <View
                                    key={index}
                                    style={[
                                        styles.progressBox,
                                        isActive && styles.progressBoxActive
                                    ]}
                                />
                            );
                        })}
                    </View>
                </View>
                
                <Text style={styles.progressText}>{progressPercent}%</Text>
            </View>
        );
    }

    return (
        <AppErrorBoundary>
            <NavigationContainer ref={navigationRef}>
                <StatusBar style="light" backgroundColor={heroPalette.bg} />
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
                    <Stack.Screen
                        name="Login"
                        component={LoginScreen}
                        options={{ headerShown: false }}
                    />
                    <Stack.Screen
                        name="Estoque"
                        component={EstoqueScreen}
                        options={{
                            title: 'GALINT Mobile',
                            headerBackVisible: false,
                        }}
                    />
                    <Stack.Screen
                        name="DocumentosFiscais"
                        component={DocumentosFiscaisScreen}
                        options={{ title: 'Documentos Fiscais' }}
                    />
                    <Stack.Screen
                        name="Scanner"
                        component={ScannerScreen}
                        options={{
                            title: 'Escanear Código',
                            headerTransparent: true
                        }}
                    />

                    <Stack.Screen
                        name="EditarItem"
                        component={EditarItemScreen}
                        options={{ title: 'Editar Item' }}
                    />

                    <Stack.Screen
                        name="Retirada"
                        component={RetiradaScreen}
                        options={{ title: 'Retirar Material' }}
                    />

                    <Stack.Screen
                        name="Devolver"
                        component={DevolverScreen}
                        options={{ title: 'Devolução' }}
                    />
                    <Stack.Screen
                        name="Config"
                        component={ConfigScreen}
                        options={{ title: 'Configurações' }}
                    />
                    <Stack.Screen
                        name="Menu"
                        component={MenuScreen}
                        options={{ title: 'Painel' }}
                    />
                    <Stack.Screen
                        name="Profile"
                        component={ProfileScreen}
                        options={{ title: 'Perfil do Usuário' }}
                    />
                    <Stack.Screen
                        name="Notifications"
                        component={NotificationsScreen}
                        options={{ title: 'Notificações' }}
                    />
                    <Stack.Screen
                        name="Reports"
                        component={ReportsScreen}
                        options={{ title: 'Relatórios' }}
                    />
                    <Stack.Screen
                        name="ReportsDaily"
                        component={ReportsDailyScreen}
                        options={{ title: 'Relatório Diário' }}
                    />
                    <Stack.Screen
                        name="ReportsMonthly"
                        component={ReportsMonthlyScreen}
                        options={{ title: 'Relatório Mensal' }}
                    />
                    <Stack.Screen
                        name="ReportsConsumption"
                        component={ReportsConsumptionScreen}
                        options={{ title: 'Consumo Analítico' }}
                    />
                    <Stack.Screen
                        name="ReportsHistory"
                        component={ReportsHistoryScreen}
                        options={{ title: 'Histórico de Relatórios' }}
                    />
                </Stack.Navigator>
            </NavigationContainer>
        </AppErrorBoundary>
    );
}

const styles = StyleSheet.create({
    splashContainer: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.bg,
        padding: 24,
    },
    splashTitle: {
        fontSize: 34,
        fontWeight: '800',
        color: '#ffffff',
        letterSpacing: 0.8,
    },
    splashSubtitle: {
        fontSize: 15,
        color: heroPalette.textMuted,
        marginTop: 6,
        marginBottom: 22,
    },
    headerActionButton: {
        minWidth: 60,
        height: 34,
        borderRadius: 16,
        paddingHorizontal: 12,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(34, 211, 238, 0.16)',
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    headerActionButtonText: {
        color: heroPalette.text,
        fontSize: 13,
        fontWeight: '800',
    },
    progressContainer: {
        width: '86%',
        marginTop: 10,
    },
    progressTrack: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        height: 14,
        gap: 4,
    },
    progressBox: {
        flex: 1,
        height: 14,
        backgroundColor: 'rgba(255,255,255,0.12)',
        borderRadius: 3,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    progressBoxActive: {
        backgroundColor: heroPalette.primaryStrong,
        borderColor: heroPalette.text,
    },
    progressText: {
        marginTop: 12,
        color: heroPalette.text,
        fontWeight: '700',
    },
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

