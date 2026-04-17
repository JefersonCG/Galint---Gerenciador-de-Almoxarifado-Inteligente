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
    Image,
} from 'react-native';
import ApiService from '../services/api';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

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
        id: 'tinta_asfaltica',
        label: 'Tinta Asfáltica',
        default_unit: 'litro',
        keywords: ['tinta asfaltica', 'asfaltica'],
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

function buildWithdrawalEntryKey(entry) {
    const codigo = String(entry?.item?.id || entry?.item?.codigo_barras || '').trim();
    const tipoCustodia = String(entry?.tipo_custodia || '').trim().toLowerCase();
    const tipoFerramenta = String(entry?.tipo_ferramenta || '').trim().toLowerCase();
    return [codigo, tipoCustodia, tipoFerramenta].join('::');
}

function resolveItemPhotoUri(item, baseURL) {
    const raw = String(item?.foto_url || item?.foto_path || '').trim();
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    if (!baseURL) return raw;
    if (raw.startsWith('/')) return `${baseURL}${raw}`;
    return `${baseURL}/static/${raw.replace(/^\/+/, '')}`;
}

function getItemCode(item) {
    return String(item?.id || item?.codigo_barras || '').trim();
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
        codigoBusca: '',
    });

    // Estados compartilhados (usados tanto em single quanto multi)
    const [localServico, setLocalServico] = useState('');
    const [loading, setLoading] = useState(false);

    // Custódia e tipo (apenas ferramentas)
    const [tipoCustodia, setTipoCustodia] = useState('temporaria');
    const [tipoFerramenta, setTipoFerramenta] = useState('diaria'); // 'diaria' ou 'permanente'

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

    // Estado para seletor de unidade de retirada
    const [unidadeRetirada, setUnidadeRetirada] = useState('principal'); // 'principal' ou 'secundaria'

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
            setItemAtual({ item: null, quantidade: '1', codigoBusca: '' });
        } else if (item) {
            // Modo single: inicializa com o item recebido
            setItemAtual({
                item,
                quantidade: defaultQuantity != null && String(defaultQuantity).trim() !== '' 
                    ? sanitizeIntText(defaultQuantity) 
                    : '1',
                codigoBusca: '',
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
                codigoBusca: '',
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

    // Formatar saldo com detalhes de unidade
    const saldoDetalhado = useMemo(() => {
        const item = itemAtual?.item;
        if (!item) return { principal: '0', secundario: null, unidadePrincipal: 'unidades' };
        
        const saldo = saldoAtual;
        const unidade = (item.unidade || 'Unidade').toString().trim();
        const unidadesNome = saldo === 1 ? 'unidade' : 'unidades';
        
        // Se tem unidades_por_embalagem (ex: 20 metros por rolo)
        const unidadesPorEmbalagem = Number(item.unidades_por_embalagem);
        const tipoEmbalagem = (item.tipo_embalagem_novo || '').toString().toLowerCase();
        
        if (Number.isFinite(unidadesPorEmbalagem) && unidadesPorEmbalagem > 0) {
            const totalSecundario = saldo * unidadesPorEmbalagem;
            const nomeEmbalagem = saldo === 1 
                ? (tipoEmbalagem || 'unidade')
                : (tipoEmbalagem === 'rolo' ? 'rolos' : 
                   tipoEmbalagem === 'lata' ? 'latas' : 
                         tipoEmbalagem === 'bombona' ? 'bombonas' : 
                   tipoEmbalagem === 'pacote' ? 'pacotes' : 
                   tipoEmbalagem === 'caixa' ? 'caixas' : 
                   tipoEmbalagem === 'balde' ? 'baldes' : 'unidades');
            
            return {
                principal: `${saldo} ${nomeEmbalagem}`,
                secundario: `${totalSecundario.toFixed(2)} ${unidade.toLowerCase()}`,
                unidadePrincipal: nomeEmbalagem
            };
        }
        
        // Caso padrão: apenas saldo + unidade
        return {
            principal: `${saldo} ${unidadesNome}`,
            secundario: null,
            unidadePrincipal: unidadesNome
        };
    }, [saldoAtual, itemAtual]);

    // Opções de unidade para retirada
    const opcoesUnidade = useMemo(() => {
        const item = itemAtual?.item;
        if (!item) return [];
        
        const opcoes = [];
        const unidadesPorEmbalagem = Number(item.unidades_por_embalagem);
        const tipoEmbalagem = (item.tipo_embalagem_novo || '').toString().toLowerCase();
        const unidade = (item.unidade || 'Unidade').toString().trim();
        
        // Opção principal: embalagem/unidade
        if (Number.isFinite(unidadesPorEmbalagem) && unidadesPorEmbalagem > 0) {
            const nomeEmbalagem = tipoEmbalagem === 'rolo' ? 'Rolo' : 
                                 tipoEmbalagem === 'lata' ? 'Lata' : 
                                 tipoEmbalagem === 'bombona' ? 'Bombona' : 
                                 tipoEmbalagem === 'pacote' ? 'Pacote' : 
                                 tipoEmbalagem === 'caixa' ? 'Caixa' : 
                                 tipoEmbalagem === 'balde' ? 'Balde' : 'Unidade';
            opcoes.push({
                id: 'principal',
                label: nomeEmbalagem,
                fator: 1
            });
            
            // Opção secundária: unidade base (metro, kg, litro, etc)
            opcoes.push({
                id: 'secundaria',
                label: unidade,
                fator: unidadesPorEmbalagem // Ex: 1 rolo = 20 metros, então fator é 20
            });
        } else {
            // Apenas uma opção: a unidade padrão
            opcoes.push({
                id: 'principal',
                label: unidade,
                fator: 1
            });
        }
        
        return opcoes;
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
            bombona: plural ? 'bombonas' : 'bombona',
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

    const localServicoNormalizado = useMemo(() => {
        return String(localServico || '').trim().toUpperCase();
    }, [localServico]);

    const fotoItemAtualUri = useMemo(() => {
        return resolveItemPhotoUri(itemAtual?.item, ApiService.baseURL);
    }, [itemAtual]);

    const galeriaRetiradaMultipla = useMemo(() => {
        const seen = new Set();
        return itensRetirada.reduce((acc, entry) => {
            const currentItem = entry?.item;
            const code = getItemCode(currentItem);
            const uri = resolveItemPhotoUri(currentItem, ApiService.baseURL);
            if (!uri || (code && seen.has(code))) {
                return acc;
            }
            if (code) {
                seen.add(code);
            }
            acc.push({
                key: code || `${acc.length}`,
                uri,
                descricao: String(currentItem?.descricao || currentItem?.nome || 'Item').trim(),
            });
            return acc;
        }, []).slice(0, 4);
    }, [itensRetirada]);

    const contextoObrigatorioOk = useMemo(() => {
        return Boolean(
            retiranteSelecionado?.matricula
            && String(retiranteSelecionado?.nome || '').trim()
            && localServicoNormalizado
        );
    }, [retiranteSelecionado, localServicoNormalizado]);

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
            tipo_ferramenta: isFerramenta ? tipoFerramenta : undefined,
        };

        const chaveNovoItem = buildWithdrawalEntryKey(novoItem);
        const existingIndex = itensRetirada.findIndex(
            (entry) => buildWithdrawalEntryKey(entry) === chaveNovoItem
        );
        const agrupouItemExistente = existingIndex !== -1;

        if (agrupouItemExistente) {
            setItensRetirada((currentItems) => currentItems.map((entry, index) => {
                if (index !== existingIndex) {
                    return entry;
                }

                const quantidadeAtual = parseInt(sanitizeIntText(entry?.quantidade || ''), 10) || 0;
                return {
                    ...entry,
                    quantidade: String(quantidadeAtual + quantidadeInt),
                };
            }));
        } else {
            setItensRetirada((currentItems) => [...currentItems, novoItem]);
        }

        if (!agrupouItemExistente) {
            setItemAtualId((currentId) => currentId + 1);
        }

        // Resetar formulário para o próximo item
        setItemAtual({ item: null, quantidade: '1', codigoBusca: '' });
        setTipoCustodia('temporaria');
        setTipoFerramenta('diaria');

        Alert.alert(
            'Sucesso',
            agrupouItemExistente
                ? 'Quantidade somada ao item já existente na lista.'
                : 'Item adicionado! Escaneie o próximo item.'
        );
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

        if (!localServicoNormalizado) {
            Alert.alert('Erro', 'Informe o local de serviço para concluir a retirada.');
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
            `${totalItens} item(ns) serão retirados por:\n\n👤 ${retiranteSelecionado.nome}\n📍 ${localServicoNormalizado}\n\n${resumoItens}${maisItens}`,
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
                                tipo_ferramenta: entry?.tipo_ferramenta,
                            }));

                            // Enviar tudo em uma única requisição
                            const result = await ApiService.registrarRetiradaMultipla({
                                itens: itensPayload,
                                matricula_retirante: String(retiranteSelecionado?.matricula || '').trim(),
                                local_servico: localServicoNormalizado,
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
                                                setItemAtual({ item: null, quantidade: '1', codigoBusca: '' });
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
                                                    setItemAtual({ item: null, quantidade: '1', codigoBusca: '' });
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
                                                    setItemAtual({ item: null, quantidade: '1', codigoBusca: '' });
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

        let quantidadeInt = parseInt(sanitizeIntText(itemAtual.quantidade), 10);
        
        // Converter quantidade baseado na unidade selecionada
        if (unidadeRetirada === 'secundaria' && opcoesUnidade.length > 1) {
            const unidadeSecundaria = opcoesUnidade.find(o => o.id === 'secundaria');
            if (unidadeSecundaria && unidadeSecundaria.fator > 0) {
                // Se usuário digitou em unidade secundária (metros, kg, litros), converter para principal
                const quantidadeOriginal = quantidadeInt;
                const quantidadePrincipal = quantidadeInt / unidadeSecundaria.fator;
                
                // Verificar se a conversão é exata
                if (!Number.isInteger(quantidadePrincipal)) {
                    const quantidadeArredondada = Math.ceil(quantidadePrincipal);
                    const totalReal = quantidadeArredondada * unidadeSecundaria.fator;
                    const unidadePrincipal = opcoesUnidade.find(o => o.id === 'principal');
                    const nomeSecundaria = unidadeSecundaria.label.toLowerCase();
                    const nomePrincipal = unidadePrincipal?.label || 'unidade';
                    
                    // Perguntar ao usuário se deseja arredondar
                    const confirmar = await new Promise((resolve) => {
                        Alert.alert(
                            'Atenção: Conversão de Unidade',
                            `A quantidade ${quantidadeOriginal} ${nomeSecundaria} não é divisível exatamente.\n\n` +
                            `Será retirado ${quantidadeArredondada} ${nomePrincipal}(s), totalizando ${totalReal} ${nomeSecundaria}.\n\n` +
                            `Deseja continuar?`,
                            [
                                { text: 'Cancelar', style: 'cancel', onPress: () => resolve(false) },
                                { text: 'Continuar', onPress: () => resolve(true) }
                            ]
                        );
                    });
                    
                    if (!confirmar) {
                        setLoading(false);
                        return;
                    }
                    
                    quantidadeInt = quantidadeArredondada;
                } else {
                    quantidadeInt = quantidadePrincipal;
                }
            }
        }
        
        if (!usarFracao && !itemTemEmbalagens) {
            if (Number.isNaN(quantidadeInt) || quantidadeInt <= 0) {
                Alert.alert('Erro', 'Informe uma quantidade válida (inteiro > 0).');
                setLoading(false);
                return;
            }
        }

        if (!retiranteSelecionado) {
            Alert.alert('Erro', 'Selecione quem está retirando.');
            return;
        }

        if (!localServicoNormalizado) {
            Alert.alert('Erro', 'Informe o local de serviço para concluir a retirada.');
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
                local_servico: localServicoNormalizado,
                tipo_custodia: isFerramenta ? tipoCustodia : undefined,
                tipo_ferramenta: isFerramenta ? tipoFerramenta : undefined,
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
                                setItemAtual({ item: null, quantidade: '1', codigoBusca: '' });
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
                    <View style={styles.heroBox}>
                        <Text style={styles.heroEyebrow}>Registro de saídas</Text>
                        <Text style={styles.title}>{titulo}</Text>
                        <Text style={styles.heroSubtitle}>
                            Fluxo alinhado ao web Flask, com menos ruído visual e confirmação obrigatória de retirante e local.
                        </Text>
                        <View style={styles.heroMetaRow}>
                            <View style={styles.heroMetaChip}>
                                <Text style={styles.heroMetaLabel}>Retirante</Text>
                                <Text style={styles.heroMetaValue} numberOfLines={1}>
                                    {retiranteSelecionado?.nome || 'Obrigatório'}
                                </Text>
                            </View>
                            <View style={styles.heroMetaChip}>
                                <Text style={styles.heroMetaLabel}>Local</Text>
                                <Text style={styles.heroMetaValue} numberOfLines={1}>
                                    {localServicoNormalizado || 'Obrigatório'}
                                </Text>
                            </View>
                            <View style={styles.heroMetaChip}>
                                <Text style={styles.heroMetaLabel}>Modo</Text>
                                <Text style={styles.heroMetaValue} numberOfLines={1}>
                                    {multi ? `${itensRetirada.length} item(ns)` : isFerramenta ? 'Ferramenta' : 'Material'}
                                </Text>
                            </View>
                        </View>
                    </View>

                    <View style={styles.hintsRow}>
                        <View style={styles.hintCard}>
                            <Text style={styles.hintIcon}>!</Text>
                            <Text style={styles.hintText}>Sem retirante e local a baixa não é liberada.</Text>
                        </View>
                        <View style={styles.hintCard}>
                            <Text style={styles.hintIcon}>i</Text>
                            <Text style={styles.hintText}>A foto do item acompanha a seleção e a retirada múltipla.</Text>
                        </View>
                    </View>

                    {/* MODO MÚLTIPLO */}
                    {multi ? (
                        <>
                            {/* Lista de itens já adicionados */}
                            {itensRetirada.length > 0 && (
                                <View style={styles.listaItensBox}>
                                    <Text style={styles.listaItensTitle}>Itens adicionados ({itensRetirada.length})</Text>
                                    {galeriaRetiradaMultipla.length > 0 && (
                                        <View style={styles.galleryStrip}>
                                            {galeriaRetiradaMultipla.map((photo) => (
                                                <Image
                                                    key={photo.key}
                                                    source={{ uri: photo.uri }}
                                                    style={styles.galleryThumb}
                                                    resizeMode="cover"
                                                />
                                            ))}
                                            {itensRetirada.length > galeriaRetiradaMultipla.length && (
                                                <View style={styles.galleryMoreBadge}>
                                                    <Text style={styles.galleryMoreText}>+{itensRetirada.length - galeriaRetiradaMultipla.length}</Text>
                                                </View>
                                            )}
                                        </View>
                                    )}
                                    {itensRetirada.map((entry) => (
                                        <View key={entry.id} style={styles.itemAdicionadoCard}>
                                            {resolveItemPhotoUri(entry?.item, ApiService.baseURL) ? (
                                                <Image
                                                    source={{ uri: resolveItemPhotoUri(entry?.item, ApiService.baseURL) }}
                                                    style={styles.itemThumb}
                                                    resizeMode="cover"
                                                />
                                            ) : (
                                                <View style={styles.itemThumbFallback}>
                                                    <Text style={styles.itemThumbFallbackText}>Sem foto</Text>
                                                </View>
                                            )}
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
                                        <View style={styles.itemPreviewRow}>
                                            {fotoItemAtualUri ? (
                                                <Image source={{ uri: fotoItemAtualUri }} style={styles.itemPhoto} resizeMode="cover" />
                                            ) : (
                                                <View style={styles.itemPhotoFallback}>
                                                    <Text style={styles.itemPhotoFallbackText}>Sem foto</Text>
                                                </View>
                                            )}
                                            <View style={styles.itemPreviewCopy}>
                                                <Text style={styles.itemName}>
                                                    {(itemAtual.item?.descricao || itemAtual.item?.nome || '').toString().toUpperCase()}
                                                </Text>
                                                <Text style={styles.itemLine}>
                                                    Código: {(itemAtual.item?.codigo_barras || itemAtual.item?.id || '').toString()}
                                                </Text>
                                                <Text style={styles.itemLine}>Saldo atual: {saldoDetalhado.principal}</Text>
                                                {saldoDetalhado.secundario && (
                                                    <Text style={styles.itemLineSecondary}>({saldoDetalhado.secundario} no total)</Text>
                                                )}
                                            </View>
                                        </View>
                                    </View>
                                ) : (
                                    <View style={styles.buscarItemContainer}>
                                        <View style={styles.labelRow}>
                                            <Text style={styles.label}>Código do item</Text>
                                            <Text style={styles.labelHint}>Busca rápida</Text>
                                        </View>
                                        <TextInput
                                            style={styles.input}
                                            value={itemAtual.codigoBusca || ''}
                                            onChangeText={(text) => setItemAtual({ ...itemAtual, codigoBusca: text })}
                                            placeholder="Digite o código do item"
                                            placeholderTextColor={heroPalette.textMuted}
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
                                        <View style={styles.labelRow}>
                                            <Text style={styles.label}>Quantidade *</Text>
                                            <Text style={styles.labelHint}>Informe a retirada real</Text>
                                        </View>
                                        <TextInput
                                            style={styles.input}
                                            value={itemAtual.quantidade}
                                            onChangeText={(text) => setItemAtual({ ...itemAtual, quantidade: sanitizeIntText(text) })}
                                            placeholder="Quantidade"
                                            placeholderTextColor={heroPalette.textMuted}
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
                            <View style={styles.itemPreviewRow}>
                                {fotoItemAtualUri ? (
                                    <Image source={{ uri: fotoItemAtualUri }} style={styles.itemPhoto} resizeMode="cover" />
                                ) : (
                                    <View style={styles.itemPhotoFallback}>
                                        <Text style={styles.itemPhotoFallbackText}>Sem foto</Text>
                                    </View>
                                )}
                                <View style={styles.itemPreviewCopy}>
                                    <Text style={styles.itemName}>
                                        {(itemAtual?.item?.descricao || itemAtual?.item?.nome || '').toString().toUpperCase()}
                                    </Text>
                                    <Text style={styles.itemLine}>
                                        Código: {(itemAtual?.item?.codigo_barras || itemAtual?.item?.id || '').toString()}
                                    </Text>
                                    <Text style={styles.itemLine}>Saldo atual: {saldoDetalhado.principal}</Text>
                                    {saldoDetalhado.secundario && (
                                        <Text style={styles.itemLineSecondary}>({saldoDetalhado.secundario} no total)</Text>
                                    )}
                                    {!multi && usarFracao && saldoTotalFracionada != null && (
                                        <Text style={styles.itemLine}>
                                            Saldo total em estoque: {saldoTotalFracionada} {unidadeSaldoTotalFracionada}
                                        </Text>
                                    )}
                                </View>
                            </View>
                        </View>
                    )}

                    {/* Campos comuns */}
                    <View style={styles.inputGroup}>
                        <View style={styles.labelRow}>
                            <Text style={styles.label}>Retirado por *</Text>
                            <Text style={styles.labelHint}>Obrigatório para registrar</Text>
                        </View>
                        <Text style={styles.helperText}>A saída e a notificação ficam vinculadas a este colaborador.</Text>
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
                            placeholderTextColor={heroPalette.textMuted}
                            autoCapitalize="words"
                            autoCorrect={false}
                            blurOnSubmit={false}
                        />
                        {canChooseRetirante && showAutocompleteLista && usuariosFiltrados.length > 0 && (
                            <View style={styles.autocompleteContainer}>
                                <FlatList
                                    data={usuariosFiltrados.slice(0, 8)}
                                    keyExtractor={(item) => item.matricula}
                                    style={styles.autocompleteList}
                                    keyboardShouldPersistTaps="always"
                                    nestedScrollEnabled={true}
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
                                <View style={styles.labelRow}>
                                    <Text style={styles.label}>Capacidade da embalagem *</Text>
                                    <Text style={styles.labelHint}>Exemplo 3.6</Text>
                                </View>
                                <TextInput
                                    style={styles.input}
                                    value={totalEmbalagem}
                                    onChangeText={(text) => setTotalEmbalagem(sanitizeFloatText(text))}
                                    placeholder="Ex: 3.6"
                                    placeholderTextColor={heroPalette.textMuted}
                                    keyboardType="numeric"
                                    returnKeyType="next"
                                />
                            </View>
                        </>
                    )}

                    {!multi && !usarFracao && (
                        <>
                            <View style={styles.inputGroup}>
                                <View style={styles.labelRow}>
                                    <Text style={styles.label}>Quantidade *</Text>
                                    <Text style={styles.labelHint}>Saída real</Text>
                                </View>
                                <TextInput
                                    style={styles.input}
                                    value={itemAtual.quantidade}
                                    onChangeText={(text) => setItemAtual({ ...itemAtual, quantidade: sanitizeIntText(text) })}
                                    placeholder="Quantidade"
                                    placeholderTextColor={heroPalette.textMuted}
                                    keyboardType="numeric"
                                    returnKeyType="next"
                                />
                            </View>

                            {opcoesUnidade.length > 1 && (
                                <View style={styles.inputGroup}>
                                    <Text style={styles.label}>Unidade de medida</Text>
                                    <View style={styles.unidadeRow}>
                                        {opcoesUnidade.map((opcao) => (
                                            <TouchableOpacity
                                                key={opcao.id}
                                                style={[
                                                    styles.unidadeButton,
                                                    unidadeRetirada === opcao.id && styles.unidadeButtonActive,
                                                ]}
                                                onPress={() => setUnidadeRetirada(opcao.id)}
                                            >
                                                <Text
                                                    style={[
                                                        styles.unidadeButtonText,
                                                        unidadeRetirada === opcao.id && styles.unidadeButtonTextActive,
                                                    ]}
                                                >
                                                    {opcao.label}
                                                </Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                </View>
                            )}
                        </>
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
                                    onPress={() => {
                                        setTipoCustodia('temporaria');
                                        setTipoFerramenta('diaria');
                                    }}
                                >
                                    <Text
                                        style={[
                                            styles.custodiaButtonText,
                                            tipoCustodia === 'temporaria' && styles.custodiaButtonTextActive,
                                        ]}
                                    >
                                        Custódia Diária
                                    </Text>
                                </TouchableOpacity>

                                <TouchableOpacity
                                    style={[
                                        styles.custodiaButton,
                                        tipoCustodia === 'permanente' && styles.custodiaButtonActive,
                                    ]}
                                    onPress={() => {
                                        setTipoCustodia('permanente');
                                        setTipoFerramenta('permanente');
                                    }}
                                >
                                    <Text
                                        style={[
                                            styles.custodiaButtonText,
                                            tipoCustodia === 'permanente' && styles.custodiaButtonTextActive,
                                        ]}
                                    >
                                        Custódia Permanente
                                    </Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    )}

                    <View style={styles.inputGroup}>
                        <View style={styles.labelRow}>
                            <Text style={styles.label}>Local de Serviço *</Text>
                            <Text style={styles.labelHint}>Obrigatório agora</Text>
                        </View>
                        <Text style={styles.helperText}>Sem local não é permitido baixar material ou ferramenta.</Text>
                        <TextInput
                            style={styles.input}
                            value={localServico}
                            onChangeText={(text) => setLocalServico(String(text ?? ''))}
                            placeholder="EX: BLOCO A - APTO 201"
                            placeholderTextColor={heroPalette.textMuted}
                            autoCapitalize="characters"
                            returnKeyType="next"
                            onBlur={() => setLocalServico((prev) => String(prev || '').toUpperCase())}
                            onSubmitEditing={() => setLocalServico((prev) => String(prev || '').toUpperCase())}
                            onEndEditing={() => setLocalServico((prev) => String(prev || '').toUpperCase())}
                        />
                    </View>

                    {!contextoObrigatorioOk && (
                        <View style={styles.requirementBanner}>
                            <Text style={styles.requirementBannerText}>Preencha retirante e local para liberar o envio da saída.</Text>
                        </View>
                    )}

                    <TouchableOpacity
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={multi ? handleFinalizarRetiradaMultipla : handleSubmitSingle}
                        disabled={loading || !contextoObrigatorioOk || (multi ? itensRetirada.length === 0 : !itemAtual?.item)}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>
                                {multi ? 'Finalizar Retirada Múltipla' : 'Registrar Saída'}
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
        backgroundColor: heroPalette.bg,
    },
    scroll: {
        padding: 16,
        paddingBottom: 28,
    },
    card: {
        backgroundColor: heroPalette.panel,
        padding: 20,
        borderRadius: 28,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    heroBox: {
        backgroundColor: heroPalette.hero,
        borderRadius: 22,
        padding: 18,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
        marginBottom: 14,
    },
    heroEyebrow: {
        color: heroPalette.primary,
        fontSize: 11,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 1.1,
        marginBottom: 8,
    },
    title: {
        fontSize: 28,
        fontWeight: '900',
        color: heroPalette.text,
        marginBottom: 8,
    },
    heroSubtitle: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    heroMetaRow: {
        flexDirection: 'row',
        gap: 10,
        marginTop: 16,
    },
    heroMetaChip: {
        flex: 1,
        backgroundColor: heroPalette.panelAlt,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingHorizontal: 12,
        paddingVertical: 12,
    },
    heroMetaLabel: {
        color: heroPalette.textMuted,
        fontSize: 10,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 0.9,
    },
    heroMetaValue: {
        color: heroPalette.text,
        fontSize: 13,
        fontWeight: '700',
        marginTop: 6,
    },
    hintsRow: {
        gap: 10,
        marginBottom: 18,
    },
    hintCard: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        backgroundColor: heroPalette.panelAlt,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingHorizontal: 14,
        paddingVertical: 12,
        ...heroSoftShadow,
    },
    hintIcon: {
        width: 24,
        height: 24,
        borderRadius: 12,
        overflow: 'hidden',
        textAlign: 'center',
        textAlignVertical: 'center',
        backgroundColor: 'rgba(103, 232, 249, 0.18)',
        color: heroPalette.primary,
        fontSize: 14,
        fontWeight: '900',
        lineHeight: 24,
    },
    hintText: {
        flex: 1,
        color: heroPalette.textSoft,
        fontSize: 12,
        lineHeight: 18,
    },
    listaItensBox: {
        backgroundColor: heroPalette.panelAlt,
        padding: 15,
        borderRadius: 18,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    listaItensTitle: {
        fontSize: 16,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 12,
    },
    galleryStrip: {
        flexDirection: 'row',
        gap: 8,
        marginBottom: 12,
    },
    galleryThumb: {
        width: 52,
        height: 52,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    galleryMoreBadge: {
        width: 52,
        height: 52,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    galleryMoreText: {
        color: heroPalette.primary,
        fontWeight: '800',
    },
    itemAdicionadoCard: {
        backgroundColor: heroPalette.bgAlt,
        padding: 12,
        borderRadius: 16,
        marginBottom: 8,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    itemThumb: {
        width: 52,
        height: 52,
        borderRadius: 14,
        marginRight: 12,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    itemThumbFallback: {
        width: 52,
        height: 52,
        borderRadius: 14,
        marginRight: 12,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.panelSoft,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    itemThumbFallbackText: {
        color: heroPalette.textMuted,
        fontSize: 10,
        fontWeight: '700',
        textAlign: 'center',
        paddingHorizontal: 4,
    },
    itemAdicionadoInfo: {
        flex: 1,
    },
    itemAdicionadoNome: {
        fontSize: 14,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 4,
    },
    itemAdicionadoDetalhe: {
        fontSize: 12,
        color: heroPalette.textMuted,
    },
    removeButton: {
        backgroundColor: 'rgba(251, 113, 133, 0.18)',
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: 10,
        marginLeft: 8,
        borderWidth: 1,
        borderColor: 'rgba(251, 113, 133, 0.4)',
    },
    removeButtonText: {
        color: heroPalette.danger,
        fontWeight: '700',
        fontSize: 14,
    },
    itemAtualBox: {
        backgroundColor: heroPalette.panelAlt,
        padding: 15,
        borderRadius: 18,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: 'rgba(52, 211, 153, 0.35)',
    },
    itemAtualTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: heroPalette.accent,
        marginBottom: 12,
    },
    buscarItemContainer: {
        gap: 10,
    },
    buscarButton: {
        backgroundColor: heroPalette.heroAlt,
        paddingVertical: 12,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    buscarButtonText: {
        color: heroPalette.text,
        fontWeight: '700',
        fontSize: 14,
    },
    scanButton: {
        backgroundColor: 'rgba(34, 211, 238, 0.18)',
        paddingVertical: 12,
        borderRadius: 14,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    scanButtonText: {
        color: heroPalette.text,
        fontWeight: '700',
        fontSize: 14,
    },
    adicionarButton: {
        backgroundColor: heroPalette.accent,
        paddingVertical: 12,
        borderRadius: 14,
        alignItems: 'center',
        marginTop: 10,
    },
    adicionarButtonText: {
        color: '#04121b',
        fontWeight: '800',
        fontSize: 14,
    },
    itemBox: {
        backgroundColor: heroPalette.panelAlt,
        padding: 15,
        borderRadius: 18,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    itemPreviewRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
    },
    itemPhoto: {
        width: 92,
        height: 92,
        borderRadius: 18,
        marginRight: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    itemPhotoFallback: {
        width: 92,
        height: 92,
        borderRadius: 18,
        marginRight: 14,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.panelSoft,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    itemPhotoFallbackText: {
        color: heroPalette.textMuted,
        fontSize: 11,
        fontWeight: '700',
    },
    itemPreviewCopy: {
        flex: 1,
    },
    itemName: {
        fontSize: 18,
        fontWeight: 'bold',
        color: heroPalette.text,
        marginBottom: 8,
    },
    itemLine: {
        fontSize: 14,
        color: heroPalette.textSoft,
        marginTop: 4,
    },
    itemLineSecondary: {
        fontSize: 13,
        color: heroPalette.textMuted,
        fontStyle: 'italic',
        marginTop: 2,
        marginLeft: 4,
    },
    inputGroup: {
        marginBottom: 16,
    },
    labelRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 8,
        gap: 10,
    },
    switchRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    label: {
        fontSize: 14,
        fontWeight: '700',
        color: heroPalette.text,
    },
    labelHint: {
        color: heroPalette.primary,
        fontSize: 11,
        fontWeight: '800',
        textTransform: 'uppercase',
        letterSpacing: 0.6,
    },
    helperText: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 18,
        marginBottom: 8,
    },
    input: {
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        borderRadius: 14,
        padding: 12,
        fontSize: 16,
        color: heroPalette.text,
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
        borderColor: heroPalette.border,
        borderRadius: 10,
        backgroundColor: heroPalette.bgAlt,
    },
    radioOuter: {
        width: 20,
        height: 20,
        borderRadius: 10,
        borderWidth: 2,
        borderColor: heroPalette.textMuted,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.panel,
    },
    radioOuterActive: {
        borderColor: heroPalette.primary,
    },
    radioInner: {
        width: 10,
        height: 10,
        borderRadius: 5,
        backgroundColor: heroPalette.primary,
    },
    radioLabel: {
        flex: 1,
        fontSize: 14,
        color: heroPalette.text,
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
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.bgAlt,
    },
    fractionButtonActive: {
        backgroundColor: heroPalette.primary,
        borderColor: heroPalette.primary,
    },
    fractionButtonText: {
        fontSize: 14,
        fontWeight: '600',
        color: heroPalette.text,
    },
    fractionButtonTextActive: {
        color: '#04121b',
    },
    custodiaRow: {
        flexDirection: 'row',
        gap: 10,
    },
    custodiaButton: {
        flex: 1,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingVertical: 10,
        borderRadius: 10,
        backgroundColor: heroPalette.bgAlt,
        alignItems: 'center',
    },
    custodiaButtonActive: {
        backgroundColor: heroPalette.primary,
        borderColor: heroPalette.primary,
    },
    custodiaButtonText: {
        color: heroPalette.text,
        fontWeight: '600',
    },
    custodiaButtonTextActive: {
        color: '#04121b',
    },
    unidadeRow: {
        flexDirection: 'row',
        gap: 10,
    },
    unidadeButton: {
        flex: 1,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingVertical: 10,
        borderRadius: 10,
        backgroundColor: heroPalette.bgAlt,
        alignItems: 'center',
    },
    unidadeButtonActive: {
        backgroundColor: heroPalette.accent,
        borderColor: heroPalette.accent,
    },
    unidadeButtonText: {
        color: heroPalette.text,
        fontWeight: '600',
    },
    unidadeButtonTextActive: {
        color: '#04121b',
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
        borderColor: heroPalette.border,
        borderRadius: 14,
        backgroundColor: heroPalette.panel,
        overflow: 'hidden',
    },
    autocompleteList: {
        flexGrow: 0,
    },
    autocompleteItem: {
        padding: 12,
        borderBottomWidth: 1,
        borderBottomColor: heroPalette.border,
    },
    autocompleteNome: {
        fontSize: 15,
        fontWeight: '600',
        color: heroPalette.text,
    },
    autocompleteDetalhe: {
        fontSize: 12,
        color: heroPalette.textMuted,
        marginTop: 2,
    },
    requirementBanner: {
        backgroundColor: 'rgba(251, 113, 133, 0.12)',
        borderWidth: 1,
        borderColor: 'rgba(251, 113, 133, 0.28)',
        borderRadius: 14,
        paddingHorizontal: 14,
        paddingVertical: 12,
        marginBottom: 10,
    },
    requirementBannerText: {
        color: heroPalette.danger,
        fontSize: 12,
        lineHeight: 18,
        fontWeight: '700',
    },
    button: {
        backgroundColor: heroPalette.primary,
        paddingVertical: 14,
        borderRadius: 16,
        alignItems: 'center',
        marginTop: 10,
    },
    buttonDisabled: {
        backgroundColor: 'rgba(148, 163, 184, 0.28)',
    },
    buttonText: {
        color: '#04121b',
        fontSize: 16,
        fontWeight: '900',
    },
    // Estilos do modal de embalagens
    modalOverlay: {
        flex: 1,
        backgroundColor: 'rgba(3, 10, 18, 0.78)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 20,
    },
    modalContainer: {
        backgroundColor: heroPalette.panel,
        borderRadius: 16,
        padding: 24,
        width: '100%',
        maxWidth: 500,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    modalTitle: {
        fontSize: 22,
        fontWeight: '700',
        color: heroPalette.text,
        textAlign: 'center',
        marginBottom: 8,
    },
    modalSubtitle: {
        fontSize: 15,
        color: heroPalette.textMuted,
       textAlign: 'center',
        marginBottom: 16,
    },
    modalInfo: {
        backgroundColor: heroPalette.panelAlt,
        padding: 12,
        borderRadius: 8,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    modalInfoText: {
        fontSize: 13,
        color: heroPalette.textSoft,
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
        borderColor: heroPalette.border,
        borderRadius: 12,
        backgroundColor: heroPalette.bgAlt,
    },
    modalOptionActive: {
        borderColor: heroPalette.primary,
        backgroundColor: 'rgba(103, 232, 249, 0.12)',
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
        color: heroPalette.text,
    },
    modalOptionTitleActive: {
        color: heroPalette.primary,
    },
    modalInputGroup: {
        marginBottom: 20,
    },
    modalLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: heroPalette.text,
        marginBottom: 8,
    },
    modalInput: {
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
        color: heroPalette.text,
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
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    modalButtonConfirm: {
        backgroundColor: heroPalette.primary,
    },
    modalButtonTextCancel: {
        color: heroPalette.text,
        fontSize: 15,
        fontWeight: '600',
    },
    modalButtonTextConfirm: {
        color: '#04121b',
        fontSize: 15,
        fontWeight: '800',
    },
});
