import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import Constants from 'expo-constants';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { palette } from '../theme';

export default function LoginScreen({ onLogin }) {
  const [baseUrl, setBaseUrl] = useState(Constants.expoConfig?.extra?.defaultServerUrl || '');
  const [matricula, setMatricula] = useState('');
  const [senha, setSenha] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.restoreSession().then((session) => {
      if (session?.baseUrl) {
        setBaseUrl(session.baseUrl);
      }
    }).catch(() => {});
  }, []);

  async function handleLogin() {
    try {
      setLoading(true);
      await api.saveBaseUrl(baseUrl);
      await onLogin({ matricula, senha });
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao fazer login');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScreenShell title="GalintNotify" subtitle="Inbox corporativo com failover do Telegram, push Android e relatórios compartilháveis.">
      <View style={styles.card}>
        <Text style={styles.label}>Servidor GALINT</Text>
        <TextInput value={baseUrl} onChangeText={setBaseUrl} style={styles.input} autoCapitalize="none" placeholder="http://192.168.1.41:5000" placeholderTextColor={palette.muted} />
        <Text style={styles.label}>Matrícula</Text>
        <TextInput value={matricula} onChangeText={setMatricula} style={styles.input} autoCapitalize="none" placeholder="Ex.: 9840737226325" placeholderTextColor={palette.muted} />
        <Text style={styles.label}>Senha</Text>
        <TextInput value={senha} onChangeText={setSenha} style={styles.input} secureTextEntry placeholder="Sua senha" placeholderTextColor={palette.muted} />
        <Pressable style={styles.button} onPress={handleLogin} disabled={loading}>
          {loading ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.buttonText}>Entrar no Messenger</Text>}
        </Pressable>
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 20 },
  label: { color: palette.text, marginBottom: 8, fontWeight: '700', marginTop: 10 },
  input: { backgroundColor: palette.panelAlt, color: palette.text, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, borderWidth: 1, borderColor: palette.border },
  button: { marginTop: 20, borderRadius: 999, backgroundColor: palette.primary, paddingVertical: 14, alignItems: 'center' },
  buttonText: { color: palette.bg, fontWeight: '800', fontSize: 16 },
});