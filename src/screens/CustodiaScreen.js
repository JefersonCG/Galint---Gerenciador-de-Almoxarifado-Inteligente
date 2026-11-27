// Com quem está a ferramenta (2.6.2). Pedido do usuário em 27/11/2026: "coloca um comando de custódia, para sabermos
// com quem está a ferramenta". Abre pelo comando de voz ("custódia furadeira", "com quem está a trena", "custódia
// Gláucia", "custódia" sozinha = todas) ou pela opção Custódia do item tocado na lista da tela inicial.
// Os dados vêm de /api/mobile/custodia: a mesma conta da página Custódia de ferramentas do site (temporária e
// permanente, sem devolução). Só consulta.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import TextInput from '../components/UpperTextInput';
import BotaoVoz from '../components/BotaoVoz';
import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import { filtrarCustodia, interpretarComando } from '../utils/buscaFalada';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';

const dias = (n) => (n === 1 ? '1 dia' : `${n} dias`);

export default function CustodiaScreen({ navigation, route }) {
    const codigo = String(route.params?.codigo || '').trim();
    const [filtro, setFiltro] = useState(route.params?.filtro || '');
    const [linhas, setLinhas] = useState([]);
    const [carregando, setCarregando] = useState(true);
    const [aviso, setAviso] = useState('');

    useLayoutEffect(() => {
        navigation.setOptions({ title: 'Custódia' });
    }, [navigation]);

    const carregar = useCallback(async () => {
        setCarregando(true);
        const resposta = await ApiService.getCustodia(codigo);
        if (resposta?.success) {
            setLinhas(Array.isArray(resposta.data) ? resposta.data : []);
            setAviso('');
        } else {
            setLinhas([]);
            setAviso(resposta?.message || 'Sem resposta do servidor.');
        }
        setCarregando(false);
    }, [codigo]);

    useEffect(() => {
        carregar();
    }, [carregar]);

    const visiveis = useMemo(() => filtrarCustodia(linhas, filtro), [filtro, linhas]);

    const vazio = aviso
        || (codigo ? `${route.params?.titulo || 'Esta ferramenta'}: ninguém está com ela.` : filtro.trim() ? 'Ninguém com essa ferramenta.' : 'Nenhuma ferramenta com colaborador.');

    return (
        <View style={styles.container}>
            {codigo ? null : (
                <View style={styles.buscaLinha}>
                    <TextInput
                        style={styles.input}
                        value={filtro}
                        onChangeText={(texto) => { InactivityService.recordActivity(); setFiltro(texto); }}
                        placeholder="Ferramenta ou pessoa"
                        placeholderTextColor="#94a3b8"
                        autoCorrect={false}
                    />
                    {filtro ? (
                        <TouchableOpacity onPress={() => setFiltro('')} hitSlop={10} accessibilityLabel="Limpar">
                            <Text style={styles.limpar}>✕</Text>
                        </TouchableOpacity>
                    ) : null}
                    <BotaoVoz tamanho={54} onFala={(frase) => setFiltro(interpretarComando(frase).material || frase)} />
                </View>
            )}
            {carregando && !linhas.length ? <ActivityIndicator color={heroPalette.primary} style={styles.carregando} /> : null}
            <FlatList
                data={visiveis}
                keyExtractor={(linha, indice) => `${linha.codigo}-${linha.matricula}-${indice}`}
                contentContainerStyle={styles.listaConteudo}
                keyboardShouldPersistTaps="handled"
                refreshControl={<RefreshControl refreshing={carregando && linhas.length > 0} onRefresh={carregar} tintColor={heroPalette.primary} />}
                ListHeaderComponent={codigo && route.params?.titulo ? <Text style={styles.titulo}>{route.params.titulo}</Text> : null}
                ListEmptyComponent={carregando ? null : <Text style={[styles.vazio, aviso && styles.vazioAviso]}>{vazio}</Text>}
                renderItem={({ item: linha }) => (
                    <View style={[styles.cartao, linha.atrasada && styles.cartaoAtrasado]}>
                        <Text style={styles.ferramenta} numberOfLines={2}>{linha.descricao}</Text>
                        <View style={styles.pessoaLinha}>
                            <Text style={styles.pessoa} numberOfLines={1}>👤 {linha.nome || linha.matricula}</Text>
                            {Number(linha.quantidade) > 1 ? <Text style={styles.quantidade}>{linha.quantidade} un.</Text> : null}
                        </View>
                        <Text style={styles.meta} numberOfLines={2}>
                            {[linha.desde ? `desde ${linha.desde}` : '', dias(Number(linha.dias) || 0), linha.local ? `📍 ${linha.local}` : ''].filter(Boolean).join(' · ')}
                        </Text>
                        {linha.tipo_custodia === 'permanente' || linha.atrasada ? (
                            <View style={styles.selos}>
                                {linha.tipo_custodia === 'permanente' ? <Text style={[styles.selo, styles.seloPermanente]}>PERMANENTE</Text> : null}
                                {linha.atrasada ? <Text style={[styles.selo, styles.seloAtrasada]}>ATRASADA</Text> : null}
                            </View>
                        ) : null}
                    </View>
                )}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    buscaLinha: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingTop: 16 },
    input: { flex: 1, backgroundColor: '#fff', color: '#0f172a', borderRadius: 14, paddingHorizontal: 16, height: 54, fontSize: 16, fontWeight: '700' },
    limpar: { color: heroPalette.textMuted, fontSize: 20, paddingHorizontal: 2 },
    carregando: { marginTop: 24 },
    listaConteudo: { padding: 16, paddingBottom: 40 },
    titulo: { color: heroPalette.text, fontSize: 18, fontWeight: '900', marginBottom: 12 },
    vazio: { color: heroPalette.textMuted, textAlign: 'center', marginTop: 30, fontSize: 15 },
    vazioAviso: { color: heroPalette.danger, fontWeight: '800' },
    cartao: { backgroundColor: heroPalette.panel, borderRadius: 16, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: heroPalette.border, ...heroSoftShadow },
    cartaoAtrasado: { borderColor: 'rgba(251, 113, 133, 0.6)' },
    ferramenta: { color: heroPalette.text, fontSize: 16, fontWeight: '900' },
    pessoaLinha: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 },
    pessoa: { flex: 1, color: heroPalette.accent, fontSize: 16, fontWeight: '900' },
    quantidade: { color: heroPalette.primary, fontSize: 14, fontWeight: '800' },
    meta: { color: heroPalette.textMuted, fontSize: 13, marginTop: 4 },
    selos: { flexDirection: 'row', gap: 8, marginTop: 8 },
    selo: { fontSize: 11, fontWeight: '900', letterSpacing: 0.5, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, overflow: 'hidden' },
    seloPermanente: { color: heroPalette.bg, backgroundColor: heroPalette.primary },
    seloAtrasada: { color: '#fff', backgroundColor: heroPalette.danger },
});
