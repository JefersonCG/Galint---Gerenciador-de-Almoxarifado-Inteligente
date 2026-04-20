import React, { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    FlatList,
    Alert,
    RefreshControl,
    ActivityIndicator,
    Platform,
    Image,
    Keyboard,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import ApiService from '../services/api';
import DailyCustodyPanel from '../components/DailyCustodyPanel';
import HeartbeatService from '../services/heartbeatService';
import InactivityService from '../services/inactivityService';
import SyncService from '../services/dbSync';
import { 
    getOnlineSnapshot, 
    getOfflineDelta, 
    saveOnlineSnapshot, 
    searchItems as searchOfflineItems, // Alias para deixar claro que é local
    upsertItems,
    listPendingOps
} from '../services/offlineDb';
import { formatQuantityWithPackaging } from '../utils/formatQuantity';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

// Função Centralizada de Permissões
function getUserRole(user) {
    if (!user) return 'operacional'; // Default seguro se não tiver user
    
    // Normalização segura
    const cargo = (user.cargo || '').toString().toLowerCase().trim();
    const setor = (user.setor || '').toString().toLowerCase().trim();
    
    // Check Admin explicito '1' ou true
    const isAdmin = user.is_admin === true || user.is_admin === 1 || String(user.is_admin || '').trim() === '1';
    
    // Check Legacy
    const isManagerLegacy = !!user.is_manager; 

    // 1. MASTER (Almoxarifes e Admins)
    if (isAdmin || cargo.includes('almoxarif') || cargo === 'master') {
        return 'master';
    }

    // 2. GERENCIA (inclui supervisor)
    if (
        cargo.includes('gerente') ||
        setor.includes('gerenc') ||
        setor.includes('adm') ||
        cargo.includes('supervisor') ||
        setor.includes('supervisor')
    ) {
        return 'gerencia';
    }

    // 3. OPERACIONAL (Default)
    return 'operacional'; 
}

function getRoleLabel(role) {
    if (role === 'master') return 'Master';
    if (role === 'gerencia') return 'Gerência';
    return 'Operação';
}

function mapNotificationLabel(entry) {
    const messageType = String(entry?.message_type || '').trim().toLowerCase();
    const category = String(entry?.category || '').trim().toLowerCase();
    if (messageType.includes('withdrawal') || category === 'withdrawal') return 'Saídas';
    if (messageType.includes('inventory') || category === 'inventory') return 'Devoluções';
    if (messageType.includes('stock') || category === 'stock' || category === 'item') return 'Entradas';
    return 'Alertas';
}

export default function EstoqueScreen({ navigation, route }) {
    const [items, setItems] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [categoriaStats, setCategoriaStats] = useState({});
    const [selectedCategoria, setSelectedCategoria] = useState(null);
    const [offlineSnapshot, setOfflineSnapshot] = useState(null); // { totalItens, totalQuantidade }
    const [offlineDelta, setOfflineDelta] = useState({ entradas: 0, retiradas: 0 });
    const [isOfflineMode, setIsOfflineMode] = useState(false);
    const [kpiServer, setKpiServer] = useState(null);
    const [user, setUser] = useState(route.params?.user || null);
    const [dailyCustodyVisible, setDailyCustodyVisible] = useState(true);
    const [dailyCustodyLoading, setDailyCustodyLoading] = useState(false);
    const [dailyCustodyGroups, setDailyCustodyGroups] = useState([]);
    const [dailyCustodySummary, setDailyCustodySummary] = useState({ employees: 0, tools: 0, overdue: 0 });
    const [dailyCustodyMessage, setDailyCustodyMessage] = useState('');
    const [dailyCustodyReturning, setDailyCustodyReturning] = useState(false);
    const [erpOverview, setErpOverview] = useState(null);
    
    // 🔄 Estados para Banner de Conexão
    const [connectionStatus, setConnectionStatus] = useState('online'); // 'online' | 'offline' | 'syncing'
    const [pendingOpsCount, setPendingOpsCount] = useState(0);
    const [isSyncing, setIsSyncing] = useState(false);
    const [downloadingDatabase, setDownloadingDatabase] = useState(false);
    const latestSearchRef = useRef('');

    // Determinar permissão
    const role = useMemo(() => getUserRole(user), [user]);
    const roleLabel = useMemo(() => getRoleLabel(role), [role]);
    const unreadNotifications = Number(erpOverview?.notifications?.unread_count || 0);
    const canManageDocuments = Boolean(erpOverview?.features?.documentos_fiscais);
    const recentNotificationLabels = useMemo(() => {
        const recent = Array.isArray(erpOverview?.notifications?.recent) ? erpOverview.notifications.recent : [];
        return Array.from(new Set(recent.map((entry) => mapNotificationLabel(entry)).filter(Boolean))).slice(0, 3);
    }, [erpOverview]);

    const loadOverviewSummary = useCallback(async (silent = false) => {
        const result = await ApiService.getErpOverview();
        if (result?.success) {
            setErpOverview(result.data || null);
            if (result.data?.user && !user) {
                setUser((current) => current || result.data.user);
            }
            return;
        }

        if (!silent) {
            setErpOverview(null);
        }
    }, [user]);

    const loadDailyCustody = useCallback(async (silent = false) => {
        if (!silent) {
            setDailyCustodyLoading(true);
        }

        try {
            const result = await ApiService.getDailyCustodyFeed();

            if (result?.success) {
                const payload = result.data || {};
                setDailyCustodyVisible(true);
                setDailyCustodyGroups(Array.isArray(payload.groups) ? payload.groups : []);
                setDailyCustodySummary(payload.summary || { employees: 0, tools: 0, overdue: 0 });
                setDailyCustodyMessage('');
                return;
            }

            if (Number(result?.status) === 403) {
                setDailyCustodyVisible(false);
                setDailyCustodyGroups([]);
                setDailyCustodySummary({ employees: 0, tools: 0, overdue: 0 });
                setDailyCustodyMessage('');
                return;
            }

            setDailyCustodyVisible(true);
            setDailyCustodyGroups([]);
            setDailyCustodySummary({ employees: 0, tools: 0, overdue: 0 });
            setDailyCustodyMessage(result?.message || 'Não foi possível carregar a custódia diária agora.');
        } catch (error) {
            setDailyCustodyVisible(true);
            setDailyCustodyGroups([]);
            setDailyCustodySummary({ employees: 0, tools: 0, overdue: 0 });
            setDailyCustodyMessage(error?.message || 'Não foi possível carregar a custódia diária agora.');
        } finally {
            if (!silent) {
                setDailyCustodyLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        latestSearchRef.current = searchQuery;
    }, [searchQuery]);

    // Carregar usuário inicial e iniciar serviços
    useEffect(() => {
        // Se verificação de usuário
        if (!route.params?.user) {
            AsyncStorage.getItem('user')
                .then((stored) => {
                    if (stored) {
                        try {
                            setUser(JSON.parse(stored));
                        } catch (error) {
                            setUser(null);
                        }
                    }
                })
                .catch(() => {});
        } else {
             // Atualizar storage com o user vindo da navegação (provavelmente login fresco)
             AsyncStorage.setItem('user', JSON.stringify(route.params.user)).catch(()=>{});
        }
        
        // Iniciar Sync Service (Ciclo de 5s)
        SyncService.start();

        // Listener de Sync para atualizar a tela automaticamente
        const removeSyncListener = SyncService.addListener(() => {
            // Quando ocorrer um sync, recarregamos dados locais e KPIs
            // console.log('[EstoqueScreen] Sync detectado, atualizando UI...');
            loadEstoque(searchQuery, true); // true = silent update
            loadDailyCustody(true);
            loadOverviewSummary(true);
        });
        
        // Carregamento inicial direto
        (async () => {
             // Tenta carregar local imediatamente para ser rápido
             const local = await searchOfflineItems('');
             if(local && local.length > 0) {
                 setItems(local);
                 calcularCategoriaStats(local);
                 setLoading(false);
             } else {
                 // Cache vazio! Verificar se está online e fazer pre-load
                 console.log('[EstoqueScreen] ⚠️ Cache SQLite vazio - verificando conexão...');
                 try {
                     const online = await ApiService.isOnline();
                     if (online) {
                         console.log('[EstoqueScreen] 🌐 Online detectado - iniciando pre-load automático...');
                         const preloadResult = await ApiService.preloadEstoqueCompleto();
                         if (preloadResult.success) {
                             console.log(`[EstoqueScreen] ✅ Pre-load concluído: ${preloadResult.totalItens} itens`);
                             // Recarregar do cache após pre-load
                             const localAfterPreload = await searchOfflineItems('');
                             if (localAfterPreload && localAfterPreload.length > 0) {
                                 setItems(localAfterPreload);
                                 calcularCategoriaStats(localAfterPreload);
                             }
                         } else {
                             console.log('[EstoqueScreen] ⚠️ Pre-load falhou');
                         }
                     } else {
                         console.log('[EstoqueScreen] 📵 Modo offline - não é possível carregar dados');
                         Alert.alert(
                             'Sem Dados Disponíveis', 
                             'O cache local está vazio e você está offline.\\n\\nConecte-se à internet para carregar os dados.',
                             [{ text: 'OK' }]
                         );
                     }
                 } catch (error) {
                     console.error('[EstoqueScreen] Erro ao verificar pre-load:', error);
                 }
                 setLoading(false);
             }
             // Depois roda o full load
             loadEstoque('', false);
                             loadDailyCustody(false);
                             loadOverviewSummary(false);
        })();

        HeartbeatService.start();
        
        InactivityService.start((reason) => {
            Alert.alert(
                'Sessão Expirada',
                'Você foi desconectado por inatividade (6 minutos sem uso).',
                [
                    {
                        text: 'OK',
                        onPress: () => {
                            HeartbeatService.stop();
                            InactivityService.stop();
                            SyncService.stop();
                            ApiService.logout().catch(() => {});
                            navigation.reset({
                                index: 0,
                                routes: [{ name: 'Login' }],
                            });
                        }
                    }
                ],
                { cancelable: false }
            );
        });

        return () => {
            HeartbeatService.stop();
            InactivityService.stop();
            SyncService.stop();
            removeSyncListener();
        };
    }, [loadDailyCustody, loadOverviewSummary, navigation]);

    // 📡 Monitorar Conexão e Operações Pendentes
    useEffect(() => {
        // Atualizar contador de operações pendentes periodicamente
        const updatePendingOps = async () => {
            const pending = await listPendingOps();
            setPendingOpsCount(pending.length);
        };

        updatePendingOps(); // Inicial
        const timer = setInterval(updatePendingOps, 3000); // A cada 3s

        // Listener do NetInfo
        const unsubscribeNetInfo = NetInfo.addEventListener(state => {
            const isConnected = state.isConnected && state.isInternetReachable !== false;
            setConnectionStatus(isConnected ? 'online' : 'offline');
        });

        return () => {
            clearInterval(timer);
            unsubscribeNetInfo();
        };
    }, []);

    useEffect(() => {
        const unsubscribe = navigation.addListener('focus', () => {
             loadEstoque(latestSearchRef.current, true);
             loadDailyCustody(true);
             loadOverviewSummary(true);
        });
        return unsubscribe;
    }, [loadDailyCustody, loadOverviewSummary, navigation]);

    // Função Principal de Carga de Dados
    // Estratégia: Local First -> Network Update
    const loadEstoque = async (search = '', silent = false) => {
        if (!silent && items.length === 0) setLoading(true);
        
        try {
            // 1. Carregar do Banco Local (Sempre, para garantir que estamos vendo o que o user tem)
            const localItems = await searchOfflineItems(search);
            // Se tiver dados locais, use-os como source of truth imediato
            // Por quê? Porque o SyncService está atualizando o sqlite em background.
            // Então ler do SQLite é ler o estado mais atual 'sincronizado'.
            if (localItems) {
                setItems(localItems);
                calcularCategoriaStats(localItems);
            }

            // 2. Se NÃO for silent, força um request de rede para garantir que o SyncService não está dormindo
            // ou se for a primeira carga. Mas o ideal é deixar o SyncService rodar sozinho.
            // Porem, user quer ver atualizações "na hora".
            // Se estivermos offline, isOfflineMode ficará true naturalmente pelo SyncService se falhar?
            // O SyncService não exporta estado de conexão reativo fácil, mas podemos checar ApiService.isOnline se quisermos badge.
            
            // Vamos confiar no SyncService para dados pesados e update, mas verificar flag de offline
            const snapshot = await getOnlineSnapshot();
            const delta = await getOfflineDelta();
            setOfflineSnapshot(snapshot);
            setOfflineDelta(delta);
            
            // Verifica se tem pendencias
            setIsOfflineMode(delta.entradas > 0 || delta.retiradas > 0); 
            // Ou checa API simples
            // const online = await ApiService.testConnection(); ... (muito pesado para loop)

        } catch (error) {
            console.log('Erro loadEstoque', error);
        } finally {
            if (!silent) setLoading(false);
            setRefreshing(false);
        }
    };

    const calcularCategoriaStats = (currentItems) => {
        if (!currentItems) return;
        const stats = {};
        currentItems.forEach(item => {
            const cat = item.categoria || 'Outros';
            if (!stats[cat]) {
                stats[cat] = { total: 0, quantidade: 0, nome: cat };
            }
            stats[cat].total += 1;
            stats[cat].quantidade += Number(item.quantidade || 0);
        });
        setCategoriaStats(stats);
    };

    // Autocomplete Logic: Filter items locally based on search query
    // O items já vem filtrado do sqlite se passamos search no searchOfflineItems,
    // ENTRETANTO, para performance de digitação, melhor filtrar em memória o que já temos
    // e disparar a busca no sqlite (que é async) com debounce.
    const filteredItems = useMemo(() => {
        if (!searchQuery) return items;
        const lower = searchQuery.toLowerCase();
        return items.filter(i => 
            (i.nome || '').toLowerCase().includes(lower) || 
            (i.descricao || '').toLowerCase().includes(lower) ||
            (i.categoria || '').toLowerCase().includes(lower) ||
            (i.codigo_barras || '').includes(lower)
        );
    }, [items, searchQuery]);

    // REMOVIDO: debounce causava fechamento do teclado
    // A filtragem acontece em memória via useMemo (filteredItems)

    const handleSearch = useCallback((text) => {
        setSearchQuery(text);
    }, []);

    const handleClearSearch = useCallback(() => {
        setSearchQuery('');
    }, []);

    const handleRefresh = () => {
        setRefreshing(true);
        // Forçar um sync Cycle agora
        SyncService.runSync().finally(() => {
            loadEstoque(searchQuery);
            loadDailyCustody(true);
            loadOverviewSummary(true);
            setRefreshing(false);
        });
    };

    const executeDailyCustodyReturn = useCallback(async (entries) => {
        const normalizedEntries = Array.isArray(entries)
            ? entries.filter((entry) => entry?.group && entry?.item)
            : [];

        if (!normalizedEntries.length) {
            return;
        }

        setDailyCustodyReturning(true);
        InactivityService.recordActivity();

        try {
            let successCount = 0;
            const failures = [];

            for (const entry of normalizedEntries) {
                const group = entry.group;
                const item = entry.item;
                const result = await ApiService.returnDailyCustodyTool({
                    codigo: item?.codigo,
                    quantidade: item?.quantidade || 1,
                    saida_id: item?.saida_id || item?.id || null,
                    matricula: group?.matricula_full || group?.matricula || '',
                });

                if (result?.success) {
                    successCount += 1;
                } else {
                    failures.push(`${item?.descricao || item?.codigo || 'Ferramenta'}: ${result?.message || 'Falha ao devolver.'}`);
                }
            }

            if (successCount > 0) {
                await Promise.all([
                    loadDailyCustody(true),
                    loadEstoque(latestSearchRef.current, true),
                ]);
            }

            if (!failures.length) {
                Alert.alert(
                    'Custódia diária',
                    successCount === 1
                        ? 'Ferramenta devolvida com sucesso.'
                        : `${successCount} ferramenta(s) devolvida(s) com sucesso.`
                );
                return;
            }

            if (successCount > 0) {
                Alert.alert(
                    'Custódia diária',
                    `${successCount} devolução(ões) concluída(s) e ${failures.length} falha(s).\n\n${failures.slice(0, 3).join('\n')}`
                );
                return;
            }

            Alert.alert('Custódia diária', failures[0] || 'Não foi possível dar baixa na ferramenta.');
        } catch (error) {
            Alert.alert('Custódia diária', error?.message || 'Não foi possível dar baixa na ferramenta.');
        } finally {
            setDailyCustodyReturning(false);
        }
    }, [loadDailyCustody, loadEstoque]);

    const handleDailyCustodyReturn = useCallback((entries, options = {}) => {
        const normalizedEntries = Array.isArray(entries)
            ? entries.filter((entry) => entry?.group && entry?.item)
            : [];

        if (!normalizedEntries.length) {
            return;
        }

        const scope = options?.scope || 'selected';
        const itemCount = normalizedEntries.length;
        const collaborators = Array.from(new Set(normalizedEntries.map((entry) => entry?.group?.usuario).filter(Boolean)));
        let title = 'Dar baixa das ferramentas';
        let message = `Confirmar a baixa de ${itemCount} ferramenta(s) selecionada(s)?`;

        if (scope === 'group-selected') {
            title = 'Dar baixa das selecionadas';
            message = `Confirmar a baixa de ${itemCount} ferramenta(s) selecionada(s) para ${options?.group?.usuario || 'este colaborador'}?`;
        } else if (scope === 'group-all') {
            title = 'Dar baixa de todas';
            message = `Confirmar a baixa de todas as ${itemCount} ferramenta(s) em custódia de ${options?.group?.usuario || 'este colaborador'}?`;
        } else if (scope === 'global-selected') {
            title = 'Dar baixa das selecionadas';
            message = `Confirmar a baixa de ${itemCount} ferramenta(s) distribuída(s) em ${collaborators.length} colaborador(es)?`;
        } else if (scope === 'global-all') {
            title = 'Dar baixa de tudo';
            message = `Confirmar a baixa de todas as ${itemCount} ferramenta(s) visíveis na custódia diária?`;
        } else if (itemCount === 1) {
            title = 'Dar baixa da ferramenta';
            message = `Confirmar a baixa de ${normalizedEntries[0]?.item?.descricao || 'esta ferramenta'}?`;
        }

        Alert.alert(
            title,
            message,
            [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'Dar baixa', onPress: () => executeDailyCustodyReturn(normalizedEntries) },
            ]
        );
    }, [executeDailyCustodyReturn]);

    // 🔄 Sincronização Manual (botão no banner offline)
    const handleManualSync = async () => {
        try {
            setIsSyncing(true);
            setConnectionStatus('syncing');
            
            console.log('[ManualSync] Iniciando sincronização manual...');
            
            // Forçar sync de operações pendentes
            await SyncService.runSync();
            
            // Recarregar estoque
            await loadEstoque(searchQuery, true);
            
            // Atualizar contador
            const pending = await listPendingOps();
            setPendingOpsCount(pending.length);
            
            if (pending.length === 0) {
                Alert.alert('Sucesso', '✅ Todas as operações foram sincronizadas');
            } else {
                Alert.alert('Sucesso', `✅ Sincronização concluída\n${pending.length} operação(ões) ainda pendente(s)`);
            }
            
            console.log(`[ManualSync] ✅ Sincronização completa. Pendentes: ${pending.length}`);
        } catch (error) {
            console.error('[ManualSync] Erro:', error);
            Alert.alert('Erro', 'Falha ao sincronizar. Verifique sua conexão.');
        } finally {
            setIsSyncing(false);
            // Restaurar status baseado na conexão real
            const netState = await NetInfo.fetch();
            const isConnected = netState.isConnected && netState.isInternetReachable !== false;
            setConnectionStatus(isConnected ? 'online' : 'offline');
        }
    };

    // Navigation Handlers
    const handleAction = (action, params = {}) => {
        InactivityService.recordActivity();
        navigation.navigate(action, { user, ...params });
    };

    // 📥 Função para baixar/atualizar base de dados completa
    const handleDownloadDatabase = async () => {
        const online = await ApiService.isOnline();
        if (!online) {
            Alert.alert(
                'Sem Conexão',
                'Você precisa estar online para baixar a base de dados.',
                [{ text: 'OK' }]
            );
            return;
        }

        Alert.alert(
            'Baixar Base de Dados',
            'Deseja baixar todos os itens do estoque? Isso pode levar alguns segundos.',
            [
                { text: 'Cancelar', style: 'cancel' },
                {
                    text: 'Baixar',
                    onPress: async () => {
                        setDownloadingDatabase(true);
                        try {
                            const result = await ApiService.preloadEstoqueCompleto();
                            if (result.success) {
                                Alert.alert(
                                    '✅ Sucesso',
                                    `Base de dados atualizada!\n\n${result.totalItens} itens baixados para o cache local.`,
                                    [{ text: 'OK' }]
                                );
                                // Recarregar dados após download
                                await loadEstoque('', false);
                            } else {
                                Alert.alert(
                                    '⚠️ Erro',
                                    result.message || 'Não foi possível baixar a base de dados.',
                                    [{ text: 'OK' }]
                                );
                            }
                        } catch (error) {
                            Alert.alert(
                                '❌ Erro',
                                'Falha ao baixar base de dados. Tente novamente.',
                                [{ text: 'OK' }]
                            );
                        } finally {
                            setDownloadingDatabase(false);
                        }
                    }
                }
            ]
        );
    };

    const getCategoriaIcon = (categoria) => {
        const icons = {
            'Material Elétrico': '⚡',
            'Material Hidráulico': '💧',
            'Material de Construção': '🔨',
            'Materiais de Limpeza': '🧽',
            'Material Descartável': '🧽',
            'Ferramentas': '🔧',
            'EPI': '🦺',
        };
        return icons[categoria] || '📦';
    };

    const handleItemPress = (item) => {
        if (role === 'master') {
            Alert.alert(
                'Consulta somente',
                'A manutenção de itens foi removida do app mobile. Utilize a interface web administrativa para editar cadastros.'
            );
        }
    };

    const handleCategoriaPress = (categoria) => {
        setSearchQuery(categoria);
    };

    const handleOpenMenu = useCallback(() => {
        InactivityService.recordActivity();
        navigation.navigate('Menu');
    }, [navigation]);

    const handleOpenNotifications = useCallback(() => {
        InactivityService.recordActivity();
        navigation.navigate('Notifications');
    }, [navigation]);

    const handleOpenDocumentos = useCallback(() => {
        if (!canManageDocuments) {
            Alert.alert('Acesso restrito', 'Entradas fiscais e documentos fiscais no mobile agora ficam disponíveis somente para administradores cadastrados no servidor.');
            return;
        }
        InactivityService.recordActivity();
        navigation.navigate('DocumentosFiscais');
    }, [canManageDocuments, navigation]);

    const renderItem = useCallback(({ item }) => {
        const q = Number(item?.quantidade ?? 0);
        const quantidadeInt = Number.isFinite(q) ? Math.trunc(q) : 0;
        const quantidadeFormatada = formatQuantityWithPackaging(item.quantidade, item);
        return (
        <TouchableOpacity
            style={styles.itemCard}
            activeOpacity={role === 'master' ? 0.7 : 1}
            onPress={() => handleItemPress(item)}
        >
            <View style={styles.itemHeader}>
                <Text style={styles.itemName}>{item.descricao || item.nome}</Text>
                <View style={[
                    styles.badge,
                    quantidadeInt > 10 ? styles.badgeSuccess :
                        quantidadeInt > 0 ? styles.badgeWarning : styles.badgeDanger
                ]}>
                    <Text style={styles.badgeText}>{quantidadeFormatada}</Text>
                </View>
            </View>

            {item.codigo_barras ? (
                <Text style={styles.itemBarcode}>Código: {item.codigo_barras}</Text>
            ) : null}

            <View style={styles.itemDetails}>
                {item.categoria ? (
                    <Text style={styles.itemDetail}>Categoria: {item.categoria}</Text>
                ) : null}
                {item.localizacao ? (
                    <Text style={styles.itemDetail}>Local: {item.localizacao}</Text>
                ) : null}
                {item.marca ? (
                    <Text style={styles.itemDetail}>Marca: {item.marca}</Text>
                ) : null}
            </View>
        </TouchableOpacity>
        );
    }, [role]);

    const renderCategoryCard = (catName) => {
        const stats = categoriaStats[catName] || { total: 0 };
        return (
            <TouchableOpacity 
                key={catName}
                style={styles.categoryCard} 
                onPress={() => handleCategoriaPress(catName)}
                activeOpacity={0.8}
            >
                <Text style={styles.categoryIcon}>{getCategoriaIcon(catName)}</Text>
                <Text style={styles.categoryTitle}>{catName}</Text>
                <Text style={styles.categoryCount}>{stats.total} itens</Text>
            </TouchableOpacity>
        );
    };

    const listHeaderComponent = useMemo(() => {
        const availableCategories = Object.keys(categoriaStats);
        const pendingLocalOps = offlineDelta.entradas + offlineDelta.retiradas;
        const displayName = user?.nome || user?.username || 'Usuário';
        const displayUserRef = user?.matricula || user?.username || 'sem matrícula';
        
        return (
            <View>
                <View style={styles.modernHeader}>
                    <View style={styles.headerTop}>
                        <View style={styles.headerTextContainer}>
                            <Text style={styles.headerEyebrow}>Shell hero</Text>
                            <Text style={styles.headerTitle}>GALINT Mobile</Text>
                            <Text style={styles.headerOperatorName}>{displayName}</Text>
                            <Text style={styles.headerSubtitle}>{roleLabel} • {displayUserRef}</Text>
                        </View>
                        <View style={styles.headerButtons}>
                            <TouchableOpacity
                                onPress={handleOpenNotifications}
                                style={styles.modernMenuButton}
                                activeOpacity={0.85}
                            >
                                <Text style={styles.modernMenuIcon}>🔔</Text>
                                {unreadNotifications > 0 ? (
                                    <View style={styles.headerNotifyBadge}>
                                        <Text style={styles.headerNotifyBadgeText}>{unreadNotifications > 99 ? '99+' : unreadNotifications}</Text>
                                    </View>
                                ) : null}
                            </TouchableOpacity>
                            <TouchableOpacity
                                onPress={handleDownloadDatabase}
                                style={[styles.modernMenuButton, styles.downloadDatabaseButton]}
                                disabled={downloadingDatabase}
                                activeOpacity={0.85}
                            >
                                {downloadingDatabase ? (
                                    <ActivityIndicator size="small" color={heroPalette.text} />
                                ) : (
                                    <Text style={styles.downloadDatabaseButtonText}>⬇ Base</Text>
                                )}
                            </TouchableOpacity>
                            <TouchableOpacity
                                onPress={handleOpenMenu}
                                style={styles.modernMenuButton}
                                activeOpacity={0.85}
                            >
                                <Text style={styles.modernMenuIcon}>☰</Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                    <View style={styles.headerMetaRow}>
                        <View style={styles.headerMetaCard}>
                            <Text style={styles.headerMetaLabel}>Base local</Text>
                            <Text style={styles.headerMetaValue}>{items.length}</Text>
                            <Text style={styles.headerMetaHint}>itens no aparelho</Text>
                        </View>
                        <View style={styles.headerMetaCard}>
                            <Text style={styles.headerMetaLabel}>Conexão</Text>
                            <Text style={styles.headerMetaValue}>
                                {connectionStatus === 'syncing' ? 'Sincronizando' : connectionStatus === 'offline' ? 'Offline' : 'Online'}
                            </Text>
                            <Text style={styles.headerMetaHint}>{pendingOpsCount} pendência(s)</Text>
                        </View>
                    </View>
                    
                    <View style={styles.headerSearchContainer}>
                        <Text style={styles.searchIcon}>🔍</Text>
                        <TextInput
                            style={styles.headerSearchInput}
                            placeholder="Pesquisar item, código ou categoria"
                            placeholderTextColor={heroPalette.textMuted}
                            value={searchQuery}
                            onChangeText={handleSearch}
                            returnKeyType="search"
                            blurOnSubmit={false}
                            autoCorrect={false}
                        />
                        {searchQuery !== '' && (
                            <TouchableOpacity onPress={handleClearSearch} activeOpacity={0.85}>
                                <Text style={styles.clearSearchIcon}>✕</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                </View>

                {isOfflineMode && (
                    <View style={styles.kpiSection}>
                        <View style={styles.kpiHeader}>
                            <Text style={styles.kpiTitle}>Indicador local</Text>
                            <View style={styles.offlineModeBadge}>
                                <Text style={styles.offlineModeText}>Modo offline</Text>
                            </View>
                        </View>
                        <View style={styles.kpiGrid}>
                            <View style={[styles.kpiCard, styles.kpiOfflineEntradas]}>
                                <View style={styles.kpiValueContainer}>
                                    <Text style={styles.kpiValue}>{pendingLocalOps}</Text>
                                </View>
                                <Text style={styles.kpiLabel}>Operações pendentes</Text>
                            </View>
                            <View style={[styles.kpiCard, styles.kpiInventoryCard]}>
                                <View style={styles.kpiValueContainer}>
                                    <Text style={styles.kpiValue}>{offlineSnapshot?.totalItens || items.length}</Text>
                                </View>
                                <Text style={styles.kpiLabel}>Itens no cache</Text>
                            </View>
                        </View>
                    </View>
                )}

                {role === 'gerencia' && (
                    <View style={styles.actionsSection}>
                        <View style={styles.actionsTitleContainer}>
                            <Text style={styles.actionsTitle}>Categorias rápidas</Text>
                        </View>
                        <View style={styles.actionsGrid}>
                            {availableCategories.map(cat => renderCategoryCard(cat))}
                            {availableCategories.length === 0 && (
                                <Text style={styles.emptyText}>Sem categorias disponíveis</Text>
                            )}
                        </View>
                    </View>
                )}

                {(role === 'operacional' || role === 'master') && (
                    <View style={styles.actionsSection}>
                        <View style={styles.actionsTitleContainer}>
                            <Text style={styles.actionsTitle}>Ações rápidas</Text>
                            <Text style={styles.actionsSubtitle}>Botões maiores para o fluxo principal do almoxarifado.</Text>
                        </View>
                        <View style={styles.actionsGrid}>
                            {canManageDocuments ? (
                                <TouchableOpacity
                                    style={[styles.actionCard, styles.actionCardWide, styles.documentsCard]}
                                    onPress={handleOpenDocumentos}
                                    activeOpacity={0.86}
                                >
                                    <Text style={styles.actionIcon}>🧾</Text>
                                    <Text style={styles.actionLabel}>Entradas fiscais</Text>
                                    <Text style={styles.actionSubLabel}>NF, cupom, recibo e lançamento manual</Text>
                                </TouchableOpacity>
                            ) : (
                                <View style={[styles.actionCard, styles.actionCardWide, styles.lockedActionCard]}>
                                    <Text style={styles.actionIcon}>🔒</Text>
                                    <Text style={styles.actionLabel}>Entradas fiscais</Text>
                                    <Text style={styles.actionSubLabel}>Disponível apenas para administradores do servidor</Text>
                                </View>
                            )}

                            <TouchableOpacity
                                style={[styles.actionCard, styles.materialCard]}
                                onPress={() => handleAction('Scanner', { mode: 'withdraw' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>📤</Text>
                                <Text style={styles.actionLabel}>Retirar Material</Text>
                                <Text style={styles.actionSubLabel}>Saída rápida por código ou câmera</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.returnMaterialCard]}
                                onPress={() => handleAction('Scanner', { mode: 'return' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>📥</Text>
                                <Text style={styles.actionLabel}>Devolver</Text>
                                <Text style={styles.actionSubLabel}>Retorno simples ao estoque</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.multipleCard]}
                                onPress={() => handleAction('Retirada', { multi: true, items: [] })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>🧰</Text>
                                <Text style={styles.actionLabel}>Retirada Múltipla</Text>
                                <Text style={styles.actionSubLabel}>Monte a saída com vários itens</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.fractionCard]}
                                onPress={() => handleAction('Scanner', { mode: 'withdraw_fraction' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>✂️</Text>
                                <Text style={styles.actionLabel}>Retirada Fracionada</Text>
                                <Text style={styles.actionSubLabel}>Movimente frações sem sair da base</Text>
                            </TouchableOpacity>

                        </View>
                    </View>
                )}

                {dailyCustodyVisible && (
                    <DailyCustodyPanel
                        groups={dailyCustodyGroups}
                        summary={dailyCustodySummary}
                        loading={dailyCustodyLoading}
                        message={dailyCustodyMessage}
                        isReturning={dailyCustodyReturning}
                        onReload={loadDailyCustody}
                        onReturnSelectedPress={handleDailyCustodyReturn}
                        onReturnAllPress={handleDailyCustodyReturn}
                    />
                )}
            </View>
        );
    }, [canManageDocuments, categoriaStats, connectionStatus, dailyCustodyGroups, dailyCustodyLoading, dailyCustodyMessage, dailyCustodyReturning, dailyCustodySummary, dailyCustodyVisible, downloadingDatabase, handleClearSearch, handleDailyCustodyReturn, handleDownloadDatabase, handleOpenDocumentos, handleOpenMenu, handleOpenNotifications, items.length, loadDailyCustody, offlineDelta.entradas, offlineDelta.retiradas, offlineSnapshot?.totalItens, pendingOpsCount, recentNotificationLabels, role, roleLabel, searchQuery, unreadNotifications, user]);


                    {(unreadNotifications > 0 || recentNotificationLabels.length > 0) && (
                        <TouchableOpacity
                            style={styles.alertHighlightCard}
                            onPress={handleOpenNotifications}
                            activeOpacity={0.86}
                        >
                            <View style={styles.alertHighlightHeader}>
                                <Text style={styles.alertHighlightTitle}>Notificações operacionais</Text>
                                <Text style={styles.alertHighlightCount}>{unreadNotifications > 0 ? `${unreadNotifications} nova(s)` : 'Inbox'}</Text>
                            </View>
                            <Text style={styles.alertHighlightText}>
                                {recentNotificationLabels.length > 0
                                    ? `Saídas, entradas e devoluções em destaque: ${recentNotificationLabels.join(' • ')}`
                                    : 'Abra o inbox para acompanhar as movimentações do dia.'}
                            </Text>
                        </TouchableOpacity>
                    )}
    return (
        <View style={styles.container}>
            {/* 🌐 Banner de Status de Conexão */}
            {connectionStatus === 'offline' && (
                <View style={styles.offlineBanner}>
                    <View style={styles.offlineBannerContent}>
                        <Text style={styles.offlineBannerText}>
                            Modo offline
                            {pendingOpsCount > 0 && ` - ${pendingOpsCount} operação(ões) pendente(s)`}
                        </Text>
                        <TouchableOpacity
                            style={styles.syncButton}
                            onPress={handleManualSync}
                            disabled={isSyncing}
                        >
                            <Text style={styles.syncButtonText}>
                                {isSyncing ? 'Sincronizando...' : 'Sincronizar'}
                            </Text>
                        </TouchableOpacity>
                    </View>
                </View>
            )}
            {connectionStatus === 'syncing' && (
                <View style={[styles.offlineBanner, styles.syncingBanner]}>
                    <View style={styles.offlineBannerContent}>
                        <Text style={styles.offlineBannerText}>
                            Sincronizando operações...
                        </Text>
                    </View>
                </View>
            )}
            
            <FlatList
                data={filteredItems}
                renderItem={renderItem}
                keyExtractor={(item, index) => item.codigo_barras || item.id?.toString() || `${item.descricao || item.nome || 'item'}-${index}`}
                contentContainerStyle={styles.listContainer}
                ListHeaderComponent={listHeaderComponent}
                refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} colors={['#22c55e']} />
                }
                initialNumToRender={10}
                maxToRenderPerBatch={10}
                windowSize={5}
                removeClippedSubviews={false}
                keyboardShouldPersistTaps="always"
                keyboardDismissMode="none"
                ListEmptyComponent={
                    !loading && (
                        <View style={styles.emptyContainer}>
                            <Text style={styles.emptyText}>Nenhum item encontrado</Text>
                        </View>
                    )
                }
            />
            {loading && !refreshing && items.length === 0 && (
                 <View style={styles.loadingOverlay}>
                    <ActivityIndicator size="large" color="#22c55e" />
                    <Text style={styles.loadingText}>Sincronizando...</Text>
                 </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: heroPalette.bg,
    },
    loadingOverlay: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(6,16,27,0.88)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 10,
    },
    loadingText: {
        marginTop: 10,
        color: heroPalette.primary,
        fontWeight: 'bold',
    },
    modernHeader: {
        marginTop: 14,
        marginHorizontal: 14,
        marginBottom: 14,
        backgroundColor: heroPalette.panel,
        borderRadius: 28,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingTop: Platform.OS === 'ios' ? 18 : 16,
        paddingBottom: 16,
        paddingHorizontal: 16,
        ...heroShadow,
    },
    headerTop: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 14,
    },
    headerTextContainer: {
        flex: 1,
        paddingRight: 12,
    },
    headerEyebrow: {
        fontSize: 10,
        fontWeight: '900',
        letterSpacing: 1.2,
        textTransform: 'uppercase',
        color: heroPalette.primary,
    },
    headerOperatorName: {
        marginTop: 12,
        fontSize: 17,
        fontWeight: '700',
        color: heroPalette.text,
    },
    headerTitle: {
        marginTop: 6,
        fontSize: 26,
        fontWeight: '800',
        color: heroPalette.text,
        letterSpacing: -0.6,
    },
    headerSubtitle: {
        fontSize: 12,
        fontWeight: '600',
        color: heroPalette.textMuted,
        marginTop: 4,
    },
    modernMenuButton: {
        minWidth: 44,
        minHeight: 44,
        backgroundColor: heroPalette.panelAlt,
        borderRadius: 14,
        paddingHorizontal: 10,
        paddingVertical: 10,
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    headerButtons: {
        flexDirection: 'row',
        gap: 8,
        alignItems: 'center',
    },
    headerNotifyBadge: {
        position: 'absolute',
        top: -6,
        right: -6,
        minWidth: 20,
        height: 20,
        borderRadius: 10,
        paddingHorizontal: 4,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.danger,
        borderWidth: 1,
        borderColor: heroPalette.bg,
    },
    headerNotifyBadgeText: {
        color: '#fff',
        fontSize: 10,
        fontWeight: '800',
    },
    modernMenuIcon: {
        fontSize: 18,
        fontWeight: '900',
        color: heroPalette.text,
    },
    downloadDatabaseButton: {
        minWidth: 92,
    },
    downloadDatabaseButtonText: {
        fontSize: 12,
        fontWeight: '800',
        color: heroPalette.text,
    },
    headerMetaRow: {
        flexDirection: 'row',
        gap: 10,
        marginBottom: 14,
    },
    headerMetaCard: {
        flex: 1,
        borderRadius: 18,
        paddingHorizontal: 14,
        paddingVertical: 12,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    headerMetaLabel: {
        fontSize: 10,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 0.9,
        color: heroPalette.textMuted,
    },
    headerMetaValue: {
        marginTop: 8,
        fontSize: 18,
        fontWeight: '800',
        color: heroPalette.text,
    },
    headerMetaHint: {
        marginTop: 2,
        fontSize: 11,
        color: heroPalette.textMuted,
    },
    headerSearchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: heroPalette.bgAlt,
        borderRadius: 20,
        paddingHorizontal: 16,
        paddingVertical: 13,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
    },
    searchIcon: {
        fontSize: 18,
        marginRight: 10,
        color: heroPalette.primary,
    },
    headerSearchInput: {
        flex: 1,
        fontSize: 15,
        color: heroPalette.text,
        fontWeight: '600',
    },
    clearSearchIcon: {
        fontSize: 18,
        color: heroPalette.textMuted,
        paddingLeft: 8,
    },
    alertHighlightCard: {
        marginTop: 14,
        borderRadius: 18,
        borderWidth: 1,
        borderColor: 'rgba(251, 191, 36, 0.34)',
        backgroundColor: 'rgba(251, 191, 36, 0.1)',
        paddingHorizontal: 14,
        paddingVertical: 14,
    },
    alertHighlightHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 6,
        gap: 12,
    },
    alertHighlightTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '800',
    },
    alertHighlightCount: {
        color: heroPalette.warning,
        fontSize: 12,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 0.6,
    },
    alertHighlightText: {
        color: heroPalette.textSoft,
        fontSize: 12,
        lineHeight: 18,
    },
    kpiSection: {
        padding: 16,
        backgroundColor: heroPalette.panel,
        marginBottom: 12,
        marginHorizontal: 14,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    kpiHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 14,
    },
    kpiTitle: {
        fontSize: 17,
        fontWeight: '700',
        color: heroPalette.text,
    },
    offlineModeBadge: {
        backgroundColor: 'rgba(251, 113, 133, 0.14)',
        paddingHorizontal: 12,
        paddingVertical: 5,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: 'rgba(251, 113, 133, 0.35)',
    },
    offlineModeText: {
        fontSize: 11,
        fontWeight: '700',
        color: heroPalette.danger,
    },
    kpiGrid: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 12,
    },
    kpiCard: {
        flex: 1,
        borderRadius: 18,
        paddingVertical: 16,
        alignItems: 'center',
        borderWidth: 1,
        paddingHorizontal: 10,
    },
    kpiOfflineEntradas: {
        backgroundColor: 'rgba(251, 191, 36, 0.14)',
        minHeight: 120,
        borderColor: 'rgba(251, 191, 36, 0.32)',
    },
    kpiInventoryCard: {
        backgroundColor: 'rgba(34, 211, 238, 0.12)',
        minHeight: 120,
        borderColor: 'rgba(34, 211, 238, 0.28)',
    },
    kpiValue: {
        fontSize: 22,
        fontWeight: '800',
        color: heroPalette.text,
    },
    kpiLabel: {
        marginTop: 5,
        fontSize: 12,
        fontWeight: '600',
        color: heroPalette.textMuted,
    },
    kpiValueContainer: {
        flexDirection: 'row',
        justifyContent: 'center',
    },
    actionsSection: {
        paddingHorizontal: 14,
        paddingBottom: 12,
        backgroundColor: heroPalette.panel,
        marginBottom: 12,
        marginHorizontal: 14,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    actionsTitleContainer: {
        paddingTop: 14,
        paddingBottom: 8,
    },
    actionsTitle: {
        fontSize: 18,
        fontWeight: '800',
        color: heroPalette.text,
    },
    actionsSubtitle: {
        marginTop: 4,
        fontSize: 12,
        color: heroPalette.textMuted,
    },
    actionsGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        gap: 12,
        paddingBottom: 14,
    },
    actionCard: {
        width: '48%',
        minHeight: 132,
        borderRadius: 22,
        paddingVertical: 20,
        paddingHorizontal: 16,
        alignItems: 'flex-start',
        justifyContent: 'flex-end',
        borderWidth: 1,
        ...heroSoftShadow,
    },
    actionCardWide: {
        width: '100%',
        minHeight: 116,
    },
    categoryCard: {
        width: '48%',
        backgroundColor: heroPalette.panelAlt,
        borderRadius: 20,
        padding: 18,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: heroPalette.border,
        marginBottom: 8,
        ...heroSoftShadow,
    },
    categoryIcon: {
        fontSize: 34,
        marginBottom: 10,
    },
    categoryTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: heroPalette.text,
        textAlign: 'center',
        marginBottom: 4,
    },
    categoryCount: {
        fontSize: 12,
        color: heroPalette.textMuted,
    },
    actionIcon: {
        fontSize: 30,
        marginBottom: 10,
    },
    actionLabel: {
        color: heroPalette.text,
        fontWeight: '800',
        fontSize: 16,
        lineHeight: 20,
    },
    actionSubLabel: {
        marginTop: 6,
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 17,
    },
    materialCard: { backgroundColor: 'rgba(96, 165, 250, 0.16)', borderColor: 'rgba(96, 165, 250, 0.38)' },
    multipleCard: { backgroundColor: 'rgba(167, 139, 250, 0.16)', borderColor: 'rgba(167, 139, 250, 0.38)' },
    toolCard: { backgroundColor: 'rgba(251, 146, 60, 0.16)', borderColor: 'rgba(251, 146, 60, 0.38)' },
    returnCard: { backgroundColor: 'rgba(251, 113, 133, 0.14)', borderColor: 'rgba(251, 113, 133, 0.35)' },
    returnMaterialCard: { backgroundColor: 'rgba(52, 211, 153, 0.15)', borderColor: 'rgba(52, 211, 153, 0.35)' },
    fractionCard: { backgroundColor: 'rgba(34, 211, 238, 0.15)', borderColor: 'rgba(34, 211, 238, 0.35)' },
    documentsCard: { backgroundColor: 'rgba(251, 191, 36, 0.14)', borderColor: 'rgba(251, 191, 36, 0.38)' },
    lockedActionCard: { backgroundColor: 'rgba(148, 163, 184, 0.12)', borderColor: 'rgba(148, 163, 184, 0.28)' },
    multipleToolsCard: { backgroundColor: '#fef3c7', borderWidth: 2, borderColor: '#fbbf24' },
    multipleReturnToolsCard: { backgroundColor: '#ddd6fe', borderWidth: 2, borderColor: '#a78bfa' },
    multipleReturnMaterialsCard: { backgroundColor: '#bbf7d0', borderWidth: 2, borderColor: '#4ade80' },
    cadastroCard: { backgroundColor: '#dcfce7', borderWidth: 2, borderColor: '#22c55e' },
    ferramentasCard: { backgroundColor: '#e0e7ff', borderWidth: 2, borderColor: '#6366f1' },
    
    listContainer: {
        paddingBottom: 28,
    },
    itemCard: {
        backgroundColor: heroPalette.panel,
        borderRadius: 20,
        padding: 16,
        marginBottom: 12,
        marginHorizontal: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    itemHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 10,
    },
    itemName: {
        flex: 1,
        fontSize: 16,
        fontWeight: '700',
        color: heroPalette.text,
        marginRight: 10,
    },
    badge: {
        paddingHorizontal: 13,
        paddingVertical: 7,
        borderRadius: 14,
        minWidth: 50,
        alignItems: 'center',
    },
    badgeSuccess: { backgroundColor: '#22c55e' },
    badgeWarning: { backgroundColor: '#f59e0b' },
    badgeDanger: { backgroundColor: '#ef4444' },
    badgeText: {
        color: '#fff',
        fontWeight: '800',
        fontSize: 14,
    },
    itemBarcode: {
        fontSize: 13,
        color: heroPalette.primary,
        marginBottom: 6,
        fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
        fontWeight: '500',
    },
    itemDetails: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
    },
    itemDetail: {
        fontSize: 13,
        color: heroPalette.textMuted,
        fontWeight: '500',
    },
    emptyContainer: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 70,
        paddingHorizontal: 24,
    },
    emptyIcon: {
        fontSize: 68,
        marginBottom: 16,
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 6,
    },
    emptySubtext: {
        fontSize: 14,
        color: heroPalette.textMuted,
        fontWeight: '500',
    },
    offlineBanner: {
        backgroundColor: '#9a3412',
        paddingVertical: 11,
        paddingHorizontal: 16,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(255,255,255,0.12)',
    },
    syncingBanner: {
        backgroundColor: '#0f766e',
        borderBottomColor: 'rgba(255,255,255,0.12)',
    },
    offlineBannerContent: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    offlineBannerText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '700',
        flex: 1,
    },
    syncButton: {
        backgroundColor: 'rgba(255,255,255,0.18)',
        paddingVertical: 7,
        paddingHorizontal: 14,
        borderRadius: 10,
        marginLeft: 10,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.18)',
    },
    syncButtonText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '800',
    },
});
