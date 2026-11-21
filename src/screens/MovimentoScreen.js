// Movimento de material (2.2.0). Pedido do usuário em 21/11/2026: no menu ☰, um item só para as
// movimentações, com as mesmas abas da página "Lançamentos" do site (Materiais, Ferramentas,
// Fracionados, Devoluções). Cada aba abre os fluxos que já existiam (leitor de código, retirada
// de vários itens, devolução). A custódia do dia, que ficava em "Consultar estoque" (removido),
// mora na aba Devoluções e só é carregada quando ela está aberta (o servidor leva alguns segundos).
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useFocusEffect } from '@react-navigation/native';

import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import DailyCustodyPanel from '../components/DailyCustodyPanel';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

const TAB_KEY = 'galint_movimento_aba';
const TABS = [
    { key: 'materiais', icon: '📦', label: 'Materiais', description: 'Saída de materiais de consumo do estoque.' },
    { key: 'ferramentas', icon: '🔧', label: 'Ferramentas', description: 'Empréstimo de ferramentas: elas ficam na custódia de quem retirou.' },
    { key: 'fracionados', icon: '💧', label: 'Fracionados', description: 'Líquidos e materiais em fração (litro, quilo, parte da embalagem).' },
    { key: 'devolucoes', icon: '↩️', label: 'Devoluções', description: 'Volta de ferramentas e materiais ao estoque, por código ou pela custódia do dia.' },
];
const EMPTY_SUMMARY = { employees: 0, tools: 0, overdue: 0 };

