import React, { useState, useEffect } from 'react';
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
} from 'react-native';
import ApiService from '../services/api';

export default function DevolucaoMultiplaFerramentasScreen({ navigation, route }) {
    const user = route.params?.user;
    
    // Estados
    const [ferramentasAtivas, setFerramentasAtivas] = useState([]);
    const [ferramentasSelecionadas, setFerramentasSelecionadas] = useState({});
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [matriculaFuncionario, setMatriculaFuncionario] = useState('');

    const loadFerramentasAtivas = async () => {
        setLoading(true);
        try {
            // Chamar API para listar ferramentas ativas do funcionário
            const result = await ApiService.getFerramentasAtivas(matriculaFuncionario.trim());
            
            if (result.success) {
                setFerramentasAtivas(result.data || []);
            } else {
                Alert.alert('Erro', result.message || 'Falha ao carregar ferramentas');
                setFerramentasAtivas([]);
            }
        } catch (error) {
            console.error('[DevolucaoMultipla] Erro:', error);
            Alert.alert('Erro', 'Falha ao carregar ferramentas ativas');
            setFerramentasAtivas([]);
        } finally {
            setLoading(false);
        }
    };

    const handleBuscarFuncionario = () => {
        if (!matriculaFuncionario.trim()) {
            Alert.alert('Atenção', 'Digite a matrícula do funcionário');
            return;
        }
        loadFerramentasAtivas();
    };

    // Filtrar ferramentas por busca
    const ferramentasFiltradas = ferramentasAtivas.filter(item => {
        if (!searchQuery) return true;
        const query = searchQuery.toLowerCase();
        return (
            item.descricao?.toLowerCase().includes(query) ||
            item.codigo_barras?.toLowerCase().includes(query)
        );
    });

    // Toggle seleção de ferramenta
    const toggleSelecao = (codigo) => {
        setFerramentasSelecionadas(prev => ({
            ...prev,
            [codigo]: !prev[codigo]
        }));
    };

    // Contar itens selecionados
    const totalSelecionados = Object.values(ferramentasSelecionadas).filter(Boolean).length;

    // Validar e confirmar devolução
    const handleConfirmarDevolucao = async () => {
        if (totalSelecionados === 0) {
            Alert.alert('Atenção', 'Selecione pelo menos uma ferramenta para devolver');
            return;
        }

        Alert.alert(
            'Confirmar Devolução',
            `Devolver ${totalSelecionados} ferramenta(s) de ${matriculaFuncionario}?`,
            [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'Confirmar', onPress: () => executarDevolucao() }
            ]
        );
    };

    const executarDevolucao = async () => {
        setSubmitting(true);

        try {
            // Montar array de itens selecionados
            const itensSelecionados = ferramentasAtivas
                .filter(item => ferramentasSelecionadas[item.codigo_barras])
                .map(item => ({
                    codigo: item.codigo_barras,
                    quantidade: 1, // Ferramentas sempre quantidade 1
                }));

            // Chamar API de devolução múltipla
            const result = await ApiService.registrarDevolucaoMultiplaFerramentas({
                itens: itensSelecionados,
                matricula: matriculaFuncionario.trim(),
            });

            if (result.success) {
                Alert.alert(
                    'Sucesso',
                    `✅ ${totalSelecionados} ferramenta(s) devolvida(s) com sucesso`,
                    [
                        {
                            text: 'OK',
                            onPress: () => navigation.goBack()
                        }
                    ]
                );
            } else {
                Alert.alert('Erro', result.message || 'Falha ao registrar devolução');
            }
        } catch (error) {
            console.error('[DevolucaoMultipla] Erro:', error);
            Alert.alert('Erro', 'Falha ao processar devolução múltipla');
        } finally {
            setSubmitting(false);
        }
    };

    // Renderizar item da lista
    const renderFerramentaItem = ({ item }) => {
        const isSelected = ferramentasSelecionadas[item.codigo_barras] || false;

        return (
            <TouchableOpacity
                style={[styles.ferramentaCard, isSelected && styles.ferramentaCardSelected]}
                onPress={() => toggleSelecao(item.codigo_barras)}
                activeOpacity={0.7}
            >
                <View style={styles.checkbox}>
                    {isSelected && <Text style={styles.checkmark}>✓</Text>}
                </View>
                <View style={styles.ferramentaInfo}>
                    <Text style={styles.ferramentaDescricao}>{item.descricao}</Text>
                    <Text style={styles.ferramentaCodigo}>Código: {item.codigo_barras}</Text>
                    {item.data_retirada && (
                        <Text style={styles.ferramentaData}>
                            Retirada: {new Date(item.data_retirada).toLocaleDateString('pt-BR')}
                        </Text>
                    )}
                    {item.dias_em_uso > 0 && (
                        <Text style={[
                            styles.ferramentaDias,
                            item.dias_em_uso > 30 && styles.ferramentaDiasAlerta
                        ]}>
                            {item.dias_em_uso} dias em uso
                        </Text>
                    )}
                </View>
            </TouchableOpacity>
        );
    };

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
            <ScrollView style={styles.scrollView} keyboardShouldPersistTaps="handled">
                {/* Header */}
                <View style={styles.header}>
                    <Text style={styles.headerTitle}>🔄 Devolução Múltipla de Ferramentas</Text>
                    <Text style={styles.headerSubtitle}>
                        Devolver múltiplas ferramentas de um funcionário
                    </Text>
                </View>

                {/* Buscar Funcionário */}
                <View style={styles.buscaContainer}>
                    <Text style={styles.inputLabel}>Matrícula do Funcionário *</Text>
                    <View style={styles.buscaRow}>
                        <TextInput
                            style={styles.buscaInput}
                            placeholder="Digite a matrícula"
                            value={matriculaFuncionario}
                            onChangeText={setMatriculaFuncionario}
                            keyboardType="default"
                            autoCapitalize="characters"
                        />
                        <TouchableOpacity
                            style={styles.btnBuscar}
                            onPress={handleBuscarFuncionario}
                        >
                            <Text style={styles.btnBuscarText}>🔍 Buscar</Text>
                        </TouchableOpacity>
                    </View>
                </View>

                {loading && (
                    <View style={styles.loadingContainer}>
                        <ActivityIndicator size="large" color="#22c55e" />
                        <Text style={styles.loadingText}>Carregando ferramentas...</Text>
                    </View>
                )}

                {!loading && ferramentasAtivas.length > 0 && (
                    <>
                        {/* Barra de Busca */}
                        <View style={styles.searchContainer}>
                            <TextInput
                                style={styles.searchInput}
                                placeholder="🔍 Filtrar ferramentas..."
                                value={searchQuery}
                                onChangeText={setSearchQuery}
                                placeholderTextColor="#999"
                            />
                        </View>

                        {/* Badge de Selecionados */}
                        {totalSelecionados > 0 && (
                            <View style={styles.selectionBadge}>
                                <Text style={styles.selectionBadgeText}>
                                    ✓ {totalSelecionados} ferramenta(s) selecionada(s)
                                </Text>
                            </View>
                        )}

                        {/* Lista de Ferramentas */}
                        <View style={styles.listaContainer}>
                            <FlatList
                                data={ferramentasFiltradas}
                                renderItem={renderFerramentaItem}
                                keyExtractor={(item) => item.codigo_barras}
                                scrollEnabled={false}
                                ListEmptyComponent={
                                    <View style={styles.emptyContainer}>
                                        <Text style={styles.emptyIcon}>🔧</Text>
                                        <Text style={styles.emptyText}>Nenhuma ferramenta ativa encontrada</Text>
                                    </View>
                                }
                            />
                        </View>

                        {/* Formulário de Devolução */}
                        {totalSelecionados > 0 && (
                            <View style={styles.formContainer}>
                                <Text style={styles.formTitle}>Informações da Devolução</Text>

                                {/* Botão Confirmar */}
                                <TouchableOpacity
                                    style={[styles.btnConfirmar, submitting && styles.btnDisabled]}
                                    onPress={handleConfirmarDevolucao}
                                    disabled={submitting}
                                >
                                    {submitting ? (
                                        <ActivityIndicator color="#fff" />
                                    ) : (
                                        <Text style={styles.btnConfirmarText}>
                                            ✓ Confirmar Devolução ({totalSelecionados})
                                        </Text>
                                    )}
                                </TouchableOpacity>
                            </View>
                        )}
                    </>
                )}

                {!loading && matriculaFuncionario && ferramentasAtivas.length === 0 && (
                    <View style={styles.emptyContainer}>
                        <Text style={styles.emptyIcon}>🔧</Text>
                        <Text style={styles.emptyText}>Funcionário sem ferramentas ativas</Text>
                    </View>
                )}
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f5f5f5',
    },
    scrollView: {
        flex: 1,
    },
    header: {
        backgroundColor: '#22c55e',
        paddingTop: Platform.OS === 'ios' ? 50 : 20,
        paddingBottom: 20,
        paddingHorizontal: 16,
    },
    headerTitle: {
        fontSize: 22,
        fontWeight: 'bold',
        color: '#fff',
        marginBottom: 6,
    },
    headerSubtitle: {
        fontSize: 14,
        color: 'rgba(255,255,255,0.9)',
    },
    buscaContainer: {
        paddingHorizontal: 16,
        paddingVertical: 16,
        backgroundColor: '#fff',
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
    },
    buscaRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    buscaInput: {
        flex: 1,
        backgroundColor: '#f5f5f5',
        borderRadius: 8,
        paddingVertical: 12,
        paddingHorizontal: 14,
        fontSize: 16,
        borderWidth: 1,
        borderColor: '#e0e0e0',
        marginRight: 8,
    },
    btnBuscar: {
        backgroundColor: '#22c55e',
        borderRadius: 8,
        paddingVertical: 12,
        paddingHorizontal: 16,
    },
    btnBuscarText: {
        color: '#000',
        fontSize: 14,
        fontWeight: 'bold',
    },
    loadingContainer: {
        alignItems: 'center',
        paddingVertical: 40,
    },
    loadingText: {
        marginTop: 10,
        color: '#16a34a',
        fontWeight: 'bold',
    },
    searchContainer: {
        paddingHorizontal: 16,
        paddingVertical: 12,
        backgroundColor: '#fff',
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
    },
    searchInput: {
        backgroundColor: '#f5f5f5',
        borderRadius: 8,
        paddingVertical: 10,
        paddingHorizontal: 14,
        fontSize: 16,
    },
    selectionBadge: {
        backgroundColor: '#22c55e',
        marginHorizontal: 16,
        marginTop: 12,
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 8,
        alignItems: 'center',
    },
    selectionBadgeText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: 'bold',
    },
    listaContainer: {
        paddingHorizontal: 16,
        paddingTop: 12,
    },
    ferramentaCard: {
        backgroundColor: '#fff',
        borderRadius: 8,
        padding: 14,
        marginBottom: 10,
        flexDirection: 'row',
        alignItems: 'center',
        borderWidth: 2,
        borderColor: '#e0e0e0',
    },
    ferramentaCardSelected: {
        borderColor: '#22c55e',
        backgroundColor: '#f0fdf4',
    },
    checkbox: {
        width: 28,
        height: 28,
        borderWidth: 2,
        borderColor: '#22c55e',
        borderRadius: 6,
        marginRight: 12,
        justifyContent: 'center',
        alignItems: 'center',
    },
    checkmark: {
        color: '#22c55e',
        fontSize: 20,
        fontWeight: 'bold',
    },
    ferramentaInfo: {
        flex: 1,
    },
    ferramentaDescricao: {
        fontSize: 16,
        fontWeight: '600',
        color: '#222',
        marginBottom: 4,
    },
    ferramentaCodigo: {
        fontSize: 13,
        color: '#666',
        marginBottom: 2,
    },
    ferramentaData: {
        fontSize: 12,
        color: '#999',
        marginTop: 2,
    },
    ferramentaDias: {
        fontSize: 12,
        color: '#22c55e',
        fontWeight: '600',
        marginTop: 2,
    },
    ferramentaDiasAlerta: {
        color: '#dc2626',
    },
    emptyContainer: {
        alignItems: 'center',
        paddingVertical: 40,
    },
    emptyIcon: {
        fontSize: 64,
        marginBottom: 10,
    },
    emptyText: {
        fontSize: 16,
        color: '#666',
    },
    formContainer: {
        backgroundColor: '#fff',
        marginHorizontal: 16,
        marginTop: 16,
        marginBottom: 20,
        borderRadius: 8,
        padding: 16,
    },
    formTitle: {
        fontSize: 18,
        fontWeight: 'bold',
        color: '#222',
        marginBottom: 16,
    },
    inputGroup: {
        marginBottom: 16,
    },
    inputLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: '#444',
        marginBottom: 6,
    },
    input: {
        backgroundColor: '#f5f5f5',
        borderRadius: 8,
        paddingVertical: 12,
        paddingHorizontal: 14,
        fontSize: 16,
        borderWidth: 1,
        borderColor: '#e0e0e0',
    },
    textArea: {
        height: 80,
        textAlignVertical: 'top',
    },
    btnConfirmar: {
        backgroundColor: '#22c55e',
        borderRadius: 8,
        paddingVertical: 14,
        alignItems: 'center',
        marginTop: 8,
    },
    btnDisabled: {
        opacity: 0.6,
    },
    btnConfirmarText: {
        color: '#000',
        fontSize: 16,
        fontWeight: 'bold',
    },
});
