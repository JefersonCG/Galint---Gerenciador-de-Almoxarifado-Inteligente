import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { bootstrapPush } from '../services/push';
import { palette } from '../theme';

export default function SettingsScreen({ session, onLogout, onServerSaved }) {
  const [baseUrl, setBaseUrl] = useState(session?.baseUrl || '');

  useEffect(() => {
    setBaseUrl(session?.baseUrl || '');
  }, [session]);

  async function save() {
    try {
      await api.saveBaseUrl(baseUrl);
      await onServerSaved();
      Alert.alert('GalintNotify', 'URL do servidor atualizada.');
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao salvar servidor');
    }
  }

  async function refreshPush() {
    try {
      await bootstrapPush(session);
      Alert.alert('GalintNotify', 'Token de push atualizado.');
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao atualizar push');
    }
  }

  return (
    <ScreenShell title="Configurações" subtitle="Gerencie URL do GALINT, sessão e registro de push do aparelho.">
      <View style={styles.card}>
        <Text style={styles.label}>Servidor</Text>
        <TextInput value={baseUrl} onChangeText={setBaseUrl} style={styles.input} autoCapitalize="none" />
        <Text style={styles.meta}>Usuário atual: {session?.user?.nome || '-'} ({session?.user?.matricula || '-'})</Text>
        <View style={styles.actions}>
          <Pressable style={styles.button} onPress={save}><Text style={styles.buttonText}>Salvar servidor</Text></Pressable>
          <Pressable style={[styles.button, styles.buttonAlt]} onPress={refreshPush}><Text style={styles.buttonText}>Atualizar push</Text></Pressable>
        </View>
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
  actions: { flexDirection: 'row', gap: 12, marginTop: 18 },
  button: { flex: 1, backgroundColor: palette.primary, borderRadius: 999, paddingVertical: 12, alignItems: 'center' },
  buttonAlt: { backgroundColor: palette.accent },
  logout: { marginTop: 12, backgroundColor: palette.danger },
  buttonText: { color: palette.bg, fontWeight: '800' },
});