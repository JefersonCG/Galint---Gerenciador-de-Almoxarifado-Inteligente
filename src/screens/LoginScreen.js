import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Image,
    Alert,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
    ActivityIndicator,
    Switch
} from 'react-native';
import ApiService from '../services/api';
import { loadServerConfig, saveServerConfig, loadCredentials, saveCredentials } from '../utils/storage';

export default function LoginScreen({ navigation }) {
    const [serverIP, setServerIP] = useState('10.0.0.245');
    const [serverPort, setServerPort] = useState('5443');
    const [useHttps, setUseHttps] = useState(true);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
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
            setUseHttps(config.useHttps);
            setShowConfig(false);
        }

        const creds = await loadCredentials();
        if (creds) {
            setUsername(creds.username);
            setPassword(creds.password);
            setRememberMe(true);
        }
    };

    const handleTestConnection = async () => {
        if (!serverIP || !serverPort) {
            Alert.alert('Erro', 'Preencha IP e Porta do servidor');
            return;
        }

        setTesting(true);
        setConnectionStatus(null);

        try {
            await ApiService.initialize(serverIP, serverPort, useHttps);
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
            Alert.alert('Erro', 'Não foi possível conectar ao servidor');
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
            // Inicializar API se ainda não foi
            if (!ApiService.baseURL) {
                await ApiService.initialize(serverIP, serverPort, useHttps);
            }

            const result = await ApiService.login(username, password);

            if (result.success) {
                await saveCredentials(username, password, rememberMe);
                await saveServerConfig(serverIP, serverPort, useHttps);
                navigation.replace('Estoque', { user: result.user });
            } else {
                Alert.alert('Erro', result.message);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao fazer login');
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
            >
                {/* Logo e Título */}
                <View style={styles.header}>
                    <View style={styles.logoContainer}>
                        <Text style={styles.logoText}>GALINT</Text>
                    </View>
                    <Text style={styles.subtitle}>Gestão de Almoxarifado</Text>
                    <Text style={styles.subtitleSmall}>Mobile App</Text>
                </View>

                {/* Configuração do Servidor */}
                <View style={styles.card}>
                    <TouchableOpacity
                        style={styles.configHeader}
                        onPress={() => setShowConfig(!showConfig)}
                    >
                        <Text style={styles.cardTitle}>
                            {showConfig ? '▼' : '▶'} Configuração do Servidor
                        </Text>
                        {connectionStatus === 'success' && !showConfig && (
                            <View style={styles.statusBadge}>
                                <Text style={styles.statusText}>✓ Conectado</Text>
                            </View>
                        )}
                    </TouchableOpacity>

                    {showConfig && (
                        <>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>IP do Servidor</Text>
                                <TextInput
                                    style={styles.input}
                                    value={serverIP}
                                    onChangeText={setServerIP}
                                    placeholder="ex: 10.0.0.245"
                                    keyboardType="numeric"
                                    autoCapitalize="none"
                                />
                            </View>

                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>Porta</Text>
                                <TextInput
                                    style={styles.input}
                                    value={serverPort}
                                    onChangeText={setServerPort}
                                    placeholder="ex: 5443"
                                    keyboardType="numeric"
                                />
                            </View>

                            <View style={styles.switchContainer}>
                                <Text style={styles.label}>Usar HTTPS</Text>
                                <Switch
                                    value={useHttps}
                                    onValueChange={setUseHttps}
                                    trackColor={{ false: '#ccc', true: '#0d6efd' }}
                                    thumbColor={useHttps ? '#fff' : '#f4f3f4'}
                                />
                            </View>

                            <TouchableOpacity
                                style={[styles.testButton, testing && styles.buttonDisabled]}
                                onPress={handleTestConnection}
                                disabled={testing}
                            >
                                {testing ? (
                                    <ActivityIndicator color="#fff" />
                                ) : (
                                    <Text style={styles.buttonText}>
                                        {connectionStatus === 'success' ? '✓ Testar Novamente' : 'Testar Conexão'}
                                    </Text>
                                )}
                            </TouchableOpacity>
                        </>
                    )}
                </View>

                {/* Login */}
                <View style={styles.card}>
                    <Text style={styles.cardTitle}>Login</Text>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Usuário</Text>
                        <TextInput
                            style={styles.input}
                            value={username}
                            onChangeText={setUsername}
                            placeholder="Digite seu usuário"
                            autoCapitalize="none"
                            autoCorrect={false}
                        />
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Senha</Text>
                        <TextInput
                            style={styles.input}
                            value={password}
                            onChangeText={setPassword}
                            placeholder="Digite sua senha"
                            secureTextEntry
                            autoCapitalize="none"
                        />
                    </View>

                    <View style={styles.switchContainer}>
                        <Text style={styles.label}>Lembrar credenciais</Text>
                        <Switch
                            value={rememberMe}
                            onValueChange={setRememberMe}
                            trackColor={{ false: '#ccc', true: '#0d6efd' }}
                            thumbColor={rememberMe ? '#fff' : '#f4f3f4'}
                        />
                    </View>

                    <TouchableOpacity
                        style={[styles.loginButton, loading && styles.buttonDisabled]}
                        onPress={handleLogin}
                        disabled={loading}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>Entrar</Text>
                        )}
                    </TouchableOpacity>
                </View>

                <Text style={styles.footer}>
                    © 2025 GALINT - v1.0.0
                </Text>
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    scrollContent: {
        flexGrow: 1,
        padding: 20,
        justifyContent: 'center',
    },
    header: {
        alignItems: 'center',
        marginBottom: 30,
    },
    logoContainer: {
        width: 100,
        height: 100,
        borderRadius: 50,
        backgroundColor: '#0d6efd',
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: 15,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.25,
        shadowRadius: 3.84,
        elevation: 5,
    },
    logoText: {
        fontSize: 28,
        fontWeight: 'bold',
        color: '#fff',
    },
    subtitle: {
        fontSize: 18,
        fontWeight: '600',
        color: '#333',
        marginBottom: 5,
    },
    subtitleSmall: {
        fontSize: 14,
        color: '#666',
    },
    card: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 20,
        marginBottom: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
        elevation: 2,
    },
    configHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 10,
    },
    cardTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: '#333',
        marginBottom: 15,
    },
    statusBadge: {
        backgroundColor: '#198754',
        paddingHorizontal: 10,
        paddingVertical: 5,
        borderRadius: 12,
    },
    statusText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '600',
    },
    inputGroup: {
        marginBottom: 15,
    },
    label: {
        fontSize: 14,
        fontWeight: '500',
        color: '#555',
        marginBottom: 5,
    },
    input: {
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
        backgroundColor: '#f9f9f9',
    },
    switchContainer: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 15,
    },
    testButton: {
        backgroundColor: '#6c757d',
        padding: 15,
        borderRadius: 8,
        alignItems: 'center',
        marginTop: 10,
    },
    loginButton: {
        backgroundColor: '#0d6efd',
        padding: 15,
        borderRadius: 8,
        alignItems: 'center',
        marginTop: 10,
    },
    buttonDisabled: {
        opacity: 0.6,
    },
    buttonText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '600',
    },
    footer: {
        textAlign: 'center',
        color: '#999',
        fontSize: 12,
        marginTop: 20,
    },
});
