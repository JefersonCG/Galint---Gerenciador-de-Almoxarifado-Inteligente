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
import AsyncStorage from '@react-native-async-storage/async-storage';
import ApiService from '../services/api';
import { searchItems as searchOfflineItems } from '../services/offlineDb';

export default function RetiradaMultiplaFerramentasScreen({ navigation, route }) {
    const user = route.params?.user;
    
    // Estados
    const [ferramentas, setFerramentas] = useState([]);
    const [ferramentasSelecionadas, setFerramentasSelecionadas] = useState({});
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [matriculaRetirante, setMatriculaRetirante] = useState('');
    const [localServico, setLocalServico] = useState('');

    // Carregar ferramentas disponíveis
    useEffect(() => {
        loadFerramentas();
    }, []);

    const loadFerramentas = async () => {
        setLoading(true);
        try {
            // Buscar itens da categoria FERRAMENTA
            const result = await ApiService.getEstoque('');
            
            if (result.success) {
                const items = result.data || [];
                // Filtrar apenas ferramentas com saldo disponível
                const ferramentasDisponiveis = items.filter(item => {
                    const categoria = String(item?.categoria || '').toLowerCase();
                    const quantidade = Number(item?.quantidade ?? item?.saldo ?? 0);
                    return categoria.includes('ferrament') && quantidade > 0;
                });
                setFerramentas(ferramentasDisponiveis);
            } else if (result.offline) {
                // Modo offline: buscar do SQLite
                const items = await searchOfflineItems('');
                const ferramentasDisponiveis = items.filter(item => {
                    const categoria = String(item?.categoria || '').toLowerCase();
                    const quantidade = Number(item?.quantidade ?? item?.saldo ?? 0);
                    return categoria.includes('ferrament') && quantidade > 0;
                });
                setFerramentas(ferramentasDisponiveis);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao carregar ferramentas');
        } finally {
            setLoading(false);
        }
    };

    // Filtrar ferramentas por busca
    const ferramentasFiltradas = ferramentas.filter(item => {
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

    // Validar e confirmar retirada
    const handleConfirmarRetirada = async () => {
        // Validações
        if (totalSelecionados === 0) {
            Alert.alert('Atenção', 'Selecione pelo menos uma ferramenta');
            return;
        }

        if (!matriculaRetirante.trim()) {
            Alert.alert('Atenção', 'Informe a matrícula do responsável');
            return;
        }

        // Confirmar ação
        Alert.alert(
            'Confirmar Retirada',
            `Retirar ${totalSelecionados} ferramenta(s) para ${matriculaRetirante}?`,
            [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'Confirmar', onPress: () => executarRetirada() }
            ]
        );
    };

    const executarRetirada = async () => {
        setSubmitting(true);

        try {
            // Montar array de itens selecionados
            const itensSelecionados = ferramentas
                .filter(item => ferramentasSelecionadas[item.codigo_barras])
                .map(item => ({
                    codigo: item.codigo_barras,
                    quantidade: 1, // Ferramentas sempre quantidade 1
                    tipo: 'FERRAMENTA'
                }));

            // Chamar API de retirada múltipla
            const result = await ApiService.registrarRetiradaMultipla({
                itens: itensSelecionados,
                matricula: matriculaRetirante.trim(),
                local_servico: localServico.trim() || null,
            });

            if (result.success) {
                Alert.alert(
                    'Sucesso',
                    `✅ ${totalSelecionados} ferramenta(s) retirada(s) com sucesso`,
                    [
                        {
                            text: 'OK',
                            onPress: () => navigation.goBack()
                        }
                    ]
                );
            } else {
                Alert.alert('Erro', result.message || 'Falha ao registrar retirada');
            }
        } catch (error) {
            console.error('[RetiradaMultipla] Erro:', error);
            Alert.alert('Erro', 'Falha ao processar retirada múltipla');
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
                    <Text style={styles.ferramentaSaldo}>Saldo: {Number(item?.quantidade ?? item?.saldo ?? 0)}</Text>
                </View>
            </TouchableOpacity>
        );
    };

    if (loading) {
        return (
            <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color="#22c55e" />
                <Text style={styles.loadingText}>Carregando ferramentas...</Text>
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
                    <Text style={styles.headerTitle}>🔧 Retirada Múltipla de Ferramentas</Text>
                    <Text style={styles.headerSubtitle}>
                        Selecione as ferramentas que deseja retirar
                    </Text>
                </View>

                {/* Barra de Busca */}
                <View style={styles.searchContainer}>
                    <TextInput
                        style={styles.searchInput}
                        placeholder="🔍 Buscar ferramenta..."
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
                                <Text style={styles.emptyText}>Nenhuma ferramenta disponível</Text>
                            </View>
                        }
                    />
                </View>

                {/* Formulário de Retirada */}
                {totalSelecionados > 0 && (
                    <View style={styles.formContainer}>
                        <Text style={styles.formTitle}>Informações da Retirada</Text>

                        {/* Matrícula do Responsável */}
                        <View style={styles.inputGroup}>
                            <Text style={styles.inputLabel}>Matrícula do Responsável *</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Digite a matrícula"
                                value={matriculaRetirante}
                                onChangeText={setMatriculaRetirante}
                                keyboardType="default"
                                autoCapitalize="characters"
                            />
                        </View>

                        {/* Local de Serviço */}
                        <View style={styles.inputGroup}>
                            <Text style={styles.inputLabel}>Local de Serviço</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Ex: Obra XYZ, Setor A"
                                value={localServico}
                                onChangeText={setLocalServico}
                            />
                        </View>

                        {/* Botão Confirmar */}
                        <TouchableOpacity
                            style={[styles.btnConfirmar, submitting && styles.btnDisabled]}
                            onPress={handleConfirmarRetirada}
                            disabled={submitting}
                        >
                            {submitting ? (
                                <ActivityIndicator color="#fff" />
                            ) : (
                                <Text style={styles.btnConfirmarText}>
                                    ✓ Confirmar Retirada ({totalSelecionados})
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
    ferramentaSaldo: {
        fontSize: 13,
        color: '#22c55e',
        fontWeight: '600',
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
