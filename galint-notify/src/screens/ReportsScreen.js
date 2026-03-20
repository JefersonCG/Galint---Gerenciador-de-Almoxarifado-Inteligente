import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { palette } from '../theme';

export default function ReportsScreen() {
  const [reports, setReports] = useState([]);
  const [month, setMonth] = useState(String(new Date().getMonth() + 1));
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [scope, setScope] = useState('all');

  useEffect(() => {
    api.fetchReports().then((data) => setReports(data.reports || [])).catch((error) => {
      Alert.alert('GalintNotify', error.message || 'Falha ao carregar relatórios');
    });
  }, []);

  const params = useMemo(() => ({ scope, month, year }), [scope, month, year]);

  async function downloadAndShare(reportId, format) {
    try {
      const config = await api.buildDownloadConfig(reportId, format, reportId === 'monthly' ? params : { scope });
      const target = `${FileSystem.cacheDirectory}${reportId}.${format}`;
      const download = await FileSystem.downloadAsync(config.url, target, {
        headers: { Authorization: `Bearer ${config.token}` },
      });
      await Sharing.shareAsync(download.uri);
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao baixar relatório');
    }
  }

  return (
    <ScreenShell title="Relatórios" subtitle="Baixe e compartilhe PDF ou XLSX direto do feed de notificações.">
      <View style={styles.card}>
        <Text style={styles.label}>Escopo</Text>
        <View style={styles.chips}>
          {['all', 'materials', 'tools'].map((entry) => (
            <Pressable key={entry} style={[styles.chip, scope === entry && styles.chipActive]} onPress={() => setScope(entry)}>
              <Text style={[styles.chipText, scope === entry && styles.chipTextActive]}>{entry}</Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Mês</Text>
            <TextInput style={styles.input} value={month} onChangeText={setMonth} keyboardType="numeric" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Ano</Text>
            <TextInput style={styles.input} value={year} onChangeText={setYear} keyboardType="numeric" />
          </View>
        </View>
      </View>

      {reports.map((report) => (
        <View key={report.id} style={styles.card}>
          <Text style={styles.title}>{report.label}</Text>
          <Text style={styles.description}>Formatos disponíveis: {(report.formats || []).join(', ').toUpperCase()}</Text>
          <View style={styles.row}>
            <Pressable style={styles.button} onPress={() => downloadAndShare(report.id, 'pdf')}>
              <Text style={styles.buttonText}>Baixar PDF</Text>
            </Pressable>
            <Pressable style={[styles.button, styles.buttonAlt]} onPress={() => downloadAndShare(report.id, 'xlsx')}>
              <Text style={styles.buttonText}>Baixar XLSX</Text>
            </Pressable>
          </View>
        </View>
      ))}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 18, marginBottom: 16 },
  label: { color: palette.text, fontWeight: '700', marginBottom: 8 },
  row: { flexDirection: 'row', gap: 12 },
  input: { backgroundColor: palette.panelAlt, color: palette.text, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, borderWidth: 1, borderColor: palette.border },
  chips: { flexDirection: 'row', gap: 8, marginBottom: 14, flexWrap: 'wrap' },
  chip: { borderRadius: 999, borderWidth: 1, borderColor: palette.border, paddingHorizontal: 12, paddingVertical: 8 },
  chipActive: { backgroundColor: palette.primary, borderColor: palette.primary },
  chipText: { color: palette.muted, fontWeight: '700' },
  chipTextActive: { color: palette.bg },
  title: { color: palette.text, fontSize: 18, fontWeight: '800' },
  description: { color: palette.muted, marginTop: 6, marginBottom: 14 },
  button: { flex: 1, backgroundColor: palette.primary, borderRadius: 999, paddingVertical: 12, alignItems: 'center' },
  buttonAlt: { backgroundColor: palette.accent },
  buttonText: { color: palette.bg, fontWeight: '800' },
});