import React, { useEffect, useMemo, useState } from 'react';
import { Alert, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { palette } from '../theme';

const FILTERS = [
  { key: 'all', label: 'Tudo' },
  { key: 'withdrawal', label: 'Retiradas' },
  { key: 'inventory', label: 'Estoque' },
  { key: 'item', label: 'Itens' },
];

export default function MessengerScreen({ navigation, highlightMessageId, onConsumedHighlight }) {
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState({ items: [], unread_count: 0 });

  async function loadInbox() {
    try {
      setLoading(true);
      const response = await api.fetchInbox();
      setPayload(response);
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao carregar inbox');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInbox();
  }, []);

  useEffect(() => {
    if (highlightMessageId) {
      setTimeout(() => onConsumedHighlight?.(), 4000);
    }
  }, [highlightMessageId, onConsumedHighlight]);

  const items = useMemo(() => {
    const all = payload.items || [];
    if (filter === 'all') return all;
    return all.filter((item) => item.category === filter || item.message_type === filter);
  }, [payload, filter]);

  async function openItem(item) {
    try {
      if (item.status !== 'read') {
        await api.markRead(item.id);
      }
      navigation.navigate('NotificationDetail', { item });
      loadInbox();
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao abrir notificação');
    }
  }

  return (
    <ScreenShell title="Messenger" subtitle={`${payload.unread_count || 0} não lidas. Feed resumido, sem excesso de texto bruto.`} scroll={false}>
      <View style={styles.filters}>
        {FILTERS.map((entry) => (
          <Pressable key={entry.key} onPress={() => setFilter(entry.key)} style={[styles.filterChip, filter === entry.key && styles.filterChipActive]}>
            <Text style={[styles.filterText, filter === entry.key && styles.filterTextActive]}>{entry.label}</Text>
          </Pressable>
        ))}
      </View>
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={loadInbox} tintColor={palette.primary} />}
        contentContainerStyle={{ paddingBottom: 40 }}
        renderItem={({ item }) => {
          const highlighted = highlightMessageId && Number(highlightMessageId) === Number(item.id);
          return (
            <Pressable onPress={() => openItem(item)} style={[styles.card, item.status !== 'read' && styles.cardUnread, highlighted && styles.cardHighlight]}>
              <View style={styles.cardHeader}>
                <Text style={styles.category}>{item.category || item.message_type || 'mensagem'}</Text>
                <Text style={styles.timestamp}>{item.created_at ? new Date(item.created_at).toLocaleString('pt-BR') : '-'}</Text>
              </View>
              <Text style={styles.title} numberOfLines={2}>{item.title}</Text>
              <Text style={styles.body} numberOfLines={3}>{item.body}</Text>
              <View style={styles.statusRow}>
                <Text style={styles.status}>{item.status === 'read' ? 'Lida' : 'Não lida'}</Text>
              </View>
            </Pressable>
          );
        }}
        ListEmptyComponent={<Text style={styles.empty}>Nenhuma notificação para o filtro selecionado.</Text>}
      />
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  filterChip: { borderRadius: 999, borderWidth: 1, borderColor: palette.border, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: palette.panel },
  filterChipActive: { backgroundColor: palette.primary, borderColor: palette.primary },
  filterText: { color: palette.muted, fontWeight: '700', textTransform: 'uppercase', fontSize: 11 },
  filterTextActive: { color: palette.bg },
  card: { backgroundColor: palette.panel, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: palette.border, marginBottom: 12 },
  cardUnread: { borderColor: palette.primary },
  cardHighlight: { shadowColor: palette.primary, shadowOpacity: 0.4, shadowRadius: 10, elevation: 5 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8, gap: 12 },
  category: { color: palette.primary, textTransform: 'uppercase', fontSize: 11, fontWeight: '800' },
  timestamp: { color: palette.muted, fontSize: 12 },
  title: { color: palette.text, fontSize: 17, fontWeight: '800', marginBottom: 6 },
  body: { color: palette.muted, lineHeight: 20 },
  statusRow: { marginTop: 12, flexDirection: 'row' },
  status: { color: palette.accent, fontWeight: '700' },
  empty: { color: palette.muted, textAlign: 'center', marginTop: 40 },
});