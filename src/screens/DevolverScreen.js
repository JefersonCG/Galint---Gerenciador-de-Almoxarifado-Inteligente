import React, { useMemo, useState, useEffect, useLayoutEffect } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Alert,
    ScrollView,
    KeyboardAvoidingView,
    Platform,
    ActivityIndicator,
    FlatList,
    Image,
    Keyboard,
} from 'react-native';
import TextInput from '../components/UpperTextInput';
import ApiService from '../services/api';
import { formatQuantityWithPackaging } from '../utils/formatQuantity';
import { resolvePhotoUri } from '../components/StockCountPanel';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';
import { returnMessage } from '../utils/shareWhatsApp';
import {
    faltaNaQuantidade,
    fmt,
    fracaoTexto,
    nomeEmbalagem,
    parseQuantidade,
    embalagemEmDuvida,
    quantidadeBase,
    quantidadeFaladaDevolucao,
    quantidadeTexto,
    tipoSemServidor,
} from '../utils/devolucaoConta';
import DoneModal from '../components/DoneModal';
import { acharPessoa } from '../utils/buscaFalada';

const FRACOES = [0.25, 0.5, 0.75, 1];

/**
 * Tela unificada de devolução: ferramenta, fracionado ou unitário (2.4.1, 26/11/2026).
 * O servidor diz o tipo e a unidade (/api/mobile/devolucao/tipo/<codigo>); fracionado com embalagem
 * (lata de 18 L) volta em fração da embalagem (¼, ½, ¾) e vai ao servidor em litros.
 */
