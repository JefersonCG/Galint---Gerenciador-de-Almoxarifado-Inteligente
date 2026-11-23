// Painel do item lido na tela inicial (Conferência, 2.2.0): foto, nome, código e saldo do
// sistema e, para quem pode alterar o estoque, a quantidade contada. Grava pelo mesmo motor
// auditado do site (/api/mobile/conferencia-estoque/ajuste). Veio da tela ContagemFisicaScreen
// (2.1.0, câmera em tela cheia), que saiu: a conferência agora é a tela inicial.
//
// item.pode_ajustar vem do servidor (caixa "Pode alterar o estoque" em Usuários; administradores
// sempre podem). Sem ela, o painel só mostra o item: é a consulta que substituiu "Consultar estoque".
import React, { useCallback, useState } from 'react';
import {
    ActivityIndicator,
    Image,
    Keyboard,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    Vibration,
    View,
} from 'react-native';

import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

export function resolvePhotoUri(item) {
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
    return (allowDecimal ? /^\d+(\.\d+)?$/ : /^\d+$/).test(value);
}

// item: o que a busca devolveu. detailsLoading: ainda esperando o servidor (o painel já mostra o
// que veio da base do celular). note: aviso sobre o item (ex.: sem conexão, só consulta).
// onMenu: abre o ☰ do item (lançar entrada com NF); só vem para quem pode lançar (administrador).
// onAddPhoto: item sem foto, toque abre a foto pelo link (só administradores).
export default function StockCountPanel({ item, detailsLoading, note, onSaved, onClose, onMenu, onAddPhoto }) {
    const [quantity, setQuantity] = useState('');
    const [packages, setPackages] = useState('');
    const [loose, setLoose] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [photoFailed, setPhotoFailed] = useState(false);

    const input = item?.input || {};
    const packaged = Boolean(input.supports_packaging);
    const allowDecimal = Boolean(input.internal_allow_decimal);
    const unit = input.internal_unit_display || item?.unidade || 'un';
    const pending = Boolean(item?.pre_cadastro_pendente);
    const canAdjust = item?.pode_ajustar === true && !detailsLoading;
    const canSave = canAdjust && !pending && (packaged
        ? isValidQuantity(packages, false) && isValidQuantity(loose || '0', allowDecimal)
        : isValidQuantity(quantity, allowDecimal));
    const photoUri = photoFailed ? null : resolvePhotoUri(item);
    const codigo = item?.codigo || item?.codigo_barras || item?.id || '';
    // Itens antigos têm "None" gravado no local: não mostrar.
    const local = ['', 'none', 'null'].includes(String(item?.localizacao || '').trim().toLowerCase()) ? '' : item.localizacao;

    const save = useCallback(async () => {
        if (!canSave || saving) return;
        InactivityService.recordActivity();
        Keyboard.dismiss();
        setSaving(true);
        setError('');
        const payload = packaged
            ? { codigo, mode: 'packages_plus_internal', package_quantity: normalizeNumber(packages), internal_quantity: normalizeNumber(loose || '0') }
            : { codigo, mode: 'direct', quantity: normalizeNumber(quantity) };
        const result = await ApiService.salvarContagem(payload);
        setSaving(false);
        if (!result.success) {
            setError(result.message || 'Não foi possível salvar. Tente de novo.');
            return;
        }
        Vibration.vibrate(120);
        if (onSaved) onSaved(item, result);
    }, [canSave, codigo, item, loose, onSaved, packaged, packages, quantity, saving]);

    return (
        <View style={styles.card}>
            {onMenu ? (
                <TouchableOpacity style={styles.menuButton} onPress={onMenu} accessibilityLabel="Mais opções do item" hitSlop={10}>
                    <Text style={styles.menuIcon}>☰</Text>
                </TouchableOpacity>
            ) : null}
            <View style={styles.photoBox}>
                {photoUri ? (
                    <Image source={{ uri: photoUri }} style={styles.photo} resizeMode="contain" onError={() => setPhotoFailed(true)} />
                ) : onAddPhoto ? (
                    <TouchableOpacity style={styles.photoEmpty} onPress={onAddPhoto} activeOpacity={0.8} accessibilityLabel="Pôr foto no item">
                        <Text style={styles.photoEmptyIcon}>📷</Text>
                        <Text style={styles.photoAddText}>Pôr foto</Text>
                    </TouchableOpacity>
                ) : (
                    <View style={styles.photoEmpty}>
                        <Text style={styles.photoEmptyIcon}>🖼️</Text>
                        <Text style={styles.photoEmptyText}>Sem foto</Text>
                    </View>
                )}
            </View>
            <Text style={styles.name}>{item?.descricao || item?.nome || 'Item'}</Text>
            <Text style={styles.code}>Código: {codigo}</Text>
            {item?.categoria ? <Text style={styles.meta}>{item.categoria}{local ? ` • ${local}` : ''}</Text> : null}
            <View style={styles.balanceBox}>
                <Text style={styles.balanceLabel}>NO SISTEMA</Text>
                <Text style={styles.balanceValue}>{item?.saldo_display || '—'}</Text>
            </View>

            {note ? <Text style={styles.note}>{note}</Text> : null}

            {detailsLoading ? (
                <View style={styles.loadingRow}>
                    <ActivityIndicator color={heroPalette.primaryStrong} />
                    <Text style={styles.loadingText}>Conferindo no servidor...</Text>
                </View>
            ) : pending ? (
                <Text style={styles.warning}>Este item ainda está pendente de cadastro e não pode ter o estoque ajustado. Termine o cadastro no GALINT.</Text>
            ) : !canAdjust ? (
                <Text style={styles.readOnly}>Só consulta. Para alterar a quantidade, peça a um administrador para marcar "Pode alterar o estoque" no seu cadastro.</Text>
            ) : packaged ? (
                <View style={styles.form}>
                    {input.package_content_display ? <Text style={styles.hint}>{input.package_content_display}</Text> : null}
                    <Text style={styles.label}>{`${input.package_plural || 'Embalagens'} fechadas`}</Text>
                    <TextInput style={styles.input} value={packages} onChangeText={setPackages} keyboardType="number-pad" placeholder="0" placeholderTextColor="#94a3b8" />
                    <Text style={styles.label}>{`Quantidade solta (${unit})`}</Text>
                    <TextInput style={styles.input} value={loose} onChangeText={setLoose} keyboardType={allowDecimal ? 'decimal-pad' : 'number-pad'} placeholder="0" placeholderTextColor="#94a3b8" returnKeyType="done" onSubmitEditing={save} />
                </View>
            ) : (
                <View style={styles.form}>
                    <Text style={styles.label}>{`Quantidade física (${unit})`}</Text>
                    <TextInput style={[styles.input, styles.inputBig]} value={quantity} onChangeText={setQuantity} keyboardType={allowDecimal ? 'decimal-pad' : 'number-pad'} placeholder="0" placeholderTextColor="#94a3b8" returnKeyType="done" onSubmitEditing={save} />
                </View>
            )}

            {error ? <Text style={styles.error}>⚠ {error}</Text> : null}

            {canAdjust && !pending ? (
                <TouchableOpacity style={[styles.primary, (!canSave || saving) && styles.disabled]} onPress={save} disabled={!canSave || saving} activeOpacity={0.85}>
                    {saving ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.primaryText}>Salvar contagem</Text>}
                </TouchableOpacity>
            ) : null}
            <TouchableOpacity style={styles.secondary} onPress={onClose} disabled={saving} activeOpacity={0.85}>
                <Text style={styles.secondaryText}>{canAdjust && !pending ? 'Cancelar e ler outro código' : 'Ler outro código'}</Text>
            </TouchableOpacity>
        </View>
    );
}

