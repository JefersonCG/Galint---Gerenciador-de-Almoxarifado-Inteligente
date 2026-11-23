// Lançar entrada com NF de um item que já existe (2.2.3). Pedido do usuário em 21/11/2026: no ☰ do
// item lido na Conferência, um lançamento prático: quantidade, chave de acesso LIDA pela câmera (não
// há campo para digitar a chave nem o número da NF: o número, a série e o CNPJ saem da própria
// chave, como em Documentos Fiscais do site), datas e valor. Grava pela mesma rota da tela de
// Documentos Fiscais (/api/mobile/documentos-fiscais), com financeiro, estoque e aviso.
import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Image,
    KeyboardAvoidingView,
    Modal,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    Vibration,
    View,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { DateTimePickerAndroid } from '@react-native-community/datetimepicker';

import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import DoneModal from '../components/DoneModal';
import ItemPhotoLinkModal from '../components/ItemPhotoLinkModal';
import { resolvePhotoUri } from '../components/StockCountPanel';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

function isoDate(date) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function brDate(iso) {
    if (!iso) return '';
    const [year, month, day] = iso.split('-');
    return `${day}/${month}/${year}`;
}

function parseIso(iso) {
    if (!iso) return new Date();
    const [year, month, day] = iso.split('-').map(Number);
    return new Date(year, month - 1, day);
}

function groupKey(key) {
    return String(key || '').replace(/(\d{4})(?=\d)/g, '$1 ');
}

function normalizeDecimal(text) {
    return String(text || '').replace(/[^0-9.,]/g, '').replace(',', '.');
}

