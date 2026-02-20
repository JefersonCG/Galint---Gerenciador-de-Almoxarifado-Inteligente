import React, { useMemo, useState, useEffect, useCallback } from 'react';
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
    
    // 🔄 Estados para Banner de Conexão
    const [connectionStatus, setConnectionStatus] = useState('online'); // 'online' | 'offline' | 'syncing'
    const [pendingOpsCount, setPendingOpsCount] = useState(0);
    const [isSyncing, setIsSyncing] = useState(false);
    const [downloadingDatabase, setDownloadingDatabase] = useState(false);

    // Determinar permissão
    const role = useMemo(() => getUserRole(user), [user]);

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
    }, [navigation]);

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
             // Ao focar, tenta dar um refresh suave
             loadEstoque(searchQuery, true);
        });
        return unsubscribe;
    }, [navigation, searchQuery]);

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

    const handleSearch = (text) => {
        setSearchQuery(text);
        // O useEffect cuida do reload
    };

    const handleRefresh = () => {
        setRefreshing(true);
        // Forçar um sync Cycle agora
        SyncService.runSync().finally(() => {
            loadEstoque(searchQuery);
            setRefreshing(false);
        });
    };

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
            navigation.navigate('EditarItem', { user, item });
        }
    };

    const handleCategoriaPress = (categoria) => {
        setSearchQuery(categoria);
    };

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

    // Componente de Header da Lista (Tudo que fica acima dos itens)
    const renderListHeader = () => {
        const availableCategories = Object.keys(categoriaStats);
        
        return (
            <View>
                {/* Header Topo */}
                <View style={styles.modernHeader}>
                    <View style={styles.headerTop}>
                        <View style={styles.headerTextContainer}>
                            <Text style={styles.headerTitle}>{user?.nome || user?.username || 'Usuário'}</Text>
                            <Text style={styles.headerSubtitle}>{role.toUpperCase()} - {user?.matricula || ''}</Text>
                        </View>
                        <View style={styles.headerButtons}>
                            <TouchableOpacity
                                onPress={handleDownloadDatabase}
                                style={[styles.modernMenuButton, styles.syncButton]}
                                disabled={downloadingDatabase}
                            >
                                {downloadingDatabase ? (
                                    <ActivityIndicator size="small" color="#fff" />
                                ) : (
                                    <Text style={styles.modernMenuIcon}>📥</Text>
                                )}
                            </TouchableOpacity>
                            <TouchableOpacity
                                onPress={() => navigation.navigate('Menu')}
                                style={styles.modernMenuButton}
                            >
                                <Text style={styles.modernMenuIcon}>Menu</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                    
                    {/* Search Bar */}
                    <View style={styles.headerSearchContainer}>
                        <Text style={styles.searchIcon}>🔍</Text>
                        <TextInput
                            style={styles.headerSearchInput}
                            placeholder="Pesquisar (Autocomplete)..."
                            placeholderTextColor="#a3d9a5"
                            value={searchQuery}
                            onChangeText={handleSearch}
                            returnKeyType="search"
                        />
                        {searchQuery !== '' && (
                            <TouchableOpacity onPress={() => setSearchQuery('')}>
                                <Text style={styles.clearSearchIcon}>✕</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                </View>

                {/* KPI Offline */}
                {isOfflineMode && (
                    <View style={styles.kpiSection}>
                        <View style={styles.kpiHeader}>
                            <Text style={styles.kpiTitle}>📊 Indicador</Text>
                            <View style={styles.offlineModeBadge}>
                                <Text style={styles.offlineModeText}>Modo offline</Text>
                            </View>
                        </View>
                        <View style={styles.kpiGrid}>
                            <View style={[styles.kpiCard, styles.kpiOfflineEntradas]}>
                                <View style={styles.kpiValueContainer}>
                                    <Text style={styles.kpiValue}>
                                        {offlineDelta.entradas + offlineDelta.retiradas}
                                    </Text>
                                </View>
                                <Text style={styles.kpiLabel}>Operações pendentes</Text>
                            </View>
                        </View>
                    </View>
                )}

                {/* VISÃO GERENCIA: CATEGORIAS */}
                {role === 'gerencia' && (
                    <View style={styles.actionsSection}>
                        <View style={styles.actionsTitleContainer}>
                            <Text style={styles.actionsTitle}>📂 Categorias</Text>
                        </View>
                        <View style={styles.actionsGrid}>
                            {availableCategories.map(cat => renderCategoryCard(cat))}
                            {availableCategories.length === 0 && (
                                <Text style={styles.emptyText}>Sem categorias disponíveis</Text>
                            )}
                        </View>
                    </View>
                )}

                {/* VISÃO OPERACIONAL e MASTER: AÇÕES */}
                {(role === 'operacional' || role === 'master') && (
                    <View style={styles.actionsSection}>
                        <View style={styles.actionsTitleContainer}>
                            <Text style={styles.actionsTitle}>Ações rápidas</Text>
                        </View>
                        <View style={styles.actionsGrid}>
                            <TouchableOpacity
                                style={[styles.actionCard, styles.materialCard]}
                                onPress={() => handleAction('Scanner', { mode: 'withdraw' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionLabel}>Retirar Material</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.returnMaterialCard]}
                                onPress={() => handleAction('Scanner', { mode: 'return' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionLabel}>Devolver</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.multipleCard]}
                                onPress={() => handleAction('Retirada', { multi: true, items: [] })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionLabel}>Retirada Múltipla</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.fractionCard]}
                                onPress={() => handleAction('Scanner', { mode: 'withdraw_fraction' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionLabel}>Retirada Fracionada</Text>
                            </TouchableOpacity>

                            {/* CADASTRAR - MASTER OU GERENCIA */}
                            {(role === 'master' || role === 'gerencia') && (
                                <TouchableOpacity
                                    style={[styles.actionCard, styles.cadastroCard]}
                                    onPress={() => handleAction('CadastroMultiplo')}
                                    activeOpacity={0.8}
                                >
                                    <Text style={styles.actionLabel}>Cadastrar Itens</Text>
                                </TouchableOpacity>
                            )}

                        </View>
                    </View>
                )}
            </View>
        );
    };

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
                keyExtractor={(item) => item.codigo_barras || item.id?.toString() || Math.random().toString()}
                contentContainerStyle={styles.listContainer}
                ListHeaderComponent={renderListHeader}
                refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} colors={['#22c55e']} />
                }
                initialNumToRender={10}
                maxToRenderPerBatch={10}
                windowSize={5}
                removeClippedSubviews={true}
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
        backgroundColor: '#f8fafc',
    },
    listContainer: {
        paddingBottom: 20,
    },
    loadingOverlay: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(248,250,252,0.9)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 10,
    },
    loadingText: {
        marginTop: 10,
        color: '#10b981',
        fontWeight: 'bold',
    },
    // ========== HEADER ==========
    modernHeader: {
        backgroundColor: '#10b981',
        paddingTop: Platform.OS === 'ios' ? 50 : 15,
        paddingBottom: 15,
        paddingHorizontal: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.2,
        shadowRadius: 8,
        elevation: 10,
    },
    headerTop: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 14,
    },
    headerTextContainer: {
        flex: 1,
    },
    headerTitle: {
        fontSize: 20,
        fontWeight: '800',
        color: '#ffffff',
        letterSpacing: 0.6,
    },
    headerSubtitle: {
        fontSize: 13,
        fontWeight: '600',
        color: '#d1fae5',
        marginTop: 2,
    },
    modernMenuButton: {
        backgroundColor: 'rgba(255, 255, 255, 0.3)',
        borderRadius: 12,
        padding: 11,
        justifyContent: 'center',
        alignItems: 'center',
    },
    headerButtons: {
        flexDirection: 'row',
        gap: 10,
    },
    syncButton: {
        minWidth: 44,
    },
    modernMenuIcon: {
        fontSize: 22,
    },
    headerSearchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#ffffff',
        borderRadius: 28,
        paddingHorizontal: 16,
        paddingVertical: 11,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 3 },
        shadowOpacity: 0.15,
        shadowRadius: 6,
        elevation: 5,
    },
    searchIcon: {
        fontSize: 18,
        marginRight: 10,
        color: '#10b981',
    },
    headerSearchInput: {
        flex: 1,
        fontSize: 15,
        color: '#1f2937',
        fontWeight: '500',
    },
    clearSearchIcon: {
        fontSize: 18,
        color: '#9ca3af',
        paddingLeft: 8,
    },
    // ========== KPI ==========
    kpiSection: {
        padding: 16,
        backgroundColor: '#fff',
        marginBottom: 12,
        marginHorizontal: 12,
        marginTop: 12,
        borderRadius: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.08,
        shadowRadius: 8,
        elevation: 3,
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
        color: '#111827',
    },
    offlineModeBadge: {
        backgroundColor: '#fef2f2',
        paddingHorizontal: 12,
        paddingVertical: 5,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: '#fca5a5',
    },
    offlineModeText: {
        fontSize: 11,
        fontWeight: '700',
        color: '#dc2626',
    },
    kpiGrid: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 12,
    },
    kpiCard: {
        flex: 1,
        borderRadius: 14,
        paddingVertical: 16,
        alignItems: 'center',
        borderWidth: 1,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 6,
        elevation: 2,
    },
    kpiOfflineEntradas: {
        backgroundColor: '#fef3c7',
        minHeight: 120,
        borderColor: '#fbbf24',
    },
    kpiValue: {
        fontSize: 22,
        fontWeight: '800',
        color: '#111827',
    },
    kpiLabel: {
        marginTop: 5,
        fontSize: 12,
        fontWeight: '600',
        color: '#4b5563',
    },
    kpiValueContainer: {
        flexDirection: 'row',
        justifyContent: 'center',
    },
    // ========== AÇÕES / CARDS ==========
    actionsSection: {
        paddingHorizontal: 12,
        paddingBottom: 12,
        backgroundColor: '#fff',
        marginBottom: 12,
        marginHorizontal: 12,
        borderRadius: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.08,
        shadowRadius: 8,
        elevation: 3,
    },
    actionsTitleContainer: {
        paddingTop: 14,
        paddingBottom: 8,
    },
    actionsTitle: {
        fontSize: 15,
        fontWeight: '700',
        color: '#111827',
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
        minHeight: 96,
        borderRadius: 16,
        paddingVertical: 16,
        paddingHorizontal: 12,
        alignItems: 'center',
        justifyContent: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 3 },
        shadowOpacity: 0.1,
        shadowRadius: 8,
        elevation: 4,
    },
    categoryCard: {
        width: '48%',
        backgroundColor: '#ffffff',
        borderRadius: 16,
        padding: 18,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 2,
        borderColor: '#e5e7eb',
        marginBottom: 8,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 6,
        elevation: 2,
    },
    categoryIcon: {
        fontSize: 34,
        marginBottom: 10,
    },
    categoryTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: '#1f2937',
        textAlign: 'center',
        marginBottom: 4,
    },
    categoryCount: {
        fontSize: 12,
        color: '#6b7280',
    },
    actionIcon: {
        fontSize: 26,
        marginBottom: 7,
    },
    actionLabel: {
        color: '#1f2937',
        fontWeight: '700',
        fontSize: 13,
        lineHeight: 17,
        textAlign: 'center',
    },
    materialCard: { backgroundColor: '#dbeafe', borderWidth: 1, borderColor: '#93c5fd' },
    multipleCard: { backgroundColor: '#f3e8ff', borderWidth: 1, borderColor: '#d8b4fe' },
    toolCard: { backgroundColor: '#ffedd5', borderWidth: 1, borderColor: '#fdba74' },
    returnCard: { backgroundColor: '#fee2e2', borderWidth: 1, borderColor: '#fca5a5' },
    returnMaterialCard: { backgroundColor: '#d1fae5', borderWidth: 1, borderColor: '#6ee7b7' },
    fractionCard: { backgroundColor: '#cffafe', borderWidth: 1, borderColor: '#67e8f9' },
    multipleToolsCard: { backgroundColor: '#fef3c7', borderWidth: 2, borderColor: '#fbbf24' },
    multipleReturnToolsCard: { backgroundColor: '#ddd6fe', borderWidth: 2, borderColor: '#a78bfa' },
    multipleReturnMaterialsCard: { backgroundColor: '#bbf7d0', borderWidth: 2, borderColor: '#4ade80' },
    cadastroCard: { backgroundColor: '#dcfce7', borderWidth: 2, borderColor: '#22c55e' },
    ferramentasCard: { backgroundColor: '#e0e7ff', borderWidth: 2, borderColor: '#6366f1' },
    
    listContainer: {
        padding: 15,
        paddingTop: 10,
    },
    itemCard: {
        backgroundColor: '#ffffff',
        borderRadius: 14,
        padding: 16,
        marginBottom: 12,
        borderWidth: 1,
        borderColor: '#e5e7eb',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.06,
        shadowRadius: 6,
        elevation: 2,
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
        color: '#1f2937',
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
        color: '#6b7280',
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
        color: '#6b7280',
        fontWeight: '500',
    },
    emptyContainer: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 70,
    },
    emptyIcon: {
        fontSize: 68,
        marginBottom: 16,
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '700',
        color: '#4b5563',
        marginBottom: 6,
    },
    emptySubtext: {
        fontSize: 14,
        color: '#9ca3af',
        fontWeight: '500',
    },
    // ========== BANNER DE CONEXÃO ==========
    offlineBanner: {
        backgroundColor: '#f97316',
        paddingVertical: 11,
        paddingHorizontal: 16,
        borderBottomWidth: 2,
        borderBottomColor: '#ea580c',
    },
    syncingBanner: {
        backgroundColor: '#3b82f6',
        borderBottomColor: '#2563eb',
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
        backgroundColor: 'rgba(255,255,255,0.35)',
        paddingVertical: 7,
        paddingHorizontal: 14,
        borderRadius: 8,
        marginLeft: 10,
    },
    syncButtonText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '800',
    },
});
