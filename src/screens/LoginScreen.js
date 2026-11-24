// Entrada do app (2.2.0). Pedido do usuário em 21/11/2026: tela curta, servidor só num ícone de
// engrenagem, sem "Entrar offline" (o modo offline nunca funcionou: ver services/api.js) e com
// entrada pela digital ou pelo rosto (services/biometricLogin.js).
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    KeyboardAvoidingView,
    Modal,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import TextInput from '../components/UpperTextInput';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Application from 'expo-application';

import ApiService from '../services/api';
import {
    biometricAvailability,
    clearBiometricLogin,
    forgetPlainPassword,
    saveBiometricLogin,
    savedBiometricUser,
    unlockWithBiometrics,
} from '../services/biometricLogin';
import { clearServerConfig, loadLastUsername, loadServerConfig, saveLastUsername, saveServerConfig } from '../utils/storage';
import { heroPalette, heroShadow } from '../theme/heroTheme';

const DEFAULT_IP = '10.0.0.245';
const DEFAULT_PORT = '5000';
const MARK_BARS = [3, 1, 2, 1, 3, 2, 1, 1, 3, 1, 2];

function serverKeyOf(ip, port) {
    return `${String(ip || '').trim()}:${String(port || '').trim()}`;
}

export default function LoginScreen({ navigation, route }) {
    const [serverIP, setServerIP] = useState(DEFAULT_IP);
    const [serverPort, setServerPort] = useState(DEFAULT_PORT);
    const [hasServer, setHasServer] = useState(false);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [configOpen, setConfigOpen] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null); // { ok, message }
    const [bio, setBio] = useState({ available: false, label: 'digital', icon: '👆' });
    const [bioUser, setBioUser] = useState(null);
    const passwordRef = useRef(null);
    const autoPrompted = useRef(false);

    const refreshBiometric = useCallback(async (ip, port) => {
        const availability = await biometricAvailability();
        setBio(availability);
        const saved = availability.available ? await savedBiometricUser(serverKeyOf(ip, port)) : null;
        setBioUser(saved);
        return { availability, saved };
    }, []);

    const finishLogin = useCallback(async (user, typedUser, typedPassword, ip, port, viaBiometric) => {
        await saveServerConfig(ip, port);
        await saveLastUsername(typedUser);
        await forgetPlainPassword();
        try {
            const lastPushToken = await AsyncStorage.getItem('last_expo_push_token');
            if (lastPushToken) await ApiService.registerNotifyPushToken(lastPushToken);
        } catch (error) {
            // o aviso no celular é opcional
        }

        const go = () => navigation.reset({ index: 0, routes: [{ name: 'Estoque', params: { user } }] });
        if (viaBiometric) {
            go();
            return;
        }
        const availability = await biometricAvailability();
        const key = serverKeyOf(ip, port);
        const saved = availability.available ? await savedBiometricUser(key) : null;
        if (!availability.available || saved === typedUser) {
            if (saved === typedUser) await saveBiometricLogin(key, typedUser, typedPassword); // senha nova
            go();
            return;
        }
        Alert.alert(
            `Entrar com ${availability.label}?`,
            `Da próxima vez, entre só com a ${availability.label}, sem digitar a senha. A senha fica guardada no cofre do celular.`,
            [
                { text: 'Agora não', style: 'cancel', onPress: go },
                {
                    text: `Usar ${availability.label}`,
                    onPress: async () => {
                        await saveBiometricLogin(key, typedUser, typedPassword);
                        go();
                    },
                },
            ],
            { cancelable: false }
        );
    }, [navigation]);

    // ip/port vêm de quem chama: na entrada automática pela digital o estado ainda não tem o
    // servidor salvo (o primeiro desenho usa o padrão).
    const doLogin = useCallback(async (typedUser, typedPassword, { viaBiometric = false, ip, port } = {}) => {
        const user = String(typedUser || '').trim();
        if (!user || !typedPassword) {
            Alert.alert('Entrar', 'Preencha usuário e senha.');
            return;
        }
        setLoading(true);
        try {
            await ApiService.initialize(ip, port);
            const result = await ApiService.login(user, typedPassword);
            if (!result.success) {
                if (viaBiometric && /senha|credencia|inválid/i.test(result.message || '')) {
                    // A senha mudou no site: a guardada não vale mais.
                    await clearBiometricLogin();
                    setBioUser(null);
                    Alert.alert('Entrar', 'A senha guardada não vale mais. Entre com a senha nova.');
                } else {
                    Alert.alert('Entrar', result.message || 'Não foi possível entrar.');
                }
                return;
            }
            await finishLogin(result.user, user, typedPassword, ip, port, viaBiometric);
        } catch (error) {
            Alert.alert('Entrar', 'Não foi possível falar com o servidor. Confira a engrenagem ⚙.');
        } finally {
            setLoading(false);
        }
    }, [finishLogin]);

    const loginWithBiometric = useCallback(async (ip = serverIP, port = serverPort, label = bio.label) => {
        const unlocked = await unlockWithBiometrics(serverKeyOf(ip, port), label);
        if (!unlocked.success) {
            if (unlocked.message) Alert.alert('Entrar', unlocked.message);
            return;
        }
        setUsername(unlocked.usuario);
        await doLogin(unlocked.usuario, unlocked.senha, { viaBiometric: true, ip, port });
    }, [bio.label, doLogin, serverIP, serverPort]);

    useEffect(() => {
        (async () => {
            const config = await loadServerConfig();
            const ip = config?.serverIP || DEFAULT_IP;
            const port = String(config?.serverPort || DEFAULT_PORT);
            setServerIP(ip);
            setServerPort(port);
            setHasServer(Boolean(config));
            setUsername(await loadLastUsername());
            if (!config) {
                setConfigOpen(true);
                return;
            }
            const { availability, saved } = await refreshBiometric(ip, port);
            // Na abertura do app a digital já é pedida; depois de "Sair", não.
            if (saved && !route?.params?.fromLogout && !autoPrompted.current) {
                autoPrompted.current = true;
                loginWithBiometric(ip, port, availability.label);
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleTest = useCallback(async () => {
        if (!serverIP || !serverPort) {
            setTestResult({ ok: false, message: 'Preencha o IP e a porta.' });
            return;
        }
        setTesting(true);
        setTestResult(null);
        try {
            await ApiService.initialize(serverIP, serverPort);
            const result = await ApiService.testConnection();
            setTestResult({ ok: result.success, message: result.success ? 'Servidor respondeu.' : result.message });
        } catch (error) {
            setTestResult({ ok: false, message: `Sem resposta de http://${serverIP}:${serverPort}` });
        } finally {
            setTesting(false);
        }
    }, [serverIP, serverPort]);

    const handleSaveServer = useCallback(async () => {
        await saveServerConfig(serverIP, serverPort);
        await ApiService.initialize(serverIP, serverPort);
        setHasServer(true);
        setConfigOpen(false);
        await refreshBiometric(serverIP, serverPort);
    }, [refreshBiometric, serverIP, serverPort]);

    const handleClearServer = useCallback(() => {
        Alert.alert('Limpar servidor', 'Apagar o endereço do servidor e o acesso por biometria deste celular?', [
            { text: 'Cancelar', style: 'cancel' },
            {
                text: 'Limpar',
                style: 'destructive',
                onPress: async () => {
                    await clearServerConfig();
                    await clearBiometricLogin();
                    setServerIP(DEFAULT_IP);
                    setServerPort(DEFAULT_PORT);
                    setHasServer(false);
                    setBioUser(null);
                    setTestResult(null);
                },
            },
        ]);
    }, []);

    const version = Application.nativeApplicationVersion || '';

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <TouchableOpacity style={styles.gear} onPress={() => setConfigOpen(true)} accessibilityLabel="Configurar servidor" hitSlop={12}>
                <Text style={styles.gearIcon}>⚙</Text>
                {hasServer ? null : <View style={styles.gearDot} />}
            </TouchableOpacity>

            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
                <View style={styles.brandBox}>
                    <View style={styles.mark}>
                        {MARK_BARS.map((width, index) => (
                            <View key={index} style={[styles.markBar, { width: width * 2, backgroundColor: index === 4 ? heroPalette.primaryStrong : heroPalette.text }]} />
                        ))}
                    </View>
                    <Text style={styles.brand}>GALINT</Text>
                    <Text style={styles.subtitle}>Sublime Max Condominium</Text>
                </View>

                <View style={styles.card}>
                    {bio.available && bioUser ? (
                        <TouchableOpacity style={styles.bioButton} onPress={() => loginWithBiometric()} disabled={loading} activeOpacity={0.85}>
                            <Text style={styles.bioIcon}>{bio.icon}</Text>
                            <View style={{ flex: 1 }}>
                                <Text style={styles.bioTitle}>Entrar com {bio.label}</Text>
                                <Text style={styles.bioUser} numberOfLines={1}>{bioUser}</Text>
                            </View>
                        </TouchableOpacity>
                    ) : null}

                    <TextInput
                        style={styles.input}
                        value={username}
                        onChangeText={setUsername}
                        placeholder="Usuário ou matrícula"
                        placeholderTextColor={heroPalette.textMuted}
                        keepCase
                        autoCapitalize="none"
                        autoCorrect={false}
                        returnKeyType="next"
                        onSubmitEditing={() => passwordRef.current?.focus()}
                    />
                    <View style={styles.passwordRow}>
                        <TextInput
                            ref={passwordRef}
                            style={[styles.input, styles.passwordInput]}
                            value={password}
                            onChangeText={setPassword}
                            placeholder="Senha"
                            placeholderTextColor={heroPalette.textMuted}
                            secureTextEntry={!showPassword}
                            keepCase
                            autoCapitalize="none"
                            returnKeyType="go"
                            onSubmitEditing={() => doLogin(username, password, { ip: serverIP, port: serverPort })}
                        />
                        <TouchableOpacity style={styles.eye} onPress={() => setShowPassword((value) => !value)} accessibilityLabel={showPassword ? 'Esconder senha' : 'Mostrar senha'}>
                            <Text style={styles.eyeIcon}>{showPassword ? '🙈' : '👁'}</Text>
                        </TouchableOpacity>
                    </View>
                    <TouchableOpacity style={[styles.loginButton, loading && styles.disabled]} onPress={() => doLogin(username, password, { ip: serverIP, port: serverPort })} disabled={loading} activeOpacity={0.85}>
                        {loading ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.loginText}>Entrar</Text>}
                    </TouchableOpacity>
                    {bio.available && !bioUser ? (
                        <Text style={styles.bioHint}>Depois de entrar com a senha, você pode ligar a entrada pela {bio.label}.</Text>
                    ) : null}
                </View>

                <Text style={styles.footer}>GALINT{version ? ` ${version}` : ''} · {hasServer ? `${serverIP}:${serverPort}` : 'servidor não configurado'}</Text>
            </ScrollView>

            <Modal visible={configOpen} transparent animationType="fade" onRequestClose={() => setConfigOpen(false)}>
                <View style={styles.modalBackdrop}>
                    <View style={styles.modalCard}>
                        <Text style={styles.modalTitle}>Servidor do GALINT</Text>
                        <Text style={styles.modalLabel}>IP</Text>
                        <TextInput style={styles.input} value={serverIP} onChangeText={setServerIP} placeholder="ex.: 10.0.0.245" placeholderTextColor={heroPalette.textMuted} keyboardType="numeric" autoCapitalize="none" />
                        <Text style={styles.modalLabel}>Porta</Text>
                        <TextInput style={styles.input} value={serverPort} onChangeText={setServerPort} placeholder="ex.: 5000" placeholderTextColor={heroPalette.textMuted} keyboardType="numeric" />
                        {testResult ? (
                            <Text style={[styles.testResult, { color: testResult.ok ? heroPalette.success : heroPalette.danger }]}>
                                {testResult.ok ? '✔ ' : '⚠ '}{testResult.message}
                            </Text>
                        ) : null}
                        <View style={styles.modalRow}>
                            <TouchableOpacity style={[styles.modalButton, styles.modalButtonGhost]} onPress={handleTest} disabled={testing}>
                                {testing ? <ActivityIndicator color={heroPalette.text} /> : <Text style={styles.modalButtonGhostText}>Testar</Text>}
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.modalButton} onPress={handleSaveServer} disabled={testing}>
                                <Text style={styles.modalButtonText}>Salvar</Text>
                            </TouchableOpacity>
                        </View>
                        <View style={styles.modalRow}>
                            {hasServer ? (
                                <TouchableOpacity onPress={handleClearServer}>
                                    <Text style={styles.clearText}>Limpar servidor</Text>
                                </TouchableOpacity>
                            ) : <View />}
                            {hasServer ? (
                                <TouchableOpacity onPress={() => setConfigOpen(false)}>
                                    <Text style={styles.closeText}>Fechar</Text>
                                </TouchableOpacity>
                            ) : null}
                        </View>
                    </View>
                </View>
            </Modal>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    gear: { position: 'absolute', top: 44, right: 18, zIndex: 5, width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border },
    gearIcon: { color: heroPalette.text, fontSize: 22 },
    gearDot: { position: 'absolute', top: 8, right: 8, width: 9, height: 9, borderRadius: 5, backgroundColor: heroPalette.warning },
    scroll: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: 24, paddingVertical: 40 },
    brandBox: { alignItems: 'center', marginBottom: 28 },
    mark: { flexDirection: 'row', alignItems: 'flex-end', height: 34, marginBottom: 12 },
    markBar: { height: 34, marginHorizontal: 1.5, borderRadius: 1 },
    brand: { color: heroPalette.text, fontSize: 30, fontWeight: '900', letterSpacing: 8, marginLeft: 8 },
    subtitle: { color: heroPalette.textMuted, fontSize: 13, marginTop: 4, letterSpacing: 0.4 },
    card: { backgroundColor: heroPalette.panel, borderRadius: 22, padding: 18, borderWidth: 1, borderColor: heroPalette.border, ...heroShadow },
    bioButton: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, borderRadius: 16, backgroundColor: heroPalette.panelAlt, borderWidth: 1, borderColor: heroPalette.borderStrong, marginBottom: 14 },
    bioIcon: { fontSize: 30 },
    bioTitle: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    bioUser: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    input: { backgroundColor: heroPalette.bgAlt, color: heroPalette.text, borderRadius: 14, borderWidth: 1, borderColor: heroPalette.border, paddingHorizontal: 16, height: 52, fontSize: 16, marginBottom: 12 },
    passwordRow: { position: 'relative' },
    passwordInput: { paddingRight: 52 },
    eye: { position: 'absolute', right: 6, top: 4, height: 44, width: 44, alignItems: 'center', justifyContent: 'center' },
    eyeIcon: { fontSize: 18 },
    loginButton: { height: 54, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
    loginText: { color: heroPalette.bg, fontSize: 17, fontWeight: '900', letterSpacing: 0.4 },
    disabled: { opacity: 0.55 },
    bioHint: { color: heroPalette.textMuted, fontSize: 12, textAlign: 'center', marginTop: 12 },
    footer: { color: heroPalette.textMuted, fontSize: 12, textAlign: 'center', marginTop: 22 },
    modalBackdrop: { flex: 1, backgroundColor: 'rgba(2, 6, 23, 0.72)', justifyContent: 'center', padding: 22 },
    modalCard: { backgroundColor: heroPalette.panel, borderRadius: 22, padding: 18, borderWidth: 1, borderColor: heroPalette.border },
    modalTitle: { color: heroPalette.text, fontSize: 18, fontWeight: '900', marginBottom: 12 },
    modalLabel: { color: heroPalette.textSoft, fontSize: 13, fontWeight: '700', marginBottom: 6 },
    testResult: { fontSize: 13, fontWeight: '700', marginBottom: 10 },
    modalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 6 },
    modalButton: { flex: 1, height: 48, borderRadius: 14, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    modalButtonText: { color: heroPalette.bg, fontSize: 15, fontWeight: '900' },
    modalButtonGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: heroPalette.border },
    modalButtonGhostText: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    clearText: { color: heroPalette.danger, fontSize: 14, fontWeight: '700', paddingVertical: 10 },
    closeText: { color: heroPalette.textSoft, fontSize: 14, fontWeight: '700', paddingVertical: 10 },
});
