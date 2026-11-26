// "Será que temos!?" (2.5.0, pedido do usuário em 26/11/2026): foto do material → os itens do estoque mais
// parecidos, com foto e saldo. No servidor, DINOv2 + OpenCLIP (busca_visual/servico.py); a Fase 0 mediu 97% de
// acerto entre os 3 primeiros, por isso a tela mostra sempre 3 (e o 4º/5º quando empatam, como as CURVA 90 de
// tamanhos diferentes com a mesma foto). Tocar no item certo ensina a busca (a foto vira referência dele) e, se
// houver saldo, mostra "Retirar", que abre a Retirada com o item.
// A primeira busca do dia liga o serviço de visão no servidor (uns 30 s); a tela espera sozinha.
// 2.5.1 (pedido do usuário no mesmo dia): "a pessoa não sabe se tirou ou não". No toque: vibração, flash branco
// e ampulheta girando; com a foto tirada, a imagem congela e uma tartaruga anda na trilha enquanto a busca roda.
// Regras do usuário: sem textos explicativos; o botão diz o que falta.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Easing, Image, ScrollView, StyleSheet, Text, TouchableOpacity, Vibration, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';

import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import { resolvePhotoUri } from '../components/StockCountPanel';
import { heroPalette } from '../theme/heroTheme';

const ESPERA_MS = 2500;
const ESPERA_MAXIMA_MS = 150000;
const TRILHA = 220; // largura da trilha da tartaruga

// Ampulheta girando: aparece no instante do toque, até a foto sair da câmera.
function Ampulheta() {
    const giro = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        const laco = Animated.loop(Animated.timing(giro, { toValue: 1, duration: 1100, easing: Easing.inOut(Easing.quad), useNativeDriver: true }));
        laco.start();
        return () => laco.stop();
    }, [giro]);
    const rotate = giro.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '180deg'] });
    return <Animated.Text style={[styles.ampulheta, { transform: [{ rotate }] }]}>⏳</Animated.Text>;
}

