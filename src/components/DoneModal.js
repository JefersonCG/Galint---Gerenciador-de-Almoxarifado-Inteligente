// Janela de conclusão de saída e devolução (2.2.2). Pedido do usuário em 21/11/2026: no lugar do
// alerta branco do Android, uma janela com o visual do app que mostra o que foi feito e pergunta se
// quer compartilhar no WhatsApp (com a foto do item). Depois: "Nova …" ou "Concluir".
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Keyboard, Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { heroPalette, heroShadow } from '../theme/heroTheme';
import { shareOnWhatsApp } from '../utils/shareWhatsApp';

// done: { title, summary, itemName, photoUri, message, newLabel, onNew, onFinish } ou null.
export default function DoneModal({ done }) {
    const [sharing, setSharing] = useState(false);
    const [shared, setShared] = useState(false);
    const [photoFailed, setPhotoFailed] = useState(false);

    useEffect(() => {
        if (done) {
            Keyboard.dismiss();
            setSharing(false);
            setShared(false);
            setPhotoFailed(false);
        }
    }, [done]);

    if (!done) return null;

    const share = async () => {
        setSharing(true);
        await shareOnWhatsApp(done.message, done.photoUri || null);
        setSharing(false);
        setShared(true);
    };

    return (
        <Modal visible transparent animationType="fade" onRequestClose={done.onFinish}>
            <View style={styles.backdrop}>
                <View style={styles.card}>
                    <View style={styles.header}>
                        <View style={styles.check}><Text style={styles.checkText}>✓</Text></View>
                        <Text style={styles.title}>{done.title}</Text>
                    </View>

                    <View style={styles.itemRow}>
                        {done.photoUri && !photoFailed ? (
                            <Image source={{ uri: done.photoUri }} style={styles.photo} resizeMode="cover" onError={() => setPhotoFailed(true)} />
                        ) : (
                            <View style={[styles.photo, styles.photoEmpty]}><Text style={styles.photoEmptyText}>📦</Text></View>
                        )}
                        <View style={styles.itemCopy}>
                            <Text style={styles.itemName} numberOfLines={2}>{done.itemName}</Text>
                            <Text style={styles.summary}>{done.summary}</Text>
                        </View>
                    </View>

                    {/* Sem mensagem (ex.: entrada com NF), não há o que compartilhar. */}
                    {done.message ? (
                        <>
                            <Text style={styles.question}>{shared ? 'Enviado para o WhatsApp.' : 'Deseja compartilhar no WhatsApp?'}</Text>
                            <TouchableOpacity style={[styles.share, (sharing || shared) && styles.shareDone]} onPress={share} disabled={sharing} activeOpacity={0.85}>
                                {sharing ? (
                                    <ActivityIndicator color={heroPalette.bg} />
                                ) : (
                                    <Text style={styles.shareText}>{shared ? 'Compartilhar de novo' : 'Compartilhar no WhatsApp'}</Text>
                                )}
                            </TouchableOpacity>
                        </>
                    ) : null}

                    <View style={styles.row}>
                        <TouchableOpacity style={styles.ghost} onPress={done.onNew} activeOpacity={0.85}>
                            <Text style={styles.ghostText}>{done.newLabel || 'Nova'}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.ghost} onPress={done.onFinish} activeOpacity={0.85}>
                            <Text style={styles.ghostText}>Concluir</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </Modal>
    );
}

const styles = StyleSheet.create({
    backdrop: { flex: 1, backgroundColor: 'rgba(2, 6, 23, 0.72)', justifyContent: 'center', padding: 22 },
    card: { backgroundColor: heroPalette.panel, borderRadius: 24, padding: 20, borderWidth: 1, borderColor: heroPalette.borderStrong, ...heroShadow },
    header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 },
    check: { width: 36, height: 36, borderRadius: 18, backgroundColor: heroPalette.success, alignItems: 'center', justifyContent: 'center' },
    checkText: { color: '#fff', fontSize: 20, fontWeight: '900' },
    title: { flex: 1, color: heroPalette.text, fontSize: 20, fontWeight: '900' },
    itemRow: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 12, borderRadius: 16, backgroundColor: heroPalette.panelAlt },
    photo: { width: 64, height: 64, borderRadius: 12, backgroundColor: '#fff' },
    photoEmpty: { alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelSoft },
    photoEmptyText: { fontSize: 26 },
    itemCopy: { flex: 1 },
    itemName: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    summary: { color: heroPalette.primary, fontSize: 14, fontWeight: '800', marginTop: 4 },
    question: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '700', textAlign: 'center', marginTop: 18, marginBottom: 10 },
    share: { height: 52, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    shareDone: { opacity: 0.7 },
    shareText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    row: { flexDirection: 'row', gap: 10, marginTop: 16 },
    ghost: { flex: 1, height: 48, borderRadius: 14, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    ghostText: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
});