export default function MovimentoScreen({ navigation, route }) {
    const user = route?.params?.user || null;
    const [tab, setTab] = useState(route?.params?.tab || 'materiais');
    const [custody, setCustody] = useState({ visible: true, loading: false, groups: [], summary: EMPTY_SUMMARY, message: '' });
    const [returning, setReturning] = useState(false);

    useEffect(() => {
        if (route?.params?.tab) return;
        AsyncStorage.getItem(TAB_KEY)
            .then((saved) => {
                if (TABS.some((entry) => entry.key === saved)) setTab(saved);
            })
            .catch(() => {});
    }, [route?.params?.tab]);

    const chooseTab = useCallback((key) => {
        InactivityService.recordActivity();
        setTab(key);
        AsyncStorage.setItem(TAB_KEY, key).catch(() => {});
    }, []);

    const open = useCallback((screen, params = {}) => {
        InactivityService.recordActivity();
        navigation.navigate(screen, { user, ...params });
    }, [navigation, user]);

    const loadCustody = useCallback(async (silent = false) => {
        if (!silent) setCustody((current) => ({ ...current, loading: true }));
        const result = await ApiService.getDailyCustodyFeed();
        if (result?.success) {
            const payload = result.data || {};
            setCustody({
                visible: true,
                loading: false,
                groups: Array.isArray(payload.groups) ? payload.groups : [],
                summary: payload.summary || EMPTY_SUMMARY,
                message: '',
            });
            return;
        }
        setCustody({
            visible: Number(result?.status) !== 403, // sem permissão: a custódia some
            loading: false,
            groups: [],
            summary: EMPTY_SUMMARY,
            message: result?.message || 'Não foi possível carregar a custódia do dia agora.',
        });
    }, []);

    useFocusEffect(
        useCallback(() => {
            if (tab === 'devolucoes') loadCustody(true);
            return undefined;
        }, [loadCustody, tab])
    );

    useEffect(() => {
        if (tab === 'devolucoes') loadCustody(false);
    }, [loadCustody, tab]);

    const executeReturn = useCallback(async (entries) => {
        setReturning(true);
        InactivityService.recordActivity();
        let done = 0;
        const failures = [];
        try {
            for (const entry of entries) {
                const result = await ApiService.returnDailyCustodyTool({
                    codigo: entry.item?.codigo,
                    quantidade: entry.item?.quantidade || 1,
                    saida_id: entry.item?.saida_id || entry.item?.id || null,
                    matricula: entry.group?.matricula_full || entry.group?.matricula || '',
                });
                if (result?.success) done += 1;
                else failures.push(`${entry.item?.descricao || entry.item?.codigo || 'Ferramenta'}: ${result?.message || 'falhou'}`);
            }
        } finally {
            setReturning(false);
        }
        if (done > 0) loadCustody(true);
        if (!failures.length) {
            Alert.alert('Custódia do dia', done === 1 ? 'Ferramenta devolvida.' : `${done} ferramentas devolvidas.`);
        } else {
            Alert.alert('Custódia do dia', `${done} devolvida(s) e ${failures.length} com falha.\n\n${failures.slice(0, 3).join('\n')}`);
        }
    }, [loadCustody]);

    const confirmReturn = useCallback((entries, options = {}) => {
        const list = Array.isArray(entries) ? entries.filter((entry) => entry?.group && entry?.item) : [];
        if (!list.length) return;
        const who = options?.group?.usuario;
        const message = list.length === 1
            ? `Dar baixa de ${list[0].item?.descricao || 'esta ferramenta'}?`
            : `Dar baixa de ${list.length} ferramentas${who ? ` de ${who}` : ''}?`;
        Alert.alert('Dar baixa', message, [
            { text: 'Cancelar', style: 'cancel' },
            { text: 'Dar baixa', onPress: () => executeReturn(list) },
        ]);
    }, [executeReturn]);

    const current = TABS.find((entry) => entry.key === tab) || TABS[0];

    const action = (icon, title, hint, onPress, primary = false) => (
        <TouchableOpacity key={title} style={[styles.action, primary && styles.actionPrimary]} onPress={onPress} activeOpacity={0.85}>
            <Text style={styles.actionIcon}>{icon}</Text>
            <View style={styles.actionText}>
                <Text style={[styles.actionTitle, primary && styles.actionTitlePrimary]}>{title}</Text>
                <Text style={[styles.actionHint, primary && styles.actionHintPrimary]}>{hint}</Text>
            </View>
            <Text style={[styles.actionArrow, primary && styles.actionTitlePrimary]}>›</Text>
        </TouchableOpacity>
    );

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            <View style={styles.track} accessibilityRole="tablist">
                {TABS.map((entry) => {
                    const active = entry.key === tab;
                    return (
                        <TouchableOpacity
                            key={entry.key}
                            style={[styles.tab, active && styles.tabActive]}
                            onPress={() => chooseTab(entry.key)}
                            accessibilityRole="tab"
                            accessibilityState={{ selected: active }}
                            activeOpacity={0.85}
                        >
                            <Text style={styles.tabIcon}>{entry.icon}</Text>
                            <Text style={[styles.tabLabel, active && styles.tabLabelActive]} numberOfLines={1}>{entry.label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>
            <Text style={styles.description}>{current.description}</Text>

            {tab === 'materiais' ? (
                <>
                    {action('📷', 'Ler código e retirar', 'Aponte a câmera para o código do material', () => open('Scanner', { mode: 'withdraw' }), true)}
                    {action('🧰', 'Vários itens de uma vez', 'Monte a saída com vários materiais', () => open('Retirada', { multi: true, items: [] }))}
                </>
            ) : null}

            {tab === 'ferramentas' ? (
                <>
                    {action('📷', 'Ler código da ferramenta', 'Retirada com a pessoa responsável pela custódia', () => open('Scanner', { mode: 'tool_withdraw' }), true)}
                    {action('🧰', 'Várias ferramentas de uma vez', 'Monte a retirada com vários itens', () => open('Retirada', { multi: true, items: [] }))}
                </>
            ) : null}

            {tab === 'fracionados' ? (
                action('📷', 'Ler código e retirar uma fração', 'Litro, quilo ou parte da embalagem', () => open('Scanner', { mode: 'withdraw_fraction' }), true)
            ) : null}

            {tab === 'devolucoes' ? (
                <>
                    {action('📷', 'Ler código e devolver', 'Ferramenta ou material de volta ao estoque', () => open('Scanner', { mode: 'return' }), true)}
                    {custody.visible ? (
                        <View style={styles.custody}>
                            <DailyCustodyPanel
                                groups={custody.groups}
                                summary={custody.summary}
                                loading={custody.loading}
                                message={custody.message}
                                isReturning={returning}
                                onReload={() => loadCustody(false)}
                                onReturnSelectedPress={confirmReturn}
                                onReturnAllPress={confirmReturn}
                            />
                        </View>
                    ) : null}
                </>
            ) : null}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    content: { padding: 16, paddingBottom: 40 },
    track: { flexDirection: 'row', backgroundColor: heroPalette.panel, borderRadius: 18, padding: 4, borderWidth: 1, borderColor: heroPalette.border },
    tab: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 14 },
    tabActive: { backgroundColor: heroPalette.primaryStrong },
    tabIcon: { fontSize: 18 },
    tabLabel: { color: heroPalette.textSoft, fontSize: 11, fontWeight: '800', marginTop: 3 },
    tabLabelActive: { color: heroPalette.bg },
    description: { color: heroPalette.textMuted, fontSize: 14, lineHeight: 20, marginTop: 12, marginBottom: 14, textAlign: 'center' },
    action: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: heroPalette.panel, borderRadius: 18, padding: 16, borderWidth: 1, borderColor: heroPalette.border, marginBottom: 12, ...heroSoftShadow },
    actionPrimary: { backgroundColor: heroPalette.primaryStrong, borderColor: heroPalette.primaryStrong },
    actionIcon: { fontSize: 28 },
    actionText: { flex: 1 },
    actionTitle: { color: heroPalette.text, fontSize: 17, fontWeight: '800' },
    actionTitlePrimary: { color: heroPalette.bg },
    actionHint: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    actionHintPrimary: { color: heroPalette.bg, opacity: 0.8 },
    actionArrow: { color: heroPalette.textMuted, fontSize: 26, fontWeight: '300' },
    custody: { marginTop: 6 },
});
