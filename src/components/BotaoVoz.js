// Botão do microfone (2.6.0): abre a escuta de voz do Android (módulo nativo GalintVoz) e devolve o que a pessoa
// falou, já pronto para a busca (utils/buscaFalada.js). Pedido do usuário em 27/11/2026: retirada e pesquisa de
// materiais por voz ("aperto no microfone e falo 0265 e ele acha a parafusadeira"). 2.6.1: a frase também pode ser
// um comando ("retirada lâmpada kian 6 unidades"); quem recebe decide (utils/buscaFalada.js, interpretarComando).
import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, NativeModules, StyleSheet, Text, TouchableOpacity } from 'react-native';

import { heroPalette } from '../theme/heroTheme';

export default function BotaoVoz({ onFala, estilo, tamanho = 44 }) {
    const [ouvindo, setOuvindo] = useState(false);

    const ouvir = useCallback(async () => {
        const voz = NativeModules?.GalintVoz;
        if (!voz?.ouvir) {
            Alert.alert('Voz', 'Atualize o app para falar o material.');
            return;
        }
        setOuvindo(true);
        try {
            const frases = await voz.ouvir('Fale o material ou o código');
            const frase = Array.isArray(frases) ? String(frases[0] || '').trim() : '';
            if (frase) onFala?.(frase);
        } catch (erro) {
            if (erro?.code === 'sem_voz') Alert.alert('Voz', erro.message || 'Este celular não tem o reconhecimento de voz.');
        } finally {
            setOuvindo(false);
        }
    }, [onFala]);

    return (
        <TouchableOpacity
            style={[styles.botao, { width: tamanho, height: tamanho, borderRadius: tamanho / 2 }, estilo]}
            onPress={ouvir}
            disabled={ouvindo}
            activeOpacity={0.8}
            accessibilityLabel="Falar o material"
        >
            {ouvindo ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={[styles.icone, { fontSize: Math.max(20, Math.round(tamanho * 0.42)) }]}>🎤</Text>}
        </TouchableOpacity>
    );
}

const styles = StyleSheet.create({
    botao: { backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    icone: { fontSize: 20 },
});
