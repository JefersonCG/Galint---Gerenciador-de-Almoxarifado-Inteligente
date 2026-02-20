import React, { useMemo, useState, useEffect } from 'react';
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
    ScrollView,
    Image,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ApiService from '../services/api';
import HeartbeatService from '../services/heartbeatService';
import InactivityService from '../services/inactivityService';
import { getOnlineSnapshot, getOfflineDelta, saveOnlineSnapshot } from '../services/offlineDb';

// Função Centralizada de Permissões
function getUserRole(user) {
    if (!user) return 'guest';
    
    const cargo = (user.cargo || '').toString().toLowerCase().trim();
    const setor = (user.setor || '').toString().toLowerCase().trim();
    const isAdmin = user.is_admin || String(user.is_admin || '').trim() === '1';
    // is_manager deprecated in favor of specific cargo checks, but kept for compatibility
    const isManagerLegacy = user.is_manager; 

    // 1. MASTER (Almoxarifes)
    // "Somente os Almoxarifes são administradores master"
    if (isAdmin || cargo.includes('almoxarif')) {
        return 'master';
    }

    // 2. GERENCIA
    // "Os cadastrados no setor GRENCIA somente terão cards"
    if (cargo.includes('gerente') || setor.includes('gerenc') || setor.includes('adm')) {
        return 'gerencia';
    }

    // 3. OPERACIONAL (Supervisores, Zeladores)
    // "todos que são supervisores e zeladores"
    if (cargo.includes('supervisor') || cargo.includes('zelador') || isManagerLegacy) {
        return 'operacional';
    }

    // Fallback: Se tiver cargo mas não caiu nos acima, tratamos como Operacional (visão restrita)
    // ou Guest se não tiver login válido.
    return 'operacional'; 
}

