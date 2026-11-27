// Movimento de material. Pedido do usuário em 21/11/2026: no menu ☰, um item só para as
// movimentações. Na 2.2.0 eram as quatro abas do site; na 2.2.1 ficaram duas (segundo pedido do
// mesmo dia): Retirada, com materiais e ferramentas juntos (a tela de retirada reconhece a
// ferramenta pela categoria e pede a custódia), e Devolução. Fracionados saíram do app e ficam só
// no site. A custódia do dia, que ficava em "Consultar estoque" (removido), mora na aba Devolução
// e só é carregada quando ela está aberta (o servidor leva alguns segundos).
// 2.4.0 (25/11/2026): "Vários itens" virou "Fila de saída" (FilaSaidaScreen), a fila do site por
// colaborador, guardada no celular; o cartão mostra quantos itens esperam a saída.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Keyboard, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useFocusEffect } from '@react-navigation/native';

import TextInput from '../components/UpperTextInput';
import BotaoVoz from '../components/BotaoVoz';
import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import DailyCustodyPanel from '../components/DailyCustodyPanel';
import { contarFila } from '../services/filaSaida';
import { listarTodosItens } from '../services/localDb';
import { pessoasParaVoz } from '../services/pessoasVoz';
import { buscarComNota, buscarMaterial, interpretarComando, vencedorClaro } from '../utils/buscaFalada';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

const TAB_KEY = 'galint_movimento_aba';
const TABS = [
    { key: 'retirada', icon: '📤', label: 'Retirada' },
    { key: 'devolucao', icon: '📥', label: 'Devolução' },
];
const EMPTY_SUMMARY = { employees: 0, tools: 0, overdue: 0 };

