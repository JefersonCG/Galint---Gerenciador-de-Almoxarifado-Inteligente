// Fila de saída (2.4.0, 25/11/2026). Pedido do usuário: "preciso que no apk tenha restauração de saída dos
// itens, caso o apk feche ele restaure o que estava sendo retirado. e quero que crie fila de retirada igual
// temos. para quando quiser dar a saída vai sair todos."
//
// Igual à lista "Itens para Saída" do site (templates_mako/movements/saida.mako): a fila é dividida por
// colaborador e local; "Dar saída em tudo" manda uma parte por colaborador (o site usa
// /movimentos/saida-multipla, o app /api/mobile/retirar_multipla) e o que falhar fica na fila com o motivo.
// A fila é gravada no celular a cada mudança e quando o app vai para o fundo (services/filaSaida.js), e
// volta ao abrir esta tela. Item com embalagem sai na embalagem ou na unidade base ("3 pacotes = 3.000
// unidades"); a rota recebe a quantidade na unidade base. "Estoque zera com esta saída" e "Saldo
// insuficiente" somam o mesmo item em toda a fila, como no site.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    AppState,
    FlatList,
    Image,
    Keyboard,
    KeyboardAvoidingView,
    Modal,
    Platform,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';

import TextInput from '../components/UpperTextInput';
import ApiService from '../services/api';
import InactivityService from '../services/inactivityService';
import DoneModal from '../components/DoneModal';
import { resolvePhotoUri } from '../components/StockCountPanel';
import { heroPalette, heroSoftShadow } from '../theme/heroTheme';
import { unitLabel } from '../utils/provaReal';
import { baseQty, baseQtyAccepted, fmt, isTool, onlyWholePackages, qtyText, snapshot, stockWarning } from '../utils/filaSaidaConta';
import { withdrawalMessage } from '../utils/shareWhatsApp';
import { apagarFila, gravarFila, lerFila } from '../services/filaSaida';

const cap = (text) => {
    const value = String(text || '');
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
};
const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
const normalize = (text) => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

function filterUsers(usuarios, texto) {
    const termo = normalize(texto);
    if (!termo) return usuarios;
    return usuarios.filter((u) => normalize(u?.nome).includes(termo) || String(u?.matricula || '').includes(termo));
}