export default function EstoqueScreen({ navigation, route }) {
    const [items, setItems] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [categoriaStats, setCategoriaStats] = useState({});
    const [selectedCategoria, setSelectedCategoria] = useState(null);
    const [offlineSnapshot, setOfflineSnapshot] = useState(null);
    const [offlineDelta, setOfflineDelta] = useState({ entradas: 0, retiradas: 0 });
    const [isOfflineMode, setIsOfflineMode] = useState(false);
    const [kpiServer, setKpiServer] = useState(null);
    const [user, setUser] = useState(route.params?.user || null);

    // Determinar permissão
    const role = useMemo(() => getUserRole(user), [user]);

    useEffect(() => {
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
        }
        loadEstoque();
        loadOfflineData();
        
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
        };
    }, [navigation]);

    useEffect(() => {
        const unsubscribe = navigation.addListener('focus', () => {
            loadEstoque(searchQuery);
        });
        return unsubscribe;
    }, [navigation, searchQuery]);

    const loadEstoque = async (search = '') => {
        try {
            const result = await ApiService.getEstoque(search);
            if (result.success) {
                setItems(result.data);
                calcularCategoriaStats(result.data);
                const offline = !!result.offline;
                setIsOfflineMode(offline);
                if (offline) {
                    setKpiServer(null);
                }

                if (!offline) {
                    const resumo = await ApiService.getEstoqueResumo();
                    if (resumo.success) {
                        setKpiServer(resumo.data);
                        await saveOnlineSnapshot(
                            resumo.data.total_itens,
                            resumo.data.total_quantidade,
                            resumo.data.total_categorias
                        );
                    } else {
                        setKpiServer(null);
                        const totalItens = result.data.length;
                        const totalQuantidade = result.data.reduce((acc, item) => acc + (Number(item?.quantidade) || 0), 0);
                        const categorias = [...new Set(result.data.map(i => i.categoria || 'Outros'))];
                        const totalCategorias = categorias.length;
                        await saveOnlineSnapshot(totalItens, totalQuantidade, totalCategorias);
                    }
                }

                await loadOfflineData();
            } else {
                Alert.alert('Erro', result.message);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao carregar estoque');
            setIsOfflineMode(true);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    const loadOfflineData = async () => {
        try {
            const snapshot = await getOnlineSnapshot();
            const delta = await getOfflineDelta();
            setOfflineSnapshot(snapshot);
            setOfflineDelta(delta);
        } catch (error) {
            console.log('[EstoqueScreen] Erro ao carregar dados offline:', error);
        }
    };

    const calcularCategoriaStats = (items) => {
        const stats = {};
        items.forEach(item => {
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
    // Displayed items will be filteredItems, unless reloading from server.
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

    const handleSearch = () => {
        // Keeps keyboard open, acts as "Go" button, but local filtering is already happening
        InactivityService.recordActivity();
        loadEstoque(searchQuery); // Optional: force refresh from server
    };

    const handleCategoriaPress = (categoria) => {
        setSelectedCategoria(categoria);
        setSearchQuery(categoria);
        // loadEstoque(categoria); // Keep local filter feeling first
    };

    const handleRefresh = () => {
        setRefreshing(true);
        loadEstoque(searchQuery);
    };

    // Navigation Handlers
    const handleAction = (action, params = {}) => {
        InactivityService.recordActivity();
        navigation.navigate(action, { user, ...params });
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
        // Gerencia: Apenas visualiza (detalhes ou não, aqui sem permissão de editar)
        // Master: Pode editar
        // Operacional: Apenas visualiza
        if (role === 'master') {
            navigation.navigate('EditarItem', { user, item });
        } else {
            // Apenas Feedback visual ou navegação para detalhe (se existisse)
            // Alert.alert('Detalhes', `${item.descricao}\nQuantidade: ${item.quantidade}`);
        }
    };

    const renderItem = ({ item }) => {
        const q = Number(item?.quantidade ?? 0);
        const quantidadeInt = Number.isFinite(q) ? Math.trunc(q) : 0;
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
                    <Text style={styles.badgeText}>{quantidadeInt}</Text>
                </View>
            </View>

            {item.codigo_barras && (
                <Text style={styles.itemBarcode}>📊 {item.codigo_barras}</Text>
            )}

            <View style={styles.itemDetails}>
                {item.categoria && (
                    <Text style={styles.itemDetail}>🏷️ {item.categoria}</Text>
                )}
                {item.localizacao && (
                    <Text style={styles.itemDetail}>📍 {item.localizacao}</Text>
                )}
                {item.marca && (
                    <Text style={styles.itemDetail}>🏭 {item.marca}</Text>
                )}
            </View>
        </TouchableOpacity>
        );
    };

    const renderCategoryCard = (catName) => {
        const stats = categoriaStats[catName];
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

    if (loading && !refreshing) {
        return (
            <View style={styles.centerContainer}>
                <ActivityIndicator size="large" color="#0d6efd" />
                <Text style={styles.loadingText}>Carregando estoque...</Text>
            </View>
        );
    }

    // LISTAS DE CATEGORIAS DISPONÍVEIS
    const availableCategories = Object.keys(categoriaStats);

    return (
        <View style={styles.container}>
            {/* Header Verde Moderno com Logo e Pesquisa */}
            <View style={styles.modernHeader}>
                <View style={styles.headerTop}>
                    <View style={styles.headerTextContainer}>
                        <Text style={styles.headerTitle}>{user?.nome || user?.username || 'Usuário'}</Text>
                        <Text style={styles.headerSubtitle}>{role.toUpperCase()} - {user?.matricula || ''}</Text>
                    </View>
                    <TouchableOpacity
                        onPress={() => navigation.navigate('Menu')}
                        style={styles.modernMenuButton}
                    >
                        <Text style={styles.modernMenuIcon}>⚙️</Text>
                    </TouchableOpacity>
                </View>
                
                {/* Barra de Pesquisa Autocomplete */}
                <View style={styles.headerSearchContainer}>
                    <Text style={styles.searchIcon}>🔍</Text>
                    <TextInput
                        style={styles.headerSearchInput}
                        placeholder="Pesquisar (Autocomplete)..."
                        placeholderTextColor="#a3d9a5"
                        value={searchQuery}
                        onChangeText={setSearchQuery} // Updates filteredItems automatically
                        returnKeyType="search"
                    />
                    {searchQuery !== '' && (
                        <TouchableOpacity onPress={() => setSearchQuery('')}>
                            <Text style={styles.clearSearchIcon}>✕</Text>
                        </TouchableOpacity>
                    )}
                </View>
            </View>

            <ScrollView style={styles.scrollContainer} keyboardShouldPersistTaps="handled">

                {/* Indicador de Entradas Offline */}
                {isOfflineMode && (
                    <View style={styles.kpiSection}>
                        <View style={styles.kpiHeader}>
                            <Text style={styles.kpiTitle}>📊 Indicador</Text>
                            <View style={styles.offlineModeBadge}>
                                <Text style={styles.offlineModeText}>🔴 Modo Offline</Text>
                            </View>
                        </View>
                        <View style={styles.kpiGrid}>
                            <View style={[styles.kpiCard, styles.kpiOfflineEntradas]}>
                                <View style={styles.kpiValueContainer}>
                                    <Text style={styles.kpiValue}>
                                        {offlineDelta.entradas}
                                    </Text>
                                </View>
                                <Text style={styles.kpiLabel}>📦 Entradas Offline</Text>
                            </View>
                        </View>
                    </View>
                )}

                {/* ================= SEÇÃO DE AÇÕES OU CATEGORIAS ================= */}
                
                {/* 1. GERENCIA: VÊ APENAS CARDS DE CATEGORIA */}
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

                {/* 2. OPERACIONAL & MASTER: VEEM BOTÕES DE AÇÃO */}
                {(role === 'operacional' || role === 'master') && (
                    <View style={styles.actionsSection}>
                        <View style={styles.actionsTitleContainer}>
                            <Text style={styles.actionsTitle}>🚀 Ações Rápidas</Text>
                        </View>
                        <View style={styles.actionsGrid}>
                            {/* BOTOES COMUNS (Operacional e Master) */}
                            <TouchableOpacity
                                style={[styles.actionCard, styles.materialCard]}
                                onPress={() => handleAction('Scanner', { mode: 'withdraw' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>✋</Text>
                                <Text style={styles.actionLabel}>Retirar Material</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.returnMaterialCard]}
                                onPress={() => handleAction('Scanner', { mode: 'material_return' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>📥</Text>
                                <Text style={styles.actionLabel}>Devolver Material</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.toolCard]}
                                onPress={() => handleAction('Scanner', { mode: 'tool_withdraw' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>🔧</Text>
                                <Text style={styles.actionLabel}>Retirar Ferramenta</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.returnCard]}
                                onPress={() => handleAction('Scanner', { mode: 'tool_return' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>↩️</Text>
                                <Text style={styles.actionLabel}>Devolver Ferramenta</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.multipleCard]}
                                onPress={() => handleAction('Retirada', { multi: true, items: [] })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>📚</Text>
                                <Text style={styles.actionLabel}>Retirada Múltipla</Text>
                            </TouchableOpacity>

                            <TouchableOpacity
                                style={[styles.actionCard, styles.fractionCard]}
                                onPress={() => handleAction('Scanner', { mode: 'withdraw_fraction' })}
                                activeOpacity={0.8}
                            >
                                <Text style={styles.actionIcon}>🧪</Text>
                                <Text style={styles.actionLabel}>Retirada Fracionada</Text>
                            </TouchableOpacity>

                            {/* EXCLUSIVO MASTER: CADASTRAR */}
                            {role === 'master' && (
                                <TouchableOpacity
                                    style={[styles.actionCard, styles.cadastroCard]}
                                    onPress={() => handleAction('CadastroMultiplo')}
                                    activeOpacity={0.8}
                                >
                                    <Text style={styles.actionIcon}>📝</Text>
                                    <Text style={styles.actionLabel}>Cadastrar Itens</Text>
                                </TouchableOpacity>
                            )}
                        </View>
                    </View>
                )}

                {/* Lista de Itens (Autocomplete Result / Listagem) */}
                <FlatList
                    data={filteredItems}
                    renderItem={renderItem}
                    keyExtractor={(item) => item.id?.toString() || item.codigo_barras?.toString() || Math.random().toString()}
                    contentContainerStyle={styles.listContainer}
                    refreshControl={
                        <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
                    }
                    scrollEnabled={false}
                    ListEmptyComponent={
                        <View style={styles.emptyContainer}>
                            <Text style={styles.emptyIcon}>📦</Text>
                            <Text style={styles.emptyText}>Nenhum item encontrado</Text>
                            <Text style={styles.emptySubtext}>
                                {searchQuery ? 'Tente outra pesquisa' : 'Estoque vazio.'}
                            </Text>
                        </View>
                    }
                />
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    scrollContainer: {
        flex: 1,
    },
    centerContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#f5f5f5',
    },
    loadingText: {
        marginTop: 10,
        fontSize: 16,
        color: '#666',
    },
    // ========== HEADER ==========
    modernHeader: {
        backgroundColor: '#22c55e',
        paddingTop: Platform.OS === 'ios' ? 50 : 15,
        paddingBottom: 15,
        paddingHorizontal: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 6,
        elevation: 8,
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
        fontSize: 18,
        fontWeight: '800',
        color: '#ffffff',
        letterSpacing: 0.5,
    },
    headerSubtitle: {
        fontSize: 13,
        fontWeight: '500',
        color: '#e0ffe6',
        marginTop: 2,
    },
    modernMenuButton: {
        backgroundColor: 'rgba(255, 255, 255, 0.25)',
        borderRadius: 10,
        padding: 10,
        justifyContent: 'center',
        alignItems: 'center',
    },
    modernMenuIcon: {
        fontSize: 22,
    },
    headerSearchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderRadius: 25,
        paddingHorizontal: 16,
        paddingVertical: 10,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    searchIcon: {
        fontSize: 18,
        marginRight: 10,
        color: '#16a34a',
    },
    headerSearchInput: {
        flex: 1,
        fontSize: 15,
        color: '#111827',
        fontWeight: '500',
    },
    clearSearchIcon: {
        fontSize: 18,
        color: '#9ca3af',
        paddingLeft: 8,
    },
    // ========== KPI ==========
    kpiSection: {
        padding: 15,
        backgroundColor: '#fff',
        marginBottom: 10,
    },
    kpiHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 12,
    },
    kpiTitle: {
        fontSize: 16,
        fontWeight: '700',
        color: '#111827',
    },
    offlineModeBadge: {
        backgroundColor: '#fee2e2',
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: '#fecaca',
    },
    offlineModeText: {
        fontSize: 11,
        fontWeight: '600',
        color: '#dc2626',
    },
    kpiGrid: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 10,
    },
    kpiCard: {
        flex: 1,
        borderRadius: 12,
        paddingVertical: 14,
        alignItems: 'center',
        borderWidth: 1,
    },
    kpiOfflineEntradas: {
        backgroundColor: '#f59e0b',
        minHeight: 120,
        borderColor: '#fbbf24',
    },
    kpiValue: {
        fontSize: 20,
        fontWeight: '800',
        color: '#111827',
    },
    kpiLabel: {
        marginTop: 4,
        fontSize: 12,
        fontWeight: '600',
        color: '#374151',
    },
    kpiValueContainer: {
        flexDirection: 'row',
        justifyContent: 'center',
    },
    // ========== AÇÕES / CARDS ==========
    actionsSection: {
        paddingHorizontal: 15,
        paddingBottom: 10,
        backgroundColor: '#fff',
        marginBottom: 10,
        borderTopWidth: 1,
        borderTopColor: '#f0f0f0',
    },
    actionsTitleContainer: {
        paddingVertical: 10,
    },
    actionsTitle: {
        fontSize: 14,
        fontWeight: '700',
        color: '#111827',
    },
    actionsGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        gap: 10,
        paddingBottom: 10,
    },
    actionCard: {
        width: '48%',
        minHeight: 92,
        borderRadius: 12,
        paddingVertical: 14,
        paddingHorizontal: 10,
        alignItems: 'center',
        justifyContent: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.12,
        shadowRadius: 4,
        elevation: 3,
    },
    categoryCard: {
        width: '48%',
        backgroundColor: '#ffffff',
        borderRadius: 12,
        padding: 16,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: '#e5e7eb',
        marginBottom: 6,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.05,
        shadowRadius: 2,
        elevation: 2,
    },
    categoryIcon: {
        fontSize: 32,
        marginBottom: 8,
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
        fontSize: 24,
        marginBottom: 6,
    },
    actionLabel: {
        color: '#fff',
        fontWeight: '700',
        fontSize: 13,
        lineHeight: 16,
        textAlign: 'center',
    },
    materialCard: { backgroundColor: '#1e40af' },
    multipleCard: { backgroundColor: '#8b5cf6' },
    toolCard: { backgroundColor: '#f97316' },
    returnCard: { backgroundColor: '#c2410c' },
    returnMaterialCard: { backgroundColor: '#1d4ed8' },
    fractionCard: { backgroundColor: '#7c3aed' },
    cadastroCard: { backgroundColor: '#166534' },
    
    listContainer: {
        padding: 15,
        paddingTop: 10,
    },
    itemCard: {
        backgroundColor: '#fff',
        borderRadius: 10,
        padding: 15,
        marginBottom: 10,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
        elevation: 2,
    },
    itemHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 8,
    },
    itemName: {
        flex: 1,
        fontSize: 16,
        fontWeight: '600',
        color: '#333',
        marginRight: 10,
    },
    badge: {
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: 12,
        minWidth: 45,
        alignItems: 'center',
    },
    badgeSuccess: { backgroundColor: '#198754' },
    badgeWarning: { backgroundColor: '#ffc107' },
    badgeDanger: { backgroundColor: '#dc3545' },
    badgeText: {
        color: '#fff',
        fontWeight: 'bold',
        fontSize: 14,
    },
    itemBarcode: {
        fontSize: 13,
        color: '#666',
        marginBottom: 5,
        fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    },
    itemDetails: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
    },
    itemDetail: {
        fontSize: 13,
        color: '#666',
    },
    emptyContainer: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 60,
    },
    emptyIcon: {
        fontSize: 64,
        marginBottom: 15,
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '600',
        color: '#666',
        marginBottom: 5,
    },
    emptySubtext: {
        fontSize: 14,
        color: '#999',
    },
});
