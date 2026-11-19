// Conferência física: lê o código de barras da planilha, mostra o item (foto, nome, saldo do
// sistema), recebe a quantidade contada e grava no servidor pelo motor auditado. Depois de
// salvar, volta direto para a câmera para o próximo item.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Dimensions,
    Image,
    Keyboard,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    Vibration,
    View,
} from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

const { width } = Dimensions.get('window');
const SCAN_BOX = Math.min(width * 0.82, 360);
// Planilha usa Code128; os produtos costumam ter EAN/UPC na embalagem.
const BARCODE_TYPES = ['code128', 'ean13', 'ean8', 'upc_a', 'upc_e', 'code39', 'code93', 'itf14', 'qr'];

function resolvePhotoUri(item) {
    const raw = String(item?.foto_url || '').trim();
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = ApiService.baseURL;
    if (!base) return null;
    return raw.startsWith('/') ? `${base}${raw}` : `${base}/static/${raw.replace(/^\/+/, '')}`;
}

function normalizeNumber(text) {
    return String(text || '').replace(',', '.').trim();
}

function isValidQuantity(text, allowDecimal) {
    const value = normalizeNumber(text);
    if (value === '') return false;
    const pattern = allowDecimal ? /^\d+(\.\d+)?$/ : /^\d+$/;
    return pattern.test(value);
}

