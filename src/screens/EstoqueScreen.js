// Tela inicial do app (2.2.0): a Conferência.
//
// Pedido do usuário em 21/11/2026:
// - no lugar do círculo azul, a câmera do código de barras fica sempre ligada dentro do círculo,
//   mas só lê quando a pessoa toca nele;
// - "Consultar estoque" sai: a consulta é a própria conferência (todos veem foto, nome e saldo;
//   só quem tem "Pode alterar o estoque" grava a quantidade). A busca por nome usa a base do
//   celular (services/localDb.js), que a sincronização mantém igual à do servidor;
// - avisos mais visíveis (ninguém olha o Telegram): faixa na tela, sino com número e alerta do
//   celular quando chega aviso novo com o app aberto;
// - menu ☰ enxuto: Conferência, Movimento de material, Avisos, Painel e Sair.
// Em 23/11/2026 (2.2.6): código que não existe no GALINT pergunta "Deseja cadastrar?" (só para quem
// lança entrada) e abre o mesmo "Lançar entrada" com os campos do item novo; na volta, o item abre aqui.
//
// A tela também cuida da sessão (sinal de vida, inatividade) e da sincronização da base.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    AppState,
    Dimensions,
    FlatList,
    Keyboard,
    KeyboardAvoidingView,
    Modal,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    Vibration,
    View,
} from 'react-native';
import TextInput from '../components/UpperTextInput';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useIsFocused } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Notifications from 'expo-notifications';

import ApiService from '../services/api';
import HeartbeatService from '../services/heartbeatService';
import InactivityService from '../services/inactivityService';
import SyncService from '../services/dbSync';
import { getItemByCodigo, searchItems } from '../services/localDb';
import { subscribeNotifyInboxChanged } from '../services/notifyEvents';
import StockCountPanel from '../components/StockCountPanel';
import ItemPhotoLinkModal from '../components/ItemPhotoLinkModal';
import { ENTRADAS_FISCAIS_NO_APP } from '../config/features';
import { isRegistrableCode } from '../utils/itemCode';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CIRCLE = Math.round(Math.min(SCREEN_WIDTH * 0.72, 300));
// Máscara em anel da cor do fundo: no Android a prévia da câmera não respeita borda redonda, então
// um anel grosso cobre os cantos do quadrado (precisa de pelo menos 21% do diâmetro).
const MASK = Math.ceil(CIRCLE * 0.22) + 2;
// A planilha usa Code128; as embalagens costumam ter EAN/UPC.
const BARCODE_TYPES = ['code128', 'ean13', 'ean8', 'upc_a', 'upc_e', 'code39', 'code93', 'itf14', 'qr'];
const CAPTURE_WINDOW_MS = 700; // toque logo depois de o código aparecer: usa o que já foi visto
const ARMED_MS = 4000; // sem código à vista no toque: espera até 4 s pelo primeiro que aparecer
const INBOX_POLL_MS = 30 * 1000;
const LAST_ALERTED_KEY = 'galint_ultimo_aviso_alertado';

function getUserRole(user) {
    if (!user) return 'operacional';
    const cargo = String(user.cargo || '').toLowerCase().trim();
    const setor = String(user.setor || '').toLowerCase().trim();
    const isAdmin = user.is_admin === true || user.is_admin === 1 || String(user.is_admin || '').trim() === '1';
    if (isAdmin || cargo.includes('almoxarif') || cargo === 'master') return 'master';
    if (cargo.includes('gerente') || setor.includes('gerenc') || setor.includes('adm') || cargo.includes('supervisor') || setor.includes('supervisor')) return 'gerencia';
    return 'operacional';
}

function roleLabel(role) {
    if (role === 'master') return 'Master';
    if (role === 'gerencia') return 'Gerência';
    return 'Operação';
}

function syncLabel(status) {
    if (!status.lastSyncAt) return status.online ? 'Baixando a base...' : 'Sem conexão';
    if (!status.online) return `Sem conexão • ${status.count} itens no celular`;
    const seconds = Math.max(0, Math.round((Date.now() - status.lastSyncAt) / 1000));
    const when = seconds < 60 ? 'agora' : `há ${Math.round(seconds / 60)} min`;
    return `${status.count} itens • atualizada ${when}`;
}

