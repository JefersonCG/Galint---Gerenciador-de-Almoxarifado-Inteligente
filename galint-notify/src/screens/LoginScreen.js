import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import Constants from 'expo-constants';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { palette } from '../theme';

export default function LoginScreen({ onLogin }) {
  const [serverUrl, setServerUrl] = useState('');
  const [matricula, setMatricula] = useState('');
  const [senha, setSenha] = useState('');
  const [loading, setLoading] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [testing, setTesting] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('idle');
  const [connectionMessage, setConnectionMessage] = useState('');

  useEffect(() => {
    api.getServerConfig().then((config) => {
      setServerUrl(config.baseUrl || '');
    }).catch(() => {});
  }, []);

  async function handleLogin() {
    try {
      if (!matricula.trim() || !senha.trim()) {
        throw new Error('Informe matrícula e senha para entrar.');
      }
      if (!serverUrl.trim()) {
        throw new Error('Informe a URL base do servidor.');
      }

      setLoading(true);
      await api.saveServerConfig({ baseUrl: serverUrl });
      await onLogin({ matricula, senha });
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao fazer login');
    } finally {
      setLoading(false);
    }
  }

  async function handleTestConnection() {
    try {
      setTesting(true);
      setConnectionStatus('idle');
      setConnectionMessage('');
      const result = await api.testConnection(serverUrl);
      setConnectionStatus('success');
      setConnectionMessage(`Servidor acessível em ${result.baseUrl}`);
    } catch (error) {
      setConnectionStatus('error');
      setConnectionMessage(error.message || 'Falha ao testar conexão.');
    } finally {
      setTesting(false);
    }
  }

  async function handleClearConfig() {
    try {
      const config = await api.clearServerConfig();
      setServerUrl(config.baseUrl || '');
      setConnectionStatus('idle');
      setConnectionMessage('Configuração restaurada para o padrão.');
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao limpar configuração.');
    }
  }

  const statusColor = connectionStatus === 'success'
    ? palette.accent
    : connectionStatus === 'error'
      ? palette.danger
      : palette.warning;

  return (
    <ScreenShell title="GalintNotify" subtitle="Inbox corporativo com failover do Telegram, push Android e relatórios compartilháveis.">
      <View style={styles.card}>
        <View style={styles.brandBlock}>
          <Image source={require('../../galintnotify.png')} style={styles.logo} resizeMode="contain" />
          <Text style={styles.brandTitle}>Messenger corporativo</Text>
          <Text style={styles.brandSubtitle}>Entre com a sua matrícula e senha do GALINT. O servidor pode ser alterado na configuração expansível abaixo.</Text>
        </View>

        <Text style={styles.label}>Matrícula</Text>
        <TextInput value={matricula} onChangeText={setMatricula} style={styles.input} autoCapitalize="none" placeholder="Ex.: 9840737226325" placeholderTextColor={palette.muted} />
        <Text style={styles.label}>Senha</Text>
        <View style={styles.passwordRow}>
          <TextInput value={senha} onChangeText={setSenha} style={[styles.input, styles.passwordInput]} secureTextEntry={!showPassword} placeholder="Sua senha" placeholderTextColor={palette.muted} />
          <Pressable style={styles.toggleButton} onPress={() => setShowPassword((value) => !value)}>
            <Text style={styles.toggleButtonText}>{showPassword ? 'Ocultar' : 'Mostrar'}</Text>
          </Pressable>
        </View>
        <Pressable style={styles.button} onPress={handleLogin} disabled={loading}>
          {loading ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.buttonText}>Entrar no Messenger</Text>}
        </Pressable>

        <Pressable style={styles.configButton} onPress={() => setShowConfig((value) => !value)}>
          <Text style={styles.configButtonText}>{showConfig ? 'Ocultar configuração' : 'Configuração do servidor'}</Text>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
        </Pressable>

        {showConfig ? (
          <View style={styles.configCard}>
            <Text style={styles.configTitle}>Conectar com servidor</Text>
            <Text style={styles.configHelp}>Use uma URL base completa. Isso permite LAN hoje e domínio/HTTPS no futuro sem trocar o app.</Text>
            <Text style={styles.label}>URL base do servidor</Text>
            <TextInput value={serverUrl} onChangeText={setServerUrl} style={styles.input} autoCapitalize="none" placeholder="http://10.0.0.245:5000 ou https://notify.suaempresa.com" placeholderTextColor={palette.muted} />
            <Pressable style={[styles.secondaryButton, testing && styles.secondaryButtonDisabled]} onPress={handleTestConnection} disabled={testing}>
              {testing ? <ActivityIndicator color={palette.text} /> : <Text style={styles.secondaryButtonText}>Testar conexão</Text>}
            </Pressable>
            <Pressable style={styles.clearButton} onPress={handleClearConfig}>
              <Text style={styles.clearButtonText}>Limpar configuração</Text>
            </Pressable>
            {connectionMessage ? (
              <Text style={[styles.connectionMessage, connectionStatus === 'success' ? styles.connectionSuccess : styles.connectionError]}>{connectionMessage}</Text>
            ) : null}
          </View>
        ) : null}
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 20 },
  brandBlock: { alignItems: 'center', marginBottom: 8 },
  logo: { width: 88, height: 88, marginBottom: 12, borderRadius: 20 },
  brandTitle: { color: palette.text, fontSize: 20, fontWeight: '800' },
  brandSubtitle: { color: palette.muted, marginTop: 6, textAlign: 'center', lineHeight: 20 },
  label: { color: palette.text, marginBottom: 8, fontWeight: '700', marginTop: 10 },
  input: { backgroundColor: palette.panelAlt, color: palette.text, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, borderWidth: 1, borderColor: palette.border },
  passwordRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  passwordInput: { flex: 1 },
  toggleButton: { borderRadius: 14, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.panelAlt, paddingHorizontal: 14, paddingVertical: 12, minWidth: 92, alignItems: 'center' },
  toggleButtonText: { color: palette.text, fontWeight: '700' },
  button: { marginTop: 20, borderRadius: 999, backgroundColor: palette.primary, paddingVertical: 14, alignItems: 'center' },
  buttonText: { color: palette.bg, fontWeight: '800', fontSize: 16 },
  configButton: { marginTop: 16, borderRadius: 16, borderWidth: 1, borderColor: palette.border, paddingHorizontal: 16, paddingVertical: 14, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  configButtonText: { color: palette.text, fontWeight: '700' },
  statusDot: { width: 10, height: 10, borderRadius: 999, backgroundColor: palette.accent },
  configCard: { marginTop: 14, borderRadius: 18, backgroundColor: palette.panelAlt, borderWidth: 1, borderColor: palette.border, padding: 16 },
  configTitle: { color: palette.text, fontWeight: '800', fontSize: 16 },
  configHelp: { color: palette.muted, marginTop: 6, lineHeight: 19 },
  secondaryButton: { marginTop: 14, borderRadius: 14, borderWidth: 1, borderColor: palette.primary, paddingVertical: 12, alignItems: 'center' },
  secondaryButtonDisabled: { opacity: 0.7 },
  secondaryButtonText: { color: palette.primary, fontWeight: '800' },
  clearButton: { marginTop: 10, borderRadius: 14, borderWidth: 1, borderColor: palette.danger, paddingVertical: 12, alignItems: 'center' },
  clearButtonText: { color: palette.danger, fontWeight: '800' },
  connectionMessage: { marginTop: 12, fontWeight: '600', lineHeight: 18 },
  connectionSuccess: { color: palette.accent },
  connectionError: { color: palette.danger },
});