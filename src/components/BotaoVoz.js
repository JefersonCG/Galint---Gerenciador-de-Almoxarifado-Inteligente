// Botão do microfone (2.6.0): abre a escuta de voz e devolve o que a pessoa falou, já pronto para a busca
// (utils/buscaFalada.js). Pedido do usuário em 27/11/2026: retirada e pesquisa de materiais por voz ("aperto no
// microfone e falo 0265 e ele acha a parafusadeira"). 2.6.1: a frase também pode ser um comando ("retirada lâmpada
// kian 6 unidades"); quem recebe decide (utils/buscaFalada.js, interpretarComando). 2.7.1: a escuta é a do
// components/EscutaVoz.js, que não fecha numa pausa de 2 s.
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity } from 'react-native';

import { useEscutaVoz } from './EscutaVoz';
import { heroPalette } from '../theme/heroTheme';

export default function BotaoVoz({ onFala, estilo, tamanho = 44 }) {
    const { ouvir, ouvindo, janela } = useEscutaVoz();

    return (
        <>
            <TouchableOpacity
                style={[styles.botao, { width: tamanho, height: tamanho, borderRadius: tamanho / 2 }, estilo]}
                onPress={() => ouvir((frase) => onFala?.(frase))}
                disabled={ouvindo}
                activeOpacity={0.8}
                accessibilityLabel="Falar o material"
            >
                {ouvindo ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={[styles.icone, { fontSize: Math.max(20, Math.round(tamanho * 0.42)) }]}>🎤</Text>}
            </TouchableOpacity>
            {janela}
        </>
    );
}

const styles = StyleSheet.create({
    botao: { backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    icone: { fontSize: 20 },
});