export default function EstoqueScreen({ navigation, route }) {
    const [user, setUser] = useState(route.params?.user || null);
    const [permission, requestPermission] = useCameraPermissions();
    const insets = useSafeAreaInsets();
    const isFocused = useIsFocused();
    const [appActive, setAppActive] = useState(AppState.currentState === 'active');
    const [menuOpen, setMenuOpen] = useState(false);
    const [torch, setTorch] = useState(false);
    const [armed, setArmed] = useState(false);
    const [panel, setPanel] = useState(null); // { item, loading, note }
    const [notice, setNotice] = useState(null); // { tone, text }
    const [counted, setCounted] = useState(0);
    const [search, setSearch] = useState('');
    const [results, setResults] = useState([]);
    const [sync, setSync] = useState(SyncService.getStatus());
    const [inbox, setInbox] = useState({ unread: 0, latest: null });
    const [itemMenu, setItemMenu] = useState(false); // ☰ do item lido (lançar entrada com NF)
    const [photoModal, setPhotoModal] = useState(false); // foto do item pelo link
    const [missing, setMissing] = useState(null); // código lido que não existe: pergunta se cadastra
    const registering = useRef(''); // código que foi para o cadastro: abre o item na volta
    const lastSeen = useRef({ code: '', at: 0 });
    const armedUntil = useRef(0);
    const lookupId = useRef(0);

    const role = useMemo(() => getUserRole(user), [user]);
    // Lançar entrada com NF usa a rota dos documentos fiscais: só administradores (como no servidor).
    const canLaunchEntry = user?.is_admin === true || user?.is_admin === 1 || String(user?.is_admin || '') === '1';
    const firstName = String(user?.nome || user?.username || '').trim().split(/\s+/)[0] || '';
    const cameraActive = Boolean(permission?.granted) && isFocused && appActive && !menuOpen && !panel && !search;

    // ---------- sessão e sincronização ----------
    useEffect(() => {
        if (!route.params?.user) {
            AsyncStorage.getItem('user')
                .then((stored) => stored && setUser(JSON.parse(stored)))
                .catch(() => {});
        } else {
            AsyncStorage.setItem('user', JSON.stringify(route.params.user)).catch(() => {});
        }

        SyncService.start();
        const removeSync = SyncService.addListener(() => setSync(SyncService.getStatus()));
        HeartbeatService.start();
        InactivityService.start(() => {
            Alert.alert('Sessão encerrada', 'Você saiu por inatividade (6 minutos sem uso).', [
                {
                    text: 'OK',
                    onPress: () => {
                        HeartbeatService.stop();
                        InactivityService.stop();
                        SyncService.stop();
                        ApiService.logout().catch(() => {});
                        navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
                    },
                },
            ], { cancelable: false });
        });
        const appStateSub = AppState.addEventListener('change', (state) => setAppActive(state === 'active'));

        return () => {
            removeSync();
            appStateSub.remove();
            HeartbeatService.stop();
            InactivityService.stop();
            SyncService.stop();
        };
    }, [navigation, route.params?.user]);

    useEffect(() => {
        if (permission && !permission.granted && permission.canAskAgain) requestPermission();
    }, [permission, requestPermission]);

    // O rótulo "atualizada agora / há N min" anda sozinho.
    useEffect(() => {
        const timer = setInterval(() => setSync(SyncService.getStatus()), 20000);
        return () => clearInterval(timer);
    }, []);

    // ---------- avisos ----------
    const loadInbox = useCallback(async () => {
        const result = await ApiService.getNotifyInbox(1, 3);
        if (!result?.success) return;
        const items = Array.isArray(result.items) ? result.items : [];
        const unread = Number(result.unread_count || 0);
        const latestUnread = items.find((entry) => entry.status === 'unread') || null;
        setInbox({ unread, latest: latestUnread });
        if (!latestUnread) return;
        // Alerta no celular só para aviso novo de verdade (o primeiro carregamento marca o ponto de partida).
        const lastAlerted = Number(await AsyncStorage.getItem(LAST_ALERTED_KEY).catch(() => null)) || 0;
        if (lastAlerted && latestUnread.id > lastAlerted) {
            Notifications.scheduleNotificationAsync({
                content: {
                    title: latestUnread.title || 'GALINT',
                    body: String(latestUnread.body || '').slice(0, 180),
                    data: { screen: 'Notifications' },
                },
                trigger: null,
            }).catch(() => {});
        }
        if (latestUnread.id > lastAlerted) AsyncStorage.setItem(LAST_ALERTED_KEY, String(latestUnread.id)).catch(() => {});
    }, []);

    useEffect(() => {
        if (!isFocused || !appActive) return undefined;
        loadInbox();
        const timer = setInterval(loadInbox, INBOX_POLL_MS);
        const unsubscribe = subscribeNotifyInboxChanged(() => loadInbox());
        return () => {
            clearInterval(timer);
            unsubscribe();
        };
    }, [appActive, isFocused, loadInbox]);

    const openNotifications = useCallback(() => {
        InactivityService.recordActivity();
        setMenuOpen(false);
        navigation.navigate('Notifications');
    }, [navigation]);

    // ---------- leitura e consulta ----------
    const lookup = useCallback(async (rawCode) => {
        const code = String(rawCode || '').trim();
        if (!code) return;
        InactivityService.recordActivity();
        Keyboard.dismiss();
        const requestId = ++lookupId.current;
        Vibration.vibrate(50);
        setArmed(false);
        armedUntil.current = 0;
        setNotice(null);
        setSearch('');
        setResults([]);

        const local = await getItemByCodigo(code).catch(() => null);
        const localItem = local ? { ...local, codigo: local.codigo_barras || local.id || code } : null;
        if (requestId !== lookupId.current) return;
        setPanel({ item: localItem || { codigo: code, descricao: 'Procurando...' }, loading: true, note: '' });

        const result = await ApiService.buscarItemContagem(code);
        if (requestId !== lookupId.current) return;
        if (result.success && result.item) {
            setPanel({ item: { ...localItem, ...result.item }, loading: false, note: '' });
            return;
        }
        if (result.authError) {
            Alert.alert('Sessão', result.message || 'Faça login novamente.');
        }
        if (result.notFound && !localItem) {
            setPanel(null);
            Vibration.vibrate([0, 80, 80, 80]);
            if (canLaunchEntry && isRegistrableCode(code)) {
                setMissing(code);
                return;
            }
            setNotice({ tone: 'error', text: `Código ${code} não encontrado no GALINT.` });
            return;
        }
        if (localItem) {
            // Sem resposta do servidor: mostra o que a base do celular tem, só para consulta.
            setPanel({
                item: { ...localItem, pode_ajustar: false },
                loading: false,
                note: result.notFound ? 'O servidor não achou este código.' : (result.message || 'Sem conexão: só consulta agora.'),
            });
            return;
        }
        setPanel(null);
        setNotice({ tone: 'error', text: result.message || 'Não foi possível buscar o item.' });
    }, [canLaunchEntry]);

    // Voltou de outra tela (ex.: lançar entrada) com um item aberto: o saldo dele se atualiza sozinho.
    // Voltou do cadastro de um código novo: o item cadastrado abre (se a pessoa desistiu, nada abre).
    const wasFocused = useRef(isFocused);
    useEffect(() => {
        const codigo = panel?.item?.codigo;
        if (isFocused && !wasFocused.current && registering.current) {
            const novoCodigo = registering.current;
            registering.current = '';
            ApiService.buscarItemContagem(novoCodigo).then((result) => {
                if (!result?.success || !result.item) return;
                setPanel((current) => current || { item: result.item, loading: false, note: '' });
            });
        } else if (isFocused && !wasFocused.current && codigo && !panel?.loading) {
            ApiService.buscarItemContagem(codigo).then((result) => {
                if (!result?.success || !result.item) return;
                setPanel((current) => (current && current.item?.codigo === codigo
                    ? { ...current, item: { ...current.item, ...result.item } }
                    : current));
            });
        }
        wasFocused.current = isFocused;
    }, [isFocused, panel?.item?.codigo, panel?.loading]);

    const onBarcode = useCallback(({ data }) => {
        const code = String(data || '').trim();
        if (!code) return;
        lastSeen.current = { code, at: Date.now() };
        if (armedUntil.current && armedUntil.current >= Date.now()) {
            armedUntil.current = 0;
            lookup(code);
        }
    }, [lookup]);

    // Só lê quando a pessoa toca no círculo.
    const capture = useCallback(() => {
        InactivityService.recordActivity();
        Keyboard.dismiss();
        if (!permission?.granted) {
            requestPermission();
            return;
        }
        const seen = lastSeen.current;
        if (seen.code && Date.now() - seen.at <= CAPTURE_WINDOW_MS) {
            lookup(seen.code);
            return;
        }
        armedUntil.current = Date.now() + ARMED_MS;
        setArmed(true);
        setNotice(null);
        setTimeout(() => {
            if (armedUntil.current && armedUntil.current <= Date.now()) {
                armedUntil.current = 0;
                setArmed(false);
                setNotice({ tone: 'error', text: 'Nenhum código lido. Aproxime o código do círculo e toque de novo.' });
            }
        }, ARMED_MS + 100);
    }, [lookup, permission?.granted, requestPermission]);

    const closePanel = useCallback(() => {
        Keyboard.dismiss();
        lookupId.current += 1;
        setPanel(null);
        lastSeen.current = { code: '', at: 0 };
    }, []);

    const onSaved = useCallback((item, result) => {
        setCounted((total) => total + 1);
        const before = item?.saldo_display || '';
        const after = result?.saldo_display || '';
        setNotice({
            tone: 'success',
            text: result?.changed ? `${item?.descricao}: ${before} → ${after}` : `${item?.descricao}: já estava certo (${after || before}).`,
        });
        closePanel();
    }, [closePanel]);

    useEffect(() => {
        const term = search.trim();
        if (!term) {
            setResults([]);
            return undefined;
        }
        const timer = setTimeout(() => {
            searchItems(term, 40).then(setResults).catch(() => setResults([]));
        }, 180);
        return () => clearTimeout(timer);
    }, [search]);

    // ---------- menu e cabeçalho ----------
    const go = useCallback((screen, params = {}) => {
        InactivityService.recordActivity();
        setMenuOpen(false);
        navigation.navigate(screen, { user, ...params });
    }, [navigation, user]);

    const logout = useCallback(() => {
        setMenuOpen(false);
        Alert.alert('Sair', 'Sair do GALINT neste celular?', [
            { text: 'Cancelar', style: 'cancel' },
            {
                text: 'Sair',
                style: 'destructive',
                onPress: () => {
                    HeartbeatService.stop();
                    InactivityService.stop();
                    SyncService.stop();
                    ApiService.logout().catch(() => {});
                    navigation.reset({ index: 0, routes: [{ name: 'Login', params: { fromLogout: true } }] });
                },
            },
        ]);
    }, [navigation]);

    const refreshBase = useCallback(async () => {
        setMenuOpen(false);
        setNotice({ tone: 'info', text: 'Atualizando a base do celular...' });
        await SyncService.syncNow({ full: true });
        const status = SyncService.getStatus();
        setSync(status);
        setNotice(status.online && !status.lastError
            ? { tone: 'success', text: `Base atualizada: ${status.count} itens.` }
            : { tone: 'error', text: status.lastError || 'Sem conexão com o servidor.' });
    }, []);

    useLayoutEffect(() => {
        navigation.setOptions({
            title: 'GALINT',
            headerLeft: () => (
                <TouchableOpacity onPress={() => { InactivityService.recordActivity(); setMenuOpen(true); }} style={styles.headerButton} accessibilityLabel="Abrir menu">
                    <Text style={styles.headerHamburger}>☰</Text>
                </TouchableOpacity>
            ),
            headerRight: () => (
                <TouchableOpacity onPress={openNotifications} style={[styles.headerButton, inbox.unread > 0 && styles.headerBellOn]} accessibilityLabel={`Avisos${inbox.unread ? `, ${inbox.unread} novos` : ''}`}>
                    <Text style={styles.headerBell}>🔔</Text>
                    {inbox.unread > 0 ? (
                        <View style={styles.headerBadge}>
                            <Text style={styles.headerBadgeText}>{inbox.unread > 99 ? '99+' : inbox.unread}</Text>
                        </View>
                    ) : null}
                </TouchableOpacity>
            ),
        });
    }, [inbox.unread, navigation, openNotifications]);

    const menuEntry = (icon, label, onPress, hint = null, badge = 0) => (
        <TouchableOpacity key={label} style={styles.menuEntry} onPress={onPress} activeOpacity={0.8}>
            <Text style={styles.menuEntryIcon}>{icon}</Text>
            <View style={{ flex: 1 }}>
                <Text style={styles.menuEntryLabel}>{label}</Text>
                {hint ? <Text style={styles.menuEntryHint}>{hint}</Text> : null}
            </View>
            {badge > 0 ? (
                <View style={styles.menuBadge}>
                    <Text style={styles.menuBadgeText}>{badge > 99 ? '99+' : badge}</Text>
                </View>
            ) : null}
        </TouchableOpacity>
    );

    const sideMenu = (
        <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={() => setMenuOpen(false)}>
            <View style={styles.menuBackdrop}>
                <View style={[styles.menuPanel, { paddingTop: insets.top + 16 }]}>
                    <View style={styles.menuHeader}>
                        <Text style={styles.menuTitle}>GALINT</Text>
                        <Text style={styles.menuUser}>{user?.nome || user?.username || 'Usuário'}</Text>
                        <Text style={styles.menuMeta}>{roleLabel(role)} • {syncLabel(sync)}</Text>
                    </View>
                    <ScrollView contentContainerStyle={[styles.menuList, { paddingBottom: insets.bottom + 24 }]}>
                        {menuEntry('📷', 'Conferência', () => setMenuOpen(false), 'Ler código, consultar e contar')}
                        {role !== 'gerencia' ? menuEntry('🔄', 'Movimento de material', () => go('Movimento'), 'Materiais, ferramentas, fracionados e devoluções') : null}
                        {menuEntry('🔔', 'Avisos', openNotifications, 'Saídas, devoluções e alertas do estoque', inbox.unread)}
                        {ENTRADAS_FISCAIS_NO_APP ? menuEntry('🧾', 'Entradas fiscais', () => go('DocumentosFiscais'), 'NF, cupom, recibo') : null}
                        {canLaunchEntry ? menuEntry('📊', 'Relatórios', () => go('Reports'), 'Dia, mês e consumo em PDF ou Excel') : null}
                        {menuEntry('🗂️', 'Painel e configurações', () => go('Menu'))}
                        {menuEntry('⟳', 'Atualizar a base agora', refreshBase, syncLabel(sync))}
                        {menuEntry('🚪', 'Sair', logout)}
                    </ScrollView>
                </View>
                <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={() => setMenuOpen(false)} accessibilityLabel="Fechar menu" />
            </View>
        </Modal>
    );

    // ---------- tela ----------
    const noticeView = notice ? (
        <View style={[styles.notice, notice.tone === 'success' ? styles.noticeSuccess : notice.tone === 'info' ? styles.noticeInfo : styles.noticeError]}>
            <Text style={styles.noticeText}>{notice.tone === 'success' ? '✔ ' : notice.tone === 'info' ? '' : '⚠ '}{notice.text}</Text>
        </View>
    ) : null;

    const inboxBanner = inbox.unread > 0 ? (
        <TouchableOpacity style={styles.inbox} onPress={openNotifications} activeOpacity={0.85}>
            <Text style={styles.inboxIcon}>🔔</Text>
            <View style={{ flex: 1 }}>
                <Text style={styles.inboxTitle}>{inbox.unread === 1 ? '1 aviso novo' : `${inbox.unread > 999 ? '999+' : inbox.unread} avisos novos`}</Text>
                {inbox.latest?.title ? <Text style={styles.inboxText} numberOfLines={1}>{inbox.latest.title}</Text> : null}
            </View>
            <Text style={styles.inboxArrow}>›</Text>
        </TouchableOpacity>
    ) : null;

    const circle = (
        <View style={styles.circleWrap}>
            <View style={styles.circle}>
                {cameraActive ? (
                    <CameraView
                        style={StyleSheet.absoluteFill}
                        facing="back"
                        enableTorch={torch}
                        autoFocus="on"
                        barcodeScannerSettings={{ barcodeTypes: BARCODE_TYPES }}
                        onBarcodeScanned={onBarcode}
                    />
                ) : (
                    <View style={styles.cameraOff}>
                        <Text style={styles.cameraOffIcon}>📷</Text>
                        <Text style={styles.cameraOffText}>{permission?.granted ? 'Câmera em pausa' : 'Toque para permitir a câmera'}</Text>
                    </View>
                )}
            </View>
            <View pointerEvents="none" style={styles.circleMask} />
            <View pointerEvents="none" style={[styles.circleRing, armed && styles.circleRingArmed]} />
            <TouchableOpacity style={styles.circleTouch} onPress={capture} activeOpacity={0.7} accessibilityLabel="Ler código de barras">
                <View style={styles.reticle}>
                    <View style={[styles.reticleLine, armed && styles.reticleLineArmed]} />
                </View>
                <View style={styles.circleLabel}>
                    {armed ? <ActivityIndicator color="#fff" size="small" /> : null}
                    <Text style={styles.circleLabelText}>{armed ? 'Procurando o código...' : 'TOQUE PARA LER'}</Text>
                </View>
            </TouchableOpacity>
        </View>
    );

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={styles.topRow}>
                <Text style={styles.greeting} numberOfLines={1}>{firstName ? `Olá, ${firstName}` : 'Olá'}</Text>
                <View style={[styles.syncChip, !sync.online && styles.syncChipOff]}>
                    <View style={[styles.syncDot, { backgroundColor: sync.online ? heroPalette.success : heroPalette.danger }]} />
                    <Text style={styles.syncText} numberOfLines={1}>{syncLabel(sync)}</Text>
                </View>
            </View>
            {inboxBanner}
            {noticeView}

            {panel ? (
                <ScrollView contentContainerStyle={styles.panelScroll} keyboardShouldPersistTaps="handled">
                    <StockCountPanel
                        item={panel.item}
                        detailsLoading={panel.loading}
                        note={panel.note}
                        onSaved={onSaved}
                        onClose={closePanel}
                        onMenu={canLaunchEntry && !panel.loading && panel.item?.descricao ? () => setItemMenu(true) : undefined}
                        onAddPhoto={canLaunchEntry && !panel.loading && panel.item?.descricao ? () => setPhotoModal(true) : undefined}
                    />
                </ScrollView>
            ) : search.trim() ? (
                <FlatList
                    style={styles.results}
                    data={results}
                    keyExtractor={(entry, index) => String(entry.codigo_barras || entry.id || index)}
                    keyboardShouldPersistTaps="handled"
                    ListEmptyComponent={<Text style={styles.emptyText}>{sync.count ? 'Nenhum item com esse nome ou código.' : 'A base do celular ainda está vazia.'}</Text>}
                    renderItem={({ item: entry }) => (
                        <TouchableOpacity style={styles.result} onPress={() => lookup(entry.codigo_barras || entry.id)} activeOpacity={0.8}>
                            <View style={{ flex: 1 }}>
                                <Text style={styles.resultName} numberOfLines={2}>{entry.descricao}</Text>
                                <Text style={styles.resultMeta} numberOfLines={1}>{entry.codigo_barras || entry.id}{entry.categoria ? ` • ${entry.categoria}` : ''}</Text>
                            </View>
                            <Text style={styles.resultBalance}>{entry.saldo_display || ''}</Text>
                        </TouchableOpacity>
                    )}
                />
            ) : (
                <View style={styles.center}>
                    {circle}
                    <View style={styles.tools}>
                        <TouchableOpacity style={[styles.toolChip, torch && styles.toolChipOn]} onPress={() => setTorch((value) => !value)} activeOpacity={0.85}>
                            <Text style={styles.toolText}>{torch ? '🔦 Lanterna ligada' : '💡 Lanterna'}</Text>
                        </TouchableOpacity>
                        {counted > 0 ? <Text style={styles.counter}>{counted === 1 ? '1 item contado' : `${counted} itens contados`}</Text> : null}
                    </View>
                </View>
            )}

            {!panel ? (
                <View style={styles.searchBox}>
                    <Text style={styles.searchIcon}>🔍</Text>
                    <TextInput
                        style={styles.searchInput}
                        value={search}
                        onChangeText={(text) => { InactivityService.recordActivity(); setSearch(text); }}
                        placeholder="Buscar pelo nome ou digitar o código"
                        placeholderTextColor={heroPalette.textMuted}
                        autoCorrect={false}
                        returnKeyType="search"
                        onSubmitEditing={() => {
                            // Código digitado inteiro: abre direto.
                            if (results.length === 1) lookup(results[0].codigo_barras || results[0].id);
                            else if (search.trim() && !results.length) lookup(search.trim());
                        }}
                    />
                    {search ? (
                        <TouchableOpacity onPress={() => setSearch('')} hitSlop={10}>
                            <Text style={styles.searchClear}>✕</Text>
                        </TouchableOpacity>
                    ) : null}
                </View>
            ) : null}
            {sideMenu}
            <ItemPhotoLinkModal
                item={panel?.item}
                visible={photoModal}
                onClose={() => setPhotoModal(false)}
                onSaved={(fotoUrl) => {
                    setPhotoModal(false);
                    setPanel((current) => (current ? { ...current, item: { ...current.item, foto_url: fotoUrl } } : current));
                }}
            />
            <Modal visible={itemMenu} transparent animationType="fade" onRequestClose={() => setItemMenu(false)}>
                <TouchableOpacity style={styles.itemMenuBackdrop} activeOpacity={1} onPress={() => setItemMenu(false)}>
                    <View style={[styles.itemMenuCard, { marginBottom: insets.bottom + 16 }]}>
                        <Text style={styles.itemMenuTitle} numberOfLines={1}>{panel?.item?.descricao}</Text>
                        <TouchableOpacity
                            style={styles.itemMenuEntry}
                            onPress={() => {
                                setItemMenu(false);
                                go('EntradaNF', { item: panel?.item });
                            }}
                            activeOpacity={0.85}
                        >
                            <Text style={styles.itemMenuIcon}>📥</Text>
                            <Text style={styles.itemMenuLabel}>Lançar entrada com NF</Text>
                        </TouchableOpacity>
                    </View>
                </TouchableOpacity>
            </Modal>
            <Modal visible={Boolean(missing)} transparent animationType="fade" onRequestClose={() => setMissing(null)}>
                <TouchableOpacity style={styles.itemMenuBackdrop} activeOpacity={1} onPress={() => setMissing(null)}>
                    <View style={[styles.itemMenuCard, styles.missingCard, { marginBottom: insets.bottom + 16 }]} onStartShouldSetResponder={() => true}>
                        <Text style={styles.missingTitle}>Código não encontrado</Text>
                        <Text style={styles.missingCode} selectable>{missing}</Text>
                        <Text style={styles.missingQuestion}>Deseja cadastrar?</Text>
                        <View style={styles.missingRow}>
                            <TouchableOpacity style={styles.missingNo} onPress={() => setMissing(null)} activeOpacity={0.85}>
                                <Text style={styles.missingNoText}>Não</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.missingYes}
                                onPress={() => {
                                    const code = missing;
                                    setMissing(null);
                                    registering.current = code;
                                    go('EntradaNF', { codigoNovo: code });
                                }}
                                activeOpacity={0.85}
                            >
                                <Text style={styles.missingYesText}>Cadastrar</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </TouchableOpacity>
            </Modal>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    headerButton: { paddingHorizontal: 12, paddingVertical: 6, justifyContent: 'center', alignItems: 'center', borderRadius: 18 },
    headerHamburger: { color: heroPalette.text, fontSize: 26, fontWeight: '700' },
    headerBellOn: { backgroundColor: 'rgba(251, 113, 133, 0.18)' },
    headerBell: { fontSize: 24 },
    headerBadge: { position: 'absolute', top: -2, right: 2, minWidth: 20, height: 20, borderRadius: 10, backgroundColor: heroPalette.danger, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 5 },
    headerBadgeText: { color: '#fff', fontSize: 11, fontWeight: '900' },
    topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 12, gap: 10 },
    greeting: { color: heroPalette.text, fontSize: 20, fontWeight: '800', flexShrink: 1 },
    syncChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, maxWidth: '62%' },
    syncChipOff: { borderColor: 'rgba(251, 113, 133, 0.5)' },
    syncDot: { width: 8, height: 8, borderRadius: 4 },
    syncText: { color: heroPalette.textMuted, fontSize: 11, fontWeight: '700' },
    inbox: { flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: 16, marginTop: 12, padding: 12, borderRadius: 16, backgroundColor: 'rgba(251, 113, 133, 0.14)', borderWidth: 1, borderColor: 'rgba(251, 113, 133, 0.45)' },
    inboxIcon: { fontSize: 24 },
    inboxTitle: { color: heroPalette.text, fontSize: 15, fontWeight: '900' },
    inboxText: { color: heroPalette.textSoft, fontSize: 13, marginTop: 2 },
    inboxArrow: { color: heroPalette.textSoft, fontSize: 24 },
    notice: { marginHorizontal: 16, marginTop: 10, borderRadius: 12, paddingVertical: 10, paddingHorizontal: 14 },
    noticeSuccess: { backgroundColor: 'rgba(34,197,94,0.92)' },
    noticeError: { backgroundColor: 'rgba(225,29,72,0.92)' },
    noticeInfo: { backgroundColor: heroPalette.panelAlt },
    noticeText: { color: '#fff', fontSize: 14, fontWeight: '700' },
    center: { flex: 1, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
    circleWrap: { width: CIRCLE, height: CIRCLE, marginVertical: MASK * 0.35 },
    circle: { width: CIRCLE, height: CIRCLE, borderRadius: CIRCLE / 2, overflow: 'hidden', backgroundColor: '#000' },
    circleMask: {
        position: 'absolute',
        left: -MASK,
        top: -MASK,
        width: CIRCLE + MASK * 2,
        height: CIRCLE + MASK * 2,
        borderRadius: (CIRCLE + MASK * 2) / 2,
        borderWidth: MASK,
        borderColor: heroPalette.bg,
    },
    circleRing: { position: 'absolute', left: -3, top: -3, width: CIRCLE + 6, height: CIRCLE + 6, borderRadius: (CIRCLE + 6) / 2, borderWidth: 5, borderColor: heroPalette.primaryStrong },
    circleRingArmed: { borderColor: heroPalette.warning },
    circleTouch: { position: 'absolute', left: 0, top: 0, width: CIRCLE, height: CIRCLE, borderRadius: CIRCLE / 2, alignItems: 'center', justifyContent: 'center' },
    reticle: { width: CIRCLE * 0.62, height: CIRCLE * 0.3, borderRadius: 14, borderWidth: 2, borderColor: 'rgba(255,255,255,0.75)', alignItems: 'center', justifyContent: 'center' },
    reticleLine: { width: '86%', height: 2, backgroundColor: 'rgba(251, 113, 133, 0.9)' },
    reticleLineArmed: { backgroundColor: heroPalette.warning, height: 3 },
    circleLabel: { position: 'absolute', bottom: CIRCLE * 0.12, flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999, backgroundColor: 'rgba(6,16,27,0.7)' },
    circleLabelText: { color: '#fff', fontSize: 13, fontWeight: '900', letterSpacing: 1 },
    cameraOff: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panel },
    cameraOffIcon: { fontSize: 44 },
    cameraOffText: { color: heroPalette.textMuted, fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 30 },
    tools: { alignItems: 'center', gap: 8, marginTop: 4 },
    toolChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: heroPalette.border, backgroundColor: heroPalette.panel },
    toolChipOn: { borderColor: heroPalette.warning },
    toolText: { color: heroPalette.textSoft, fontSize: 13, fontWeight: '700' },
    counter: { color: heroPalette.primary, fontSize: 13, fontWeight: '800' },
    panelScroll: { padding: 16, paddingBottom: 40 },
    results: { flex: 1, marginTop: 10 },
    result: { flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: 16, marginBottom: 8, padding: 14, borderRadius: 14, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border },
    resultName: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    resultMeta: { color: heroPalette.textMuted, fontSize: 12, marginTop: 2 },
    resultBalance: { color: heroPalette.primary, fontSize: 13, fontWeight: '800', maxWidth: '35%', textAlign: 'right' },
    emptyText: { color: heroPalette.textMuted, textAlign: 'center', marginTop: 30 },
    searchBox: { flexDirection: 'row', alignItems: 'center', gap: 8, margin: 16, marginTop: 8, paddingHorizontal: 14, height: 52, borderRadius: 16, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, ...heroSoftShadow },
    searchIcon: { fontSize: 16 },
    searchInput: { flex: 1, color: heroPalette.text, fontSize: 15 },
    searchClear: { color: heroPalette.textMuted, fontSize: 18, paddingHorizontal: 4 },
    itemMenuBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(2, 6, 23, 0.6)', paddingHorizontal: 16 },
    itemMenuCard: { backgroundColor: heroPalette.panel, borderRadius: 20, padding: 8, borderWidth: 1, borderColor: heroPalette.border },
    itemMenuTitle: { color: heroPalette.textMuted, fontSize: 13, fontWeight: '700', paddingHorizontal: 14, paddingTop: 10, paddingBottom: 6 },
    itemMenuEntry: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 14, paddingVertical: 16, borderRadius: 14 },
    itemMenuIcon: { fontSize: 24 },
    itemMenuLabel: { color: heroPalette.text, fontSize: 17, fontWeight: '800' },
    missingCard: { padding: 18 },
    missingTitle: { color: heroPalette.text, fontSize: 19, fontWeight: '900', textAlign: 'center' },
    missingCode: { color: heroPalette.textSoft, fontSize: 16, fontWeight: '700', textAlign: 'center', marginTop: 6, letterSpacing: 0.5 },
    missingQuestion: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '700', textAlign: 'center', marginTop: 16 },
    missingRow: { flexDirection: 'row', gap: 10, marginTop: 14 },
    missingNo: { flex: 1, height: 52, borderRadius: 14, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    missingNoText: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    missingYes: { flex: 1, height: 52, borderRadius: 14, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    missingYesText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    menuBackdrop: { flex: 1, flexDirection: 'row', backgroundColor: 'rgba(2, 6, 23, 0.6)' },
    menuPanel: { width: '82%', maxWidth: 340, backgroundColor: heroPalette.bgAlt, borderRightWidth: 1, borderRightColor: heroPalette.border, paddingTop: 36 },
    menuHeader: { paddingHorizontal: 20, paddingBottom: 16, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    menuTitle: { color: heroPalette.primary, fontSize: 22, fontWeight: '900', letterSpacing: 4 },
    menuUser: { color: heroPalette.text, fontSize: 16, fontWeight: '700', marginTop: 6 },
    menuMeta: { color: heroPalette.textMuted, fontSize: 12, marginTop: 2 },
    menuList: { paddingVertical: 8, paddingBottom: 32 },
    menuEntry: { flexDirection: 'row', alignItems: 'center', paddingVertical: 13, paddingHorizontal: 20 },
    menuEntryIcon: { fontSize: 22, width: 36, color: heroPalette.text },
    menuEntryLabel: { color: heroPalette.text, fontSize: 16, fontWeight: '700' },
    menuEntryHint: { color: heroPalette.textMuted, fontSize: 12, marginTop: 1 },
    menuBadge: { minWidth: 24, height: 24, borderRadius: 12, backgroundColor: heroPalette.danger, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
    menuBadgeText: { color: '#fff', fontSize: 11, fontWeight: '900' },
});
