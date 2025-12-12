import React, { useState, useEffect } from 'react';
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
} from 'react-native';
import ApiService from '../services/api';

export default function EstoqueScreen({ navigation, route }) {
    const [items, setItems] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const user = route.params?.user;

    useEffect(() => {
        loadEstoque();
    }, []);

    const loadEstoque = async (search = '') => {
        try {
            const result = await ApiService.getEstoque(search);
            if (result.success) {
                setItems(result.data);
            } else {
                Alert.alert('Erro', result.message);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao carregar estoque');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    const handleSearch = () => {
        setLoading(true);
        loadEstoque(searchQuery);
    };

    const handleRefresh = () => {
        setRefreshing(true);
        loadEstoque(searchQuery);
    };

    const handleLogout = () => {
        Alert.alert(
            'Sair',
            'Deseja realmente sair?',
            [
                { text: 'Cancelar', style: 'cancel' },
                {
                    text: 'Sair',
                    style: 'destructive',
                    onPress: async () => {
                        await ApiService.logout();
                        navigation.replace('Login');
                    },
                },
            ]
        );
    };

    const renderItem = ({ item }) => (
        <View style={styles.itemCard}>
            <View style={styles.itemHeader}>
                <Text style={styles.itemName}>{item.descricao || item.nome}</Text>
                <View style={[
                    styles.badge,
                    item.quantidade > 10 ? styles.badgeSuccess :
                        item.quantidade > 0 ? styles.badgeWarning : styles.badgeDanger
                ]}>
                    <Text style={styles.badgeText}>{item.quantidade || 0}</Text>
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
        </View>
    );

    if (loading && !refreshing) {
        return (
            <View style={styles.centerContainer}>
                <ActivityIndicator size="large" color="#0d6efd" />
                <Text style={styles.loadingText}>Carregando estoque...</Text>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            {/* Header com usuário */}
            <View style={styles.userHeader}>
                <View>
                    <Text style={styles.welcomeText}>Olá, {user?.nome || user?.username || 'Usuário'}</Text>
                    <Text style={styles.roleText}>{user?.setor || 'Almoxarifado'}</Text>
                </View>
                <TouchableOpacity onPress={handleLogout} style={styles.logoutButton}>
                    <Text style={styles.logoutText}>Sair</Text>
                </TouchableOpacity>
            </View>

            {/* Barra de Pesquisa */}
            <View style={styles.searchContainer}>
                <TextInput
                    style={styles.searchInput}
                    placeholder="Pesquisar itens..."
                    value={searchQuery}
                    onChangeText={setSearchQuery}
                    onSubmitEditing={handleSearch}
                    returnKeyType="search"
                />
                <TouchableOpacity style={styles.searchButton} onPress={handleSearch}>
                    <Text style={styles.searchButtonText}>🔍</Text>
                </TouchableOpacity>
            </View>

            {/* Botões de Ação */}
            <View style={styles.actionButtons}>
                <TouchableOpacity
                    style={[styles.actionButton, styles.scanButton]}
                    onPress={() => navigation.navigate('Scanner')}
                >
                    <Text style={styles.actionButtonIcon}>📷</Text>
                    <Text style={styles.actionButtonText}>Escanear</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.actionButton, styles.addButton]}
                    onPress={() => navigation.navigate('Cadastro')}
                >
                    <Text style={styles.actionButtonIcon}>➕</Text>
                    <Text style={styles.actionButtonText}>Cadastrar</Text>
                </TouchableOpacity>
            </View>

            {/* Lista de Itens */}
            <FlatList
                data={items}
                renderItem={renderItem}
                keyExtractor={(item) => item.id?.toString() || Math.random().toString()}
                contentContainerStyle={styles.listContainer}
                refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
                }
                ListEmptyComponent={
                    <View style={styles.emptyContainer}>
                        <Text style={styles.emptyIcon}>📦</Text>
                        <Text style={styles.emptyText}>Nenhum item encontrado</Text>
                        <Text style={styles.emptySubtext}>
                            {searchQuery ? 'Tente outra pesquisa' : 'Comece cadastrando itens'}
                        </Text>
                    </View>
                }
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
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
    userHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: '#fff',
        padding: 15,
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
    },
    welcomeText: {
        fontSize: 18,
        fontWeight: '600',
        color: '#333',
    },
    roleText: {
        fontSize: 14,
        color: '#666',
        marginTop: 2,
    },
    logoutButton: {
        paddingHorizontal: 15,
        paddingVertical: 8,
        backgroundColor: '#dc3545',
        borderRadius: 6,
    },
    logoutText: {
        color: '#fff',
        fontWeight: '600',
    },
    searchContainer: {
        flexDirection: 'row',
        padding: 15,
        backgroundColor: '#fff',
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
    },
    searchInput: {
        flex: 1,
        backgroundColor: '#f5f5f5',
        borderRadius: 8,
        paddingHorizontal: 15,
        paddingVertical: 10,
        fontSize: 16,
        marginRight: 10,
    },
    searchButton: {
        backgroundColor: '#0d6efd',
        borderRadius: 8,
        paddingHorizontal: 20,
        justifyContent: 'center',
        alignItems: 'center',
    },
    searchButtonText: {
        fontSize: 20,
    },
    actionButtons: {
        flexDirection: 'row',
        padding: 15,
        gap: 10,
    },
    actionButton: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 15,
        borderRadius: 10,
        gap: 8,
    },
    scanButton: {
        backgroundColor: '#6610f2',
    },
    addButton: {
        backgroundColor: '#198754',
    },
    actionButtonIcon: {
        fontSize: 24,
    },
    actionButtonText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '600',
    },
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
    badgeSuccess: {
        backgroundColor: '#198754',
    },
    badgeWarning: {
        backgroundColor: '#ffc107',
    },
    badgeDanger: {
        backgroundColor: '#dc3545',
    },
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
