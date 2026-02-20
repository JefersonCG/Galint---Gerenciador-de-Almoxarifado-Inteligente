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
import { searchItems as searchOfflineItems } from '../services/offlineDb';

export default function DevolucaoMultiplaMateriaisScreen({ navigation, route }) {
    const user = route.params?.user;
    
    // Estados
    const [materiais, setMateriais] = useState([]);
    const [materiaisSelecionados, setMateriaisSelecionados] = useState({});
    const [quantidades, setQuantidades] = useState({});
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [matriculaFuncionario, setMatriculaFuncionario] = useState('');

    // Carregar materiais disponíveis
    useEffect(() => {
        loadMateriais();
    }, []);

    const loadMateriais = async () => {
        setLoading(true);
        try {
            const result = await ApiService.getEstoque('');
            
            if (result.success) {
                const items = result.data || [];
                // Filtrar apenas materiais (NÃO ferramentas)
                const materiaisDisponiveis = items.filter(item => {
                    const categoria = String(item?.categoria || '').toLowerCase();
                    return !categoria.includes('ferrament');
                });
                setMateriais(materiaisDisponiveis);
            } else if (result.offline) {
                const items = await searchOfflineItems('');
                const materiaisDisponiveis = items.filter(item => {
                    const categoria = String(item?.categoria || '').toLowerCase();
                    return !categoria.includes('ferrament');
                });
                setMateriais(materiaisDisponiveis);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao carregar materiais');
        } finally {
            setLoading(false);
        }
    };

    // Filtrar materiais por busca
    const materiaisFiltrados = materiais.filter(item => {
        if (!searchQuery) return true;
        const query = searchQuery.toLowerCase();
        return (
            item.descricao?.toLowerCase().includes(query) ||
            item.codigo_barras?.toLowerCase().includes(query) ||
            item.categoria?.toLowerCase().includes(query)
        );
    });

    // Toggle seleção de material
    const toggleSelecao = (codigo) => {
        const isSelected = materiaisSelecionados[codigo];
        setMateriaisSelecionados(prev => ({
            ...prev,
            [codigo]: !isSelected
        }));

        // Se deselecionou, limpar quantidade
        if (isSelected) {
            setQuantidades(prev => {
                const newQtd = { ...prev };
                delete newQtd[codigo];
                return newQtd;
            });
        } else {
            // Se selecionou, inicializar com 1
            setQuantidades(prev => ({
                ...prev,
                [codigo]: '1'
            }));
        }
    };

    // Atualizar quantidade de um material
    const handleQuantidadeChange = (codigo, valor) => {
        const valorLimpo = valor.replace(/[^0-9]/g, '');
        setQuantidades(prev => ({
            ...prev,
            [codigo]: valorLimpo
        }));
    };

    // Contar itens selecionados
    const totalSelecionados = Object.values(materiaisSelecionados).filter(Boolean).length;

    // Validar e confirmar devolução
    const handleConfirmarDevolucao = async () => {
        if (totalSelecionados === 0) {
            Alert.alert('Atenção', 'Selecione pelo menos um material para devolver');
            return;
        }

        if (!matriculaFuncionario.trim()) {
            Alert.alert('Atenção', 'Informe a matrícula do funcionário');
            return;
        }

        // Validar quantidades
        const materiaisSelecionadosArr = materiais.filter(item => 
            materiaisSelecionados[item.codigo_barras]
        );

        for (const item of materiaisSelecionadosArr) {
            const qtd = parseInt(quantidades[item.codigo_barras] || '0');
            if (qtd <= 0) {
                Alert.alert('Atenção', `Quantidade inválida para ${item.descricao}`);
                return;
            }
        }

        Alert.alert(
            'Confirmar Devolução',
            `Devolver ${totalSelecionados} material(is) de ${matriculaFuncionario}?`,
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
            const itensSelecionados = materiais
                .filter(item => materiaisSelecionados[item.codigo_barras])
                .map(item => ({
                    codigo: item.codigo_barras,
                    quantidade: parseInt(quantidades[item.codigo_barras] || '1'),
                }));

            // Chamar API de devolução múltipla de materiais
            const result = await ApiService.registrarDevolucaoMultiplaMateriais({
                itens: itensSelecionados,
                matricula: matriculaFuncionario.trim(),
            });

            if (result.success) {
                Alert.alert(
                    'Sucesso',
                    `✅ ${totalSelecionados} material(is) devolvido(s) com sucesso`,
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
            console.error('[DevolucaoMultiplaMateriais] Erro:', error);
            Alert.alert('Erro', 'Falha ao processar devolução múltipla');
        } finally {
            setSubmitting(false);
        }
    };

    // Renderizar item da lista
    const renderMaterialItem = ({ item }) => {
        const isSelected = materiaisSelecionados[item.codigo_barras] || false;
        const quantidade = quantidades[item.codigo_barras] || '1';

        return (
            <View style={[styles.materialCard, isSelected && styles.materialCardSelected]}>
                <TouchableOpacity
                    style={styles.materialHeader}
                    onPress={() => toggleSelecao(item.codigo_barras)}
                    activeOpacity={0.7}
                >
                    <View style={styles.checkbox}>
                        {isSelected && <Text style={styles.checkmark}>✓</Text>}
                    </View>
                    <View style={styles.materialInfo}>
                        <Text style={styles.materialDescricao}>{item.descricao}</Text>
                        <Text style={styles.materialCategoria}>{item.categoria}</Text>
                        <Text style={styles.materialCodigo}>Código: {item.codigo_barras}</Text>
                    </View>
                </TouchableOpacity>

                {isSelected && (
                    <View style={styles.quantidadeContainer}>
                        <Text style={styles.quantidadeLabel}>Quantidade a devolver:</Text>
                        <TextInput
                            style={styles.quantidadeInput}
                            value={quantidade}
                            onChangeText={(valor) => handleQuantidadeChange(item.codigo_barras, valor)}
                            keyboardType="number-pad"
                            placeholder="0"
                        />
                    </View>
                )}
            </View>
        );
    };

    if (loading) {
        return (
            <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color="#22c55e" />
                <Text style={styles.loadingText}>Carregando materiais...</Text>
            </View>
        );
    }

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
            <ScrollView style={styles.scrollView} keyboardShouldPersistTaps="handled">
                {/* Header */}
                <View style={styles.header}>
                    <Text style={styles.headerTitle}>📦 Devolução Múltipla de Materiais</Text>
                    <Text style={styles.headerSubtitle}>
                        Devolver múltiplos materiais ao estoque
                    </Text>
                </View>

                {/* Matrícula do Funcionário */}
                <View style={styles.matriculaContainer}>
                    <Text style={styles.inputLabel}>Matrícula do Funcionário *</Text>
                    <TextInput
                        style={styles.matriculaInput}
                        placeholder="Digite a matrícula"
                        value={matriculaFuncionario}
                        onChangeText={setMatriculaFuncionario}
                        keyboardType="default"
                        autoCapitalize="characters"
                    />
                </View>

                {/* Barra de Busca */}
                <View style={styles.searchContainer}>
                    <TextInput
                        style={styles.searchInput}
                        placeholder="🔍 Buscar material..."
                        value={searchQuery}
                        onChangeText={setSearchQuery}
                        placeholderTextColor="#999"
                    />
                </View>

                {/* Badge de Selecionados */}
                {totalSelecionados > 0 && (
                    <View style={styles.selectionBadge}>
                        <Text style={styles.selectionBadgeText}>
                            ✓ {totalSelecionados} material(is) selecionado(s)
                        </Text>
                    </View>
                )}

                {/* Lista de Materiais */}
                <View style={styles.listaContainer}>
                    <FlatList
                        data={materiaisFiltrados}
                        renderItem={renderMaterialItem}
                        keyExtractor={(item) => item.codigo_barras}
                        scrollEnabled={false}
                        ListEmptyComponent={
                            <View style={styles.emptyContainer}>
                                <Text style={styles.emptyIcon}>📦</Text>
                                <Text style={styles.emptyText}>Nenhum material encontrado</Text>
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
            </ScrollView>
        </KeyboardAvoidingView>
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
        color: '#16a34a',
        fontWeight: 'bold',
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
    matriculaContainer: {
        paddingHorizontal: 16,
        paddingVertical: 16,
        backgroundColor: '#fff',
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
    },
    matriculaInput: {
        backgroundColor: '#f5f5f5',
        borderRadius: 8,
        paddingVertical: 12,
        paddingHorizontal: 14,
        fontSize: 16,
        borderWidth: 1,
        borderColor: '#e0e0e0',
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
    materialCard: {
        backgroundColor: '#fff',
        borderRadius: 8,
        padding: 14,
        marginBottom: 10,
        borderWidth: 2,
        borderColor: '#e0e0e0',
    },
    materialCardSelected: {
        borderColor: '#22c55e',
        backgroundColor: '#f0fdf4',
    },
    materialHeader: {
        flexDirection: 'row',
        alignItems: 'center',
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
    materialInfo: {
        flex: 1,
    },
    materialDescricao: {
        fontSize: 16,
        fontWeight: '600',
        color: '#222',
        marginBottom: 4,
    },
    materialCategoria: {
        fontSize: 13,
        color: '#22c55e',
        fontWeight: '600',
        marginBottom: 2,
    },
    materialCodigo: {
        fontSize: 13,
        color: '#666',
    },
    quantidadeContainer: {
        marginTop: 12,
        paddingTop: 12,
        borderTopWidth: 1,
        borderTopColor: '#e0e0e0',
        flexDirection: 'row',
        alignItems: 'center',
    },
    quantidadeLabel: {
        fontSize: 14,
        color: '#444',
        fontWeight: '600',
        flex: 1,
    },
    quantidadeInput: {
        backgroundColor: '#fff',
        borderWidth: 1,
        borderColor: '#22c55e',
        borderRadius: 6,
        paddingVertical: 8,
        paddingHorizontal: 12,
        fontSize: 16,
        fontWeight: 'bold',
        textAlign: 'center',
        minWidth: 80,
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