export default function DevolverScreen({ navigation, route }) {
    const user = route.params?.user;
    const item = route.params?.item;
    // 2.6.1: comando de voz da tela inicial ("devolução fio 2 rolos") chega com a quantidade dita.
    const quantidadeFalada = route.params?.quantidadeFalada ?? null;
    const modoFalado = route.params?.modoFalado || null;
    // 2.6.2: quem devolve dito na voz ("devolução por Júlio César furadeira").
    const [pessoaPendente, setPessoaPendente] = useState(route.params?.pessoaFalada || null);

    const [tipo, setTipo] = useState(() => tipoSemServidor(item));
    const [loadingTipo, setLoadingTipo] = useState(true);
    const [quantidade, setQuantidade] = useState(() => (
        quantidadeFaladaDevolucao(tipoSemServidor(item), item, quantidadeFalada, modoFalado)
        || (tipoSemServidor(item).tipo === 'fracionado' ? '' : '1')
    ));
    const [loading, setLoading] = useState(false);
    const [usuarios, setUsuarios] = useState([]);
    const [devolvedorBusca, setDevolvedorBusca] = useState('');
    const [devolvedorSelecionado, setDevolvedorSelecionado] = useState(null);
    const [showAutocompleteLista, setShowAutocompleteLista] = useState(false);
    const [ultimoResponsavel, setUltimoResponsavel] = useState(null);
    const [loadingUltimoResponsavel, setLoadingUltimoResponsavel] = useState(true);

    const isFerramenta = tipo.tipo === 'ferramenta';
    const isFracionado = tipo.tipo === 'fracionado';
    const comEmbalagem = isFracionado && tipo.conteudo > 0;

    // O tipo vem do servidor, com a mesma regra da gravação; sem resposta, fica o palpite local, só inteiro.
    useEffect(() => {
        let ativo = true;
        const codigo = String(item?.id || item?.codigo_barras || '').trim();
        ApiService.getTipoDevolucao(codigo)
            .then((remoto) => {
                if (!ativo || !remoto?.tipo) return;
                setTipo(remoto);
                // a quantidade falada já entrou pelo tipo local; o servidor só muda a conta do fracionado (lata)
                setQuantidade((atual) => (
                    (remoto.tipo === 'fracionado' ? quantidadeFaladaDevolucao(remoto, item, quantidadeFalada, modoFalado) : '')
                    || (remoto.tipo === 'fracionado' ? (atual === '1' ? '' : atual) : (atual || '1'))
                ));
            })
            .finally(() => {
                if (ativo) setLoadingTipo(false);
            });
        return () => {
            ativo = false;
        };
    }, [item]); // eslint-disable-line react-hooks/exhaustive-deps

    // 2.2.1: o nome da operação fica só no cabeçalho (sem o cartão de título nem a dica do rodapé).
    useLayoutEffect(() => {
        const title = isFerramenta ? 'Devolver ferramenta' : isFracionado ? 'Devolver fracionado' : 'Devolver material';
        navigation.setOptions({ title });
    }, [isFerramenta, isFracionado, navigation]);

    const quantidadeNum = useMemo(() => parseQuantidade(quantidade, tipo.decimal).valor, [quantidade, tipo.decimal]);
    const falta = faltaNaQuantidade(tipo, quantidadeNum);
    const [photoFailed, setPhotoFailed] = useState(false);
    const [done, setDone] = useState(null); // janela de conclusão (DoneModal)
    const photoUri = photoFailed ? null : resolvePhotoUri(item);

    const saldoAtual = useMemo(() => {
        const q = Number(item?.quantidade ?? 0);
        return Number.isFinite(q) ? Number(q.toFixed(6)) : 0;
    }, [item]);

    // Formata saldo com visualização inteligente de embalagens
    const saldoFormatado = useMemo(() => {
        return formatQuantityWithPackaging(saldoAtual, item);
    }, [saldoAtual, item]);

    const canChooseDevolvedor = useMemo(() => {
        if (!user) return false;
        if (user.is_admin) return true;
        if (user.is_manager) return true;
        const cargo = (user.cargo || '').toString().trim().toLowerCase();
        return cargo.includes('gerente');
    }, [user]);

    const userMatricula = useMemo(() => {
        return (user?.matricula || '').toString().trim();
    }, [user]);

    const userNome = useMemo(() => {
        return (user?.nome || user?.username || '').toString().trim();
    }, [user]);

    // Buscar último responsável que retirou o item
    useEffect(() => {
        const buscarUltimoResponsavel = async () => {
            try {
                setLoadingUltimoResponsavel(true);
                const codigo = String(item?.id || item?.codigo_barras || '').trim();
                if (!codigo) return;

                const ultimaRetirada = await ApiService.getUltimaRetirada(codigo);
                if (ultimaRetirada) {
                    setUltimoResponsavel(ultimaRetirada);
                }
            } catch (error) {
                console.error('Erro ao buscar último responsável:', error);
            } finally {
                setLoadingUltimoResponsavel(false);
            }
        };

        buscarUltimoResponsavel();
    }, [item]);

    useEffect(() => {
        if (!canChooseDevolvedor) {
            if (userMatricula) {
                const selfUser = {
                    matricula: userMatricula,
                    nome: userNome || userMatricula,
                    cargo: user?.cargo || null,
                    setor: user?.setor || null,
                };
                setDevolvedorSelecionado(selfUser);
                setDevolvedorBusca(selfUser.nome);
                setShowAutocompleteLista(false);
            }
            return;
        }

        const carregarUsuarios = async () => {
            const lista = await ApiService.getUsuarios();
            setUsuarios(lista);
        };

        carregarUsuarios();
    }, [canChooseDevolvedor, userMatricula, userNome, user]);

    const usuariosFiltrados = useMemo(() => {
        if (!devolvedorBusca.trim()) return usuarios;
        const busca = devolvedorBusca.toLowerCase();
        const achados = usuarios.filter((u) =>
            u.nome.toLowerCase().includes(busca) ||
            (u.matricula || '').toString().includes(busca)
        );
        // 2.6.2: nome falado ("Rafael" para RAPHAEL) quando a busca por trecho não acha ninguém
        return achados.length ? achados : acharPessoa(usuarios, devolvedorBusca).candidatos;
    }, [devolvedorBusca, usuarios]);

    // Quem devolve dito na voz: uma pessoa à frente entra direto; senão a lista abre com o nome dito.
    useEffect(() => {
        if (!pessoaPendente) return;
        if (!canChooseDevolvedor) {
            const eu = userMatricula ? [{ matricula: userMatricula, nome: userNome || userMatricula }] : [];
            if (!acharPessoa(eu, pessoaPendente).pessoa) Alert.alert('Quem devolve', `A devolução fica no seu nome: ${userNome || userMatricula || ''}.`);
            setPessoaPendente(null);
            return;
        }
        const certa = acharPessoa(usuarios, pessoaPendente).pessoa;
        if (certa) {
            setDevolvedorSelecionado(certa);
            setDevolvedorBusca(certa.cargo ? `${certa.nome} (${certa.cargo})` : certa.nome);
            setShowAutocompleteLista(false);
            setPessoaPendente(null);
            return;
        }
        setDevolvedorSelecionado(null);
        setDevolvedorBusca(String(pessoaPendente).toUpperCase());
        setShowAutocompleteLista(true);
        if (usuarios.length) setPessoaPendente(null); // sem a lista ainda: tenta de novo quando ela chegar
    }, [canChooseDevolvedor, pessoaPendente, userMatricula, userNome, usuarios]);

    // "devolução 5 papel toalhas" (sem unidade) num item com embalagem: 5 pacotes ou 5 unidades?
    useEffect(() => {
        const duvida = embalagemEmDuvida(tipoSemServidor(item), item, quantidadeFalada, modoFalado);
        if (!duvida) return;
        const q = Number(quantidadeFalada);
        Alert.alert('Quantidade', item?.descricao || '', [
            { text: `${fmt(q)} ${nomeEmbalagem(duvida.embalagem, q)}`, onPress: () => setQuantidade(String(q * duvida.fator)) },
            { text: `${fmt(q)} ${q === 1 ? 'unidade' : 'unidades'}`, onPress: () => setQuantidade(String(q)) },
        ]);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const handleSubmit = async () => {
        Keyboard.dismiss();
        if (falta) {
            Alert.alert('Quantidade', falta === 'Quantidade inteira' ? 'Este item volta em quantidade inteira.' : 'Informe a quantidade devolvida.');
            return;
        }
        const enviada = quantidadeBase(tipo, quantidadeNum);

        if (!devolvedorSelecionado) {
            Alert.alert('Erro', 'Selecione quem está devolvendo.');
            return;
        }

        if (!item?.id && !item?.codigo_barras) {
            Alert.alert('Erro', 'Item inválido. Volte e selecione novamente.');
            return;
        }

        setLoading(true);
        try {
            const codigo = String(item.id || item.codigo_barras).trim();
            const payload = {
                codigo,
                quantidade: enviada,
                matricula_devolvedor: String(devolvedorSelecionado?.matricula || '').trim(),
            };

            // Ferramenta pela custódia; material na unidade de devolução (litro, quilo, metro, unidade).
            const result = isFerramenta
                ? await ApiService.registrarDevolucaoFerramenta(payload)
                : await ApiService.devolverMaterial({ ...payload, unidade: tipo.unidade });

            if (!result.success) {
                Alert.alert('Erro', result.message);
                return;
            }


            const novoSaldoRaw = result.data?.item?.saldo;
            const novoSaldo = Number.isFinite(Number(novoSaldoRaw))
                ? Number(Number(novoSaldoRaw).toFixed(6))
                : novoSaldoRaw;
            
            const novoSaldoFormatado = formatQuantityWithPackaging(novoSaldo, item);
            const textoQuantidade = quantidadeTexto(tipo, quantidadeNum, item?.unidade);
            const mensagem = returnMessage({
                descricao: item?.descricao || item?.nome || 'Item',
                quantidade: textoQuantidade,
                devolvidoPor: devolvedorSelecionado?.nome,
                ferramenta: isFerramenta,
                registradoPor: user?.nome,
            });

            // "Nova devolução" volta ao leitor de código (a tela anterior); "Concluir" volta ao menu.
            setDone({
                title: 'Devolução registrada',
                itemName: item?.descricao || item?.nome || 'Item',
                summary: `${textoQuantidade} • saldo agora: ${novoSaldoFormatado}`,
                photoUri: resolvePhotoUri(item),
                message: mensagem,
                newLabel: 'Nova devolução',
                onNew: () => {
                    setDone(null);
                    navigation.goBack();
                },
                onFinish: () => {
                    setDone(null);
                    // 2.6.2: a devolução aberta pela tela Devolução volta para ela; a aberta pela tela inicial (comando
                    // de voz, toque no item) volta para a inicial. Antes ia sempre para a Devolução, que abria por
                    // cima da tela inicial com a custódia do dia (relato do usuário em 27/11/2026).
                    const naPilha = (navigation.getState()?.routes || []).some((rota) => rota.name === 'Devolucao');
                    if (naPilha) navigation.navigate('Devolucao', { user });
                    else navigation.navigate('Estoque');
                },
            });
        } catch (e) {
            Alert.alert('Erro', 'Falha ao registrar devolução');
        } finally {
            setLoading(false);
        }
    };

    const ultimoNome = ultimoResponsavel
        ? (ultimoResponsavel.nome && !ultimoResponsavel.nome.startsWith('Matrícula')
            ? ultimoResponsavel.nome
            : `Mat. ${ultimoResponsavel.matricula}`)
        : null;

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
                <View style={styles.card}>
                    <View style={styles.itemBox}>
                        <View style={styles.itemRow}>
                            {photoUri ? (
                                <Image source={{ uri: photoUri }} style={styles.itemPhoto} resizeMode="cover" onError={() => setPhotoFailed(true)} />
                            ) : (
                                <View style={[styles.itemPhoto, styles.itemPhotoEmpty]}>
                                    <Text style={styles.itemPhotoEmptyText}>Sem foto</Text>
                                </View>
                            )}
                            <View style={styles.itemCopy}>
                                <Text style={styles.itemName}>
                                    {(item?.descricao || item?.nome || '').toString().toUpperCase()}
                                </Text>
                                <Text style={styles.itemLine}>Código: {(item?.codigo_barras || item?.id || '').toString()}</Text>
                                <Text style={styles.itemLine}>Saldo: {saldoFormatado}</Text>
                                {loadingUltimoResponsavel ? (
                                    <ActivityIndicator size="small" color={heroPalette.primary} style={styles.lastLoading} />
                                ) : ultimoNome ? (
                                    <Text style={styles.itemLine}>
                                        Última retirada: {ultimoNome} • {new Date(ultimoResponsavel.data_saida).toLocaleDateString('pt-BR')}
                                    </Text>
                                ) : null}
                            </View>
                        </View>
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Devolvido por</Text>
                        <TextInput
                            style={[styles.input, !canChooseDevolvedor && styles.inputDisabled]}
                            value={devolvedorBusca}
                            onChangeText={(text) => {
                                setDevolvedorBusca(text);
                                setShowAutocompleteLista(true);
                                setDevolvedorSelecionado(null);
                            }}
                            placeholder="Nome ou matrícula"
                            placeholderTextColor={heroPalette.textMuted}
                            editable={canChooseDevolvedor}
                        />

                        {showAutocompleteLista && canChooseDevolvedor && (
                            <View style={styles.autocompleteContainer}>
                                <FlatList
                                    data={usuariosFiltrados.slice(0, 8)}
                                    keyExtractor={(entry) => entry.matricula}
                                    style={styles.autocompleteList}
                                    keyboardShouldPersistTaps="handled"
                                    renderItem={({ item: entry }) => (
                                        <TouchableOpacity
                                            style={styles.autocompleteItem}
                                            onPress={() => {
                                                setDevolvedorSelecionado(entry);
                                                setDevolvedorBusca(entry.cargo ? `${entry.nome} (${entry.cargo})` : entry.nome);
                                                setShowAutocompleteLista(false);
                                            }}
                                        >
                                            <Text style={styles.autocompleteNome}>{entry.nome}</Text>
                                            <Text style={styles.autocompleteDetalhe}>
                                                {entry.cargo || entry.setor || ''} | Mat: {entry.matricula}
                                            </Text>
                                        </TouchableOpacity>
                                    )}
                                />
                            </View>
                        )}
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>
                            {comEmbalagem
                                ? nomeEmbalagem(tipo.embalagem, 2).replace(/^./, (letra) => letra.toUpperCase())
                                : isFracionado
                                    ? `Quantidade (${tipo.unidade_curta})`
                                    : 'Quantidade'}
                        </Text>
                        {comEmbalagem ? (
                            <View style={styles.chips}>
                                {FRACOES.map((fracao) => {
                                    const ativo = Math.abs(quantidadeNum - fracao) < 1e-9;
                                    return (
                                        <TouchableOpacity
                                            key={fracao}
                                            style={[styles.chip, ativo && styles.chipActive]}
                                            onPress={() => {
                                                Keyboard.dismiss();
                                                setQuantidade(String(fracao).replace('.', ','));
                                            }}
                                        >
                                            <Text style={[styles.chipText, ativo && styles.chipTextActive]}>{fracaoTexto(fracao)}</Text>
                                        </TouchableOpacity>
                                    );
                                })}
                            </View>
                        ) : null}
                        <TextInput
                            style={styles.input}
                            value={quantidade}
                            onChangeText={(text) => setQuantidade(parseQuantidade(text, tipo.decimal).texto)}
                            placeholder="0"
                            placeholderTextColor={heroPalette.textMuted}
                            keyboardType={tipo.decimal ? 'decimal-pad' : 'numeric'}
                        />
                        {comEmbalagem && quantidadeNum > 0 ? (
                            <Text style={styles.conta}>
                                {`${fracaoTexto(quantidadeNum)} ${nomeEmbalagem(tipo.embalagem, quantidadeNum)} = ${fmt(quantidadeBase(tipo, quantidadeNum))} ${tipo.unidade_curta}`}
                            </Text>
                        ) : null}
                    </View>

                    <TouchableOpacity
                        style={[styles.button, (loading || loadingTipo || !devolvedorSelecionado || falta) && styles.buttonDisabled]}
                        onPress={handleSubmit}
                        disabled={loading || loadingTipo || !devolvedorSelecionado || Boolean(falta)}
                    >
                        {loading || loadingTipo ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>{!devolvedorSelecionado ? 'Falta quem devolve' : falta || 'Registrar devolução'}</Text>
                        )}
                    </TouchableOpacity>
                </View>
            </ScrollView>
            <DoneModal done={done} />
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    itemRow: { flexDirection: 'row', gap: 12, alignItems: 'center' },
    itemPhoto: { width: 84, height: 84, borderRadius: 14, backgroundColor: '#fff' },
    itemPhotoEmpty: { alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    itemPhotoEmptyText: { color: heroPalette.textMuted, fontSize: 11 },
    itemCopy: { flex: 1 },
    lastLoading: { alignSelf: 'flex-start', marginTop: 4 },
    container: {
        flex: 1,
        backgroundColor: heroPalette.bg,
    },
    heroContent: {
        flex: 1,
    },
    scroll: {
        paddingBottom: 22,
    },
    card: {
        backgroundColor: heroPalette.panel,
        borderRadius: 24,
        padding: 20,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    title: {
        fontSize: 22,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 16,
        textAlign: 'center',
    },
    loadingBox: {
        backgroundColor: heroPalette.panelAlt,
        padding: 12,
        borderRadius: 14,
        marginBottom: 16,
        flexDirection: 'row',
        alignItems: 'center',
        borderLeftWidth: 4,
        borderLeftColor: heroPalette.primaryStrong,
    },
    loadingText: {
        fontSize: 14,
        color: heroPalette.text,
        marginLeft: 10,
        fontWeight: '600',
    },
    infoBox: {
        backgroundColor: 'rgba(52, 211, 153, 0.1)',
        padding: 12,
        borderRadius: 14,
        marginBottom: 16,
        borderLeftWidth: 4,
        borderLeftColor: heroPalette.accent,
    },
    infoTitle: {
        fontSize: 15,
        fontWeight: 'bold',
        color: heroPalette.text,
        marginBottom: 6,
    },
    infoText: {
        fontSize: 14,
        color: heroPalette.textSoft,
        marginTop: 3,
    },
    itemBox: {
        backgroundColor: heroPalette.panelAlt,
        padding: 16,
        borderRadius: 18,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
        ...heroSoftShadow,
    },
    itemName: {
        fontSize: 16,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 8,
    },
    itemLine: {
        fontSize: 14,
        color: heroPalette.textMuted,
        marginTop: 4,
    },
    inputGroup: {
        marginBottom: 20,
    },
    chips: { flexDirection: 'row', gap: 8, marginBottom: 10 },
    chip: {
        flex: 1,
        paddingVertical: 12,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        alignItems: 'center',
    },
    chipActive: { backgroundColor: heroPalette.accent, borderColor: heroPalette.accent },
    chipText: { fontSize: 20, fontWeight: '800', color: heroPalette.text },
    chipTextActive: { color: heroPalette.bg },
    conta: { marginTop: 8, fontSize: 15, fontWeight: '700', color: heroPalette.accent },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: heroPalette.text,
        marginBottom: 8,
    },
    input: {
        borderWidth: 1,
        borderColor: heroPalette.border,
        borderRadius: 14,
        padding: 12,
        fontSize: 16,
        backgroundColor: heroPalette.panelAlt,
        color: heroPalette.text,
    },
    inputDisabled: {
        backgroundColor: heroPalette.bgAlt,
        color: heroPalette.textMuted,
    },
    autocompleteContainer: {
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        borderRadius: 14,
        marginTop: 6,
        maxHeight: 200,
        overflow: 'hidden',
    },
    autocompleteList: {
        maxHeight: 200,
    },
    autocompleteItem: {
        padding: 10,
        borderBottomWidth: 1,
        borderBottomColor: heroPalette.border,
    },
    autocompleteNome: {
        fontSize: 14,
        fontWeight: '700',
        color: heroPalette.text,
    },
    autocompleteDetalhe: {
        fontSize: 12,
        color: heroPalette.textMuted,
        marginTop: 2,
    },
    button: {
        backgroundColor: heroPalette.accent,
        paddingVertical: 14,
        paddingHorizontal: 20,
        borderRadius: 16,
        alignItems: 'center',
        marginBottom: 12,
    },
    buttonDisabled: {
        backgroundColor: heroPalette.panelSoft,
    },
    buttonText: {
        color: heroPalette.bg,
        fontSize: 16,
        fontWeight: '800',
    },
    hint: {
        fontSize: 12,
        color: heroPalette.textMuted,
        textAlign: 'center',
        marginTop: 8,
    },
});
