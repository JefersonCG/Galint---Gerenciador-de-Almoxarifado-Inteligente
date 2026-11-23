// Atualização sozinha do app (2.2.4). Pedido do usuário em 23/11/2026: "será possível essa
// atualização subir sozinha para o APK? Igual ao do Pipocas?". O GALINT publica o APK
// (instance/apks no servidor); o app pergunta ao abrir e ao voltar para a frente se há versão nova,
// mostra esta janela, baixa o APK (módulo nativo GalintUpdate) e abre o instalador do Android.
// O Android sempre pede a confirmação da pessoa para instalar; na primeira vez, pede também a
// permissão "instalar apps desconhecidos" para o GALINT.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Modal, NativeEventEmitter, NativeModules, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Application from 'expo-application';

import ApiService from '../services/api';
import { heroPalette, heroShadow } from '../theme/heroTheme';

const CHECK_EVERY_MS = 20 * 60 * 1000;
const SNOOZE_MS = 6 * 60 * 60 * 1000;
const SNOOZE_KEY = 'galint_atualizacao_adiada';
const Updater = NativeModules?.GalintUpdate;

export default function AppUpdatePrompt() {
    const [release, setRelease] = useState(null); // { version_name, version_code, notas, url, sha256, tamanho }
    const [phase, setPhase] = useState('ask'); // ask | permission | downloading | installing | error
    const [percent, setPercent] = useState(0);
    const [message, setMessage] = useState('');
    const lastCheck = useRef(0);

    const check = useCallback(async (force = false) => {
        if (!Updater || !ApiService.baseURL) return;
        if (!force && Date.now() - lastCheck.current < CHECK_EVERY_MS) return;
        lastCheck.current = Date.now();
        const currentCode = Number(Application.nativeBuildVersion) || 0;
        const result = await ApiService.verificarAtualizacao(currentCode);
        if (!result?.success || !result.disponivel) return;
        try {
            const snooze = JSON.parse((await AsyncStorage.getItem(SNOOZE_KEY)) || 'null');
            if (snooze && snooze.code === result.version_code && snooze.until > Date.now()) return;
        } catch (error) {
            // sem adiamento guardado
        }
        setPhase('ask');
        setPercent(0);
        setMessage('');
        setRelease(result);
    }, []);

    useEffect(() => {
        check(true);
        const subscription = AppState.addEventListener('change', (state) => {
            if (state === 'active') check(false);
        });
        const emitter = Updater ? new NativeEventEmitter(Updater) : null;
        const progress = emitter?.addListener('GalintUpdateProgress', (event) => setPercent(Number(event?.percent) || 0));
        return () => {
            subscription.remove();
            progress?.remove();
        };
    }, [check]);

    const later = useCallback(async () => {
        if (release) {
            await AsyncStorage.setItem(SNOOZE_KEY, JSON.stringify({ code: release.version_code, until: Date.now() + SNOOZE_MS })).catch(() => {});
        }
        setRelease(null);
    }, [release]);

    const update = useCallback(async () => {
        if (!release || !Updater) return;
        const allowed = await Updater.canInstall().catch(() => false);
        if (!allowed) {
            setPhase('permission');
            return;
        }
        setPhase('downloading');
        setPercent(0);
        try {
            const fileName = `GALINT-${release.version_name}-codigo${release.version_code}.apk`;
            await Updater.downloadAndInstall(`${ApiService.baseURL}${release.url}`, fileName, release.sha256 || null);
            setPhase('installing');
        } catch (error) {
            setPhase('error');
            setMessage(error?.message || 'Não foi possível baixar a atualização.');
        }
    }, [release]);

    const allowInstall = useCallback(async () => {
        await Updater?.openInstallPermission().catch(() => {});
        setPhase('ask');
    }, []);

    if (!release) return null;
    const sizeMb = release.tamanho ? `${Math.round(release.tamanho / (1024 * 1024))} MB` : '';

    return (
        <Modal visible transparent animationType="fade" onRequestClose={phase === 'downloading' ? undefined : later}>
            <View style={styles.backdrop}>
                <View style={styles.card}>
                    <Text style={styles.eyebrow}>ATUALIZAÇÃO</Text>
                    <Text style={styles.title}>GALINT {release.version_name}</Text>
                    {release.notas ? <Text style={styles.notes}>{release.notas}</Text> : null}

                    {phase === 'downloading' ? (
                        <View style={styles.progressBox}>
                            <View style={styles.track}><View style={[styles.fill, { width: `${percent}%` }]} /></View>
                            <Text style={styles.progressText}>Baixando… {percent}%{sizeMb ? ` de ${sizeMb}` : ''}</Text>
                        </View>
                    ) : null}
                    {phase === 'installing' ? <Text style={styles.info}>Confirme a instalação na tela do Android.</Text> : null}
                    {phase === 'permission' ? (
                        <Text style={styles.info}>Permita que o GALINT instale a atualização (só na primeira vez) e volte aqui.</Text>
                    ) : null}
                    {phase === 'error' ? <Text style={styles.error}>⚠ {message}</Text> : null}

                    {phase === 'permission' ? (
                        <TouchableOpacity style={styles.primary} onPress={allowInstall} activeOpacity={0.85}>
                            <Text style={styles.primaryText}>Permitir</Text>
                        </TouchableOpacity>
                    ) : phase !== 'downloading' ? (
                        <TouchableOpacity style={styles.primary} onPress={update} activeOpacity={0.85}>
                            <Text style={styles.primaryText}>{phase === 'installing' ? 'Instalar de novo' : phase === 'error' ? 'Tentar de novo' : 'Atualizar agora'}</Text>
                        </TouchableOpacity>
                    ) : null}
                    {phase !== 'downloading' ? (
                        <TouchableOpacity style={styles.ghost} onPress={later} activeOpacity={0.85}>
                            <Text style={styles.ghostText}>Depois</Text>
                        </TouchableOpacity>
                    ) : null}
                </View>
            </View>
        </Modal>
    );
}

const styles = StyleSheet.create({
    backdrop: { flex: 1, backgroundColor: 'rgba(2, 6, 23, 0.72)', justifyContent: 'center', padding: 22 },
    card: { backgroundColor: heroPalette.panel, borderRadius: 24, padding: 22, borderWidth: 1, borderColor: heroPalette.borderStrong, ...heroShadow },
    eyebrow: { color: heroPalette.primary, fontSize: 12, fontWeight: '900', letterSpacing: 1.4 },
    title: { color: heroPalette.text, fontSize: 24, fontWeight: '900', marginTop: 4 },
    notes: { color: heroPalette.textSoft, fontSize: 14, lineHeight: 20, marginTop: 10 },
    progressBox: { marginTop: 18 },
    track: { height: 10, borderRadius: 5, backgroundColor: heroPalette.panelAlt, overflow: 'hidden' },
    fill: { height: 10, borderRadius: 5, backgroundColor: heroPalette.primaryStrong },
    progressText: { color: heroPalette.textMuted, fontSize: 13, marginTop: 8, textAlign: 'center' },
    info: { color: heroPalette.textSoft, fontSize: 14, marginTop: 16, textAlign: 'center' },
    error: { color: heroPalette.danger, fontSize: 14, fontWeight: '700', marginTop: 16, textAlign: 'center' },
    primary: { marginTop: 20, height: 52, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    primaryText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    ghost: { marginTop: 10, height: 46, borderRadius: 14, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    ghostText: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
});