// Tartaruga andando de um lado ao outro da trilha, com o passo balançando, enquanto a busca roda.
function Tartaruga({ texto }) {
    const andar = useRef(new Animated.Value(0)).current;
    const passo = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        const ida = Animated.loop(Animated.timing(andar, { toValue: 1, duration: 3200, easing: Easing.linear, useNativeDriver: true }));
        const pisada = Animated.loop(Animated.sequence([
            Animated.timing(passo, { toValue: 1, duration: 220, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
            Animated.timing(passo, { toValue: 0, duration: 220, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
        ]));
        ida.start();
        pisada.start();
        return () => {
            ida.stop();
            pisada.stop();
        };
    }, [andar, passo]);
    const translateX = andar.interpolate({ inputRange: [0, 1], outputRange: [-TRILHA / 2 + 18, TRILHA / 2 - 18] });
    const translateY = passo.interpolate({ inputRange: [0, 1], outputRange: [0, -4] });
    const rotate = passo.interpolate({ inputRange: [0, 1], outputRange: ['-4deg', '4deg'] });
    // Rastro crescendo da esquerda até a tartaruga (escala + deslocamento: o motor nativo não anima largura).
    const rastroEscala = andar.interpolate({ inputRange: [0, 1], outputRange: [0.001, 1] });
    const rastroDesloca = andar.interpolate({ inputRange: [0, 1], outputRange: [-TRILHA / 2, 0] });
    return (
        <View style={styles.progresso}>
            <View style={styles.trilha}>
                <Animated.View style={[styles.rastro, { transform: [{ translateX: rastroDesloca }, { scaleX: rastroEscala }] }]} />
                {/* O emoji da tartaruga olha para a esquerda: espelhado, ela anda para a direita. */}
                <Animated.Text style={[styles.tartaruga, { transform: [{ translateX }, { translateY }, { rotate }, { scaleX: -1 }] }]}>🐢</Animated.Text>
            </View>
            <Text style={styles.progressoTexto}>{texto}</Text>
        </View>
    );
}

export default function SeraQueTemosScreen({ navigation, route }) {
    const user = route.params?.user || null;
    const [permission, requestPermission] = useCameraPermissions();
    const isFocused = useIsFocused();
    const camera = useRef(null);
    const flash = useRef(new Animated.Value(0)).current;
    const [torch, setTorch] = useState(false);
    // camera | capturando (tocou, a foto ainda não saiu) | enviando | preparando | resultado | erro
    const [estado, setEstado] = useState('camera');
    const [foto, setFoto] = useState(null);
    const [itens, setItens] = useState([]);
    const [erro, setErro] = useState('');
    const [confirmado, setConfirmado] = useState(null);
    const consulta = useRef('');
    const vivo = useRef(true);
    const foiRetirar = useRef(false);
    const ocupado = estado === 'capturando' || estado === 'enviando' || estado === 'preparando';

    useEffect(() => {
        vivo.current = true;
        return () => {
            vivo.current = false;
        };
    }, []);

    useEffect(() => {
        if (permission && !permission.granted && permission.canAskAgain) requestPermission();
    }, [permission, requestPermission]);

    const mostrar = useCallback((resposta) => {
        setItens(Array.isArray(resposta.itens) ? resposta.itens : []);
        setConfirmado(null);
        setEstado('resultado');
    }, []);

    const esperar = useCallback(async () => {
        const inicio = Date.now();
        while (vivo.current && Date.now() - inicio < ESPERA_MAXIMA_MS) {
            await new Promise((resolve) => setTimeout(resolve, ESPERA_MS));
            if (!vivo.current) return;
            InactivityService.recordActivity();
            const resposta = await ApiService.seraQueTemosResultado(consulta.current);
            if (!resposta?.success) {
                setErro(resposta?.message || 'A busca não respondeu.');
                setEstado('erro');
                return;
            }
            if (resposta.pronto) {
                mostrar(resposta);
                return;
            }
        }
        if (vivo.current) {
            setErro('A busca demorou demais. Tente de novo.');
            setEstado('erro');
        }
    }, [mostrar]);

    const fotografar = useCallback(async () => {
        InactivityService.recordActivity();
        if (!permission?.granted) {
            requestPermission();
            return;
        }
        if (!camera.current || ocupado) return;
        // Sinal de que a foto foi tirada: vibração e flash branco na hora do toque.
        Vibration.vibrate(40);
        flash.setValue(0.85);
        Animated.timing(flash, { toValue: 0, duration: 320, easing: Easing.out(Easing.quad), useNativeDriver: true }).start();
        setEstado('capturando');
        setErro('');
        let tirada = null;
        try {
            tirada = await camera.current.takePictureAsync({ quality: 0.5, skipProcessing: true, shutterSound: false });
        } catch (error) {
            tirada = null;
        }
        if (!vivo.current) return;
        if (!tirada?.uri) {
            setErro('Não foi possível tirar a foto.');
            setEstado('erro');
            return;
        }
        setFoto(tirada.uri);
        setTorch(false);
        setEstado('enviando');
        const resposta = await ApiService.seraQueTemos(tirada.uri);
        if (!vivo.current) return;
        if (!resposta?.success) {
            setErro(resposta?.message || 'A busca não respondeu.');
            setEstado('erro');
            return;
        }
        consulta.current = resposta.consulta || '';
        if (resposta.pronto) {
            mostrar(resposta);
            return;
        }
        setEstado('preparando');
        esperar();
    }, [esperar, flash, mostrar, ocupado, permission?.granted, requestPermission]);

    const escolher = useCallback((item) => {
        InactivityService.recordActivity();
        const codigo = item.codigo_barras || item.id;
        setConfirmado(codigo);
        if (consulta.current) ApiService.seraQueTemosConfirmar(consulta.current, codigo);
    }, []);

    const novaFoto = useCallback(() => {
        InactivityService.recordActivity();
        consulta.current = '';
        setFoto(null);
        setItens([]);
        setErro('');
        setConfirmado(null);
        setEstado('camera');
    }, []);

    const retirar = useCallback((item) => {
        InactivityService.recordActivity();
        foiRetirar.current = true;
        navigation.navigate('FilaSaida', { user, scannedItem: item });
    }, [navigation, user]);

    // 2.5.2: voltou da Retirada, a busca anterior sai e a câmera abre limpa.
    useEffect(() => {
        if (isFocused && foiRetirar.current) {
            foiRetirar.current = false;
            novaFoto();
        }
    }, [isFocused, novaFoto]);

    if (estado === 'camera' || ocupado) {
        // Com a foto tirada, a imagem congela no visor (a câmera sai) e a tartaruga anda por cima.
        const congelada = Boolean(foto) && estado !== 'capturando';
        return (
            <View style={styles.container}>
                <View style={styles.visor}>
                    {congelada ? (
                        <Image source={{ uri: foto }} style={StyleSheet.absoluteFill} resizeMode="cover" />
                    ) : permission?.granted && isFocused ? (
                        <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" enableTorch={torch} autoFocus="on" />
                    ) : (
                        <TouchableOpacity style={styles.semCamera} onPress={requestPermission} activeOpacity={0.8}>
                            <Text style={styles.semCameraIcone}>📷</Text>
                            <Text style={styles.semCameraTexto}>Permitir a câmera</Text>
                        </TouchableOpacity>
                    )}
                    {ocupado ? (
                        <View style={styles.veu} pointerEvents="none">
                            {estado === 'capturando' ? <Ampulheta /> : <Tartaruga texto={estado === 'preparando' ? 'Preparando a busca…' : 'Procurando…'} />}
                        </View>
                    ) : null}
                    <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.flash, { opacity: flash }]} />
                </View>
                <View style={styles.barra}>
                    <TouchableOpacity style={[styles.lanterna, torch && styles.lanternaOn]} onPress={() => setTorch((v) => !v)} disabled={ocupado} activeOpacity={0.85}>
                        <Text style={styles.lanternaTexto}>{torch ? '🔦' : '💡'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.disparo, ocupado && styles.disparoOcupado]} onPress={fotografar} disabled={ocupado} activeOpacity={0.8} accessibilityLabel="Tirar foto">
                        {ocupado ? <ActivityIndicator color={heroPalette.bg} size="large" /> : <View style={styles.disparoMiolo} />}
                    </TouchableOpacity>
                    <View style={styles.lanterna} />
                </View>
            </View>
        );
    }

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.conteudo}>
            {foto ? <Image source={{ uri: foto }} style={styles.fotoTirada} resizeMode="cover" /> : null}

            {estado === 'erro' ? <Text style={styles.erro}>⚠ {erro}</Text> : null}

            {estado === 'resultado' && !itens.length ? <Text style={styles.nada}>Nenhum item parecido.</Text> : null}

            {estado === 'resultado' ? itens.map((item) => {
                const codigo = item.codigo_barras || item.id;
                const saldo = Number(item.saldo ?? item.quantidade ?? 0);
                const temSaldo = saldo > 0;
                const escolhido = confirmado === codigo;
                const fotoItem = resolvePhotoUri(item);
                return (
                    <TouchableOpacity
                        key={codigo}
                        style={[styles.cartao, escolhido && styles.cartaoEscolhido, confirmado && !escolhido && styles.cartaoApagado]}
                        onPress={() => escolher(item)}
                        activeOpacity={0.85}
                    >
                        <View style={styles.cartaoTopo}>
                            {fotoItem ? (
                                <Image source={{ uri: fotoItem }} style={styles.fotoItem} resizeMode="cover" />
                            ) : (
                                <View style={[styles.fotoItem, styles.fotoVazia]}><Text style={styles.fotoVaziaTexto}>📦</Text></View>
                            )}
                            <View style={styles.cartaoTexto}>
                                <Text style={styles.nome} numberOfLines={3}>{item.descricao}</Text>
                                <Text style={styles.meta} numberOfLines={1}>{[codigo, item.localizacao].filter(Boolean).join(' • ')}</Text>
                                <Text style={[styles.saldo, !temSaldo && styles.saldoZero]}>{temSaldo ? (item.saldo_display || String(saldo)) : 'ZERADO'}</Text>
                            </View>
                            {escolhido ? <Text style={styles.certo}>✓</Text> : null}
                        </View>
                        {escolhido && temSaldo ? (
                            <TouchableOpacity style={styles.retirar} onPress={() => retirar(item)} activeOpacity={0.85}>
                                <Text style={styles.retirarTexto}>📤 Retirar</Text>
                            </TouchableOpacity>
                        ) : null}
                    </TouchableOpacity>
                );
            }) : null}

            <TouchableOpacity style={styles.novaFoto} onPress={novaFoto} activeOpacity={0.85}>
                <Text style={styles.novaFotoTexto}>📷 Nova foto</Text>
            </TouchableOpacity>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    visor: { flex: 1, margin: 16, marginBottom: 0, borderRadius: 24, overflow: 'hidden', backgroundColor: '#000', borderWidth: 2, borderColor: heroPalette.primary },
    semCamera: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panel },
    semCameraIcone: { fontSize: 44 },
    semCameraTexto: { color: heroPalette.textMuted, fontSize: 14, marginTop: 6 },
    veu: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(2, 6, 23, 0.55)' },
    flash: { backgroundColor: '#fff' },
    ampulheta: { fontSize: 64 },
    progresso: { alignItems: 'center', paddingVertical: 18, paddingHorizontal: 20, borderRadius: 22, backgroundColor: 'rgba(2, 6, 23, 0.72)' },
    trilha: { width: TRILHA, height: 46, justifyContent: 'flex-end', alignItems: 'center', overflow: 'hidden' },
    rastro: { position: 'absolute', left: 0, bottom: 4, width: TRILHA, height: 4, borderRadius: 2, backgroundColor: heroPalette.primary, opacity: 0.85 },
    tartaruga: { fontSize: 34, marginBottom: 4 },
    progressoTexto: { color: '#fff', fontSize: 16, fontWeight: '900', marginTop: 10, letterSpacing: 0.3 },
    barra: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 36, paddingVertical: 18 },
    lanterna: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center' },
    lanternaOn: { backgroundColor: 'rgba(251, 191, 36, 0.25)' },
    lanternaTexto: { fontSize: 24 },
    disparo: { width: 82, height: 82, borderRadius: 41, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center', borderWidth: 4, borderColor: heroPalette.text },
    disparoOcupado: { opacity: 0.6 },
    disparoMiolo: { width: 56, height: 56, borderRadius: 28, backgroundColor: heroPalette.text, opacity: 0.9 },
    conteudo: { padding: 16, paddingBottom: 40 },
    fotoTirada: { width: '100%', height: 180, borderRadius: 18, marginBottom: 14, backgroundColor: '#000' },
    erro: { color: '#f87171', fontSize: 15, fontWeight: '800', marginBottom: 12 },
    nada: { color: heroPalette.textMuted, fontSize: 15, fontWeight: '700', textAlign: 'center', marginVertical: 18 },
    cartao: { padding: 12, borderRadius: 18, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, marginBottom: 10 },
    cartaoEscolhido: { borderColor: heroPalette.primary, borderWidth: 2 },
    cartaoApagado: { opacity: 0.45 },
    cartaoTopo: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    fotoItem: { width: 76, height: 76, borderRadius: 14, backgroundColor: '#fff' },
    fotoVazia: { alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    fotoVaziaTexto: { fontSize: 28 },
    cartaoTexto: { flex: 1 },
    nome: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    meta: { color: heroPalette.textMuted, fontSize: 12, marginTop: 2 },
    saldo: { color: heroPalette.primary, fontSize: 17, fontWeight: '900', marginTop: 6 },
    saldoZero: { color: '#f87171' },
    certo: { color: heroPalette.primary, fontSize: 28, fontWeight: '900' },
    retirar: { marginTop: 12, height: 50, borderRadius: 14, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    retirarTexto: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    novaFoto: { marginTop: 8, height: 54, borderRadius: 16, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    novaFotoTexto: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
});