// 2.5.0 (26/11/2026): Retirada e Devolução viraram dois itens do menu. A Retirada é a FilaSaidaScreen (uma ou
// várias de uma vez); a Devolução é esta tela fixa na aba Devolução (rota "Devolucao", params.fixo): ler o
// código de um item ou dar baixa em várias ferramentas da custódia do dia, sem textos explicativos.
// 2.6.2 (27/11/2026), pedido do usuário: "remove essas informações de custódia daqui, deixe limpo". A Devolução fica
// com "Ler código" e "Código, nome ou 🎤" (a mesma busca da Retirada; "por Júlio furadeira" leva quem devolve).
// Com quem está cada ferramenta: comando "custódia" (tela Custodia). A baixa em várias ferramentas segue no site.
export default function MovimentoScreen({ navigation, route }) {
    const user = route?.params?.user || null;
    const fixo = route?.params?.fixo === true;
    const [tab, setTab] = useState(route?.params?.tab || 'retirada');
    const [custody, setCustody] = useState({ visible: true, loading: false, groups: [], summary: EMPTY_SUMMARY, message: '' });
    const [returning, setReturning] = useState(false);
    const [limpeza, setLimpeza] = useState(0); // muda depois de cada baixa: limpa a seleção da custódia
    const [busca, setBusca] = useState('');
    const [sugestoes, setSugestoes] = useState([]);
    const [abrindo, setAbrindo] = useState(false);
    const fala = useRef(null); // quantidade e quem devolve ditos no 🎤, à espera do item tocado na lista

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
            if (tab === 'devolucao' && !fixo) loadCustody(true);
            return undefined;
        }, [fixo, loadCustody, tab])
    );

    // Fila de saída guardada no celular (2.4.0): quantos itens esperam a saída.
    const [naFila, setNaFila] = useState(0);
    useFocusEffect(
        useCallback(() => {
            let ativo = true;
            contarFila(user).then((total) => {
                if (ativo) setNaFila(total);
            });
            return () => {
                ativo = false;
            };
        }, [user])
    );

    useEffect(() => {
        if (tab === 'devolucao' && !fixo) loadCustody(false);
    }, [fixo, loadCustody, tab]);

    // ---------- Devolução pela busca e pela voz (2.6.2) ----------
    useEffect(() => {
        const termo = busca.trim();
        if (termo.length < 2) {
            setSugestoes([]);
            return undefined;
        }
        const timer = setTimeout(() => {
            listarTodosItens().then((lista) => setSugestoes(buscarMaterial(lista, termo, { limite: 10 }))).catch(() => setSugestoes([]));
        }, 180);
        return () => clearTimeout(timer);
    }, [busca]);

    const abrirDevolucao = useCallback(async (entry) => {
        const codigo = String(entry?.codigo_barras || entry?.id || entry || '').trim();
        if (!codigo || abrindo) return;
        InactivityService.recordActivity();
        Keyboard.dismiss();
        setAbrindo(true);
        const item = await ApiService.buscarItemPorCodigo(codigo).catch(() => null);
        setAbrindo(false);
        if (!item) {
            Alert.alert('Não encontrado', ApiService.lastItemLookupFailure === 'network' ? 'Sem conexão com o servidor.' : `O código ${codigo} não está cadastrado.`);
            return;
        }
        const dito = fala.current || {};
        fala.current = null;
        setBusca('');
        setSugestoes([]);
        open('Devolver', { item, ...dito });
    }, [abrindo, open]);

    const ouvirNaDevolucao = useCallback(async (frase) => {
        InactivityService.recordActivity();
        const pedido = interpretarComando(frase, { pessoas: await pessoasParaVoz() });
        fala.current = {
            ...(pedido.quantidade != null ? { quantidadeFalada: pedido.quantidade, modoFalado: pedido.modo } : {}),
            ...(pedido.pessoa ? { pessoaFalada: pedido.pessoa } : {}),
        };
        const material = String(pedido.material || '').trim();
        if (!material) return;
        const lista = await listarTodosItens().catch(() => []);
        const certo = vencedorClaro(buscarComNota(lista, material, { limite: 10 }));
        if (certo) {
            abrirDevolucao(certo);
            return;
        }
        setBusca(material);
    }, [abrirDevolucao]);

    // 2.7.1: fala dita no 🎤 da câmera ("Ler código" → Falar) volta para cá e segue o mesmo caminho.
    const falaRecebida = route?.params?.falaRecebida || '';
    const falaId = route?.params?.falaId || 0;
    useEffect(() => {
        if (!falaRecebida) return;
        navigation.setParams({ falaRecebida: null, falaId: null });
        ouvirNaDevolucao(falaRecebida);
    }, [falaId]); // eslint-disable-line react-hooks/exhaustive-deps

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
        setLimpeza((valor) => valor + 1);
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

    const action = (icon, title, hint, onPress, primary = false) => (
        <TouchableOpacity key={title} style={[styles.action, primary && styles.actionPrimary]} onPress={onPress} activeOpacity={0.85}>
            <Text style={styles.actionIcon}>{icon}</Text>
            <View style={styles.actionText}>
                <Text style={[styles.actionTitle, primary && styles.actionTitlePrimary]}>{title}</Text>
                {hint ? <Text style={[styles.actionHint, primary && styles.actionHintPrimary]}>{hint}</Text> : null}
            </View>
            <Text style={[styles.actionArrow, primary && styles.actionTitlePrimary]}>›</Text>
        </TouchableOpacity>
    );

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            {fixo ? null : (
            <>
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
            <View style={styles.tabsGap} />
            </>
            )}
            {tab === 'retirada' ? (
                <>
                    {action('📷', 'Ler código', 'Material ou ferramenta', () => open('Scanner', { mode: 'withdraw' }), true)}
                    {action(
                        '🧺',
                        'Fila de saída',
                        naFila ? `${naFila} ${naFila === 1 ? 'item esperando' : 'itens esperando'}` : 'Vários itens e colaboradores',
                        () => open('FilaSaida'),
                    )}
                </>
            ) : null}

            {tab === 'devolucao' ? (
                <>
                    {action('📷', 'Ler código', null, () => open('Scanner', { mode: 'return' }), true)}
                    {fixo ? (
                        <>
                            <View style={styles.codigoRow}>
                                <TextInput
                                    style={styles.input}
                                    value={busca}
                                    onChangeText={(texto) => { fala.current = null; setBusca(texto); }}
                                    placeholder="Código, nome ou 🎤"
                                    placeholderTextColor="#94a3b8"
                                    autoCorrect={false}
                                    returnKeyType="search"
                                    onSubmitEditing={() => {
                                        if (sugestoes.length === 1) abrirDevolucao(sugestoes[0]);
                                        else if (busca.trim() && !sugestoes.length) abrirDevolucao(busca.trim());
                                    }}
                                />
                                <BotaoVoz tamanho={54} onFala={ouvirNaDevolucao} />
                            </View>
                            {abrindo ? <ActivityIndicator color={heroPalette.primary} style={styles.abrindo} /> : null}
                            {sugestoes.length ? (
                                <View style={styles.lista}>
                                    {sugestoes.map((entry) => (
                                        <TouchableOpacity
                                            key={String(entry.codigo_barras || entry.id)}
                                            style={styles.listaLinha}
                                            onPress={() => abrirDevolucao(entry)}
                                            activeOpacity={0.8}
                                        >
                                            <Text style={styles.listaNome} numberOfLines={2}>{entry.descricao}</Text>
                                            <Text style={styles.listaDetalhe} numberOfLines={1}>{entry.codigo_barras || entry.id}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            ) : null}
                        </>
                    ) : custody.visible ? (
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
                                resetKey={limpeza}
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
    tabLabel: { color: heroPalette.textSoft, fontSize: 14, fontWeight: '800', marginTop: 3 },
    tabLabelActive: { color: heroPalette.bg },
    tabsGap: { height: 16 },
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
    codigoRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
    input: { flex: 1, backgroundColor: '#fff', color: '#0f172a', borderRadius: 14, paddingHorizontal: 16, height: 54, fontSize: 16, fontWeight: '700' },
    abrindo: { marginTop: 12 },
    lista: { marginTop: 8, borderRadius: 12, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, overflow: 'hidden' },
    listaLinha: { paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    listaNome: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    listaDetalhe: { color: heroPalette.textMuted, fontSize: 12, marginTop: 2 },
});