const styles = StyleSheet.create({
    card: { backgroundColor: heroPalette.panel, borderRadius: 22, padding: 16, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'stretch', ...heroSoftShadow },
    menuButton: { position: 'absolute', top: 10, right: 10, zIndex: 2, width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt, borderWidth: 1, borderColor: heroPalette.border },
    menuIcon: { color: heroPalette.text, fontSize: 22, fontWeight: '800' },
    photoBox: { alignSelf: 'center', width: 160, height: 160, borderRadius: 16, backgroundColor: '#fff', overflow: 'hidden', marginBottom: 12, alignItems: 'center', justifyContent: 'center' },
    photo: { width: '100%', height: '100%' },
    photoEmpty: { flex: 1, width: '100%', alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    photoEmptyIcon: { fontSize: 38 },
    photoEmptyText: { color: heroPalette.textMuted, marginTop: 4 },
    photoAddText: { color: heroPalette.primary, marginTop: 4, fontWeight: '800' },
    name: { color: heroPalette.text, fontSize: 19, fontWeight: '800', textAlign: 'center' },
    code: { color: heroPalette.textMuted, fontSize: 13, marginTop: 4, textAlign: 'center' },
    meta: { color: heroPalette.textSoft, fontSize: 13, marginTop: 2, textAlign: 'center' },
    balanceBox: { alignSelf: 'center', marginTop: 12, paddingVertical: 8, paddingHorizontal: 18, borderRadius: 12, backgroundColor: 'rgba(96,165,250,0.14)', borderWidth: 1, borderColor: 'rgba(96,165,250,0.4)', alignItems: 'center' },
    balanceLabel: { color: heroPalette.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1 },
    balanceValue: { color: heroPalette.text, fontSize: 20, fontWeight: '800', marginTop: 2 },
    note: { color: heroPalette.warning, fontSize: 13, fontWeight: '700', textAlign: 'center', marginTop: 12 },
    loadingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, marginTop: 16 },
    loadingText: { color: heroPalette.textMuted, fontSize: 14 },
    warning: { marginTop: 14, backgroundColor: '#fef3c7', color: '#78350f', borderRadius: 12, padding: 12, fontSize: 14, fontWeight: '600' },
    readOnly: { marginTop: 14, color: heroPalette.textSoft, backgroundColor: heroPalette.panelAlt, borderRadius: 12, padding: 12, fontSize: 14, lineHeight: 20, textAlign: 'center' },
    form: { marginTop: 14 },
    hint: { color: heroPalette.textMuted, fontSize: 13, marginBottom: 8, textAlign: 'center' },
    label: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '700', marginBottom: 8, marginTop: 4 },
    input: { backgroundColor: '#fff', color: '#0f172a', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 12, fontSize: 20, fontWeight: '800', marginBottom: 10 },
    inputBig: { fontSize: 30, textAlign: 'center' },
    error: { color: heroPalette.danger, fontSize: 14, fontWeight: '700', marginTop: 6, textAlign: 'center' },
    primary: { marginTop: 14, backgroundColor: heroPalette.primaryStrong, borderRadius: 16, paddingVertical: 16, alignItems: 'center' },
    primaryText: { color: heroPalette.bg, fontSize: 18, fontWeight: '800' },
    disabled: { opacity: 0.45 },
    secondary: { marginTop: 10, paddingVertical: 14, alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: heroPalette.border },
    secondaryText: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '700' },
});
