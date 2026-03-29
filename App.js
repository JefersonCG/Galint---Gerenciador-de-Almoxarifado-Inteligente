import 'react-native-gesture-handler';
import React, { useEffect, useMemo, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import { Alert, View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import * as Updates from 'expo-updates';

import LoginScreen from './src/screens/LoginScreen';
import EstoqueScreen from './src/screens/EstoqueScreen';
import ScannerScreen from './src/screens/ScannerScreen';
import EditarItemScreen from './src/screens/EditarItemScreen';
import RetiradaScreen from './src/screens/RetiradaScreen';
import DevolverScreen from './src/screens/DevolverScreen';
import ConfigScreen from './src/screens/ConfigScreen';
import MenuScreen from './src/screens/MenuScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import NotificationsScreen from './src/screens/NotificationsScreen';
import ReportsScreen from './src/screens/ReportsScreen';
import ReportsDailyScreen from './src/screens/ReportsDailyScreen';
import ReportsMonthlyScreen from './src/screens/ReportsMonthlyScreen';
import ReportsHistoryScreen from './src/screens/ReportsHistoryScreen';
import UpdateChecker from './src/services/updateChecker';
import ApiService from './src/services/api';
import { initOfflineDb } from './src/services/offlineDb'; // Inicializar DB

const Stack = createNativeStackNavigator();

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

        // Cleanup ao desmontar
        return () => {
            console.log('[App] Parando UpdateChecker...');
            UpdateChecker.stop();
            if (unsubscribeNet) unsubscribeNet();
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
            <NavigationContainer>
                <StatusBar style="light" backgroundColor="#0d6efd" />
                <Stack.Navigator
                    initialRouteName="Login"
                    screenOptions={({ navigation, route }) => ({
                        headerStyle: {
                            backgroundColor: '#0d6efd',
                        },
                        headerTintColor: '#fff',
                        headerTitleStyle: {
                            fontWeight: 'bold',
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
                            title: 'GALINT - Estoque',
                            headerBackVisible: false
                        }}
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
                        options={{ title: 'Menu' }}
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
        backgroundColor: '#0b3a82',
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
        color: '#dbeafe',
        marginTop: 6,
        marginBottom: 22,
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
        backgroundColor: 'rgba(255,255,255,0.25)',
        borderRadius: 3,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.4)',
    },
    progressBoxActive: {
        backgroundColor: '#22c55e',
        borderColor: '#ffffff',
    },
    progressText: {
        marginTop: 12,
        color: '#ffffff',
        fontWeight: '700',
    },
    errorContainer: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#ffffff',
        padding: 24,
    },
    errorTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 8,
        textAlign: 'center',
    },
    errorText: {
        fontSize: 14,
        color: '#6b7280',
        textAlign: 'center',
        marginBottom: 16,
    },
    errorButton: {
        backgroundColor: '#0d6efd',
        paddingVertical: 10,
        paddingHorizontal: 20,
        borderRadius: 8,
    },
    errorButtonText: {
        color: '#ffffff',
        fontWeight: '600',
    },
});

