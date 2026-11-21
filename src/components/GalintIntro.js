// Abertura do app (2.2.0). Antes: o Android mostrava o ícone pequeno em fundo branco e depois
// vinha uma barra de progresso de quadradinhos. Agora a tela nativa é só o fundo escuro e esta
// animação entra direto: as barras de um código de barras sobem, um feixe de leitura passa por
// elas e a marca aparece. Ela dura pelo menos MIN_MS e espera o app ficar pronto (tema e servidor).
import React, { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';

import { heroPalette } from '../theme/heroTheme';

const BARS = [3, 1, 2, 1, 1, 3, 2, 1, 3, 1, 1, 2, 3, 1, 2, 1, 1, 3, 1, 2, 2, 1, 3, 1];
const UNIT = 3;
const GAP = 3;
const BAR_HEIGHT = 72;
const MIN_MS = 1500;
const BARCODE_WIDTH = BARS.reduce((total, width) => total + width * UNIT + GAP, -GAP);

export default function GalintIntro({ ready, onFinish, version }) {
    const bars = useRef(BARS.map(() => new Animated.Value(0))).current;
    const beam = useRef(new Animated.Value(0)).current;
    const brand = useRef(new Animated.Value(0)).current;
    const loader = useRef(new Animated.Value(0)).current;
    const fade = useRef(new Animated.Value(1)).current;
    const shownAt = useRef(Date.now()).current;
    const finished = useRef(false);

    useEffect(() => {
        Animated.sequence([
            Animated.stagger(28, bars.map((value) => Animated.timing(value, {
                toValue: 1,
                duration: 260,
                easing: Easing.out(Easing.back(1.6)),
                useNativeDriver: true,
            }))),
            Animated.parallel([
                Animated.timing(beam, { toValue: 1, duration: 620, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
                Animated.timing(brand, { toValue: 1, duration: 520, delay: 180, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
            ]),
        ]).start();
        Animated.loop(Animated.timing(loader, { toValue: 1, duration: 1100, easing: Easing.inOut(Easing.quad), useNativeDriver: true })).start();
    }, [bars, beam, brand, loader]);

    useEffect(() => {
        if (!ready || finished.current) return undefined;
        const wait = Math.max(0, MIN_MS - (Date.now() - shownAt));
        const timer = setTimeout(() => {
            finished.current = true;
            Animated.timing(fade, { toValue: 0, duration: 260, useNativeDriver: true }).start(() => onFinish && onFinish());
        }, wait);
        return () => clearTimeout(timer);
    }, [fade, onFinish, ready, shownAt]);

    const beamX = beam.interpolate({ inputRange: [0, 1], outputRange: [-24, BARCODE_WIDTH + 24] });
    const beamOpacity = beam.interpolate({ inputRange: [0, 0.08, 0.9, 1], outputRange: [0, 1, 1, 0] });
    const brandY = brand.interpolate({ inputRange: [0, 1], outputRange: [14, 0] });
    const loaderX = loader.interpolate({ inputRange: [0, 1], outputRange: [-48, 120] });

    return (
        <Animated.View style={[styles.container, { backgroundColor: heroPalette.bg, opacity: fade }]}>
            <View style={styles.center}>
                <View style={[styles.barcode, { width: BARCODE_WIDTH }]}>
                    {BARS.map((width, index) => (
                        <Animated.View
                            key={index}
                            style={[
                                styles.bar,
                                {
                                    width: width * UNIT,
                                    marginRight: index === BARS.length - 1 ? 0 : GAP,
                                    backgroundColor: index % 7 === 3 ? heroPalette.primaryStrong : heroPalette.text,
                                    transform: [{ scaleY: bars[index] }],
                                    opacity: bars[index],
                                },
                            ]}
                        />
                    ))}
                    <Animated.View
                        pointerEvents="none"
                        style={[styles.beamGlow, { backgroundColor: heroPalette.primaryStrong, opacity: Animated.multiply(beamOpacity, 0.22), transform: [{ translateX: beamX }] }]}
                    />
                    <Animated.View
                        pointerEvents="none"
                        style={[styles.beam, { backgroundColor: heroPalette.primary, opacity: beamOpacity, transform: [{ translateX: beamX }] }]}
                    />
                </View>
                <Animated.View style={{ opacity: brand, transform: [{ translateY: brandY }], alignItems: 'center' }}>
                    <Text style={[styles.brand, { color: heroPalette.text }]}>GALINT</Text>
                    <Text style={[styles.tagline, { color: heroPalette.textMuted }]}>Almoxarifado inteligente</Text>
                </Animated.View>
            </View>
            <View style={styles.footer}>
                <View style={[styles.loaderTrack, { backgroundColor: heroPalette.panelAlt }]}>
                    <Animated.View style={[styles.loaderSegment, { backgroundColor: heroPalette.primaryStrong, transform: [{ translateX: loaderX }] }]} />
                </View>
                {version ? <Text style={[styles.version, { color: heroPalette.textMuted }]}>versão {version}</Text> : null}
            </View>
        </Animated.View>
    );
}

const styles = StyleSheet.create({
    container: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
    center: { alignItems: 'center' },
    barcode: { height: BAR_HEIGHT + 12, flexDirection: 'row', alignItems: 'flex-end', marginBottom: 26, overflow: 'visible' },
    bar: { height: BAR_HEIGHT, borderRadius: 1.5 },
    beam: { position: 'absolute', left: 0, top: -6, width: 3, height: BAR_HEIGHT + 18, borderRadius: 2 },
    beamGlow: { position: 'absolute', left: -9, top: -6, width: 21, height: BAR_HEIGHT + 18, borderRadius: 10 },
    brand: { fontSize: 40, fontWeight: '900', letterSpacing: 10, marginLeft: 10 },
    tagline: { fontSize: 13, fontWeight: '700', letterSpacing: 2.4, textTransform: 'uppercase', marginTop: 6 },
    footer: { position: 'absolute', bottom: 56, alignItems: 'center' },
    loaderTrack: { width: 120, height: 3, borderRadius: 2, overflow: 'hidden' },
    loaderSegment: { width: 48, height: 3, borderRadius: 2 },
    version: { fontSize: 11, marginTop: 10, letterSpacing: 0.6 },
});
