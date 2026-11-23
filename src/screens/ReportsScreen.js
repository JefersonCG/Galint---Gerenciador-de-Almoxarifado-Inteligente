// Relatórios (2.2.5). Pedido do usuário em 23/11/2026: corrigir os erros dos relatórios do app,
// tirar a verbosidade e os cartões, centralizar a informação, compartilhar no WhatsApp em PDF e em
// Excel, e uma área "mais precisa e acessível em poucos cliques".
//
// Antes eram cinco telas (escolha + diário + mensal + consumo + histórico), cada uma com textos de
// explicação, baixando o PDF pelo expo-file-system 17 (o Expo 54 pede o 19) e abrindo o compartilhar
// genérico do Android. Agora: ☰ → Relatórios → aba (Dia, Mês, Consumo) → PDF ou Excel no WhatsApp.
// O resumo e a lista vêm de /api/mobile/relatorios/<tipo>; o arquivo é o mesmo relatório, baixado
// com o token pelo módulo nativo GalintShare (shareFile) e enviado direto ao WhatsApp.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    FlatList,
    Modal,
    NativeModules,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DateTimePickerAndroid } from '@react-native-community/datetimepicker';

import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import { heroPalette } from '../theme/heroTheme';

const TAB_KEY = 'galint_relatorios_aba';
const TABS = [
    { key: 'dia', label: 'Dia' },
    { key: 'mes', label: 'Mês' },
    { key: 'consumo', label: 'Consumo' },
];
const SCOPES = [
    { key: 'all', label: 'Tudo' },
    { key: 'materials', label: 'Materiais' },
    { key: 'tools', label: 'Ferramentas' },
];
const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const MIME = {
    pdf: 'application/pdf',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};
const FILTERS = [
    { key: 'local', label: 'Local', options: (o) => (o?.locais || []).map((value) => ({ value, label: value })) },
    { key: 'categoria', label: 'Categoria', options: (o) => (o?.categorias || []).map((value) => ({ value, label: value })) },
    { key: 'matricula', label: 'Colaborador', options: (o) => (o?.colaboradores || []).map((row) => ({ value: row.matricula, label: row.nome })) },
];

