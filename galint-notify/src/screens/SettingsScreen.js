import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { bootstrapPush } from '../services/push';
import { palette } from '../theme';

export default function SettingsScreen({ session, onLogout, onServerSaved }) {
  const [serverUrl, setServerUrl] = useState('');
  const [testing, setTesting] = useState(false);
  const [connectionMessage, setConnectionMessage] = useState('');
  const [connectionStatus, setConnectionStatus] = useState('idle');

  useEffect(() => {
    api.getServerConfig().then((config) => {
      setServerUrl(config.baseUrl || '');
    }).catch(() => {});
  }, [session]);

  async function save() {
    try {
      await api.saveServerConfig({ baseUrl: serverUrl });
      await onServerSaved();
      Alert.alert('GalintNotify', 'Configuração do servidor atualizada.');
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao salvar servidor');
    }
  }

  async function testConnection() {
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

  async function clearServer() {
    try {
      const config = await api.clearServerConfig();
      setServerUrl(config.baseUrl || '');
      setConnectionStatus('idle');
      setConnectionMessage('Configuração restaurada para o padrão.');
      await onServerSaved();
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao limpar servidor');
    }
  }

  async function refreshPush() {
    try {
      const result = await bootstrapPush(session);
      Alert.alert(
        'GalintNotify',
        result?.supported
          ? 'Token de push atualizado.'
          : result?.skippedReason || 'Push não disponível neste ambiente.'
      );
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao atualizar push');
    }
  }

  return (
    <ScreenShell title="Configurações" subtitle="Servidor, sessão e push do aparelho em uma tela curta e objetiva.">
      <View style={styles.card}>
        <Text style={styles.label}>URL base do servidor</Text>
        <TextInput value={serverUrl} onChangeText={setServerUrl} style={styles.input} autoCapitalize="none" placeholder="http://10.0.0.245:5000 ou https://notify.suaempresa.com" placeholderTextColor={palette.muted} />
        <Text style={styles.meta}>Usuário atual: {session?.user?.nome || '-'} ({session?.user?.matricula || '-'})</Text>
        <View style={styles.hintCard}>
          <Text style={styles.hintTitle}>Diagnóstico de rede</Text>
          <Text style={styles.hintText}>Se a URL usar 10.x, 192.168.x ou .local, o aparelho precisa estar na mesma rede do servidor. Se o IP da máquina mudar, o Notify passa a dar falha de rede até a URL ser atualizada.</Text>
        </View>
        <View style={styles.actions}>
          <Pressable style={styles.button} onPress={save}><Text style={styles.buttonText}>Salvar servidor</Text></Pressable>
          <Pressable style={[styles.button, styles.buttonAlt]} onPress={refreshPush}><Text style={styles.buttonText}>Atualizar push</Text></Pressable>
        </View>
        <View style={styles.actions}>
          <Pressable style={styles.outlineButton} onPress={testConnection} disabled={testing}>
            {testing ? <ActivityIndicator color={palette.text} /> : <Text style={styles.outlineButtonText}>Testar conexão</Text>}
          </Pressable>
          <Pressable style={styles.clearButton} onPress={clearServer}><Text style={styles.clearButtonText}>Limpar servidor</Text></Pressable>
        </View>
        {connectionMessage ? (
          <Text style={[styles.connectionMessage, connectionStatus === 'success' ? styles.connectionSuccess : styles.connectionError]}>{connectionMessage}</Text>
        ) : null}
        <Pressable style={[styles.button, styles.logout]} onPress={onLogout}><Text style={styles.buttonText}>Sair</Text></Pressable>
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 18 },
  label: { color: palette.text, fontWeight: '700', marginBottom: 8 },
  input: { backgroundColor: palette.panelAlt, color: palette.text, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, borderWidth: 1, borderColor: palette.border },
  meta: { color: palette.muted, marginTop: 14 },
  hintCard: { marginTop: 14, borderRadius: 18, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.panelAlt, padding: 14 },
  hintTitle: { color: palette.text, fontWeight: '800' },
  hintText: { color: palette.muted, marginTop: 6, lineHeight: 19 },
  actions: { flexDirection: 'row', gap: 12, marginTop: 18 },
  button: { flex: 1, backgroundColor: palette.primary, borderRadius: 999, paddingVertical: 12, alignItems: 'center' },
  buttonAlt: { backgroundColor: palette.accent },
  outlineButton: { flex: 1, borderRadius: 999, paddingVertical: 12, alignItems: 'center', borderWidth: 1, borderColor: palette.primary, backgroundColor: palette.panelAlt },
  outlineButtonText: { color: palette.primary, fontWeight: '800' },
  clearButton: { flex: 1, borderRadius: 999, paddingVertical: 12, alignItems: 'center', borderWidth: 1, borderColor: palette.danger, backgroundColor: palette.panelAlt },
  clearButtonText: { color: palette.danger, fontWeight: '800' },
  connectionMessage: { marginTop: 12, fontWeight: '600', lineHeight: 18 },
  connectionSuccess: { color: palette.accent },
  connectionError: { color: palette.danger },
  logout: { marginTop: 12, backgroundColor: palette.danger },
  buttonText: { color: palette.bg, fontWeight: '800' },
});