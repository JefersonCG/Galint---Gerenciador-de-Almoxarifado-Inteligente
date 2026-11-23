// Painel (2.2.5). Pedido do usuário em 23/11/2026: "excluir toda verbosidade". Saíram o cartão de
// título com frase de apresentação, os subtítulos de cada cartão e os cartões que já estão no ☰
// (Avisos, Relatórios, Consumo). Ficam os números do dia, Perfil, Configurações e as últimas
// movimentações.
import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import ApiService from '../services/api';
import { subscribeNotifyInboxChanged } from '../services/notifyEvents';
import { heroPalette } from '../theme/heroTheme';

export default function MenuScreen({ navigation }) {
    const [overview, setOverview] = useState(null);
    const [loading, setLoading] = useState(true);

    const loadOverview = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        const result = await ApiService.getErpOverview();
        setOverview(result?.success ? result.data || null : null);
        if (!silent) setLoading(false);
    }, []);

    useFocusEffect(
        useCallback(() => {
            loadOverview();
            const intervalId = setInterval(() => loadOverview(true), 12000);
            const unsubscribeNotify = subscribeNotifyInboxChanged(() => loadOverview(true));
            return () => {
                clearInterval(intervalId);
                unsubscribeNotify();
            };
        }, [loadOverview])
    );

    const unreadCount = Number(overview?.notifications?.unread_count || 0);
    const today = overview?.movement_stats?.today || {};
    const totalToday = Number(today.entradas || 0) + Number(today.saidas || 0) + Number(today.inventario || 0);
    const totalItems = Number(overview?.stock?.total_itens || 0);
    const recent = Array.isArray(overview?.recent_movements) ? overview.recent_movements.slice(0, 6) : [];

    const stat = (label, value) => (
        <View style={styles.stat}>
            <Text style={styles.statValue}>{value}</Text>
            <Text style={styles.statLabel}>{label}</Text>
        </View>
    );

    const entry = (icon, label, screen) => (
        <TouchableOpacity style={styles.entry} onPress={() => navigation.navigate(screen)} activeOpacity={0.85}>
            <Text style={styles.entryIcon}>{icon}</Text>
            <Text style={styles.entryLabel}>{label}</Text>
            <Text style={styles.entryArrow}>›</Text>
        </TouchableOpacity>
    );

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            <View style={styles.stats}>
                {stat('Avisos', unreadCount > 99 ? '99+' : unreadCount)}
                {stat('Hoje', totalToday)}
                {stat('Itens', totalItems)}
            </View>

            {entry('👤', 'Perfil', 'Profile')}
            {entry('⚙️', 'Configurações', 'Config')}

            <Text style={styles.section}>Últimas movimentações</Text>
            {loading && !overview ? <ActivityIndicator color={heroPalette.primary} style={styles.loading} /> : null}
            {recent.map((movement, index) => (
                <View key={`${movement.id || index}-${movement.tipo}`} style={styles.row}>
                    <View style={styles.rowText}>
                        <Text style={styles.rowTitle} numberOfLines={2}>{movement.descricao || movement.codigo || 'Item'}</Text>
                        <Text style={styles.rowDetail} numberOfLines={1}>
                            {[movement.tipo, movement.responsavel, movement.local_servico].filter(Boolean).join(' · ')}
                        </Text>
                    </View>
                    <Text style={styles.rowValue}>{movement.quantidade}</Text>
                </View>
            ))}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    content: { padding: 16, paddingBottom: 32 },
    stats: { flexDirection: 'row', gap: 8, marginBottom: 14 },
    stat: { flex: 1, backgroundColor: heroPalette.panel, borderRadius: 14, paddingVertical: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: heroPalette.border },
    statValue: { color: heroPalette.text, fontSize: 22, fontWeight: '900' },
    statLabel: { color: heroPalette.textMuted, fontSize: 12, fontWeight: '700', marginTop: 2 },
    entry: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: heroPalette.panel, borderRadius: 16, paddingVertical: 15, paddingHorizontal: 16, borderWidth: 1, borderColor: heroPalette.border, marginBottom: 10 },
    entryIcon: { fontSize: 22 },
    entryLabel: { flex: 1, color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    entryArrow: { color: heroPalette.textMuted, fontSize: 26, fontWeight: '300' },
    section: { color: heroPalette.textMuted, fontSize: 13, fontWeight: '800', marginTop: 16, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.6 },
    loading: { marginTop: 16 },
    row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    rowText: { flex: 1 },
    rowTitle: { color: heroPalette.text, fontSize: 15, fontWeight: '700' },
    rowDetail: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    rowValue: { color: heroPalette.primary, fontSize: 16, fontWeight: '900' },
});
