// Escuta de voz do app (2.7.1). Pedido do usuário em 27/11/2026: "tem como aumentar o tempo de intervalo quando se
// fala, pois 2 segundos sem falar ele já fecha". A janela do Google (GalintVoz.ouvir) fecha sozinha na pausa; esta
// escuta usa o reconhecedor do Android sem a janela (GalintVoz.comecar) e junta os trechos até 4 s em silêncio ou
// até "Pronto", mostrando o que foi entendido enquanto a pessoa fala. Sem o reconhecedor, sem a permissão do
// microfone ou com o APK antigo, volta para a janela do Google.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Animated, Easing, Modal, NativeEventEmitter, NativeModules, PermissionsAndroid, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { heroPalette } from '../theme/heroTheme';

const SILENCIO_MS = 4000;
let donoAtual = 0; // só a escuta que começou por último recebe os eventos
let proximoDono = 1;

async function pedirMicrofone() {
    if (Platform.OS !== 'android') return true;
    try {
        const permissao = PermissionsAndroid.PERMISSIONS.RECORD_AUDIO;
        if (await PermissionsAndroid.check(permissao)) return true;
        return (await PermissionsAndroid.request(permissao)) === PermissionsAndroid.RESULTS.GRANTED;
    } catch (erro) {
        return false;
    }
}

// Janela do Google (2.6.0): fecha na pausa, mas funciona sem permissão de microfone no app.
async function ouvirPelaJanela(voz, aoFalar) {
    try {
        const frases = await voz.ouvir('Fale o material ou o código');
        const frase = Array.isArray(frases) ? String(frases[0] || '').trim() : '';
        if (frase) aoFalar(frase);
    } catch (erro) {
        if (erro?.code === 'sem_voz') Alert.alert('Voz', erro.message || 'Este celular não tem o reconhecimento de voz.');
    }
}

export function useEscutaVoz() {
    const [aberta, setAberta] = useState(false);
    const [texto, setTexto] = useState('');
    const [preparando, setPreparando] = useState(false);
    const dono = useRef(0);
    const aoFalar = useRef(null);
    const pulso = useRef(new Animated.Value(0)).current;

    useEffect(() => {
        const voz = NativeModules?.GalintVoz;
        if (!voz?.comecar) return undefined;
        const emissor = new NativeEventEmitter(voz);
        const assinatura = emissor.addListener('GalintVozEvento', (evento) => {
            if (!dono.current || dono.current !== donoAtual) return;
            const dito = String(evento?.texto || '').trim();
            if (evento?.tipo === 'parcial' || evento?.tipo === 'ouvindo') {
                if (dito) setTexto(dito);
                return;
            }
            dono.current = 0;
            setAberta(false);
            if (evento?.tipo === 'fim') {
                if (dito) aoFalar.current?.(dito);
            } else if (evento?.tipo === 'erro') {
                Alert.alert('Voz', evento?.codigo === 'sem_permissao' ? 'Permita o microfone para falar.' : 'Não foi possível ouvir agora.');
            }
        });
        return () => {
            assinatura.remove();
            if (dono.current && dono.current === donoAtual) voz.cancelar?.();
        };
    }, []);

    useEffect(() => {
        if (!aberta) return undefined;
        const animacao = Animated.loop(Animated.sequence([
            Animated.timing(pulso, { toValue: 1, duration: 700, easing: Easing.out(Easing.quad), useNativeDriver: true }),
            Animated.timing(pulso, { toValue: 0, duration: 700, easing: Easing.in(Easing.quad), useNativeDriver: true }),
        ]));
        animacao.start();
        return () => animacao.stop();
    }, [aberta, pulso]);

    const ouvir = useCallback(async (callback) => {
        const voz = NativeModules?.GalintVoz;
        if (!voz?.ouvir) {
            Alert.alert('Voz', 'Atualize o app para falar o material.');
            return;
        }
        if (!voz.comecar || !voz.disponivel) {
            await ouvirPelaJanela(voz, callback);
            return;
        }
        setPreparando(true);
        const permitido = await pedirMicrofone();
        const temReconhecedor = permitido && (await voz.disponivel().catch(() => false));
        setPreparando(false);
        if (!temReconhecedor) {
            await ouvirPelaJanela(voz, callback);
            return;
        }
        aoFalar.current = callback;
        dono.current = proximoDono;
        donoAtual = proximoDono;
        proximoDono += 1;
        setTexto('');
        setAberta(true);
        voz.comecar(SILENCIO_MS);
    }, []);

    const pronto = useCallback(() => NativeModules?.GalintVoz?.terminar?.(), []);
    const cancelar = useCallback(() => {
        aoFalar.current = null;
        NativeModules?.GalintVoz?.cancelar?.();
        dono.current = 0;
        setAberta(false);
    }, []);

    const escala = pulso.interpolate({ inputRange: [0, 1], outputRange: [1, 1.18] });
    const janela = (
        <Modal visible={aberta} transparent animationType="fade" onRequestClose={cancelar}>
            <View style={styles.fundo}>
                <View style={styles.cartao}>
                    <Animated.View style={[styles.anel, { transform: [{ scale: escala }] }]}>
                        <Text style={styles.icone}>🎤</Text>
                    </Animated.View>
                    <Text style={[styles.texto, !texto && styles.textoVazio]} numberOfLines={4}>{texto || 'Ouvindo…'}</Text>
                    <View style={styles.botoes}>
                        <TouchableOpacity style={styles.cancelar} onPress={cancelar} activeOpacity={0.85} accessibilityLabel="Cancelar">
                            <Text style={styles.cancelarTexto}>✕</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.pronto} onPress={pronto} activeOpacity={0.85}>
                            <Text style={styles.prontoTexto}>Pronto</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </View>
        </Modal>
    );

    return { ouvir, ouvindo: aberta || preparando, janela };
}

const styles = StyleSheet.create({
    fundo: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(2, 6, 23, 0.6)', padding: 16 },
    cartao: { backgroundColor: heroPalette.panel, borderRadius: 22, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: heroPalette.border, marginBottom: 12 },
    anel: { width: 88, height: 88, borderRadius: 44, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    icone: { fontSize: 38 },
    texto: { color: heroPalette.text, fontSize: 20, fontWeight: '800', textAlign: 'center', marginTop: 18, minHeight: 56 },
    textoVazio: { color: heroPalette.textMuted },
    botoes: { flexDirection: 'row', gap: 12, marginTop: 16, alignSelf: 'stretch' },
    cancelar: { width: 64, height: 54, borderRadius: 14, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    cancelarTexto: { color: heroPalette.text, fontSize: 20, fontWeight: '800' },
    pronto: { flex: 1, height: 54, borderRadius: 14, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    prontoTexto: { color: heroPalette.bg, fontSize: 18, fontWeight: '900' },
});