const pad = (value) => String(value).padStart(2, '0');
const isoDay = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const brDay = (date) => `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
const sameDay = (a, b) => isoDay(a) === isoDay(b);

export default function ReportsScreen() {
    const [tab, setTab] = useState('dia');
    const [scope, setScope] = useState('all');
    const [day, setDay] = useState(() => new Date());
    const [month, setMonth] = useState(() => {
        const now = new Date();
        return { year: now.getFullYear(), month: now.getMonth() + 1 };
    });
    const [consumo, setConsumo] = useState({ exercicio: '', local: '', categoria: '', matricula: '' });
    const [state, setState] = useState({ loading: true, data: null, error: '' });
    const [busy, setBusy] = useState('');
    const [picker, setPicker] = useState(null);

    useEffect(() => {
        AsyncStorage.getItem(TAB_KEY)
            .then((saved) => {
                if (TABS.some((entry) => entry.key === saved)) setTab(saved);
            })
            .catch(() => {});
    }, []);

    const params = useMemo(() => {
        if (tab === 'dia') return { data: isoDay(day), escopo: scope };
        if (tab === 'mes') return { ano: month.year, mes: month.month, escopo: scope };
        return { ...consumo };
    }, [consumo, day, month, scope, tab]);

    useEffect(() => {
        let alive = true;
        setState((current) => ({ ...current, loading: true, error: '' }));
        ApiService.getRelatorio(tab, params).then((result) => {
            if (!alive) return;
            if (result?.success) {
                setState({ loading: false, data: result.data, error: '' });
                const chosen = result.data?.opcoes?.exercicio;
                if (tab === 'consumo' && chosen && !consumo.exercicio) {
                    setConsumo((current) => ({ ...current, exercicio: chosen }));
                }
            } else {
                setState({ loading: false, data: null, error: result?.message || 'Não foi possível carregar.' });
            }
        });
        return () => {
            alive = false;
        };
        // consumo.exercicio entra em params; não precisa estar aqui de novo.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [params, tab]);

    const chooseTab = useCallback((key) => {
        InactivityService.recordActivity();
        setTab(key);
        AsyncStorage.setItem(TAB_KEY, key).catch(() => {});
    }, []);

    const shiftDay = useCallback((delta) => {
        InactivityService.recordActivity();
        setDay((current) => {
            const next = new Date(current);
            next.setDate(next.getDate() + delta);
            return next > new Date() ? current : next;
        });
    }, []);

    const pickDay = useCallback(() => {
        DateTimePickerAndroid.open({
            value: day,
            mode: 'date',
            maximumDate: new Date(),
            onChange: (event, value) => {
                if (event?.type === 'set' && value) setDay(value);
            },
        });
    }, [day]);

    const shiftMonth = useCallback((delta) => {
        InactivityService.recordActivity();
        setMonth((current) => {
            const index = current.year * 12 + (current.month - 1) + delta;
            const now = new Date();
            if (index > now.getFullYear() * 12 + now.getMonth()) return current;
            return { year: Math.floor(index / 12), month: (index % 12) + 1 };
        });
    }, []);

    const send = useCallback(async (format, openOnly = false) => {
        const data = state.data;
        if (!data || busy) return;
        if (data.vazio) {
            Alert.alert('Relatórios', data.mensagem_vazio || 'Nada registrado no período.');
            return;
        }
        InactivityService.recordActivity();
        setBusy(openOnly ? 'ver' : format);
        try {
            const token = await AsyncStorage.getItem('token');
            const url = ApiService.getRelatorioUrl(tab, { ...params, formato: format });
            await NativeModules.GalintShare.shareFile(url, token || '', `${data.arquivo || 'relatorio'}.${format}`, MIME[format], openOnly);
        } catch (error) {
            Alert.alert('Relatórios', error?.message || 'Não foi possível gerar o arquivo.');
        } finally {
            setBusy('');
        }
    }, [busy, params, state.data, tab]);

    const chooseFilter = useCallback((key, value) => {
        setPicker(null);
        // Um recorte por vez (local, categoria ou colaborador), como no site.
        setConsumo((current) => ({ exercicio: current.exercicio, local: '', categoria: '', matricula: '', [key]: value }));
    }, []);

    const data = state.data;
    const options = data?.opcoes;
    const activeFilter = FILTERS.find((filter) => consumo[filter.key]);
    const activeFilterLabel = activeFilter
        ? (activeFilter.options(options).find((row) => row.value === consumo[activeFilter.key])?.label || consumo[activeFilter.key])
        : '';

    const header = (
        <View>
            <View style={styles.track} accessibilityRole="tablist">
                {TABS.map((entry) => {
                    const active = entry.key === tab;
                    return (
                        <TouchableOpacity key={entry.key} style={[styles.tab, active && styles.tabActive]} onPress={() => chooseTab(entry.key)} activeOpacity={0.85}>
                            <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{entry.label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>

            {tab === 'dia' ? (
                <View style={styles.stepper}>
                    <TouchableOpacity style={styles.stepButton} onPress={() => shiftDay(-1)}><Text style={styles.stepIcon}>‹</Text></TouchableOpacity>
                    <TouchableOpacity style={styles.stepCenter} onPress={pickDay}>
                        <Text style={styles.stepText}>{sameDay(day, new Date()) ? `Hoje · ${brDay(day)}` : brDay(day)}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.stepButton} onPress={() => shiftDay(1)} disabled={sameDay(day, new Date())}>
                        <Text style={[styles.stepIcon, sameDay(day, new Date()) && styles.stepIconOff]}>›</Text>
                    </TouchableOpacity>
                </View>
            ) : null}

            {tab === 'mes' ? (
                <View style={styles.stepper}>
                    <TouchableOpacity style={styles.stepButton} onPress={() => shiftMonth(-1)}><Text style={styles.stepIcon}>‹</Text></TouchableOpacity>
                    <View style={styles.stepCenter}>
                        <Text style={styles.stepText}>{`${MONTHS[month.month - 1]} ${month.year}`}</Text>
                    </View>
                    <TouchableOpacity style={styles.stepButton} onPress={() => shiftMonth(1)}><Text style={styles.stepIcon}>›</Text></TouchableOpacity>
                </View>
            ) : null}

            {tab !== 'consumo' ? (
                <View style={styles.chips}>
                    {SCOPES.map((entry) => (
                        <TouchableOpacity key={entry.key} style={[styles.chip, scope === entry.key && styles.chipActive]} onPress={() => setScope(entry.key)}>
                            <Text style={[styles.chipText, scope === entry.key && styles.chipTextActive]}>{entry.label}</Text>
                        </TouchableOpacity>
                    ))}
                </View>
            ) : (
                <View>
                    <View style={styles.chips}>
                        {(options?.exercicios || []).map((value) => (
                            <TouchableOpacity
                                key={value}
                                style={[styles.chip, consumo.exercicio === value && styles.chipActive]}
                                onPress={() => setConsumo((current) => ({ ...current, exercicio: value }))}
                            >
                                <Text style={[styles.chipText, consumo.exercicio === value && styles.chipTextActive]}>{value}</Text>
                            </TouchableOpacity>
                        ))}
                    </View>
                    <View style={styles.chips}>
                        {FILTERS.map((filter) => {
                            const active = activeFilter?.key === filter.key;
                            return (
                                <TouchableOpacity key={filter.key} style={[styles.chip, active && styles.chipActive]} onPress={() => setPicker(filter.key)}>
                                    <Text style={[styles.chipText, active && styles.chipTextActive]} numberOfLines={1}>
                                        {active ? activeFilterLabel : `${filter.label} ▾`}
                                    </Text>
                                </TouchableOpacity>
                            );
                        })}
                        {activeFilter ? (
                            <TouchableOpacity style={styles.chip} onPress={() => chooseFilter(activeFilter.key, '')}>
                                <Text style={styles.chipText}>✕</Text>
                            </TouchableOpacity>
                        ) : null}
                    </View>
                </View>
            )}

            {data?.resumo?.length ? (
                <View style={styles.stats}>
                    {data.resumo.map((entry) => (
                        <View key={entry.rotulo} style={styles.stat}>
                            <Text style={styles.statValue} numberOfLines={1} adjustsFontSizeToFit>{entry.valor}</Text>
                            <Text style={styles.statLabel} numberOfLines={1}>{entry.rotulo}</Text>
                        </View>
                    ))}
                </View>
            ) : null}

            {state.loading ? <ActivityIndicator color={heroPalette.primary} style={styles.loading} /> : null}
            {!state.loading && state.error ? <Text style={styles.error}>{state.error}</Text> : null}
            {!state.loading && data?.vazio ? <Text style={styles.empty}>{data.mensagem_vazio}</Text> : null}
        </View>
    );

    const pickerFilter = FILTERS.find((filter) => filter.key === picker);
    const pickerRows = pickerFilter ? pickerFilter.options(options) : [];

    return (
        <View style={styles.container}>
            <FlatList
                data={state.loading || data?.vazio ? [] : (data?.linhas || [])}
                keyExtractor={(row, index) => `${index}-${row.titulo}`}
                ListHeaderComponent={header}
                contentContainerStyle={styles.content}
                renderItem={({ item }) => (
                    <View style={styles.row}>
                        <View style={styles.rowText}>
                            <Text style={styles.rowTitle} numberOfLines={2}>{item.titulo}</Text>
                            {item.detalhe ? <Text style={styles.rowDetail} numberOfLines={2}>{item.detalhe}</Text> : null}
                        </View>
                        <Text style={styles.rowValue}>{item.valor}</Text>
                    </View>
                )}
            />

            <View style={styles.bar}>
                <TouchableOpacity style={[styles.barButton, styles.barGhost]} onPress={() => send('pdf', true)} disabled={!!busy || !data}>
                    {busy === 'ver' ? <ActivityIndicator color={heroPalette.text} /> : <Text style={styles.barGhostText}>Ver</Text>}
                </TouchableOpacity>
                <TouchableOpacity style={[styles.barButton, styles.barMain]} onPress={() => send('pdf')} disabled={!!busy || !data}>
                    {busy === 'pdf' ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.barMainText}>WhatsApp PDF</Text>}
                </TouchableOpacity>
                <TouchableOpacity style={[styles.barButton, styles.barMain]} onPress={() => send('xlsx')} disabled={!!busy || !data}>
                    {busy === 'xlsx' ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.barMainText}>WhatsApp Excel</Text>}
                </TouchableOpacity>
            </View>

            <Modal visible={!!pickerFilter} transparent animationType="fade" onRequestClose={() => setPicker(null)}>
                <TouchableOpacity style={styles.pickerBackdrop} activeOpacity={1} onPress={() => setPicker(null)}>
                    <View style={styles.pickerPanel}>
                        <Text style={styles.pickerTitle}>{pickerFilter?.label}</Text>
                        <FlatList
                            data={pickerRows}
                            keyExtractor={(row) => String(row.value)}
                            renderItem={({ item }) => (
                                <TouchableOpacity style={styles.pickerRow} onPress={() => chooseFilter(pickerFilter.key, item.value)}>
                                    <Text style={styles.pickerRowText}>{item.label}</Text>
                                </TouchableOpacity>
                            )}
                        />
                    </View>
                </TouchableOpacity>
            </Modal>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    content: { padding: 16, paddingBottom: 24 },
    track: { flexDirection: 'row', backgroundColor: heroPalette.panel, borderRadius: 18, padding: 4, borderWidth: 1, borderColor: heroPalette.border },
    tab: { flex: 1, alignItems: 'center', paddingVertical: 11, borderRadius: 14 },
    tabActive: { backgroundColor: heroPalette.primaryStrong },
    tabLabel: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '800' },
    tabLabelActive: { color: heroPalette.bg },
    stepper: { flexDirection: 'row', alignItems: 'center', marginTop: 14, backgroundColor: heroPalette.panel, borderRadius: 16, borderWidth: 1, borderColor: heroPalette.border },
    stepButton: { paddingHorizontal: 20, paddingVertical: 10 },
    stepIcon: { color: heroPalette.text, fontSize: 30, fontWeight: '300', lineHeight: 32 },
    stepIconOff: { opacity: 0.25 },
    stepCenter: { flex: 1, alignItems: 'center', paddingVertical: 12 },
    stepText: { color: heroPalette.text, fontSize: 17, fontWeight: '800' },
    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
    chip: { maxWidth: '100%', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border },
    chipActive: { backgroundColor: heroPalette.primaryStrong, borderColor: heroPalette.primaryStrong },
    chipText: { color: heroPalette.textSoft, fontSize: 14, fontWeight: '700' },
    chipTextActive: { color: heroPalette.bg },
    stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
    stat: { flexGrow: 1, flexBasis: '30%', backgroundColor: heroPalette.panel, borderRadius: 14, paddingVertical: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: heroPalette.border },
    statValue: { color: heroPalette.text, fontSize: 20, fontWeight: '900' },
    statLabel: { color: heroPalette.textMuted, fontSize: 12, fontWeight: '700', marginTop: 2 },
    loading: { marginTop: 24 },
    error: { color: heroPalette.danger, fontSize: 15, fontWeight: '700', marginTop: 18, textAlign: 'center' },
    empty: { color: heroPalette.textMuted, fontSize: 15, marginTop: 18, textAlign: 'center' },
    row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    rowText: { flex: 1 },
    rowTitle: { color: heroPalette.text, fontSize: 15, fontWeight: '700' },
    rowDetail: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    rowValue: { color: heroPalette.primary, fontSize: 16, fontWeight: '900' },
    bar: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingTop: 10, paddingBottom: 12, backgroundColor: heroPalette.bgAlt, borderTopWidth: 1, borderTopColor: heroPalette.border },
    barButton: { height: 52, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
    barGhost: { width: 70, borderWidth: 1, borderColor: heroPalette.border, backgroundColor: heroPalette.panel },
    barGhostText: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    barMain: { flex: 1, backgroundColor: heroPalette.primaryStrong },
    barMainText: { color: heroPalette.bg, fontSize: 15, fontWeight: '900' },
    pickerBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', padding: 24 },
    pickerPanel: { maxHeight: '75%', backgroundColor: heroPalette.panel, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: heroPalette.borderStrong },
    pickerTitle: { color: heroPalette.text, fontSize: 18, fontWeight: '900', marginBottom: 8 },
    pickerRow: { paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    pickerRowText: { color: heroPalette.text, fontSize: 15 },
});
