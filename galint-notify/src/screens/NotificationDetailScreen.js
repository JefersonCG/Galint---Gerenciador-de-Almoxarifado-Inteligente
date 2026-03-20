import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { palette } from '../theme';

export default function NotificationDetailScreen({ route }) {
  const item = route.params?.item;
  if (!item) {
    return <View style={styles.safe}><Text style={styles.empty}>Notificação não encontrada.</Text></View>;
  }

  return (
    <ScrollView style={styles.safe} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <Text style={styles.category}>{item.category}</Text>
        <Text style={styles.title}>{item.title}</Text>
        <Text style={styles.body}>{item.body}</Text>
        <Text style={styles.blockTitle}>Payload</Text>
        <Text style={styles.payload}>{JSON.stringify(item.payload || {}, null, 2)}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.bg },
  content: { padding: 20 },
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 18 },
  category: { color: palette.primary, textTransform: 'uppercase', fontSize: 11, fontWeight: '800' },
  title: { color: palette.text, fontWeight: '800', fontSize: 24, marginTop: 8 },
  body: { color: palette.muted, marginTop: 12, lineHeight: 22 },
  blockTitle: { color: palette.text, fontWeight: '800', marginTop: 18, marginBottom: 8 },
  payload: { color: palette.text, fontFamily: 'monospace', backgroundColor: palette.panelAlt, padding: 12, borderRadius: 14 },
  empty: { color: palette.text, padding: 20 },
});