import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Alert,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
    ActivityIndicator,
    Switch,
    Image,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ApiService from '../services/api';
import { loadServerConfig, saveServerConfig, clearServerConfig, loadCredentials, saveCredentials } from '../utils/storage';

// Importação condicional do Ionicons com fallback
let Ionicons = null;
try {
    Ionicons = require('@expo/vector-icons').Ionicons;
} catch (error) {
    console.warn('Ionicons não pôde ser carregado:', error);
}

export default function LoginScreen({ navigation }) {
    const [serverIP, setServerIP] = useState('10.0.0.245');
    const [serverPort, setServerPort] = useState('5000');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [rememberMe, setRememberMe] = useState(false);
    const [loading, setLoading] = useState(false);
    const [testing, setTesting] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState(null);
    const [showConfig, setShowConfig] = useState(true);

    useEffect(() => {
        loadSavedData();
    }, []);

    const loadSavedData = async () => {
        const config = await loadServerConfig();
        if (config) {
            setServerIP(config.serverIP);
            setServerPort(config.serverPort.toString());
            setShowConfig(false);
        }

        const creds = await loadCredentials();
        if (creds) {
            setUsername(creds.username);
            setPassword(creds.password);
            setRememberMe(true);
        }
    };

    const handleClearConfig = async () => {
        await clearServerConfig();
        setServerPort('5000');
        setShowConfig(true);
        setConnectionStatus(null);
        Alert.alert('OK', 'Configuração do servidor limpa. Configure novamente e teste a conexão.');
    };

    const handleTestConnection = async () => {
        if (!serverIP || !serverPort) {
            Alert.alert('Erro', 'Preencha IP e Porta do servidor');
            return;
        }

        setTesting(true);
        setConnectionStatus(null);

        try {
            await ApiService.initialize(serverIP, serverPort);
            const result = await ApiService.testConnection();

            setConnectionStatus(result.success ? 'success' : 'error');

            if (result.success) {
                Alert.alert('Sucesso!', result.message);
                setShowConfig(false);
            } else {
                Alert.alert('Erro de Conexão', result.message);
            }
        } catch (error) {
            setConnectionStatus('error');
            const url = `http://${serverIP}:${serverPort}/api/mobile/health`;
            const details = error?.message ? `\n\nDetalhes: ${error.message}` : '';
            Alert.alert('Erro', `Não foi possível conectar ao servidor.\n\nTeste: ${url}${details}`);
        } finally {
            setTesting(false);
        }
    };

    const handleLogin = async () => {
        if (!username || !password) {
            Alert.alert('Erro', 'Preencha usuário e senha');
            return;
        }

        setLoading(true);

        try {
            // Inicializar API sempre com IP/porta atuais (permite trocar ambiente)
            await ApiService.initialize(serverIP, serverPort);

            const result = await ApiService.login(username, password);

            if (result.success) {
                await ApiService.setOfflineMode(false);
                await saveCredentials(username, password, rememberMe);
                await saveServerConfig(serverIP, serverPort);
                try {
                    const pushRegistration = await ApiService.getToken();
                    if (pushRegistration) {
                        // O bootstrap do App faz a aquisição do Expo token; aqui só reaproveitamos o fluxo se ele já estiver disponível.
                        const lastPushToken = await AsyncStorage.getItem('last_expo_push_token');
                        if (lastPushToken) {
                            await ApiService.registerNotifyPushToken(lastPushToken);
                        }
                    }
                } catch (error) {
                    console.warn('[Login] Não foi possível sincronizar push token:', error?.message || error);
                }
                
                // 🔄 PRE-LOAD DO ESTOQUE COMPLETO (modo offline aprimorado)
                console.log('[Login] Iniciando pre-load do estoque...');
                const preloadResult = await ApiService.preloadEstoqueCompleto();
                if (preloadResult.success) {
                    console.log(`[Login] ✅ ${preloadResult.totalItens} itens salvos no cache`);
                } else if (preloadResult.offline) {
                    console.log('[Login] ⚠️ Pre-load pulado (sem conexão)');
                } else {
                    console.log('[Login] ⚠️ Pre-load falhou:', preloadResult.message);
                }
                
                navigation.reset({
                    index: 0,
                    routes: [{ name: 'Estoque', params: { user: result.user } }],
                });
            } else {
                Alert.alert('Erro', result.message);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao fazer login');
        } finally {
            setLoading(false);
        }
    };

    const handleOfflineAccess = async () => {
        setLoading(true);
        try {
            await ApiService.ensureOfflineReady();
            await ApiService.setOfflineMode(true);

            let offlineUser = null;
            try {
                const storedUser = await AsyncStorage.getItem('user');
                if (storedUser) {
                    offlineUser = JSON.parse(storedUser);
                }
            } catch (error) {
                offlineUser = null;
            }

            if (!offlineUser) {
                const fallbackName = (username || '').toString().trim() || 'Usuário Offline';
                offlineUser = {
                    nome: fallbackName,
                    matricula: (username || '').toString().trim() || null,
                    cargo: 'Offline',
                    setor: 'Offline',
                    is_offline: true,
                };
            }

            navigation.reset({
                index: 0,
                routes: [{ name: 'Estoque', params: { user: offlineUser, offline: true } }],
            });
        } catch (error) {
            Alert.alert('Erro', 'Falha ao iniciar modo offline');
        } finally {
            setLoading(false);
        }
    };

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <ScrollView
                contentContainerStyle={styles.scrollContent}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
            >
                {/* Header com Logo */}
                <View style={styles.header}>
                    <Image 
                        source={require('../../assets/galint-logo.png')}
                        style={styles.logoImage}
                        resizeMode="contain"
                    />
                    <Text style={styles.title}>Gestão de Almoxarifado</Text>
                    <Text style={styles.subtitle}>Sublime Max Condominium</Text>
                </View>

                {/* Card de Login */}
                <View style={styles.loginCard}>
                    <Text style={styles.loginTitle}>Login</Text>

                    {/* Input Usuário */}
                    <View style={styles.inputContainer}>
                        <Text style={styles.inputLabel}>Usuário</Text>
                        <View style={styles.inputWrapper}>
                            <Text style={styles.inputIcon}>👤</Text>
                            <TextInput
                                style={styles.input}
                                value={username}
                                onChangeText={setUsername}
                                placeholder="Digite o nome ou matrícula"
                                placeholderTextColor="#9ca3af"
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                        </View>
                    </View>

                    {/* Input Senha */}
                    <View style={styles.inputContainer}>
                        <Text style={styles.inputLabel}>Senha</Text>
                        <View style={styles.inputWrapper}>
                            <Text style={styles.inputIcon}>🔒</Text>
                            <TextInput
                                style={styles.input}
                                value={password}
                                onChangeText={setPassword}
                                placeholder="••• ••• •••"
                                placeholderTextColor="#9ca3af"
                                secureTextEntry={!showPassword}
                                autoCapitalize="none"
                            />
                            <TouchableOpacity
                                onPress={() => setShowPassword(!showPassword)}
                                style={styles.eyeButton}
                            >
                                <Text style={{ fontSize: 20 }}>{showPassword ? '👁️' : '🙈'}</Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                    {/* Lembrar Credenciais */}
                    <View style={styles.rememberContainer}>
                        <Text style={styles.rememberLabel}>Lembrar credenciais</Text>
                        <Switch
                            value={rememberMe}
                            onValueChange={setRememberMe}
                            trackColor={{ false: '#d1d5db', true: '#3b82f6' }}
                            thumbColor={rememberMe ? '#fff' : '#f4f3f4'}
                            ios_backgroundColor="#d1d5db"
                        />
                    </View>

                    {/* Botão Entrar */}
                    <TouchableOpacity
                        style={[styles.loginButton, loading && styles.buttonDisabled]}
                        onPress={handleLogin}
                        disabled={loading}
                        activeOpacity={0.8}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" size="small" />
                        ) : (
                            <>
                                <Text style={{ fontSize: 20, marginRight: 8 }}>➡️</Text>
                                <Text style={styles.loginButtonText}>Entrar</Text>
                            </>
                        )}
                    </TouchableOpacity>

                    <TouchableOpacity
                        style={[styles.offlineButton, loading && styles.buttonDisabled]}
                        onPress={handleOfflineAccess}
                        disabled={loading}
                        activeOpacity={0.8}
                    >
                        <Text style={{ fontSize: 20, marginRight: 8 }}>📴</Text>
                        <Text style={styles.offlineButtonText}>Entrar offline</Text>
                    </TouchableOpacity>

                    {/* Configuração do Servidor */}
                    <TouchableOpacity
                        style={styles.configButton}
                        onPress={() => setShowConfig(!showConfig)}
                        activeOpacity={0.7}
                    >
                        <Text style={{ fontSize: 16, marginRight: 6 }}>⚙️</Text>
                        <Text style={styles.configButtonText}>
                            {showConfig ? 'Ocultar configuração' : 'Configuração do servidor'}
                        </Text>
                        {connectionStatus === 'success' && !showConfig && (
                            <View style={styles.connectedDot} />
                        )}
                    </TouchableOpacity>
                </View>

                {/* Painel de Configuração (Expansível) */}
                {showConfig && (
                    <View style={styles.configCard}>
                        <View style={styles.configHeader}>
                            <Text style={{ fontSize: 20, marginRight: 8 }}>🖥️</Text>
                            <Text style={styles.configTitle}>Configuração do Servidor</Text>
                        </View>

                        <View style={styles.inputContainer}>
                            <Text style={styles.inputLabel}>IP do Servidor</Text>
                            <View style={styles.inputWrapper}>
                                <Text style={styles.inputIcon}>🌐</Text>
                                <TextInput
                                    style={styles.input}
                                    value={serverIP}
                                    onChangeText={setServerIP}
                                    placeholder="ex: 10.0.0.245"
                                    placeholderTextColor="#9ca3af"
                                    keyboardType="numeric"
                                    autoCapitalize="none"
                                />
                            </View>
                        </View>

                        <View style={styles.inputContainer}>
                            <Text style={styles.inputLabel}>Porta</Text>
                            <View style={styles.inputWrapper}>
                                <Text style={styles.inputIcon}>🔌</Text>
                                <TextInput
                                    style={styles.input}
                                    value={serverPort}
                                    onChangeText={setServerPort}
                                    placeholder="ex: 5000"
                                    placeholderTextColor="#9ca3af"
                                    keyboardType="numeric"
                                />
                            </View>
                        </View>

                        <TouchableOpacity
                            style={[styles.testButton, testing && styles.buttonDisabled]}
                            onPress={handleTestConnection}
                            disabled={testing}
                            activeOpacity={0.8}
                        >
                            {testing ? (
                                <ActivityIndicator color="#fff" size="small" />
                            ) : (
                                <>
                                    <Text style={{ fontSize: 20, marginRight: 8 }}>✅</Text>
                                    <Text style={styles.testButtonText}>
                                        {connectionStatus === 'success' ? 'Testar Novamente' : 'Testar Conexão'}
                                    </Text>
                                </>
                            )}
                        </TouchableOpacity>

                        <TouchableOpacity
                            style={styles.clearButton}
                            onPress={handleClearConfig}
                            disabled={testing || loading}
                            activeOpacity={0.7}
                        >
                            <Text style={{ fontSize: 16, marginRight: 6, color: '#ef4444' }}>🗑️</Text>
                            <Text style={styles.clearButtonText}>Limpar configuração</Text>
                        </TouchableOpacity>
                    </View>
                )}

                {/* Footer */}
                <Text style={styles.footer}>© 2026 Sublime Max Condominium · GALINT v1.2.0</Text>
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f8fafc',
    },
    scrollContent: {
        flexGrow: 1,
        paddingHorizontal: 24,
        paddingVertical: 40,
        justifyContent: 'center',
    },
    
    // Header com Logo
    header: {
        alignItems: 'center',
        marginBottom: 32,
    },
    logoImage: {
        width: 660,
        height: 300,
        marginBottom: 6,
    },
    title: {
        fontSize: 18,
        fontWeight: '600',
        color: '#374151',
        marginTop: 4,
        letterSpacing: 0.5,
    },
    subtitle: {
        fontSize: 16,
        color: '#0d6efd',
        fontWeight: '700',
        marginTop: 2,
        letterSpacing: 0.3,
    },

    // Card de Login
    loginCard: {
        backgroundColor: '#ffffff',
        borderRadius: 16,
        padding: 24,
        marginBottom: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 8,
        elevation: 3,
        borderWidth: 1,
        borderColor: '#f1f5f9',
    },
    loginTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 20,
        textAlign: 'center',
    },

    // Inputs
    inputContainer: {
        marginBottom: 16,
    },
    inputLabel: {
        fontSize: 13,
        fontWeight: '600',
        color: '#374151',
        marginBottom: 8,
        letterSpacing: 0.3,
    },
    inputWrapper: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#f9fafb',
        borderWidth: 1,
        borderColor: '#e5e7eb',
        borderRadius: 10,
        paddingHorizontal: 14,
        height: 50,
    },
    inputIcon: {
        marginRight: 10,
        fontSize: 20,
        color: '#6b7280',
    },
    input: {
        flex: 1,
        fontSize: 15,
        color: '#111827',
        height: '100%',
    },
    eyeButton: {
        padding: 4,
    },

    // Lembrar Credenciais
    rememberContainer: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 24,
        paddingHorizontal: 4,
    },
    rememberLabel: {
        fontSize: 14,
        color: '#6b7280',
        fontWeight: '500',
    },

    // Botão Entrar
    loginButton: {
        backgroundColor: '#2563eb',
        height: 52,
        borderRadius: 10,
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 16,
        shadowColor: '#2563eb',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 4,
    },
    loginButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
        letterSpacing: 0.5,
    },

    // Botão Offline
    offlineButton: {
        backgroundColor: '#0f172a',
        height: 50,
        borderRadius: 10,
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 12,
        borderWidth: 1,
        borderColor: '#0f172a',
    },
    offlineButtonText: {
        color: '#000',
        fontSize: 15,
        fontWeight: '600',
        letterSpacing: 0.4,
    },

    // Botão Configuração
    configButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 12,
        gap: 6,
    },
    configButtonText: {
        fontSize: 13,
        color: '#6b7280',
        fontWeight: '500',
    },
    connectedDot: {
        width: 8,
        height: 8,
        borderRadius: 4,
        backgroundColor: '#10b981',
        marginLeft: 6,
    },

    // Card de Configuração
    configCard: {
        backgroundColor: '#ffffff',
        borderRadius: 16,
        padding: 24,
        marginBottom: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 8,
        elevation: 3,
        borderWidth: 1,
        borderColor: '#f1f5f9',
    },
    configHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 20,
        gap: 10,
    },
    configTitle: {
        fontSize: 16,
        fontWeight: '700',
        color: '#374151',
    },

    // Botão Testar
    testButton: {
        backgroundColor: '#0891b2',
        height: 48,
        borderRadius: 10,
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: 8,
        marginBottom: 12,
    },
    testButtonText: {
        color: '#000',
        fontSize: 15,
        fontWeight: '600',
    },

    // Botão Limpar
    clearButton: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        paddingVertical: 12,
        borderRadius: 8,
        backgroundColor: '#fef2f2',
        borderWidth: 1,
        borderColor: '#fecaca',
    },
    clearButtonText: {
        color: '#ef4444',
        fontSize: 14,
        fontWeight: '600',
    },

    // Estados
    buttonDisabled: {
        opacity: 0.5,
    },

    // Footer
    footer: {
        textAlign: 'center',
        color: '#9ca3af',
        fontSize: 12,
        fontWeight: '400',
        marginTop: 24,
        letterSpacing: 0.5,
    },
});
