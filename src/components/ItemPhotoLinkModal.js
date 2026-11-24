// Foto do item pelo link (2.2.4). Pedido do usuário em 23/11/2026: tocar no item sem foto e poder pôr
// uma imagem, igual em Documentos Fiscais do site: abre o navegador já buscando o nome e a marca do
// item, a pessoa copia o link da imagem, volta e cola; o servidor baixa, reduz e grava a foto.
// O teclado só abre quando a pessoa toca no campo (regra do usuário).
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Keyboard, Linking, Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import TextInput from './UpperTextInput';

import ApiService from '../services/api';
import { heroPalette, heroShadow } from '../theme/heroTheme';

export default function ItemPhotoLinkModal({ item, visible, onClose, onSaved }) {
    const [link, setLink] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        if (visible) {
            setLink('');
            setError('');
            setSaving(false);
        }
    }, [visible]);

    if (!visible || !item) return null;
    const codigo = String(item.codigo || item.codigo_barras || item.id || '').trim();
    const busca = [item.descricao, item.marca].filter((part) => part && String(part).trim() && String(part).toLowerCase() !== 'none').join(' ');

    const search = () => {
        Keyboard.dismiss();
        Linking.openURL(`https://www.google.com/search?tbm=isch&q=${encodeURIComponent(busca || codigo)}`).catch(() => {});
    };

    const save = async () => {
        const url = link.trim();
        if (!url || saving) return;
        Keyboard.dismiss();
        setSaving(true);
        setError('');
        const result = await ApiService.salvarFotoItemPorLink(codigo, url);
        setSaving(false);
        if (!result?.success) {
            setError(result?.message || 'Não foi possível salvar a foto.');
            return;
        }
        onSaved(result.foto_url);
    };

    return (
        <Modal visible transparent animationType="fade" onRequestClose={onClose}>
            <View style={styles.backdrop}>
                <View style={styles.card}>
                    <Text style={styles.title}>Foto do item</Text>
                    <Text style={styles.item} numberOfLines={2}>{item.descricao}</Text>

                    <TouchableOpacity style={styles.search} onPress={search} activeOpacity={0.85}>
                        <Text style={styles.searchText}>🔎  Buscar no Google Imagens</Text>
                    </TouchableOpacity>
                    <Text style={styles.hint}>Copie o link da imagem e cole abaixo.</Text>

                    <TextInput
                        style={styles.input}
                        value={link}
                        onChangeText={setLink}
                        placeholder="Link da imagem"
                        placeholderTextColor="#94a3b8"
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="url"
                    />
                    {error ? <Text style={styles.error}>⚠ {error}</Text> : null}

                    <TouchableOpacity style={[styles.primary, (!link.trim() || saving) && styles.off]} onPress={save} disabled={!link.trim() || saving} activeOpacity={0.85}>
                        {saving ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.primaryText}>Salvar foto</Text>}
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.ghost} onPress={onClose} disabled={saving} activeOpacity={0.85}>
                        <Text style={styles.ghostText}>Cancelar</Text>
                    </TouchableOpacity>
                </View>
            </View>
        </Modal>
    );
}

const styles = StyleSheet.create({
    backdrop: { flex: 1, backgroundColor: 'rgba(2, 6, 23, 0.72)', justifyContent: 'center', padding: 22 },
    card: { backgroundColor: heroPalette.panel, borderRadius: 24, padding: 20, borderWidth: 1, borderColor: heroPalette.borderStrong, ...heroShadow },
    title: { color: heroPalette.text, fontSize: 20, fontWeight: '900' },
    item: { color: heroPalette.textMuted, fontSize: 14, marginTop: 4 },
    search: { marginTop: 18, height: 52, borderRadius: 16, borderWidth: 1, borderColor: heroPalette.borderStrong, backgroundColor: heroPalette.panelAlt, alignItems: 'center', justifyContent: 'center' },
    searchText: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    hint: { color: heroPalette.textMuted, fontSize: 13, textAlign: 'center', marginTop: 10, marginBottom: 10 },
    input: { backgroundColor: '#fff', color: '#0f172a', borderRadius: 14, paddingHorizontal: 14, height: 52, fontSize: 15 },
    error: { color: heroPalette.danger, fontSize: 14, fontWeight: '700', marginTop: 10, textAlign: 'center' },
    primary: { marginTop: 16, height: 52, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    off: { opacity: 0.5 },
    primaryText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    ghost: { marginTop: 10, height: 46, borderRadius: 14, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    ghostText: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
});
