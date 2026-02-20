import React, { useMemo, useState, useEffect } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Alert,
    ScrollView,
    KeyboardAvoidingView,
    Platform,
    ActivityIndicator,
    FlatList,
    Switch,
    Modal,
} from 'react-native';
import ApiService from '../services/api';

function sanitizeIntText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9]/g, '');
}

function sanitizeFloatText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9.,]/g, '').replace(',', '.');
}

const LIQUID_PRODUCT_TYPES = [
    {
        id: 'massa_acrilica',
        label: 'Massa Acrílica / Massa Corrida',
        default_unit: 'quilo',
        keywords: ['massa acrilica', 'massa corrida'],
    },
    {
        id: 'tinta_piso_base_agua',
        label: 'Tinta para Piso (base água / acrílica)',
        default_unit: 'litro',
        keywords: ['tinta piso', 'piso acrilica', 'piso base agua'],
    },
    {
        id: 'tinta_epoxi_piso',
        label: 'Tinta Epóxi para Piso (bicomp / industrial)',
        default_unit: 'litro',
        keywords: ['epoxi', 'epóxi', 'bicomp', 'epoxi piso'],
    },
    {
        id: 'tinta_acrilica',
        label: 'Tinta Acrílica (padrão, PVA, semi-brilho, fosca)',
        default_unit: 'litro',
        keywords: ['tinta acrilica', 'tinta pva', 'tinta fosca', 'tinta semi'],
    },
    {
        id: 'resina_multuso',
        label: 'Resina Multiuso (base água)',
        default_unit: 'litro',
        keywords: ['resina', 'multiuso'],
    },
    {
        id: 'tinta_esmalte',
        label: 'Tinta Esmalte (base solvente)',
        default_unit: 'litro',
        keywords: ['tinta esmalte', 'esmalte'],
    },
    {
        id: 'impermeabilizante',
        label: 'Impermeabilizante (acrílico / borracha líquida)',
        default_unit: 'litro',
        keywords: ['impermeabilizante', 'borracha liquida', 'acrilico'],
    },
    {
        id: 'cloro_granulado',
        label: 'Cloro Granulado HTH (hipoclorito de cálcio 65%)',
        default_unit: 'quilo',
        keywords: ['cloro', 'cloro granulado', 'hipoclorito', 'hth'],
    },
];

const LIQUID_FRACTIONS = Array.from({ length: 19 }, (_, i) => [1, i + 2]);

function normalizeText(value) {
    if (!value) return '';
    return value
        .toString()
        .trim()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');
}

function detectLiquidType(categoria, descricao) {
    const texto = `${normalizeText(categoria)} ${normalizeText(descricao)}`.trim();
    if (!texto) return null;
    return LIQUID_PRODUCT_TYPES.find((entry) =>
        entry.keywords.some((kw) => texto.includes(normalizeText(kw)))
    );
}