export default function FilaSaidaScreen({ navigation, route }) {
    const user = route.params?.user || null;
    const scannedItem = route.params?.scannedItem || null;

    const canChoose = useMemo(() => {
        if (!user) return false;
        if (user.is_admin || user.is_manager) return true;
        return String(user.cargo || '').toLowerCase().includes('gerente');
    }, [user]);
    const eu = useMemo(() => (
        user?.matricula
            ? { matricula: String(user.matricula).trim(), nome: String(user.nome || user.username || user.matricula).trim(), cargo: user.cargo || null }
            : null
    ), [user]);

    const [pronto, setPronto] = useState(false);
    const [grupos, setGrupos] = useState([]);
    const [retirante, setRetirante] = useState(null);
    const [busca, setBusca] = useState('');
    const [mostrarLista, setMostrarLista] = useState(false);
    const [local, setLocal] = useState('');
    const [usuarios, setUsuarios] = useState([]);
    const [codigoBusca, setCodigoBusca] = useState('');
    const [buscando, setBuscando] = useState(false);
    const [itemAtual, setItemAtual] = useState(null);
    const [quantidade, setQuantidade] = useState('1');
    const [modo, setModo] = useState('base');
    const [custodia, setCustodia] = useState('temporaria');
    const [enviando, setEnviando] = useState(false);
    const [done, setDone] = useState(null);
    const [trocando, setTrocando] = useState(null);
    const [buscaTroca, setBuscaTroca] = useState('');

    const localNorm = local.trim().toUpperCase();
    const estado = useRef({ pronto: false, grupos: [], atual: null });

    useLayoutEffect(() => {
        navigation.setOptions({ title: 'Fila de saída' });
    }, [navigation]);

    // Quem retira: admin e gerente escolhem; os demais retiram para si.
    useEffect(() => {
        if (!canChoose) {
            if (eu) {
                setRetirante(eu);
                setBusca(eu.nome);
            }
            return;
        }
        ApiService.getUsuarios().then((lista) => setUsuarios(Array.isArray(lista) ? lista : [])).catch(() => {});
    }, [canChoose, eu]);

    // Volta a fila que estava no celular.
    useEffect(() => {
        let ativo = true;
        lerFila(user).then((fila) => {
            if (!ativo) return;
            if (fila) {
                setGrupos(fila.grupos);
                const atual = fila.atual || {};
                if (canChoose && atual.retirante?.matricula) {
                    setRetirante(atual.retirante);
                    setBusca(atual.retirante.nome || '');
                }
                if (atual.local) setLocal(String(atual.local));
            }
            setPronto(true);
        });
        return () => {
            ativo = false;
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Grava a cada mudança (e ao sair da tela ou mandar o app para o fundo).
    useEffect(() => {
        const atual = { retirante: canChoose ? retirante : null, local: localNorm };
        estado.current = { pronto, grupos, atual };
        if (!pronto) return undefined;
        const timer = setTimeout(() => gravarFila(user, grupos, atual), 300);
        return () => clearTimeout(timer);
    }, [canChoose, grupos, localNorm, pronto, retirante, user]);

    useEffect(() => {
        const salvarAgora = () => {
            if (estado.current.pronto) gravarFila(user, estado.current.grupos, estado.current.atual);
        };
        const sub = AppState.addEventListener('change', (status) => {
            if (status !== 'active') salvarAgora();
        });
        return () => {
            sub.remove();
            salvarAgora();
        };
    }, [user]);

    const escolherItem = useCallback((item) => {
        Keyboard.dismiss();
        if (item?.pre_cadastro_pendente) {
            Alert.alert('Pré-cadastro', 'Conclua o pré-cadastro no site antes da saída.');
            return;
        }
        setItemAtual(item);
        setQuantidade('1');
        setModo(onlyWholePackages(snapshot(item)) ? 'embalagem' : 'base');
        setCustodia('temporaria');
    }, []);

    // Item lido no leitor de código (Scanner com returnTo: 'FilaSaida').
    useEffect(() => {
        if (!scannedItem) return;
        escolherItem(scannedItem);
        navigation.setParams({ scannedItem: null });
    }, [escolherItem, navigation, scannedItem]);

    const lerCodigo = useCallback(() => {
        InactivityService.recordActivity();
        Keyboard.dismiss();
        navigation.navigate('Scanner', { mode: 'withdraw_multi', user, multiCallback: true, returnTo: 'FilaSaida' });
    }, [navigation, user]);

    const buscarCodigo = useCallback(async () => {
        const code = codigoBusca.trim();
        if (!code || buscando) return;
        InactivityService.recordActivity();
        setBuscando(true);
        const found = await ApiService.buscarItemPorCodigo(code).catch(() => null);
        setBuscando(false);
        if (!found) {
            Alert.alert('Não encontrado', ApiService.lastItemLookupFailure === 'network' ? 'Sem conexão com o servidor.' : `O código ${code} não está cadastrado.`);
            return;
        }
        setCodigoBusca('');
        escolherItem(found);
    }, [buscando, codigoBusca, escolherItem]);

    const pedidoPorCodigo = useMemo(() => {
        const mapa = new Map();
        grupos.forEach((grupo) => grupo.itens.forEach((linha) => mapa.set(linha.codigo, (mapa.get(linha.codigo) || 0) + baseQty(linha))));
        return mapa;
    }, [grupos]);

    const avisoSaldo = useCallback(
        (codigo, saldo, unidade, extra = 0) => stockWarning((pedidoPorCodigo.get(codigo) || 0) + extra, saldo, unidade),
        [pedidoPorCodigo],
    );

    const atual = itemAtual ? snapshot(itemAtual) : null;
    const qtdNum = parseInt(quantidade, 10) || 0;
    const ferramentaAtual = atual ? isTool(atual.categoria) : false;
    const previa = atual ? { ...atual, modo: atual.fator > 0 ? modo : 'base', quantidade: qtdNum } : null;
    const faltaAtual = !retirante ? 'Falta quem retira' : !localNorm ? 'Falta o local' : !(qtdNum > 0) ? 'Falta a quantidade' : '';

    const porNaFila = useCallback(() => {
        if (!atual || faltaAtual) return;
        InactivityService.recordActivity();
        if (!atual.codigo) return;
        const linha = {
            ...atual,
            id: newId(),
            modo: atual.fator > 0 ? modo : 'base',
            quantidade: qtdNum,
            tipo_custodia: ferramentaAtual ? custodia : undefined,
        };
        if (!baseQtyAccepted(linha)) {
            Alert.alert('Quantidade fracionada', `${qtyText(linha)}: dê esta saída no site.`);
            return;
        }
        const grupoId = `${retirante.matricula}::${localNorm}`;
        setGrupos((lista) => {
            const copia = lista.map((grupo) => ({ ...grupo, itens: [...grupo.itens] }));
            let grupo = copia.find((entry) => entry.id === grupoId);
            if (!grupo) {
                grupo = { id: grupoId, matricula: retirante.matricula, nome: retirante.nome, cargo: retirante.cargo || null, local: localNorm, itens: [] };
                copia.push(grupo);
            }
            const igual = grupo.itens.findIndex((l) => l.codigo === linha.codigo && l.modo === linha.modo && (l.tipo_custodia || '') === (linha.tipo_custodia || ''));
            if (igual >= 0) grupo.itens[igual] = { ...grupo.itens[igual], quantidade: grupo.itens[igual].quantidade + linha.quantidade, erro: undefined };
            else grupo.itens.push(linha);
            return copia;
        });
        setItemAtual(null);
        setQuantidade('1');
    }, [atual, custodia, faltaAtual, ferramentaAtual, localNorm, modo, qtdNum, retirante]);

    const mudarQtd = useCallback((grupoId, linhaId, delta) => {
        setGrupos((lista) => lista.map((grupo) => (grupo.id !== grupoId ? grupo : {
            ...grupo,
            itens: grupo.itens.map((l) => (l.id !== linhaId ? l : { ...l, quantidade: Math.max(1, l.quantidade + delta), erro: undefined })),
        })));
    }, []);

    const remover = useCallback((grupoId, linhaId) => {
        setGrupos((lista) => lista
            .map((grupo) => (grupo.id !== grupoId ? grupo : { ...grupo, itens: grupo.itens.filter((l) => l.id !== linhaId) }))
            .filter((grupo) => grupo.itens.length));
    }, []);

    const trocarPara = useCallback((grupoId, novo) => {
        setGrupos((lista) => {
            const origem = lista.find((grupo) => grupo.id === grupoId);
            if (!origem) return lista;
            const destinoId = `${novo.matricula}::${origem.local}`;
            if (destinoId === grupoId) return lista;
            if (lista.some((grupo) => grupo.id === destinoId)) {
                return lista
                    .filter((grupo) => grupo.id !== grupoId)
                    .map((grupo) => (grupo.id === destinoId ? { ...grupo, itens: [...grupo.itens, ...origem.itens] } : grupo));
            }
            return lista.map((grupo) => (grupo.id === grupoId ? { ...grupo, id: destinoId, matricula: novo.matricula, nome: novo.nome, cargo: novo.cargo || null } : grupo));
        });
        setTrocando(null);
        setBuscaTroca('');
    }, []);

    const totalLinhas = grupos.reduce((total, grupo) => total + grupo.itens.length, 0);

    const darSaida = useCallback(async () => {
        InactivityService.recordActivity();
        setEnviando(true);
        const restantes = [];
        const saiu = [];
        const falhas = [];
        for (const grupo of grupos) {
            const payload = {
                itens: grupo.itens.map((l) => ({
                    codigo: l.codigo,
                    quantidade: baseQty(l),
                    tipo_custodia: l.tipo_custodia,
                    tipo_ferramenta: l.tipo_custodia ? (l.tipo_custodia === 'permanente' ? 'permanente' : 'diaria') : undefined,
                })),
                matricula_retirante: grupo.matricula,
                local_servico: grupo.local,
            };
            let result;
            try {
                result = await ApiService.registrarRetiradaMultipla(payload);
            } catch (error) {
                result = { success: false, message: error?.message || 'Não foi possível dar a saída.', resultados: [] };
            }
            const porIndice = new Map((Array.isArray(result?.resultados) ? result.resultados : []).map((r) => [Number(r.index), r]));
            const ok = [];
            const ficam = [];
            grupo.itens.forEach((linha, index) => {
                const resposta = porIndice.get(index + 1);
                if (resposta?.success) {
                    ok.push(linha);
                } else {
                    const motivo = resposta?.message || result?.message || 'Não saiu';
                    ficam.push({ ...linha, erro: motivo });
                    falhas.push(`${linha.descricao}: ${motivo}`);
                }
            });
            if (ok.length) saiu.push({ grupo, linhas: ok });
            if (ficam.length) restantes.push({ ...grupo, itens: ficam });
        }
        setGrupos(restantes);
        await gravarFila(user, restantes, { retirante: canChoose ? retirante : null, local: localNorm });
        setEnviando(false);

        if (!saiu.length) {
            Alert.alert('Não saiu', falhas.slice(0, 4).join('\n') || 'Tente de novo.');
            return;
        }
        const totalSaiu = saiu.reduce((total, parte) => total + parte.linhas.length, 0);
        const mensagem = saiu.map(({ grupo, linhas }) => withdrawalMessage({
            items: linhas.map((l) => ({ descricao: l.descricao, quantidade: qtyText(l), ferramenta: Boolean(l.tipo_custodia) })),
            retiradoPor: grupo.nome,
            local: grupo.local,
            registradoPor: user?.nome,
        })).join('\n\n');
        const comFoto = saiu.flatMap((parte) => parte.linhas).find((l) => resolvePhotoUri(l));
        const primeira = saiu[0].linhas[0];
        setDone({
            title: falhas.length ? 'Parte saiu' : 'Saída registrada',
            itemName: totalSaiu === 1 ? primeira.descricao : `${totalSaiu} itens`,
            summary: falhas.length
                ? `${falhas.length} ${falhas.length === 1 ? 'ficou' : 'ficaram'} na fila`
                : (saiu.length === 1 ? `Retirado por ${saiu[0].grupo.nome}` : `${saiu.length} colaboradores`),
            photoUri: comFoto ? resolvePhotoUri(comFoto) : null,
            message: mensagem,
            onFinish: () => {
                setDone(null);
                if (!falhas.length) navigation.goBack();
            },
        });
    }, [canChoose, grupos, localNorm, navigation, retirante, user]);

    const confirmarSaida = useCallback(() => {
        if (!totalLinhas || enviando) return;
        Keyboard.dismiss();
        const pessoas = grupos.length;
        Alert.alert(
            'Dar saída',
            `${totalLinhas} ${totalLinhas === 1 ? 'item' : 'itens'} de ${pessoas} ${pessoas === 1 ? 'colaborador' : 'colaboradores'}?`,
            [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'Dar saída', onPress: () => darSaida() },
            ],
        );
    }, [darSaida, enviando, grupos.length, totalLinhas]);

    const limpar = useCallback(() => {
        Alert.alert('Limpar fila', 'Apagar todos os itens da fila?', [
            { text: 'Cancelar', style: 'cancel' },
            {
                text: 'Apagar',
                style: 'destructive',
                onPress: () => {
                    setGrupos([]);
                    apagarFila(user);
                },
            },
        ]);
    }, [user]);

    const sugestoesRetirante = useMemo(() => {
        if (!canChoose || !mostrarLista) return [];
        if (retirante && normalize(busca) === normalize(retirante.nome)) return [];
        return filterUsers(usuarios, busca).slice(0, 6);
    }, [busca, canChoose, mostrarLista, retirante, usuarios]);

    const fotoAtual = atual ? resolvePhotoUri(atual) : null;
    const avisoAtual = previa && qtdNum > 0 ? avisoSaldo(previa.codigo, previa.saldo, previa.unidade, baseQty(previa)) : '';

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
                <Text style={styles.label}>Quem retira</Text>
                {canChoose ? (
                    <>
                        <TextInput
                            style={[styles.input, styles.inputText]}
                            value={busca}
                            onChangeText={(text) => {
                                setBusca(text);
                                setMostrarLista(true);
                                if (!text.trim()) setRetirante(null);
                            }}
                            onFocus={() => setMostrarLista(true)}
                            placeholder="Nome ou matrícula"
                            placeholderTextColor="#94a3b8"
                            autoCorrect={false}
                        />
                        {sugestoesRetirante.length ? (
                            <View style={styles.lista}>
                                {sugestoesRetirante.map((u) => (
                                    <TouchableOpacity
                                        key={String(u.matricula)}
                                        style={styles.listaLinha}
                                        onPress={() => {
                                            setRetirante({ matricula: String(u.matricula), nome: u.nome, cargo: u.cargo || null });
                                            setBusca(u.nome);
                                            setMostrarLista(false);
                                            Keyboard.dismiss();
                                        }}
                                        activeOpacity={0.8}
                                    >
                                        <Text style={styles.listaNome} numberOfLines={1}>{u.nome}</Text>
                                        <Text style={styles.listaDetalhe} numberOfLines={1}>{[u.cargo || u.setor, u.matricula].filter(Boolean).join(' · ')}</Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        ) : null}
                    </>
                ) : (
                    <View style={styles.fixo}>
                        <Text style={styles.fixoTexto} numberOfLines={1}>{eu?.nome || '—'}</Text>
                    </View>
                )}

                <Text style={styles.label}>Local</Text>
                <TextInput
                    style={[styles.input, styles.inputText]}
                    value={local}
                    onChangeText={setLocal}
                    placeholder="EX: BLOCO A - APTO 201"
                    placeholderTextColor="#94a3b8"
                    autoCorrect={false}
                />

                <Text style={styles.label}>Item</Text>
                {atual ? (
                    <View style={styles.atual}>
                        <View style={styles.atualTopo}>
                            {fotoAtual ? (
                                <Image source={{ uri: fotoAtual }} style={styles.foto} resizeMode="cover" />
                            ) : (
                                <View style={[styles.foto, styles.fotoVazia]}><Text style={styles.fotoVaziaTexto}>📦</Text></View>
                            )}
                            <View style={{ flex: 1 }}>
                                <Text style={styles.atualNome} numberOfLines={2}>{atual.descricao}</Text>
                                <Text style={styles.atualMeta}>{atual.codigo}</Text>
                                <Text style={styles.atualMeta}>Saldo: {itemAtual?.saldo_display || `${fmt(atual.saldo)} ${unitLabel(atual.unidade, atual.saldo)}`}</Text>
                            </View>
                            <TouchableOpacity style={styles.fechar} onPress={() => setItemAtual(null)} accessibilityLabel="Tirar este item">
                                <Text style={styles.fecharTexto}>✖</Text>
                            </TouchableOpacity>
                        </View>

                        {atual.fator > 0 ? (
                            <View style={[styles.chips, { marginTop: 12 }]}>
                                {[['embalagem', cap(atual.embalagem)], ['base', cap(atual.unidade)]]
                                    .filter(([valor]) => valor === 'embalagem' || !onlyWholePackages(atual))
                                    .map(([valor, rotulo]) => (
                                    <TouchableOpacity key={valor} style={[styles.chip, modo === valor && styles.chipOn]} onPress={() => setModo(valor)} activeOpacity={0.85}>
                                        <Text style={[styles.chipText, modo === valor && styles.chipTextOn]}>{rotulo}</Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        ) : null}

                        <View style={styles.stepper}>
                            <TouchableOpacity style={styles.stepBtn} onPress={() => setQuantidade(String(Math.max(1, qtdNum - 1)))} activeOpacity={0.8}>
                                <Text style={styles.stepTexto}>−</Text>
                            </TouchableOpacity>
                            <TextInput
                                style={[styles.input, styles.stepInput]}
                                value={quantidade}
                                onChangeText={(text) => setQuantidade(text.replace(/[^0-9]/g, ''))}
                                keyboardType="number-pad"
                            />
                            <TouchableOpacity style={styles.stepBtn} onPress={() => setQuantidade(String(qtdNum + 1))} activeOpacity={0.8}>
                                <Text style={styles.stepTexto}>+</Text>
                            </TouchableOpacity>
                        </View>
                        {previa && qtdNum > 0 ? <Text style={styles.previa}>{qtyText(previa)}</Text> : null}
                        {avisoAtual ? <Text style={styles.alerta}>⚠ {avisoAtual}</Text> : null}

                        {ferramentaAtual ? (
                            <View style={[styles.chips, { marginTop: 12 }]}>
                                {[['temporaria', 'Diária'], ['permanente', 'Permanente']].map(([valor, rotulo]) => (
                                    <TouchableOpacity key={valor} style={[styles.chip, custodia === valor && styles.chipOn]} onPress={() => setCustodia(valor)} activeOpacity={0.85}>
                                        <Text style={[styles.chipText, custodia === valor && styles.chipTextOn]}>{rotulo}</Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        ) : null}

                        <TouchableOpacity style={[styles.button, faltaAtual && styles.buttonOff]} onPress={porNaFila} disabled={Boolean(faltaAtual)} activeOpacity={0.85}>
                            <Text style={styles.buttonText}>{faltaAtual || '➕ Pôr na fila'}</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    <>
                        <TouchableOpacity style={styles.scanButton} onPress={lerCodigo} activeOpacity={0.85}>
                            <Text style={styles.scanText}>📷  Ler código</Text>
                        </TouchableOpacity>
                        <View style={styles.codigoRow}>
                            <TextInput
                                style={[styles.input, styles.inputText, { flex: 1 }]}
                                value={codigoBusca}
                                onChangeText={setCodigoBusca}
                                placeholder="Código"
                                placeholderTextColor="#94a3b8"
                                autoCorrect={false}
                                returnKeyType="search"
                                onSubmitEditing={buscarCodigo}
                            />
                            <TouchableOpacity style={styles.buscarBtn} onPress={buscarCodigo} disabled={buscando} activeOpacity={0.85}>
                                {buscando ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.buscarTexto}>Buscar</Text>}
                            </TouchableOpacity>
                        </View>
                    </>
                )}

                {totalLinhas ? (
                    <>
                        <Text style={styles.label}>Na fila ({totalLinhas})</Text>
                        {grupos.map((grupo) => (
                            <View key={grupo.id} style={styles.grupo}>
                                <View style={styles.grupoTopo}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.grupoNome} numberOfLines={1}>{grupo.nome}{grupo.cargo ? ` (${grupo.cargo})` : ''}</Text>
                                        <Text style={styles.grupoLocal} numberOfLines={2}>{grupo.matricula} • {grupo.local}</Text>
                                    </View>
                                    {canChoose ? (
                                        <TouchableOpacity style={styles.trocar} onPress={() => setTrocando(grupo.id)} activeOpacity={0.85}>
                                            <Text style={styles.trocarTexto}>Trocar</Text>
                                        </TouchableOpacity>
                                    ) : null}
                                </View>
                                {grupo.itens.map((linha) => {
                                    const aviso = avisoSaldo(linha.codigo, linha.saldo, linha.unidade);
                                    const foto = resolvePhotoUri(linha);
                                    return (
                                        <View key={linha.id} style={[styles.linha, (aviso || linha.erro) && styles.linhaAlerta]}>
                                            {foto ? (
                                                <Image source={{ uri: foto }} style={styles.thumb} resizeMode="cover" />
                                            ) : (
                                                <View style={[styles.thumb, styles.fotoVazia]}><Text>📦</Text></View>
                                            )}
                                            <View style={{ flex: 1 }}>
                                                <Text style={[styles.linhaNome, (aviso || linha.erro) && styles.linhaNomeAlerta]} numberOfLines={2}>{linha.descricao}</Text>
                                                <Text style={styles.linhaQtd}>
                                                    {qtyText(linha)}{linha.tipo_custodia ? ` • ${linha.tipo_custodia === 'permanente' ? 'permanente' : 'diária'}` : ''}
                                                </Text>
                                                {aviso ? <Text style={styles.alerta}>⚠ {aviso}</Text> : null}
                                                {linha.erro ? <Text style={styles.alerta}>✖ {linha.erro}</Text> : null}
                                            </View>
                                            <View style={styles.linhaAcoes}>
                                                <View style={styles.mini}>
                                                    <TouchableOpacity style={styles.miniBtn} onPress={() => mudarQtd(grupo.id, linha.id, -1)} activeOpacity={0.8}>
                                                        <Text style={styles.miniTexto}>−</Text>
                                                    </TouchableOpacity>
                                                    <Text style={styles.miniValor}>{fmt(linha.quantidade)}</Text>
                                                    <TouchableOpacity style={styles.miniBtn} onPress={() => mudarQtd(grupo.id, linha.id, 1)} activeOpacity={0.8}>
                                                        <Text style={styles.miniTexto}>+</Text>
                                                    </TouchableOpacity>
                                                </View>
                                                <TouchableOpacity style={styles.remover} onPress={() => remover(grupo.id, linha.id)} activeOpacity={0.85}>
                                                    <Text style={styles.removerTexto}>Remover</Text>
                                                </TouchableOpacity>
                                            </View>
                                        </View>
                                    );
                                })}
                            </View>
                        ))}

                        <TouchableOpacity style={[styles.button, styles.buttonSaida, enviando && styles.buttonOff]} onPress={confirmarSaida} disabled={enviando} activeOpacity={0.85}>
                            {enviando ? (
                                <ActivityIndicator color={heroPalette.bg} />
                            ) : (
                                <Text style={styles.buttonText}>Dar saída em tudo · {totalLinhas} {totalLinhas === 1 ? 'item' : 'itens'}</Text>
                            )}
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.limpar} onPress={limpar} disabled={enviando} activeOpacity={0.8}>
                            <Text style={styles.limparTexto}>Limpar fila</Text>
                        </TouchableOpacity>
                    </>
                ) : null}
            </ScrollView>

            <Modal visible={Boolean(trocando)} transparent animationType="fade" onRequestClose={() => setTrocando(null)}>
                <TouchableOpacity style={styles.pickerBackdrop} activeOpacity={1} onPress={() => setTrocando(null)}>
                    <View style={styles.pickerPanel} onStartShouldSetResponder={() => true}>
                        <Text style={styles.pickerTitle}>Trocar colaborador</Text>
                        <View style={styles.pickerBusca}>
                            <TextInput
                                style={[styles.input, styles.inputText]}
                                value={buscaTroca}
                                onChangeText={setBuscaTroca}
                                placeholder="Nome ou matrícula"
                                placeholderTextColor="#94a3b8"
                                autoCorrect={false}
                            />
                        </View>
                        <FlatList
                            data={filterUsers(usuarios, buscaTroca).slice(0, 40)}
                            keyExtractor={(u) => String(u.matricula)}
                            keyboardShouldPersistTaps="handled"
                            ListEmptyComponent={usuarios.length ? null : <ActivityIndicator color={heroPalette.primaryStrong} style={{ marginVertical: 24 }} />}
                            renderItem={({ item: u }) => (
                                <TouchableOpacity
                                    style={styles.pickerRow}
                                    onPress={() => trocarPara(trocando, { matricula: String(u.matricula), nome: u.nome, cargo: u.cargo || null })}
                                >
                                    <Text style={styles.pickerRowText}>{u.nome}</Text>
                                    <Text style={styles.listaDetalhe}>{[u.cargo || u.setor, u.matricula].filter(Boolean).join(' · ')}</Text>
                                </TouchableOpacity>
                            )}
                        />
                    </View>
                </TouchableOpacity>
            </Modal>

            <DoneModal done={done} />
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: heroPalette.bg },
    scroll: { padding: 16, paddingBottom: 40 },
    label: { color: heroPalette.textSoft, fontSize: 14, fontWeight: '800', marginTop: 16, marginBottom: 8 },
    input: { backgroundColor: '#fff', color: '#0f172a', borderRadius: 14, paddingHorizontal: 16, height: 54, fontSize: 20, fontWeight: '800' },
    inputText: { fontSize: 16, fontWeight: '700' },
    lista: { marginTop: 6, borderRadius: 12, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, overflow: 'hidden' },
    listaLinha: { paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    listaNome: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    listaDetalhe: { color: heroPalette.textMuted, fontSize: 12, marginTop: 2 },
    fixo: { height: 54, borderRadius: 14, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, justifyContent: 'center', paddingHorizontal: 16 },
    fixoTexto: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    scanButton: { height: 56, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    scanText: { color: heroPalette.bg, fontSize: 16, fontWeight: '900' },
    codigoRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
    buscarBtn: { width: 96, height: 54, borderRadius: 14, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    buscarTexto: { color: heroPalette.text, fontSize: 15, fontWeight: '800' },
    atual: { padding: 14, borderRadius: 18, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, ...heroSoftShadow },
    atualTopo: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    foto: { width: 64, height: 64, borderRadius: 12, backgroundColor: '#fff' },
    fotoVazia: { alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    fotoVaziaTexto: { fontSize: 22 },
    atualNome: { color: heroPalette.text, fontSize: 16, fontWeight: '800' },
    atualMeta: { color: heroPalette.textMuted, fontSize: 13, marginTop: 2 },
    fechar: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: heroPalette.panelAlt },
    fecharTexto: { color: heroPalette.textSoft, fontSize: 16, fontWeight: '900' },
    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    chip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 999, backgroundColor: heroPalette.panelAlt, borderWidth: 1, borderColor: heroPalette.border },
    chipOn: { backgroundColor: heroPalette.primaryStrong, borderColor: heroPalette.primaryStrong },
    chipText: { color: heroPalette.textSoft, fontSize: 15, fontWeight: '800' },
    chipTextOn: { color: heroPalette.bg },
    stepper: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 12 },
    stepBtn: { width: 54, height: 54, borderRadius: 14, backgroundColor: heroPalette.panelAlt, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    stepTexto: { color: heroPalette.text, fontSize: 26, fontWeight: '800' },
    stepInput: { flex: 1, textAlign: 'center' },
    previa: { color: heroPalette.text, fontSize: 15, fontWeight: '700', marginTop: 8 },
    alerta: { color: '#f87171', fontSize: 13, fontWeight: '800', marginTop: 4 },
    button: { marginTop: 16, height: 56, borderRadius: 16, backgroundColor: heroPalette.primaryStrong, alignItems: 'center', justifyContent: 'center' },
    buttonSaida: { marginTop: 18 },
    buttonOff: { opacity: 0.5 },
    buttonText: { color: heroPalette.bg, fontSize: 17, fontWeight: '900' },
    grupo: { marginBottom: 12, borderRadius: 18, backgroundColor: heroPalette.panel, borderWidth: 1, borderColor: heroPalette.border, overflow: 'hidden' },
    grupoTopo: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, backgroundColor: heroPalette.panelAlt },
    grupoNome: { color: heroPalette.text, fontSize: 15, fontWeight: '900' },
    grupoLocal: { color: heroPalette.textSoft, fontSize: 12, fontWeight: '700', marginTop: 2 },
    trocar: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: heroPalette.border },
    trocarTexto: { color: heroPalette.text, fontSize: 13, fontWeight: '800' },
    linha: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 10, borderTopWidth: 1, borderTopColor: heroPalette.border },
    linhaAlerta: { backgroundColor: 'rgba(239, 68, 68, 0.12)' },
    thumb: { width: 44, height: 44, borderRadius: 10, backgroundColor: '#fff' },
    linhaNome: { color: heroPalette.text, fontSize: 14, fontWeight: '800' },
    linhaNomeAlerta: { color: '#f87171' },
    linhaQtd: { color: heroPalette.textSoft, fontSize: 13, fontWeight: '700', marginTop: 2 },
    linhaAcoes: { alignItems: 'flex-end', gap: 6 },
    mini: { flexDirection: 'row', alignItems: 'center', gap: 4 },
    miniBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: heroPalette.panelAlt, borderWidth: 1, borderColor: heroPalette.border, alignItems: 'center', justifyContent: 'center' },
    miniTexto: { color: heroPalette.text, fontSize: 18, fontWeight: '800' },
    miniValor: { minWidth: 30, textAlign: 'center', color: heroPalette.text, fontSize: 15, fontWeight: '900' },
    remover: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: '#dc2626' },
    removerTexto: { color: '#fff', fontSize: 12, fontWeight: '900' },
    limpar: { alignSelf: 'center', marginTop: 14, paddingHorizontal: 16, paddingVertical: 8 },
    limparTexto: { color: heroPalette.textMuted, fontSize: 14, fontWeight: '800' },
    pickerBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(2, 6, 23, 0.6)' },
    pickerPanel: { maxHeight: '75%', backgroundColor: heroPalette.panel, borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingTop: 16, paddingBottom: 24, borderWidth: 1, borderColor: heroPalette.border },
    pickerTitle: { color: heroPalette.textMuted, fontSize: 13, fontWeight: '800', paddingHorizontal: 20, paddingBottom: 8 },
    pickerBusca: { paddingHorizontal: 16, paddingBottom: 8 },
    pickerRow: { paddingHorizontal: 20, paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: heroPalette.border },
    pickerRowText: { color: heroPalette.text, fontSize: 16, fontWeight: '700' },
});