export default function ContagemFisicaScreen({ navigation }) {
    const [permission, requestPermission] = useCameraPermissions();
    const isFocused = useIsFocused();
    const [phase, setPhase] = useState('scan'); // scan | loading | count | saving
    const [item, setItem] = useState(null);
    const [quantity, setQuantity] = useState('');
    const [packages, setPackages] = useState('');
    const [loose, setLoose] = useState('');
    const [flash, setFlash] = useState(false);
    const [manualOpen, setManualOpen] = useState(false);
    const [manualCode, setManualCode] = useState('');
    const [notice, setNotice] = useState(null); // { tone: 'success' | 'error', text }
    const [countedTotal, setCountedTotal] = useState(0);
    const [photoFailed, setPhotoFailed] = useState(false);
    const lastScanRef = useRef({ code: '', at: 0 });

    useEffect(() => {
        if (permission && !permission.granted && permission.canAskAgain) {
            requestPermission();
        }
    }, [permission, requestPermission]);

    const backToScan = useCallback(() => {
        Keyboard.dismiss();
        setItem(null);
        setQuantity('');
        setPackages('');
        setLoose('');
        setPhotoFailed(false);
        setPhase('scan');
    }, []);

    const lookup = useCallback(async (rawCode) => {
        const code = String(rawCode || '').trim();
        if (!code) return;
        InactivityService.recordActivity();
        setPhase('loading');
        setNotice(null);
        const result = await ApiService.buscarItemContagem(code);
        if (!result.success || !result.item) {
            Vibration.vibrate([0, 80, 80, 80]);
            setNotice({
                tone: 'error',
                text: result.notFound ? `Código ${code} não encontrado no GALINT.` : (result.message || 'Falha ao buscar o item.'),
            });
            setPhase('scan');
            if (result.authError) {
                Alert.alert('Sessão expirada', result.message || 'Faça login novamente.');
            }
            return;
        }
        Vibration.vibrate(60);
        setItem(result.item);
        setPhotoFailed(false);
        setPhase('count');
    }, []);

    const handleScanned = useCallback(({ data }) => {
        if (phase !== 'scan') return;
        const code = String(data || '').trim();
        const now = Date.now();
        // A mesma etiqueta continua na frente da câmera logo depois de salvar: espera 2,5 s.
        if (!code || (code === lastScanRef.current.code && now - lastScanRef.current.at < 2500)) return;
        lastScanRef.current = { code, at: now };
        lookup(code);
    }, [lookup, phase]);

    const input = item?.input || {};
    const packaged = Boolean(input.supports_packaging);
    const allowDecimal = Boolean(input.internal_allow_decimal);
    const unit = input.internal_unit_display || item?.unidade || 'un';
    const pending = Boolean(item?.pre_cadastro_pendente);
    const canSave = !pending && (packaged
        ? isValidQuantity(packages, false) && isValidQuantity(loose || '0', allowDecimal)
        : isValidQuantity(quantity, allowDecimal));

    const save = useCallback(async () => {
        if (!item || !canSave) return;
        InactivityService.recordActivity();
        Keyboard.dismiss();
        setPhase('saving');
        const payload = packaged
            ? { codigo: item.codigo, mode: 'packages_plus_internal', package_quantity: normalizeNumber(packages), internal_quantity: normalizeNumber(loose || '0') }
            : { codigo: item.codigo, mode: 'direct', quantity: normalizeNumber(quantity) };
        const result = await ApiService.salvarContagem(payload);
        if (!result.success) {
            setPhase('count');
            Alert.alert('Contagem não salva', result.message || 'Tente de novo.');
            return;
        }
        Vibration.vibrate(120);
        setCountedTotal((total) => total + 1);
        const before = item.saldo_display || '';
        const after = result.saldo_display || '';
        setNotice({
            tone: 'success',
            text: result.changed
                ? `${item.descricao}: ${before} → ${after}`
                : `${item.descricao}: já estava certo (${after || before}).`,
        });
        lastScanRef.current = { code: lastScanRef.current.code, at: Date.now() };
        backToScan();
    }, [backToScan, canSave, item, loose, packaged, packages, quantity]);

    if (!permission) {
        return <View style={styles.container} />;
    }

    if (!permission.granted) {
        return (
            <View style={[styles.container, styles.center]}>
                <Text style={styles.bigIcon}>📷</Text>
                <Text style={styles.title}>Permita a câmera</Text>
                <Text style={styles.muted}>A conferência lê o código de barras da planilha pela câmera.</Text>
                <TouchableOpacity style={styles.primaryButton} onPress={requestPermission}>
                    <Text style={styles.primaryButtonText}>Permitir câmera</Text>
                </TouchableOpacity>
            </View>
        );
    }

    const noticeView = notice ? (
        <View style={[styles.notice, notice.tone === 'success' ? styles.noticeSuccess : styles.noticeError]}>
            <Text style={styles.noticeText}>{notice.tone === 'success' ? '✔ ' : '⚠ '}{notice.text}</Text>
        </View>
    ) : null;

    if (phase === 'count' || phase === 'saving') {
        const photoUri = photoFailed ? null : resolvePhotoUri(item);
        return (
            <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                <ScrollView contentContainerStyle={styles.countContent} keyboardShouldPersistTaps="handled">
                    <View style={styles.itemCard}>
                        <View style={styles.photoBox}>
                            {photoUri ? (
                                <Image source={{ uri: photoUri }} style={styles.photo} resizeMode="contain" onError={() => setPhotoFailed(true)} />
                            ) : (
                                <View style={styles.photoEmpty}>
                                    <Text style={styles.photoEmptyIcon}>🖼️</Text>
                                    <Text style={styles.photoEmptyText}>Sem foto</Text>
                                </View>
                            )}
                        </View>
                        <Text style={styles.itemName}>{item.descricao}</Text>
                        <Text style={styles.itemCode}>Código: {item.codigo}</Text>
                        {item.categoria ? <Text style={styles.itemMeta}>{item.categoria}{item.localizacao ? ` • ${item.localizacao}` : ''}</Text> : null}
                        <View style={styles.balanceBox}>
                            <Text style={styles.balanceLabel}>NO SISTEMA</Text>
                            <Text style={styles.balanceValue}>{item.saldo_display}</Text>
                        </View>
                    </View>

                    {pending ? (
                        <View style={[styles.notice, styles.noticeWarning]}>
                            <Text style={styles.noticeTextDark}>Este item ainda está pendente de cadastro e não pode ter o estoque ajustado. Termine o cadastro no GALINT.</Text>
                        </View>
                    ) : packaged ? (
                        <View style={styles.formCard}>
                            {input.package_content_display ? <Text style={styles.muted}>{input.package_content_display}</Text> : null}
                            <Text style={styles.label}>{`${input.package_plural || 'Embalagens'} fechadas`}</Text>
                            <TextInput
                                style={styles.input}
                                value={packages}
                                onChangeText={setPackages}
                                keyboardType="number-pad"
                                placeholder="0"
                                placeholderTextColor={heroPalette.textMuted}
                                autoFocus
                            />
                            <Text style={styles.label}>{`Quantidade solta (${unit})`}</Text>
                            <TextInput
                                style={styles.input}
                                value={loose}
                                onChangeText={setLoose}
                                keyboardType={allowDecimal ? 'decimal-pad' : 'number-pad'}
                                placeholder="0"
                                placeholderTextColor={heroPalette.textMuted}
                                returnKeyType="done"
                                onSubmitEditing={save}
                            />
                        </View>
                    ) : (
                        <View style={styles.formCard}>
                            <Text style={styles.label}>{`Quantidade física (${unit})`}</Text>
                            <TextInput
                                style={[styles.input, styles.inputBig]}
                                value={quantity}
                                onChangeText={setQuantity}
                                keyboardType={allowDecimal ? 'decimal-pad' : 'number-pad'}
                                placeholder="0"
                                placeholderTextColor={heroPalette.textMuted}
                                autoFocus
                                returnKeyType="done"
                                onSubmitEditing={save}
                            />
                        </View>
                    )}

                    <TouchableOpacity
                        style={[styles.primaryButton, (!canSave || phase === 'saving') && styles.buttonDisabled]}
                        onPress={save}
                        disabled={!canSave || phase === 'saving'}
                        activeOpacity={0.85}
                    >
                        {phase === 'saving' ? (
                            <ActivityIndicator color={heroPalette.bg} />
                        ) : (
                            <Text style={styles.primaryButtonText}>Salvar contagem</Text>
                        )}
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.secondaryButton} onPress={backToScan} disabled={phase === 'saving'}>
                        <Text style={styles.secondaryButtonText}>Cancelar e ler outro código</Text>
                    </TouchableOpacity>
                </ScrollView>
            </KeyboardAvoidingView>
        );
    }

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <CameraView
                style={StyleSheet.absoluteFill}
                facing="back"
                enableTorch={flash}
                autoFocus="on"
                barcodeScannerSettings={{ barcodeTypes: BARCODE_TYPES }}
                onBarcodeScanned={phase === 'scan' && isFocused && !manualOpen ? handleScanned : undefined}
            />
            <View style={styles.scanOverlay} pointerEvents="box-none">
                <View style={styles.scanTop}>
                    {noticeView}
                    <Text style={styles.scanHint}>Aponte para o código de barras da planilha</Text>
                    {countedTotal > 0 ? <Text style={styles.scanCounter}>{countedTotal} {countedTotal === 1 ? 'item contado' : 'itens contados'} agora</Text> : null}
                </View>
                <View style={[styles.scanBox, { width: SCAN_BOX, height: SCAN_BOX * 0.55 }]}>
                    {phase === 'loading' ? <ActivityIndicator size="large" color={heroPalette.primary} /> : <View style={styles.scanLine} />}
                </View>
                <View style={styles.scanBottom}>
                    {manualOpen ? (
                        <View style={styles.manualRow}>
                            <TextInput
                                style={styles.manualInput}
                                value={manualCode}
                                onChangeText={setManualCode}
                                placeholder="Digite o código"
                                placeholderTextColor="#64748b"
                                autoCapitalize="characters"
                                autoFocus
                                returnKeyType="search"
                                onSubmitEditing={() => {
                                    const code = manualCode.trim();
                                    setManualCode('');
                                    setManualOpen(false);
                                    lookup(code);
                                }}
                            />
                            <TouchableOpacity
                                style={styles.manualButton}
                                onPress={() => {
                                    const code = manualCode.trim();
                                    setManualCode('');
                                    setManualOpen(false);
                                    lookup(code);
                                }}
                            >
                                <Text style={styles.manualButtonText}>OK</Text>
                            </TouchableOpacity>
                        </View>
                    ) : null}
                    <View style={styles.controls}>
                        <TouchableOpacity style={styles.control} onPress={() => setFlash((value) => !value)}>
                            <Text style={styles.controlIcon}>{flash ? '🔦' : '💡'}</Text>
                            <Text style={styles.controlText}>Lanterna</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.control} onPress={() => setManualOpen((value) => !value)}>
                            <Text style={styles.controlIcon}>⌨️</Text>
                            <Text style={styles.controlText}>Digitar</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.control} onPress={() => navigation.goBack()}>
                            <Text style={styles.controlIcon}>✖️</Text>
                            <Text style={styles.controlText}>Fechar</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    center: { alignItems: 'center', justifyContent: 'center', padding: 24 },
    bigIcon: { fontSize: 64, marginBottom: 12 },
    title: { color: heroPalette.text, fontSize: 22, fontWeight: '800', marginBottom: 8 },
    muted: { color: heroPalette.textMuted, fontSize: 14, marginBottom: 10, textAlign: 'center' },
    scanOverlay: { ...StyleSheet.absoluteFillObject, justifyContent: 'space-between', alignItems: 'center' },
    scanTop: { width: '100%', paddingTop: 24, paddingHorizontal: 16, alignItems: 'center', backgroundColor: 'rgba(6,16,27,0.72)', paddingBottom: 14 },
    scanHint: { color: '#fff', fontSize: 17, fontWeight: '700', textAlign: 'center' },
    scanCounter: { color: heroPalette.primary, fontSize: 14, fontWeight: '700', marginTop: 6 },
    scanBox: { borderWidth: 3, borderColor: heroPalette.primaryStrong, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
    scanLine: { width: '90%', height: 2, backgroundColor: heroPalette.danger },
    scanBottom: { width: '100%', paddingBottom: 28, paddingHorizontal: 16, backgroundColor: 'rgba(6,16,27,0.72)', paddingTop: 12 },
    controls: { flexDirection: 'row', justifyContent: 'space-around' },
    control: { alignItems: 'center', padding: 10, minWidth: 84 },
    controlIcon: { fontSize: 26 },
    controlText: { color: '#fff', fontSize: 12, fontWeight: '700', marginTop: 4 },
    manualRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
    manualInput: { flex: 1, backgroundColor: '#fff', color: '#0f172a', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 17, fontWeight: '700' },
    manualButton: { backgroundColor: heroPalette.primaryStrong, borderRadius: 10, paddingHorizontal: 20, justifyContent: 'center' },
    manualButtonText: { color: heroPalette.bg, fontWeight: '800', fontSize: 16 },
    notice: { borderRadius: 12, paddingVertical: 10, paddingHorizontal: 14, marginBottom: 10, width: '100%' },
    noticeSuccess: { backgroundColor: 'rgba(34,197,94,0.92)' },
    noticeError: { backgroundColor: 'rgba(225,29,72,0.92)' },
    noticeWarning: { backgroundColor: '#fef3c7', marginTop: 4 },
    noticeText: { color: '#fff', fontSize: 15, fontWeight: '700' },
    noticeTextDark: { color: '#78350f', fontSize: 15, fontWeight: '600' },
    countContent: { padding: 16, paddingBottom: 40 },
    itemCard: { backgroundColor: heroPalette.panel, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', ...heroSoftShadow },
    photoBox: { width: 168, height: 168, borderRadius: 16, backgroundColor: '#fff', overflow: 'hidden', marginBottom: 14, alignItems: 'center', justifyContent: 'center' },
    photo: { width: '100%', height: '100%' },
    photoEmpty: { flex: 1, width: '100%', alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    photoEmptyIcon: { fontSize: 40 },
    photoEmptyText: { color: heroPalette.textMuted, marginTop: 4 },
    itemName: { color: heroPalette.text, fontSize: 20, fontWeight: '800', textAlign: 'center' },
    itemCode: { color: heroPalette.textMuted, fontSize: 13, marginTop: 4 },
    itemMeta: { color: heroPalette.textSoft, fontSize: 13, marginTop: 2 },
    balanceBox: { marginTop: 14, paddingVertical: 8, paddingHorizontal: 18, borderRadius: 12, backgroundColor: 'rgba(96,165,250,0.14)', borderWidth: 1, borderColor: 'rgba(96,165,250,0.4)', alignItems: 'center' },
    balanceLabel: { color: heroPalette.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1 },
    balanceValue: { color: heroPalette.text, fontSize: 20, fontWeight: '800', marginTop: 2 },
    formCard: { marginTop: 16, backgroundColor: heroPalette.panel, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: heroPalette.border },
    label: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '700', marginBottom: 8, marginTop: 4 },
    input: { backgroundColor: '#fff', color: '#0f172a', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 12, fontSize: 20, fontWeight: '800', marginBottom: 10 },
    inputBig: { fontSize: 30, textAlign: 'center' },
    primaryButton: { marginTop: 18, backgroundColor: heroPalette.primaryStrong, borderRadius: 16, paddingVertical: 16, alignItems: 'center' },
    primaryButtonText: { color: heroPalette.bg, fontSize: 18, fontWeight: '800' },
    buttonDisabled: { opacity: 0.45 },
    secondaryButton: { marginTop: 12, paddingVertical: 14, alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: heroPalette.border },
    secondaryButtonText: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '700' },
});