export default function RetiradaScreen({ navigation, route }) {
    const user = route.params?.user;
    const item = route.params?.item;
    const tipo = route.params?.tipo;
    const defaultQuantity = route.params?.defaultQuantity;
    const multi = route.params?.multi === true;
    const scannedItem = route.params?.scannedItem;
    const fracionada = route.params?.fracionada === true;

    // Estado para modo multi
    const [itensRetirada, setItensRetirada] = useState([]);
    const [itemAtualId, setItemAtualId] = useState(0);

    // Estado do item atual sendo editado
    const [itemAtual, setItemAtual] = useState({
        item: null,
        quantidade: '',
    });

    // Estados compartilhados (usados tanto em single quanto multi)
    const [localServico, setLocalServico] = useState('');
    const [loading, setLoading] = useState(false);

    // Custódia (apenas ferramentas)
    const [tipoCustodia, setTipoCustodia] = useState('temporaria');

    // Estados para fração (apenas single)
    const [usarFracao, setUsarFracao] = useState(fracionada);
    const [tipoLiquido, setTipoLiquido] = useState(null);
    const [fracaoSelecionada, setFracaoSelecionada] = useState(null);
    const [totalEmbalagem, setTotalEmbalagem] = useState('');

    // Estados para usuário retirante
    const [usuarios, setUsuarios] = useState([]);
    const [retiranteBusca, setRetiranteBusca] = useState('');
    const [retiranteSelecionado, setRetiranteSelecionado] = useState(null);
    const [showAutocompleteLista, setShowAutocompleteLista] = useState(false);

    // Estados para modal de embalagens (igual Flask web)
    const [showModalEmbalagem, setShowModalEmbalagem] = useState(false);
    const [tipoRetiradaEmbalagem, setTipoRetiradaEmbalagem] = useState(null); // 'caixas' ou 'unidades'
    const [quantidadeCaixas, setQuantidadeCaixas] = useState('');
    const [quantidadeUnidades, setQuantidadeUnidades] = useState('');

    const canChooseRetirante = useMemo(() => {
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

    useEffect(() => {
        if (!canChooseRetirante) {
            if (userMatricula) {
                const selfUser = {
                    matricula: userMatricula,
                    nome: userNome || userMatricula,
                    cargo: user?.cargo || null,
                    setor: user?.setor || null,
                };
                setRetiranteSelecionado(selfUser);
                setRetiranteBusca(selfUser.nome);
                setShowAutocompleteLista(false);
            }
            return;
        }

        carregarUsuarios();
    }, [canChooseRetirante, userMatricula, userNome, user]);

    useEffect(() => {
        if (multi) {
            // Modo múltiplo: inicializa sem item
            setItemAtual({ item: null, quantidade: '1' });
        } else if (item) {
            // Modo single: inicializa com o item recebido
            setItemAtual({
                item,
                quantidade: defaultQuantity != null && String(defaultQuantity).trim() !== '' 
                    ? sanitizeIntText(defaultQuantity) 
                    : '1'
            });
            const detected = detectLiquidType(item?.categoria, item?.descricao);
            if (detected) {
                setTipoLiquido(detected);
            }
        }
    }, [multi, item, defaultQuantity]);

    useEffect(() => {
        if (fracionada && !multi) {
            setUsarFracao(true);
            if (navigation?.setOptions) {
                navigation.setOptions({ title: 'Retirada Fracionada' });
            }
        }
    }, [fracionada, multi, navigation]);

    // Processar item escaneado no modo múltiplo
    useEffect(() => {
        if (multi && scannedItem) {
            setItemAtual({
                item: scannedItem,
                quantidade: '1',
            });
            // Limpar o scannedItem dos parâmetros para evitar reprocessamento
            navigation.setParams({ scannedItem: null });
        }
    }, [scannedItem, multi]);

    const carregarUsuarios = async () => {
        const lista = await ApiService.getUsuarios();
        setUsuarios(lista);
    };

    const categoriaLower = useMemo(() => {
        return (itemAtual?.item?.categoria || '').toString().trim().toLowerCase();
    }, [itemAtual]);

    const isFerramenta = useMemo(() => {
        if (!categoriaLower) return false;
        return categoriaLower === 'ferramentas' || categoriaLower.includes('ferrament');
    }, [categoriaLower]);

    const saldoAtual = useMemo(() => {
        const q = Number(itemAtual?.item?.quantidade ?? 0);
        return Number.isFinite(q) ? Number(q.toFixed(6)) : 0;
    }, [itemAtual]);

    const unidadeSaldoTotalFracionada = useMemo(() => {
        const unit = (tipoLiquido?.default_unit || '').toString().trim().toLowerCase();
        if (unit === 'quilo') return 'kg';
        return 'L';
    }, [tipoLiquido]);

    const capacidadeEmbalagemFracionada = useMemo(() => {
        const fromInput = parseFloat(sanitizeFloatText(totalEmbalagem));
        if (Number.isFinite(fromInput) && fromInput > 0) return fromInput;
        const fromItem = Number(itemAtual?.item?.unidades_por_embalagem);
        if (Number.isFinite(fromItem) && fromItem > 0) return fromItem;
        return null;
    }, [totalEmbalagem, itemAtual]);

    const saldoTotalFracionada = useMemo(() => {
        if (!usarFracao) return null;
        if (!capacidadeEmbalagemFracionada) return null;
        const total = saldoAtual * capacidadeEmbalagemFracionada;
        if (!Number.isFinite(total)) return null;
        return Number(total.toFixed(2));
    }, [usarFracao, saldoAtual, capacidadeEmbalagemFracionada]);

    useEffect(() => {
        // Reset padrão ao trocar item (evita manter permanente por engano)
        setTipoCustodia('temporaria');
    }, [itemAtual?.item?.id, itemAtual?.item?.codigo_barras]);

    // Verificar se item tem sistema de embalagens
    const itemTemEmbalagens = useMemo(() => {
        const item = itemAtual?.item;
        if (!item) return false;
        return Boolean(
            item.tipo_embalagem_novo && 
            item.unidades_por_embalagem && 
            Number(item.unidades_por_embalagem) > 0
        );
    }, [itemAtual]);

    const getNomeEmbalagem = (plural = false) => {
        const tipo = itemAtual?.item?.tipo_embalagem_novo;
        if (!tipo) return plural ? 'embalagens' : 'embalagem';
        const nomes = {
            lata: plural ? 'latas' : 'lata',
            rolo: plural ? 'rolos' : 'rolo',
            pacote: plural ? 'pacotes' : 'pacote',
            caixa: plural ? 'caixas' : 'caixa',
            litro: plural ? 'litros' : 'litro',
            balde: plural ? 'baldes' : 'balde',
        };
        return nomes[tipo] || (plural ? 'embalagens' : 'embalagem');
    };

    const usuariosFiltrados = useMemo(() => {
        if (!retiranteBusca.trim()) return usuarios;
        const busca = retiranteBusca.toLowerCase();
        return usuarios.filter((u) =>
            u.nome.toLowerCase().includes(busca) ||
            (u.matricula || '').toString().includes(busca)
        );
    }, [retiranteBusca, usuarios]);

    const titulo = useMemo(() => {
        if (multi) return 'Retirada Múltipla';
        if (tipo === 'ferramenta' || isFerramenta) return 'Retirada de Ferramenta';
        return 'Retirada de Material';
    }, [multi, tipo, isFerramenta]);

    // Adicionar item à lista (modo múltiplo)
    const handleAdicionarItem = () => {
        if (!itemAtual.item) {
            Alert.alert('Erro', 'Selecione um item para adicionar.');
            return;
        }

        const quantidadeInt = parseInt(sanitizeIntText(itemAtual.quantidade), 10);
        if (Number.isNaN(quantidadeInt) || quantidadeInt <= 0) {
            Alert.alert('Erro', 'Informe uma quantidade válida (inteiro > 0).');
            return;
        }

        // Clonar o item atual e adicionar à lista com id único
        const novoItem = {
            id: itemAtualId,
            item: { ...itemAtual.item },
            quantidade: String(quantidadeInt),
            tipo_custodia: isFerramenta ? tipoCustodia : undefined,
        };

        setItensRetirada([...itensRetirada, novoItem]);
        setItemAtualId(itemAtualId + 1);

        // Resetar formulário para o próximo item
        setItemAtual({ item: null, quantidade: '1' });
        setTipoCustodia('temporaria');

        Alert.alert('Sucesso', 'Item adicionado! Escaneie o próximo item.');
    };

    // Remover item da lista
    const handleRemoverItem = (id) => {
        setItensRetirada(itensRetirada.filter(entry => entry.id !== id));
    };

    // Finalizar retirada (modo múltiplo - envio consolidado)
    const handleFinalizarRetiradaMultipla = async () => {
        if (itensRetirada.length === 0) {
            Alert.alert('Erro', 'Adicione ao menos um item para finalizar a retirada.');
            return;
        }

        if (!retiranteSelecionado) {
            Alert.alert('Erro', 'Selecione quem está retirando.');
            return;
        }

        // Validação antecipada dos itens
        const itensInvalidos = itensRetirada.filter(entry => {
            const codigo = String(entry?.item?.id || entry?.item?.codigo_barras || '').trim();
            const qty = parseInt(sanitizeIntText(entry?.quantidade || ''), 10);
            return !codigo || Number.isNaN(qty) || qty <= 0;
        });

        if (itensInvalidos.length > 0) {
            Alert.alert('Erro', 'Alguns itens possuem informações inválidas. Verifique e tente novamente.');
            return;
        }

        // Confirmação com preview dos itens
        const totalItens = itensRetirada.length;
        const resumoItens = itensRetirada.slice(0, 3).map(e => 
            `• ${e.item.descricao} (${e.quantidade})`
        ).join('\n');
        const maisItens = totalItens > 3 ? `\n...e mais ${totalItens - 3} item(ns)` : '';

        Alert.alert(
            'Confirmar Retirada Múltipla',
            `${totalItens} item(ns) serão retirados por:\n\n👤 ${retiranteSelecionado.nome}\n📍 ${localServico || 'Não informado'}\n\n${resumoItens}${maisItens}`,
            [
                { text: 'Cancelar', style: 'cancel' },
                {
                    text: 'Confirmar',
                    onPress: async () => {
                        setLoading(true);
                        try {
                            // Preparar payload otimizado
                            const itensPayload = itensRetirada.map(entry => ({
                                codigo: String(entry?.item?.id || entry?.item?.codigo_barras || '').trim(),
                                quantidade: parseInt(sanitizeIntText(entry?.quantidade || ''), 10),
                                tipo_custodia: entry?.tipo_custodia,
                            }));

                            // Enviar tudo em uma única requisição
                            const result = await ApiService.registrarRetiradaMultipla({
                                itens: itensPayload,
                                matricula_retirante: String(retiranteSelecionado?.matricula || '').trim(),
                                local_servico: String(localServico || '').toUpperCase(),
                            });

                            if (result.success && result.offline) {
                                Alert.alert(
                                    'Registrado Offline',
                                    'Retirada múltipla salva localmente. Ela será sincronizada quando houver conexão.',
                                    [
                                        {
                                            text: 'Nova Retirada',
                                            onPress: () => {
                                                setItensRetirada([]);
                                                setItemAtual({ item: null, quantidade: '1' });
                                                setItemAtualId(0);
                                                setLocalServico('');
                                            }
                                        },
                                        { text: 'Voltar', onPress: () => navigation.goBack() }
                                    ]
                                );
                                return;
                            }

                            if (result.success) {
                                const sucessos = result.resultados?.filter(r => r.success) || [];
                                const falhas = result.resultados?.filter(r => !r.success) || [];

                                if (falhas.length > 0) {
                                    const listaFalhas = falhas.map(f => 
                                        `• ${f.codigo}: ${f.message}`
                                    ).join('\n');
                                    
                                    Alert.alert(
                                        'Retirada Parcial',
                                        `✅ ${sucessos.length} item(ns) retirado(s) com sucesso\n❌ ${falhas.length} item(ns) falharam:\n\n${listaFalhas}`,
                                        [
                                            {
                                                text: 'Nova Retirada',
                                                onPress: () => {
                                                    setItensRetirada([]);
                                                    setItemAtual({ item: null, quantidade: '1' });
                                                    setItemAtualId(0);
                                                    setLocalServico('');
                                                }
                                            },
                                            { text: 'Voltar', onPress: () => navigation.goBack() }
                                        ]
                                    );
                                } else {
                                    Alert.alert(
                                        '✅ Sucesso!',
                                        `${sucessos.length} item(ns) retirado(s) por ${retiranteSelecionado.nome}\n\n📱 Notificação enviada via Telegram`,
                                        [
                                            {
                                                text: 'Nova Retirada',
                                                onPress: () => {
                                                    setItensRetirada([]);
                                                    setItemAtual({ item: null, quantidade: '1' });
                                                    setItemAtualId(0);
                                                    setLocalServico('');
                                                }
                                            },
                                            { text: 'Voltar', onPress: () => navigation.goBack() }
                                        ]
                                    );
                                }
                            } else {
                                Alert.alert('Erro', result.message || 'Falha ao processar retirada múltipla');
                            }
                        } catch (error) {
                            Alert.alert(
                                'Erro de Conexão',
                                'Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.'
                            );
                        } finally {
                            setLoading(false);
                        }
                    }
                }
            ]
        );
    };

    // Finalizar retirada single
    const handleSubmitSingle = async () => {
        // Se o item tem embalagens E não é fração, abre o modal primeiro
        if (itemTemEmbalagens && !usarFracao && !tipoRetiradaEmbalagem) {
            setShowModalEmbalagem(true);
            return;
        }

        const quantidadeInt = parseInt(sanitizeIntText(itemAtual.quantidade), 10);
        if (!usarFracao && !itemTemEmbalagens) {
            if (Number.isNaN(quantidadeInt) || quantidadeInt <= 0) {
                Alert.alert('Erro', 'Informe uma quantidade válida (inteiro > 0).');
                return;
            }
        }

        if (!retiranteSelecionado) {
            Alert.alert('Erro', 'Selecione quem está retirando.');
            return;
        }

        if (!itemAtual?.item?.id && !itemAtual?.item?.codigo_barras) {
            Alert.alert('Erro', 'Item inválido. Volte e selecione novamente.');
            return;
        }

        setLoading(true);
        try {
            const codigo = String(itemAtual.item.id || itemAtual.item.codigo_barras).trim();
            const fracaoNumerador = fracaoSelecionada?.[0];
            const fracaoDenominador = fracaoSelecionada?.[1];
            const totalEmbalagemFloat = parseFloat(sanitizeFloatText(totalEmbalagem));

            if (usarFracao) {
                if (!tipoLiquido) {
                    Alert.alert('Erro', 'Selecione o tipo de produto líquido.');
                    return;
                }
                if (!fracaoNumerador || !fracaoDenominador) {
                    Alert.alert('Erro', 'Selecione uma fração válida.');
                    return;
                }
                if (!Number.isFinite(totalEmbalagemFloat) || totalEmbalagemFloat <= 0) {
                    Alert.alert('Erro', 'Informe a capacidade total da embalagem.');
                    return;
                }
            }

            // Montar payload com embalagens se aplicável
            const payload = {
                codigo,
                quantidade: usarFracao ? 1 : quantidadeInt,
                matricula_retirante: String(retiranteSelecionado?.matricula || '').trim(),
                local_servico: String(localServico || '').toUpperCase(),
                tipo_custodia: isFerramenta ? tipoCustodia : undefined,
                modo_fracionado: usarFracao,
                liquido_tipo_produto: tipoLiquido?.id,
                liquido_fracao_numerador: fracaoNumerador,
                liquido_fracao_denominador: fracaoDenominador,
                liquido_total_embalagem: usarFracao ? totalEmbalagemFloat : undefined,
            };

            // Adicionar dados de embalagem se selecionado
            if (itemTemEmbalagens && tipoRetiradaEmbalagem) {
                if (tipoRetiradaEmbalagem === 'caixas') {
                    const qtdCaixas = parseInt(sanitizeIntText(quantidadeCaixas), 10);
                    if (Number.isNaN(qtdCaixas) || qtdCaixas <= 0) {
                        Alert.alert('Erro', `Informe a quantidade de ${getNomeEmbalagem(true)} válida.`);
                        return;
                    }
                    payload.retirada_embalagens = qtdCaixas;
                    payload.retirada_unidades_soltas = 0;
                } else if (tipoRetiradaEmbalagem === 'unidades') {
                    const qtdUnidades = parseInt(sanitizeIntText(quantidadeUnidades), 10);
                    if (Number.isNaN(qtdUnidades) || qtdUnidades <= 0) {
                        Alert.alert('Erro', 'Informe a quantidade de unidades soltas válida.');
                        return;
                    }
                    payload.retirada_embalagens = 0;
                    payload.retirada_unidades_soltas = qtdUnidades;
                }
            }

            const result = await ApiService.registrarRetirada(payload);

            if (!result.success) {
                Alert.alert('Erro', result.message);
                return;
            }

            if (result.offline) {
                Alert.alert(
                    'Registrado Offline',
                    'Retirada salva localmente. Ela será sincronizada quando houver conexão.',
                    [
                        {
                            text: 'Nova Retirada',
                            onPress: () => {
                                setItemAtual({ item: null, quantidade: '1' });
                                setLocalServico('');
                                setTotalEmbalagem('');
                                setFracaoSelecionada(null);
                            }
                        },
                        { text: 'Voltar', onPress: () => navigation.goBack() }
                    ]
                );
                return;
            }

            const saidaId = result.data?.saida_id;
            const novoSaldo = result.data?.item?.saldo ?? result.data?.item?.quantidade;

            Alert.alert(
                'Sucesso',
                `Retirada registrada${saidaId ? ` (ID ${saidaId})` : ''}.\nNovo saldo: ${novoSaldo ?? 'OK'}`,
                [
                    {
                        text: 'Nova Retirada',
                        onPress: () => {
                            setItemAtual({ item: null, quantidade: '1' });
                            setLocalServico('');
                            setTotalEmbalagem('');
                            setFracaoSelecionada(null);
                            setTipoRetiradaEmbalagem(null);
                            setQuantidadeCaixas('');
                            setQuantidadeUnidades('');
                        }
                    },
                    { text: 'Voltar', onPress: () => navigation.goBack() }
                ]
            );
        } catch (e) {
            Alert.alert('Erro', 'Falha ao registrar retirada');
        } finally {
            setLoading(false);
        }
    };

    // Confirmar seleção do modal de embalagens
    const handleConfirmarModalEmbalagem = () => {
        if (!tipoRetiradaEmbalagem) {
            Alert.alert('Erro', 'Selecione o tipo de retirada.');
            return;
        }

        if (tipoRetiradaEmbalagem === 'caixas') {
            const qtd = parseInt(sanitizeIntText(quantidadeCaixas), 10);
            if (Number.isNaN(qtd) || qtd <= 0) {
                Alert.alert('Erro', `Informe a quantidade de ${getNomeEmbalagem(true)}.`);
                return;
            }
        } else if (tipoRetiradaEmbalagem === 'unidades') {
            const qtd = parseInt(sanitizeIntText(quantidadeUnidades), 10);
            if (Number.isNaN(qtd) || qtd <= 0) {
                Alert.alert('Erro', 'Informe a quantidade de unidades soltas.');
                return;
            }
        }

        setShowModalEmbalagem(false);
        // Chama o submit novamente com os dados preenchidos
        handleSubmitSingle();
    };

    // Buscar item por código manual (modo múltiplo)
    const handleBuscarItem = async () => {
        if (!itemAtual.codigoBusca || itemAtual.codigoBusca.trim() === '') {
            Alert.alert('Erro', 'Digite o código do item.');
            return;
        }

        try {
            const itemEncontrado = await ApiService.buscarItemPorCodigo(itemAtual.codigoBusca.trim());
            if (!itemEncontrado) {
                Alert.alert('Erro', 'Item não encontrado.');
                return;
            }

            setItemAtual({
                ...itemAtual,
                item: itemEncontrado,
                quantidade: '1',
                codigoBusca: '',
            });
        } catch (error) {
            Alert.alert('Erro', 'Falha ao buscar item.');
        }
    };

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <ScrollView
                contentContainerStyle={styles.scroll}
                keyboardShouldPersistTaps="handled"
            >
                <View style={styles.card}>
                    <Text style={styles.title}>{titulo}</Text>

                    {/* MODO MÚLTIPLO */}
                    {multi ? (
                        <>
                            {/* Lista de itens já adicionados */}
                            {itensRetirada.length > 0 && (
                                <View style={styles.listaItensBox}>
                                    <Text style={styles.listaItensTitle}>Itens adicionados ({itensRetirada.length})</Text>
                                    {itensRetirada.map((entry) => (
                                        <View key={entry.id} style={styles.itemAdicionadoCard}>
                                            <View style={styles.itemAdicionadoInfo}>
                                                <Text style={styles.itemAdicionadoNome}>
                                                    {(entry?.item?.descricao || entry?.item?.nome || '').toString()}
                                                </Text>
                                                <Text style={styles.itemAdicionadoDetalhe}>
                                                    Qtd: {entry.quantidade} | Cód: {entry?.item?.codigo_barras || entry?.item?.id || ''}
                                                </Text>
                                            </View>
                                            <TouchableOpacity
                                                style={styles.removeButton}
                                                onPress={() => handleRemoverItem(entry.id)}
                                            >
                                                <Text style={styles.removeButtonText}>✖</Text>
                                            </TouchableOpacity>
                                        </View>
                                    ))}
                                </View>
                            )}

                            {/* Formulário do item atual */}
                            <View style={styles.itemAtualBox}>
                                <Text style={styles.itemAtualTitle}>
                                    {itemAtual.item ? 'Item selecionado' : 'Adicionar novo item'}
                                </Text>

                                {itemAtual.item ? (
                                    <View style={styles.itemBox}>
                                        <Text style={styles.itemName}>
                                            {(itemAtual.item?.descricao || itemAtual.item?.nome || '').toString().toUpperCase()}
                                        </Text>
                                        <Text style={styles.itemLine}>
                                            Código: {(itemAtual.item?.codigo_barras || itemAtual.item?.id || '').toString()}
                                        </Text>
                                        <Text style={styles.itemLine}>Saldo atual: {saldoAtual}</Text>
                                    </View>
                                ) : (
                                    <View style={styles.buscarItemContainer}>
                                        <TextInput
                                            style={styles.input}
                                            value={itemAtual.codigoBusca || ''}
                                            onChangeText={(text) => setItemAtual({ ...itemAtual, codigoBusca: text })}
                                            placeholder="Digite o código do item"
                                            autoCapitalize="none"
                                        />
                                        <TouchableOpacity style={styles.buscarButton} onPress={handleBuscarItem}>
                                            <Text style={styles.buscarButtonText}>Buscar</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity 
                                            style={styles.scanButton} 
                                            onPress={() => navigation.navigate('Scanner', { mode: 'withdraw_multi', user, multiCallback: true })}
                                        >
                                            <Text style={styles.scanButtonText}>📷 Escanear</Text>
                                        </TouchableOpacity>
                                    </View>
                                )}

                                {itemAtual.item && (
                                    <View style={styles.inputGroup}>
                                        <Text style={styles.label}>Quantidade *</Text>
                                        <TextInput
                                            style={styles.input}
                                            value={itemAtual.quantidade}
                                            onChangeText={(text) => setItemAtual({ ...itemAtual, quantidade: sanitizeIntText(text) })}
                                            placeholder="Quantidade"
                                            keyboardType="numeric"
                                            returnKeyType="done"
                                        />
                                    </View>
                                )}

                                {itemAtual.item && (
                                    <TouchableOpacity
                                        style={styles.adicionarButton}
                                        onPress={handleAdicionarItem}
                                    >
                                        <Text style={styles.adicionarButtonText}>➕ Adicionar item</Text>
                                    </TouchableOpacity>
                                )}
                            </View>
                        </>
                    ) : (
                        /* MODO SINGLE */
                        <View style={styles.itemBox}>
                            <Text style={styles.itemName}>
                                {(itemAtual?.item?.descricao || itemAtual?.item?.nome || '').toString().toUpperCase()}
                            </Text>
                            <Text style={styles.itemLine}>
                                Código: {(itemAtual?.item?.codigo_barras || itemAtual?.item?.id || '').toString()}
                            </Text>
                            <Text style={styles.itemLine}>Saldo atual: {saldoAtual}</Text>
                            {!multi && usarFracao && saldoTotalFracionada != null && (
                                <Text style={styles.itemLine}>
                                    Saldo total em estoque: {saldoTotalFracionada} {unidadeSaldoTotalFracionada}
                                </Text>
                            )}
                        </View>
                    )}

                    {/* Campos comuns */}
                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Retirado por: *</Text>
                        <TextInput
                            style={styles.input}
                            value={retiranteBusca}
                            editable={canChooseRetirante}
                            onChangeText={(text) => {
                                if (!canChooseRetirante) return;
                                setRetiranteBusca(text);
                                setShowAutocompleteLista(true);
                                if (!text.trim()) setRetiranteSelecionado(null);
                            }}
                            onFocus={() => canChooseRetirante && setShowAutocompleteLista(true)}
                            placeholder="Digite o nome ou matrícula"
                            autoCapitalize="words"
                        />
                        {canChooseRetirante && showAutocompleteLista && usuariosFiltrados.length > 0 && (
                            <View style={styles.autocompleteContainer}>
                                <FlatList
                                    data={usuariosFiltrados.slice(0, 8)}
                                    keyExtractor={(item) => item.matricula}
                                    style={styles.autocompleteList}
                                    keyboardShouldPersistTaps="handled"
                                    renderItem={({ item }) => (
                                        <TouchableOpacity
                                            style={styles.autocompleteItem}
                                            onPress={() => {
                                                setRetiranteSelecionado(item);
                                                const labelCompleto = item.cargo
                                                    ? `${item.nome} (${item.cargo})`
                                                    : item.nome;
                                                setRetiranteBusca(labelCompleto);
                                                setShowAutocompleteLista(false);
                                            }}
                                        >
                                            <Text style={styles.autocompleteNome}>{item.nome}</Text>
                                            <Text style={styles.autocompleteDetalhe}>
                                                {item.cargo || item.setor || ''} | Mat: {item.matricula}
                                            </Text>
                                        </TouchableOpacity>
                                    )}
                                />
                            </View>
                        )}
                    </View>

                    {/* Fração apenas para modo single */}
                    {!multi && (
                        <View style={styles.inputGroup}>
                            <View style={styles.switchRow}>
                                <Text style={styles.label}>Retirada fracionada (líquidos)</Text>
                                <Switch
                                    value={usarFracao}
                                    onValueChange={(value) => {
                                        setUsarFracao(value);
                                    }}
                                />
                            </View>
                        </View>
                    )}

                    {!multi && usarFracao && (
                        <>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>Tipo do produto líquido *</Text>
                                <View style={styles.radioGroup}>
                                    {LIQUID_PRODUCT_TYPES.map((tipoItem) => {
                                        const selected = tipoLiquido?.id === tipoItem.id;
                                        return (
                                            <TouchableOpacity
                                                key={tipoItem.id}
                                                style={styles.radioRow}
                                                onPress={() => setTipoLiquido(tipoItem)}
                                            >
                                                <View style={[styles.radioOuter, selected && styles.radioOuterActive]}>
                                                    {selected && <View style={styles.radioInner} />}
                                                </View>
                                                <Text style={styles.radioLabel}>{tipoItem.label}</Text>
                                            </TouchableOpacity>
                                        );
                                    })}
                                </View>
                            </View>

                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>Fração *</Text>
                                <View style={styles.fractionGrid}>
                                    {LIQUID_FRACTIONS.map((fracao) => {
                                        const selected =
                                            fracaoSelecionada?.[0] === fracao[0]
                                            && fracaoSelecionada?.[1] === fracao[1];
                                        return (
                                            <TouchableOpacity
                                                key={`${fracao[0]}-${fracao[1]}`}
                                                style={[styles.fractionButton, selected && styles.fractionButtonActive]}
                                                onPress={() => setFracaoSelecionada(fracao)}
                                            >
                                                <Text style={[styles.fractionButtonText, selected && styles.fractionButtonTextActive]}>
                                                    {fracao[0]}/{fracao[1]}
                                                </Text>
                                            </TouchableOpacity>
                                        );
                                    })}
                                </View>
                            </View>

                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>Capacidade da embalagem *</Text>
                                <TextInput
                                    style={styles.input}
                                    value={totalEmbalagem}
                                    onChangeText={(text) => setTotalEmbalagem(sanitizeFloatText(text))}
                                    placeholder="Ex: 3.6"
                                    keyboardType="numeric"
                                    returnKeyType="next"
                                />
                            </View>
                        </>
                    )}

                    {!multi && !usarFracao && (
                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Quantidade *</Text>
                            <TextInput
                                style={styles.input}
                                value={itemAtual.quantidade}
                                onChangeText={(text) => setItemAtual({ ...itemAtual, quantidade: sanitizeIntText(text) })}
                                placeholder="Quantidade"
                                keyboardType="numeric"
                                returnKeyType="next"
                            />
                        </View>
                    )}

                    {isFerramenta && (
                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Custódia *</Text>
                            <View style={styles.custodiaRow}>
                                <TouchableOpacity
                                    style={[
                                        styles.custodiaButton,
                                        tipoCustodia === 'temporaria' && styles.custodiaButtonActive,
                                    ]}
                                    onPress={() => setTipoCustodia('temporaria')}
                                >
                                    <Text
                                        style={[
                                            styles.custodiaButtonText,
                                            tipoCustodia === 'temporaria' && styles.custodiaButtonTextActive,
                                        ]}
                                    >
                                        Diária
                                    </Text>
                                </TouchableOpacity>

                                <TouchableOpacity
                                    style={[
                                        styles.custodiaButton,
                                        tipoCustodia === 'permanente' && styles.custodiaButtonActive,
                                    ]}
                                    onPress={() => setTipoCustodia('permanente')}
                                >
                                    <Text
                                        style={[
                                            styles.custodiaButtonText,
                                            tipoCustodia === 'permanente' && styles.custodiaButtonTextActive,
                                        ]}
                                    >
                                        Permanente
                                    </Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    )}

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Local de Serviço</Text>
                        <TextInput
                            style={styles.input}
                            value={localServico}
                            onChangeText={(text) => setLocalServico(String(text ?? ''))}
                            placeholder="EX: BLOCO A - APTO 201"
                            autoCapitalize="none"
                            returnKeyType="next"
                            onBlur={() => setLocalServico((prev) => String(prev || '').toUpperCase())}
                            onSubmitEditing={() => setLocalServico((prev) => String(prev || '').toUpperCase())}
                            onEndEditing={() => setLocalServico((prev) => String(prev || '').toUpperCase())}
                        />
                    </View>

                    <TouchableOpacity
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={multi ? handleFinalizarRetiradaMultipla : handleSubmitSingle}
                        disabled={loading || (multi && itensRetirada.length === 0)}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>
                                {multi ? 'Finalizar Retirada Múltipla' : 'Registrar Retirada'}
                            </Text>
                        )}
                    </TouchableOpacity>
                </View>
            </ScrollView>

            {/* Modal de Embalagens (igual Flask web) */}
            <Modal
                visible={showModalEmbalagem}
                transparent
                animationType="fade"
                onRequestClose={() => setShowModalEmbalagem(false)}
            >
                <View style={styles.modalOverlay}>
                    <View style={styles.modalContainer}>
                        <Text style={styles.modalTitle}>📦 Tipo de Retirada</Text>
                        <Text style={styles.modalSubtitle}>
                            {itemAtual?.item?.descricao || 'Item'}
                        </Text>

                        <View style={styles.modalInfo}>
                            <Text style={styles.modalInfoText}>
                                • Estoque: {itemAtual?.item?.estoque_embalagens || 0} {getNomeEmbalagem(true)} + {itemAtual?.item?.estoque_unidades_soltas || 0} unidades soltas
                            </Text>
                            <Text style={styles.modalInfoText}>
                                • Unidades por {getNomeEmbalagem()}: {itemAtual?.item?.unidades_por_embalagem || 0}
                            </Text>
                        </View>

                        <View style={styles.modalOptions}>
                            <TouchableOpacity
                                style={[
                                    styles.modalOption,
                                    tipoRetiradaEmbalagem === 'caixas' && styles.modalOptionActive,
                                ]}
                                onPress={() => setTipoRetiradaEmbalagem('caixas')}
                            >
                                <Text style={[
                                    styles.modalOptionIcon,
                                    tipoRetiradaEmbalagem === 'caixas' && styles.modalOptionIconActive,
                                ]}>📦</Text>
                                <Text style={[
                                    styles.modalOptionTitle,
                                    tipoRetiradaEmbalagem === 'caixas' && styles.modalOptionTitleActive,
                                ]}>Retirar {getNomeEmbalagem(true)} completas</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[
                                    styles.modalOption,
                                    tipoRetiradaEmbalagem === 'unidades' && styles.modalOptionActive,
                                ]}
                                onPress={() => setTipoRetiradaEmbalagem('unidades')}
                            >
                                <Text style={[
                                    styles.modalOptionIcon,
                                    tipoRetiradaEmbalagem === 'unidades' && styles.modalOptionIconActive,
                                ]}>📏</Text>
                                <Text style={[
                                    styles.modalOptionTitle,
                                    tipoRetiradaEmbalagem === 'unidades' && styles.modalOptionTitleActive,
                                ]}>Retirar unidades soltas</Text>
                            </TouchableOpacity>
                        </View>

                        {tipoRetiradaEmbalagem === 'caixas' && (
                            <View style={styles.modalInputGroup}>
                                <Text style={styles.modalLabel}>Quantidade de {getNomeEmbalagem(true)}</Text>
                                <TextInput
                                    style={styles.modalInput}
                                    value={quantidadeCaixas}
                                    onChangeText={setQuantidadeCaixas}
                                    placeholder="Ex: 2"
                                    keyboardType="numeric"
                                    autoFocus
                                />
                            </View>
                        )}

                        {tipoRetiradaEmbalagem === 'unidades' && (
                            <View style={styles.modalInputGroup}>
                                <Text style={styles.modalLabel}>Quantidade de unidades soltas</Text>
                                <TextInput
                                    style={styles.modalInput}
                                    value={quantidadeUnidades}
                                    onChangeText={setQuantidadeUnidades}
                                    placeholder="Ex: 5"
                                    keyboardType="numeric"
                                    autoFocus
                                />
                            </View>
                        )}

                        <View style={styles.modalButtons}>
                            <TouchableOpacity
                                style={[styles.modalButton, styles.modalButtonCancel]}
                                onPress={() => {
                                    setShowModalEmbalagem(false);
                                    setTipoRetiradaEmbalagem(null);
                                    setQuantidadeCaixas('');
                                    setQuantidadeUnidades('');
                                }}
                            >
                                <Text style={styles.modalButtonTextCancel}>Cancelar</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={[styles.modalButton, styles.modalButtonConfirm]}
                                onPress={handleConfirmarModalEmbalagem}
                            >
                                <Text style={styles.modalButtonTextConfirm}>Confirmar</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                </View>
            </Modal>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    scroll: {
        padding: 16,
    },
    card: {
        backgroundColor: '#fff',
        padding: 20,
        borderRadius: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    title: {
        fontSize: 24,
        fontWeight: 'bold',
        color: '#333',
        marginBottom: 20,
        textAlign: 'center',
    },
    listaItensBox: {
        backgroundColor: '#f0f9ff',
        padding: 15,
        borderRadius: 8,
        marginBottom: 20,
        borderLeftWidth: 4,
        borderLeftColor: '#0ea5e9',
    },
    listaItensTitle: {
        fontSize: 16,
        fontWeight: '700',
        color: '#0369a1',
        marginBottom: 12,
    },
    itemAdicionadoCard: {
        backgroundColor: '#fff',
        padding: 12,
        borderRadius: 8,
        marginBottom: 8,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: '#bae6fd',
    },
    itemAdicionadoInfo: {
        flex: 1,
    },
    itemAdicionadoNome: {
        fontSize: 14,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 4,
    },
    itemAdicionadoDetalhe: {
        fontSize: 12,
        color: '#6b7280',
    },
    removeButton: {
        backgroundColor: '#ef4444',
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: 6,
        marginLeft: 8,
    },
    removeButtonText: {
        color: '#000',
        fontWeight: '700',
        fontSize: 14,
    },
    itemAtualBox: {
        backgroundColor: '#f8f8f8',
        padding: 15,
        borderRadius: 8,
        marginBottom: 20,
        borderLeftWidth: 4,
        borderLeftColor: '#10b981',
    },
    itemAtualTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: '#059669',
        marginBottom: 12,
    },
    buscarItemContainer: {
        gap: 10,
    },
    buscarButton: {
        backgroundColor: '#0d6efd',
        paddingVertical: 12,
        borderRadius: 8,
        alignItems: 'center',
    },
    buscarButtonText: {
        color: '#000',
        fontWeight: '600',
        fontSize: 14,
    },
    scanButton: {
        backgroundColor: '#6610f2',
        paddingVertical: 12,
        borderRadius: 8,
        alignItems: 'center',
    },
    scanButtonText: {
        color: '#000',
        fontWeight: '600',
        fontSize: 14,
    },
    adicionarButton: {
        backgroundColor: '#10b981',
        paddingVertical: 12,
        borderRadius: 8,
        alignItems: 'center',
        marginTop: 10,
    },
    adicionarButtonText: {
        color: '#000',
        fontWeight: '600',
        fontSize: 14,
    },
    itemBox: {
        backgroundColor: '#f8f8f8',
        padding: 15,
        borderRadius: 8,
        marginBottom: 20,
        borderLeftWidth: 4,
        borderLeftColor: '#007bff',
    },
    itemName: {
        fontSize: 18,
        fontWeight: 'bold',
        color: '#333',
        marginBottom: 8,
    },
    itemLine: {
        fontSize: 14,
        color: '#666',
        marginTop: 4,
    },
    inputGroup: {
        marginBottom: 16,
    },
    switchRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#333',
        marginBottom: 8,
    },
    input: {
        backgroundColor: '#fff',
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
    },
    radioGroup: {
        gap: 8,
        marginTop: 4,
    },
    radioRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingVertical: 8,
        paddingHorizontal: 10,
        borderWidth: 1,
        borderColor: '#e5e7eb',
        borderRadius: 10,
        backgroundColor: '#f9fafb',
    },
    radioOuter: {
        width: 20,
        height: 20,
        borderRadius: 10,
        borderWidth: 2,
        borderColor: '#9ca3af',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#fff',
    },
    radioOuterActive: {
        borderColor: '#0d6efd',
    },
    radioInner: {
        width: 10,
        height: 10,
        borderRadius: 5,
        backgroundColor: '#0d6efd',
    },
    radioLabel: {
        flex: 1,
        fontSize: 14,
        color: '#111827',
        fontWeight: '600',
    },
    fractionGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    fractionButton: {
        paddingVertical: 8,
        paddingHorizontal: 12,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#e5e7eb',
        backgroundColor: '#fff',
    },
    fractionButtonActive: {
        backgroundColor: '#0d6efd',
        borderColor: '#0d6efd',
    },
    fractionButtonText: {
        fontSize: 14,
        fontWeight: '600',
        color: '#111827',
    },
    fractionButtonTextActive: {
        color: '#000',
    },
    custodiaRow: {
        flexDirection: 'row',
        gap: 10,
    },
    custodiaButton: {
        flex: 1,
        borderWidth: 1,
        borderColor: '#d1d5db',
        paddingVertical: 10,
        borderRadius: 10,
        backgroundColor: '#fff',
        alignItems: 'center',
    },
    custodiaButtonActive: {
        backgroundColor: '#0d6efd',
        borderColor: '#0d6efd',
    },
    custodiaButtonText: {
        color: '#111827',
        fontWeight: '600',
    },
    custodiaButtonTextActive: {
        color: '#000',
    },
    inputText: {
        fontSize: 16,
        color: '#333',
    },
    textArea: {
        height: 80,
        textAlignVertical: 'top',
    },
    autocompleteContainer: {
        marginTop: 4,
        maxHeight: 200,
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        backgroundColor: '#fff',
        overflow: 'hidden',
    },
    autocompleteList: {
        flexGrow: 0,
    },
    autocompleteItem: {
        padding: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#f0f0f0',
    },
    autocompleteNome: {
        fontSize: 15,
        fontWeight: '600',
        color: '#333',
    },
    autocompleteDetalhe: {
        fontSize: 12,
        color: '#666',
        marginTop: 2,
    },
    button: {
        backgroundColor: '#007bff',
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
        marginTop: 10,
    },
    buttonDisabled: {
        backgroundColor: '#ccc',
    },
    buttonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: 'bold',
    },
    // Estilos do modal de embalagens
    modalOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20,
    },
    modalContainer: {
        backgroundColor: '#fff',
        borderRadius: 16,
        padding: 24,
        width: '100%',
        maxWidth: 500,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
        elevation: 8,
    },
    modalTitle: {
        fontSize: 22,
        fontWeight: '700',
        color: '#111827',
        textAlign: 'center',
        marginBottom: 8,
    },
    modalSubtitle: {
        fontSize: 15,
        color: '#6b7280',
       textAlign: 'center',
        marginBottom: 16,
    },
    modalInfo: {
        backgroundColor: '#f0f9ff',
        padding: 12,
        borderRadius: 8,
        marginBottom: 20,
        borderLeftWidth: 3,
        borderLeftColor: '#0ea5e9',
    },
    modalInfoText: {
        fontSize: 13,
        color: '#0369a1',
        marginBottom: 4,
    },
    modalOptions: {
        gap: 12,
        marginBottom: 20,
    },
    modalOption: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 16,
        borderWidth: 2,
        borderColor: '#e5e7eb',
        borderRadius: 12,
        backgroundColor: '#f9fafb',
    },
    modalOptionActive: {
        borderColor: '#0d6efd',
        backgroundColor: '#eff6ff',
    },
    modalOptionIcon: {
        fontSize: 28,
        marginRight: 12,
    },
    modalOptionIconActive: {
        // Ícone fica igual
    },
    modalOptionTitle: {
        flex: 1,
        fontSize: 16,
        fontWeight: '600',
        color: '#374151',
    },
    modalOptionTitleActive: {
        color: '#1e40af',
    },
    modalInputGroup: {
        marginBottom: 20,
    },
    modalLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: '#374151',
        marginBottom: 8,
    },
    modalInput: {
        backgroundColor: '#fff',
        borderWidth: 1,
        borderColor: '#d1d5db',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
    },
    modalButtons: {
        flexDirection: 'row',
        gap: 12,
    },
    modalButton: {
        flex: 1,
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
    },
    modalButtonCancel: {
        backgroundColor: '#f3f4f6',
        borderWidth: 1,
        borderColor: '#d1d5db',
    },
    modalButtonConfirm: {
        backgroundColor: '#0d6efd',
    },
    modalButtonTextCancel: {
        color: '#374151',
        fontSize: 15,
        fontWeight: '600',
    },
    modalButtonTextConfirm: {
        color: '#000',
        fontSize: 15,
        fontWeight: '600',
    },
});
