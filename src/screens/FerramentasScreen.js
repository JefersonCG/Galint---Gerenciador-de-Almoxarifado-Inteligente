import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    Alert,
    ActivityIndicator,
    RefreshControl
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import ApiService from '../services/api';

export default function FerramentasScreen({ navigation }) {
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [ferramentas, setFerramentas] = useState([]);
    const [stats, setStats] = useState({
        total: 0,
        retiradas: 0,
        disponiveis: 0,
        manutencao: 0
    });

    // Carregar dados ao focar na tela
    useFocusEffect(
        React.useCallback(() => {
            loadData();
        }, [])
    );

    const loadData = async () => {
        try {
            setLoading(true);
            await Promise.all([
                loadFerramentas(),
                loadStats()
            ]);
        } catch (error) {
            console.error('Erro ao carregar dados:', error);
            Alert.alert('Erro', 'Falha ao carregar dados das ferramentas');
        } finally {
            setLoading(false);
        }
    };

    const loadFerramentas = async () => {
        try {
            const response = await ApiService.getEstoque();
            if (response.success) {
                const estoque = response.data || response.items || [];
                // Filtrar apenas itens da categoria "Ferramentas"
                const ferramenta = estoque.filter(
                    item => String(item?.categoria || '').toLowerCase().includes('ferrament')
                );
                setFerramentas(ferramenta);
            }
        } catch (error) {
            console.error('Erro ao carregar ferramentas:', error);
        }
    };

    const loadStats = async () => {
        try {
            // Aqui você pode fazer uma chamada específica para estatísticas
            // Por enquanto, vamos calcular baseado nas ferramentas carregadas
            const response = await ApiService.getEstoque();
            if (response.success) {
                const estoque = response.data || response.items || [];
                const ferramenta = estoque.filter(
                    item => String(item?.categoria || '').toLowerCase().includes('ferrament')
                );
                
                const total = ferramenta.length;
                const disponiveis = ferramenta.filter(f => (f.quantidade || 0) > 0).length;
                const retiradas = ferramenta.filter(f => (f.quantidade || 0) === 0).length;
                
                setStats({
                    total,
                    retiradas,
                    disponiveis,
                    manutencao: 0 // Implementar lógica de manutenção se necessário
                });
            }
        } catch (error) {
            console.error('Erro ao carregar estatísticas:', error);
        }
    };

    const onRefresh = async () => {
        setRefreshing(true);
        await loadData();
        setRefreshing(false);
    };

    const handleRetirarFerramenta = () => {
        navigation.navigate('Scanner', {
            mode: 'retirada',
            tipo: 'ferramenta'
        });
    };

    const handleDevolverFerramenta = () => {
        navigation.navigate('Scanner', {
            mode: 'devolucao',
            tipo: 'ferramenta'
        });
    };

    const handleVerEstoque = () => {
        // Navegar para estoque com filtro de ferramentas
        navigation.navigate('Estoque', {
            filtroCategoria: 'Ferramentas'
        });
    };

    const handleHistorico = () => {
        navigation.navigate('ReportsHistory', {
            filtroCategoria: 'Ferramentas'
        });
    };

    if (loading) {
        return (
            <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color="#2196F3" />
                <Text style={styles.loadingText}>Carregando...</Text>
            </View>
        );
    }

    return (
        <ScrollView
            style={styles.container}
            refreshControl={
                <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
            }
        >
            {/* Cabeçalho com estatísticas */}
            <View style={styles.header}>
                <Text style={styles.headerTitle}>Controle de Ferramentas</Text>
                <Text style={styles.headerSubtitle}>Gestão exclusiva para administradores</Text>
            </View>

            {/* Cards de estatísticas */}
            <View style={styles.statsContainer}>
                <View style={[styles.statCard, styles.statTotal]}>
                    <Text style={styles.statNumber}>{stats.total}</Text>
                    <Text style={styles.statLabel}>Total</Text>
                </View>
                <View style={[styles.statCard, styles.statDisponivel]}>
                    <Text style={styles.statNumber}>{stats.disponiveis}</Text>
                    <Text style={styles.statLabel}>Disponíveis</Text>
                </View>
                <View style={[styles.statCard, styles.statRetirada]}>
                    <Text style={styles.statNumber}>{stats.retiradas}</Text>
                    <Text style={styles.statLabel}>Retiradas</Text>
                </View>
            </View>

            {/* Ações Rápidas */}
            <View style={styles.section}>
                <Text style={styles.sectionTitle}>Ações rápidas</Text>
                
                <TouchableOpacity
                    style={[styles.actionCard, styles.actionRetirar]}
                    onPress={handleRetirarFerramenta}
                >
                    <View style={styles.actionContent}>
                        <Text style={styles.actionTitle}>Retirar Ferramenta</Text>
                        <Text style={styles.actionDescription}>Escanear código ou digitar manualmente</Text>
                    </View>
                    <Text style={styles.actionArrow}>›</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.actionCard, styles.actionDevolver]}
                    onPress={handleDevolverFerramenta}
                >
                    <View style={styles.actionContent}>
                        <Text style={styles.actionTitle}>Devolver Ferramenta</Text>
                        <Text style={styles.actionDescription}>Escanear código ou digitar manualmente</Text>
                    </View>
                    <Text style={styles.actionArrow}>›</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.actionCard, styles.actionEstoque]}
                    onPress={handleVerEstoque}
                >
                    <View style={styles.actionContent}>
                        <Text style={styles.actionTitle}>Ver Estoque de Ferramentas</Text>
                        <Text style={styles.actionDescription}>Consultar todas as ferramentas</Text>
                    </View>
                    <Text style={styles.actionArrow}>›</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.actionCard, styles.actionHistorico]}
                    onPress={handleHistorico}
                >
                    <View style={styles.actionContent}>
                        <Text style={styles.actionTitle}>Histórico de Movimentações</Text>
                        <Text style={styles.actionDescription}>Relatório de retiradas e devoluções</Text>
                    </View>
                    <Text style={styles.actionArrow}>›</Text>
                </TouchableOpacity>
            </View>

            {/* Lista rápida de ferramentas */}
            <View style={styles.section}>
                <Text style={styles.sectionTitle}>Ferramentas Cadastradas ({ferramentas.length})</Text>
                {ferramentas.length === 0 ? (
                    <View style={styles.emptyContainer}>
                        <Text style={styles.emptyText}>Nenhuma ferramenta cadastrada</Text>
                        <Text style={styles.emptySubtext}>
                            Cadastre ferramentas através do menu principal
                        </Text>
                    </View>
                ) : (
                    ferramentas.slice(0, 5).map((item, index) => (
                        <View key={index} style={styles.ferramentaItem}>
                            <View style={styles.ferramentaInfo}>
                                <Text style={styles.ferramentaNome} numberOfLines={1}>
                                    {item.descricao}
                                </Text>
                                <Text style={styles.ferramentaDetalhes}>
                                    {item.marca || 'Sem marca'} • {item.localizacao || 'Sem local'}
                                </Text>
                            </View>
                            <View style={styles.ferramentaQuantidade}>
                                <Text style={[
                                    styles.quantidadeText,
                                    (item.quantidade || 0) === 0 && styles.quantidadeZero
                                ]}>
                                    {item.quantidade || 0}
                                </Text>
                                <Text style={styles.quantidadeLabel}>{item.unidade || 'UN'}</Text>
                            </View>
                        </View>
                    ))
                )}
                {ferramentas.length > 5 && (
                    <TouchableOpacity
                        style={styles.verMaisButton}
                        onPress={handleVerEstoque}
                    >
                        <Text style={styles.verMaisText}>
                            Ver todas ({ferramentas.length}) →
                        </Text>
                    </TouchableOpacity>
                )}
            </View>

            {/* Informações adicionais */}
            <View style={styles.infoBox}>
                <Text style={styles.infoText}>
                    Esta área é exclusiva para administradores gerenciarem ferramentas do almoxarifado.
                </Text>
            </View>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    loadingContainer: {
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
    header: {
        backgroundColor: '#2196F3',
        padding: 20,
        paddingTop: 25,
        paddingBottom: 25,
    },
    headerTitle: {
        fontSize: 24,
        fontWeight: 'bold',
        color: '#fff',
        marginBottom: 5,
    },
    headerSubtitle: {
        fontSize: 14,
        color: 'rgba(255, 255, 255, 0.9)',
    },
    statsContainer: {
        flexDirection: 'row',
        padding: 15,
        gap: 10,
    },
    statCard: {
        flex: 1,
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 15,
        alignItems: 'center',
        elevation: 2,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
    },
    statTotal: {
        borderLeftWidth: 4,
        borderLeftColor: '#2196F3',
    },
    statDisponivel: {
        borderLeftWidth: 4,
        borderLeftColor: '#4CAF50',
    },
    statRetirada: {
        borderLeftWidth: 4,
        borderLeftColor: '#FF9800',
    },
    statNumber: {
        fontSize: 28,
        fontWeight: 'bold',
        color: '#333',
    },
    statLabel: {
        fontSize: 12,
        color: '#666',
        marginTop: 5,
    },
    section: {
        padding: 15,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: 'bold',
        color: '#333',
        marginBottom: 15,
    },
    actionCard: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 15,
        marginBottom: 10,
        flexDirection: 'row',
        alignItems: 'center',
        elevation: 2,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
    },
    actionRetirar: {
        borderLeftWidth: 4,
        borderLeftColor: '#FF9800',
    },
    actionDevolver: {
        borderLeftWidth: 4,
        borderLeftColor: '#4CAF50',
    },
    actionEstoque: {
        borderLeftWidth: 4,
        borderLeftColor: '#2196F3',
    },
    actionHistorico: {
        borderLeftWidth: 4,
        borderLeftColor: '#9C27B0',
    },
    actionIcon: {
        fontSize: 32,
        marginRight: 15,
    },
    actionContent: {
        flex: 1,
    },
    actionTitle: {
        fontSize: 16,
        fontWeight: 'bold',
        color: '#333',
        marginBottom: 3,
    },
    actionDescription: {
        fontSize: 13,
        color: '#666',
    },
    actionArrow: {
        fontSize: 30,
        color: '#ccc',
        marginLeft: 10,
    },
    ferramentaItem: {
        backgroundColor: '#fff',
        borderRadius: 8,
        padding: 12,
        marginBottom: 8,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        elevation: 1,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.05,
        shadowRadius: 1,
    },
    ferramentaInfo: {
        flex: 1,
        marginRight: 10,
    },
    ferramentaNome: {
        fontSize: 15,
        fontWeight: '600',
        color: '#333',
        marginBottom: 3,
    },
    ferramentaDetalhes: {
        fontSize: 12,
        color: '#666',
    },
    ferramentaQuantidade: {
        alignItems: 'center',
        minWidth: 50,
    },
    quantidadeText: {
        fontSize: 20,
        fontWeight: 'bold',
        color: '#4CAF50',
    },
    quantidadeZero: {
        color: '#f44336',
    },
    quantidadeLabel: {
        fontSize: 11,
        color: '#999',
        marginTop: 2,
    },
    emptyContainer: {
        alignItems: 'center',
        padding: 40,
        backgroundColor: '#fff',
        borderRadius: 12,
    },
    emptyIcon: {
        fontSize: 50,
        marginBottom: 15,
    },
    emptyText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#666',
        marginBottom: 5,
    },
    emptySubtext: {
        fontSize: 13,
        color: '#999',
        textAlign: 'center',
    },
    verMaisButton: {
        marginTop: 10,
        padding: 12,
        alignItems: 'center',
        backgroundColor: '#fff',
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#2196F3',
        borderStyle: 'dashed',
    },
    verMaisText: {
        fontSize: 14,
        color: '#2196F3',
        fontWeight: '600',
    },
    infoBox: {
        margin: 15,
        marginTop: 5,
        padding: 15,
        backgroundColor: '#E3F2FD',
        borderRadius: 8,
        flexDirection: 'row',
        alignItems: 'center',
        borderLeftWidth: 4,
        borderLeftColor: '#2196F3',
    },
    infoIcon: {
        fontSize: 20,
        marginRight: 10,
    },
    infoText: {
        flex: 1,
        fontSize: 13,
        color: '#1976D2',
        lineHeight: 18,
    },
});