export default function EntradaNFScreen({ navigation, route }) {
    const [fotoNova, setFotoNova] = useState(null);
    const [photoModal, setPhotoModal] = useState(false);
    const baseItem = route.params?.item || {};
    const item = fotoNova ? { ...baseItem, foto_url: fotoNova } : baseItem;
    const codigo = String(item.codigo || item.codigo_barras || item.id || '').trim();
    const [permission, requestPermission] = useCameraPermissions();
    const [quantidade, setQuantidade] = useState('');
    const [valor, setValor] = useState('');
    const [emissao, setEmissao] = useState('');
    const [recebimento, setRecebimento] = useState(isoDate(new Date()));
    const [nota, setNota] = useState(null); // { chave, numero, serie, modelo, cnpj, fornecedor, fornecedorId }
    const [lendo, setLendo] = useState(false);
    const [consultando, setConsultando] = useState(false);
    const [erro, setErro] = useState('');
    const [salvando, setSalvando] = useState(false);
    const [done, setDone] = useState(null);
    const [photoFailed, setPhotoFailed] = useState(false);
    const lido = useRef(false);

    useLayoutEffect(() => {
        navigation.setOptions({ title: 'Lançar entrada' });
    }, [navigation]);

    const abrirLeitor = useCallback(async () => {
        InactivityService.recordActivity();
        setErro('');
        if (!permission?.granted) {
            const answer = await requestPermission();
            if (!answer?.granted) return;
        }
        lido.current = false;
        setLendo(true);
    }, [permission?.granted, requestPermission]);

    // Código de barras do DANFE (Code128, 44 dígitos) ou QR da NFC-e (a chave vem dentro do endereço).
    const aoLer = useCallback(async ({ data }) => {
        const match = String(data || '').replace(/\s+/g, '').match(/\d{44}/);
        if (!match || lido.current) return;
        lido.current = true;
        Vibration.vibrate(60);
        setLendo(false);
        setConsultando(true);
        const result = await ApiService.lerChaveAcesso(match[0]);
        setConsultando(false);
        if (!result.success) {
            setNota(null);
            setErro(result.message || 'Não foi possível ler a chave.');
            return;
        }
        const chave = result.chave || {};
        setNota({
            chave: chave.chave_acesso,
            numero: chave.numero_documento,
            serie: chave.serie,
            modelo: chave.modelo_label,
            cnpj: chave.cnpj_emitente,
            fornecedor: result.fornecedor?.nome || result.documento?.fornecedor_nome || null,
            fornecedorId: result.fornecedor?.id || null,
        });
        // Nota que já está no GALINT: as datas dela.
        if (result.documento?.data_emissao) setEmissao(String(result.documento.data_emissao).slice(0, 10));
        if (result.documento?.data_recebimento) setRecebimento(String(result.documento.data_recebimento).slice(0, 10));
    }, []);

    const escolherData = useCallback((atual, definir) => {
        InactivityService.recordActivity();
        DateTimePickerAndroid.open({
            value: parseIso(atual),
            mode: 'date',
            maximumDate: new Date(),
            onChange: (event, date) => {
                if (event?.type === 'set' && date) definir(isoDate(date));
            },
        });
    }, []);

    const quantidadeNum = Number(normalizeDecimal(quantidade));
    const faltando = useMemo(() => {
        if (!(quantidadeNum > 0)) return 'Falta a quantidade';
        if (!nota) return 'Falta ler a chave';
        if (!emissao) return 'Falta a data de emissão';
        if (!recebimento) return 'Falta a data de recebimento';
        return '';
    }, [emissao, nota, quantidadeNum, recebimento]);

    const lancar = useCallback(async () => {
        if (faltando || salvando) return;
        InactivityService.recordActivity();
        setSalvando(true);
        setErro('');
        const valorNum = Number(normalizeDecimal(valor));
        const result = await ApiService.registrarDocumentoFiscal({
            doc_mode: 'nf',
            finance_tipo_documento: 'nf',
            finance_origem_valor: 'compra_nf',
            finance_comprovacao_status: 'comprovado',
            codigo,
            quantidade: quantidadeNum,
            nota_fiscal: nota.numero,
            chave_acesso: nota.chave,
            supplier_cnpj: nota.cnpj,
            supplier_name: nota.fornecedor || undefined,
            finance_supplier_id: nota.fornecedorId || undefined,
            data_emissao: emissao,
            data_recebimento: recebimento,
            preco_unitario: valorNum > 0 ? valorNum : undefined,
        });
        setSalvando(false);
        if (!result?.success) {
            setErro(result?.message || 'Não foi possível lançar a entrada.');
            return;
        }
        const saldo = result.data?.item?.saldo_display || result.data?.item?.saldo;
        setDone({
            title: 'Entrada lançada',
            itemName: item.descricao || 'Item',
            summary: `NF ${nota.numero} • +${quantidade.replace('.', ',')}${saldo != null ? ` • saldo agora: ${saldo}` : ''}`,
            photoUri: resolvePhotoUri(item),
            newLabel: 'Outra nota',
            onNew: () => {
                setDone(null);
                setNota(null);
                setQuantidade('');
                setValor('');
                setEmissao('');
            },
            onFinish: () => {
                setDone(null);
                navigation.goBack();
            },
        });
    }, [codigo, emissao, faltando, item, navigation, nota, quantidade, quantidadeNum, recebimento, salvando, valor]);

    const photoUri = photoFailed ? null : resolvePhotoUri(item);

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
                <View style={styles.itemRow}>
                    {photoUri ? (
                        <Image source={{ uri: photoUri }} style={styles.photo} resizeMode="cover" onError={() => setPhotoFailed(true)} />
                    ) : (
                        <TouchableOpacity style={[styles.photo, styles.photoEmpty]} onPress={() => setPhotoModal(true)} activeOpacity={0.8} accessibilityLabel="Pôr foto no item">
                            <Text style={styles.photoEmptyText}>📷</Text>
                            <Text style={styles.photoAdd}>Pôr foto</Text>
                        </TouchableOpacity>
                    )}
                    <View style={{ flex: 1 }}>
                        <Text style={styles.itemName} numberOfLines={2}>{item.descricao || 'Item'}</Text>
                        <Text style={styles.itemMeta}>{codigo}</Text>
                        {item.saldo_display ? <Text style={styles.itemMeta}>Saldo: {item.saldo_display}</Text> : null}
                    </View>
                </View>

                <Text style={styles.label}>Chave de acesso</Text>
                {nota ? (
                    <TouchableOpacity style={styles.noteCard} onPress={abrirLeitor} activeOpacity={0.85}>
                        <Text style={styles.noteTitle}>NF {nota.numero} • série {nota.serie}</Text>
                        <Text style={styles.noteLine}>{nota.fornecedor ? `${nota.fornecedor} • ` : ''}{nota.cnpj}</Text>
                        <Text style={styles.noteKey}>{groupKey(nota.chave)}</Text>
                        <Text style={styles.noteAgain}>Ler outra chave</Text>
                    </TouchableOpacity>
                ) : (
                    <TouchableOpacity style={styles.scanButton} onPress={abrirLeitor} disabled={consultando} activeOpacity={0.85}>
                        {consultando ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.scanText}>📷  Ler a chave da nota</Text>}
                    </TouchableOpacity>
                )}

                <Text style={styles.label}>Quantidade{item.unidade ? ` (${String(item.unidade).toLowerCase()})` : ''}</Text>
                <TextInput
                    style={styles.input}
                    value={quantidade}
                    onChangeText={(text) => setQuantidade(text.replace(/[^0-9.,]/g, ''))}
                    keyboardType="decimal-pad"
                    placeholder="0"
                    placeholderTextColor={heroPalette.textMuted}
                />

                <View style={styles.dateRow}>
                    <View style={{ flex: 1 }}>
                        <Text style={styles.label}>Emissão</Text>
                        <TouchableOpacity style={styles.dateField} onPress={() => escolherData(emissao, setEmissao)} activeOpacity={0.85}>
                            <Text style={emissao ? styles.dateText : styles.datePlaceholder}>{emissao ? brDate(emissao) : 'dd/mm/aaaa'}</Text>
                        </TouchableOpacity>
                    </View>
                    <View style={{ flex: 1 }}>
                        <Text style={styles.label}>Recebimento</Text>
                        <TouchableOpacity style={styles.dateField} onPress={() => escolherData(recebimento, setRecebimento)} activeOpacity={0.85}>
                            <Text style={styles.dateText}>{brDate(recebimento)}</Text>
                        </TouchableOpacity>
                    </View>
                </View>

                <Text style={styles.label}>Valor unitário (R$)</Text>
                <TextInput
                    style={styles.input}
                    value={valor}
                    onChangeText={(text) => setValor(text.replace(/[^0-9.,]/g, ''))}
                    keyboardType="decimal-pad"
                    placeholder="0,00"
                    placeholderTextColor={heroPalette.textMuted}
                />

                {erro ? <Text style={styles.error}>⚠ {erro}</Text> : null}

                <TouchableOpacity style={[styles.button, (faltando || salvando) && styles.buttonOff]} onPress={lancar} disabled={Boolean(faltando) || salvando} activeOpacity={0.85}>
                    {salvando ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.buttonText}>{faltando || 'Lançar entrada'}</Text>}
                </TouchableOpacity>
            </ScrollView>

            <Modal visible={lendo} animationType="fade" onRequestClose={() => setLendo(false)}>
                <View style={styles.scanner}>
                    <CameraView
                        style={StyleSheet.absoluteFill}
                        facing="back"
                        autoFocus="on"
                        barcodeScannerSettings={{ barcodeTypes: ['code128', 'qr'] }}
                        onBarcodeScanned={lendo ? aoLer : undefined}
                    />
                    <View style={styles.scanFrame} pointerEvents="none" />
                    <Text style={styles.scanHint}>Aponte para o código de barras da nota</Text>
                    <TouchableOpacity style={styles.scanClose} onPress={() => setLendo(false)} activeOpacity={0.85}>
                        <Text style={styles.scanCloseText}>Fechar</Text>
                    </TouchableOpacity>
                </View>
            </Modal>

            <ItemPhotoLinkModal
                item={item}
                visible={photoModal}
                onClose={() => setPhotoModal(false)}
                onSaved={(fotoUrl) => {
                    setPhotoModal(false);
                    setPhotoFailed(false);
                    setFotoNova(fotoUrl);
                }}
            />
            <DoneModal done={done} />
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    scroll: { padding: 16, paddingBottom: 40 },
    itemRow: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, borderRadius: 18, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, ...heroSoftShadow },
    photo: { width: 72, height: 72, borderRadius: 14, backgroundColor: '#fff' },
    photoEmpty: { alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    photoEmptyText: { fontSize: 24 },
    photoAdd: { color: heroPalette.primary, fontSize: 11, fontWeight: '800', marginTop: 2 },
    itemName: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    itemMeta: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    label: { color: heroPalette.textSoft, fontSize: 14, fontWeight: '800', marginTop: 18, marginBottom: 8 },
    scanButton: { height: 56, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    scanText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    noteCard: { padding: 14, borderRadius: 16, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.borderStrong },
    noteTitle: { color: heroPalette.text, fontSize: 17, fontWeight: '900' },
    noteLine: { color: heroPalette.textSoft, fontSize: 13, marginTop: 4 },
    noteKey: { color: heroPalette.textMuted, fontSize: 12, marginTop: 6, letterSpacing: 0.5 },
    noteAgain: { color: heroPalette.primary, fontSize: 13, fontWeight: '800', marginTop: 8 },
    input: { backgroundColor: '#fff', color: '#0f172a', borderRadius: 14, paddingHorizontal: 16, height: 54, fontSize: 20, fontWeight: '800' },
    dateRow: { flexDirection: 'row', gap: 12 },
    dateField: { height: 54, borderRadius: 14, backgroundColor: '#fff', justifyContent: 'center', paddingHorizontal: 16 },
    dateText: { color: '#0f172a', fontSize: 17, fontWeight: '800' },
    datePlaceholder: { color: '#94a3b8', fontSize: 17, fontWeight: '700' },
    error: { color: heroPalette.danger, fontSize: 14, fontWeight: '700', marginTop: 14, textAlign: 'center' },
    button: { marginTop: 22, height: 56, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    buttonOff: { opacity: 0.5 },
    buttonText: { color: heroPalette.bg, fontSize: 17, fontWeight: '900' },
    scanner: { flex: 1, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
    scanFrame: { width: '86%', height: 130, borderRadius: 16, borderWidth: 3, borderColor: heroPalette.primaryStrong },
    scanHint: { position: 'absolute', top: 70, color: '#fff', fontSize: 16, fontWeight: '800', textAlign: 'center', paddingHorizontal: 24 },
    scanClose: { position: 'absolute', bottom: 60, paddingHorizontal: 28, paddingVertical: 14, borderRadius: 14, backgroundColor: 'rgba(6,16,27,0.8)' },
    scanCloseText: { color: '#fff', fontSize: 16, fontWeight: '800' },
});
