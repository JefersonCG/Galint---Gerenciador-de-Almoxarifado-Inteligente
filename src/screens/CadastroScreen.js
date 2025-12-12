import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    ScrollView,
    Alert,
    ActivityIndicator,
    KeyboardAvoidingView,
    Platform,
} from 'react-native';
import ApiService from '../services/api';

export default function CadastroScreen({ navigation, route }) {
    const [loading, setLoading] = useState(false);
    const [formData, setFormData] = useState({
        descricao: '',
        codigo_barras: route.params?.barcode || '',
        categoria: '',
        localizacao: '',
        marca: '',
        quantidade: '',
        unidade: 'UN',
    });

    const categorias = [
        'Ferramentas',
        'Material Elétrico',
        'Material Hidráulico',
        'EPI',
        'Limpeza',
        'Escritório',
        'Informática',
        'Outros',
    ];

    const unidades = ['UN', 'CX', 'PC', 'KG', 'L', 'M', 'M²', 'M³'];

    const handleSubmit = async () => {
        if (!formData.descricao) {
            Alert.alert('Erro', 'Descrição é obrigatória');
            return;
        }

        if (!formData.quantidade || parseFloat(formData.quantidade) < 0) {
            Alert.alert('Erro', 'Quantidade inválida');
            return;
        }

        setLoading(true);

        try {
            const dataToSend = {
                ...formData,
                quantidade: parseFloat(formData.quantidade) || 0,
            };

            const result = await ApiService.cadastrarItem(dataToSend);

            if (result.success) {
                Alert.alert(
                    'Sucesso!',
                    'Item cadastrado com sucesso',
                    [
                        {
                            text: 'Cadastrar Outro',
                            onPress: () => {
                                setFormData({
                                    descricao: '',
                                    codigo_barras: '',
                                    categoria: formData.categoria,
                                    localizacao: formData.localizacao,
                                    marca: '',
                                    quantidade: '',
                                    unidade: formData.unidade,
                                });
                            },
                        },
                        {
                            text: 'Voltar',
                            onPress: () => navigation.goBack(),
                        },
                    ]
                );
            } else {
                Alert.alert('Erro', result.message);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao cadastrar item');
        } finally {
            setLoading(false);
        }
    };

    const handleScanBarcode = () => {
        navigation.navigate('Scanner');
    };

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <ScrollView
                style={styles.scrollView}
                contentContainerStyle={styles.scrollContent}
                keyboardShouldPersistTaps="handled"
            >
                <View style={styles.form}>
                    {/* Descrição */}
                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Descrição *</Text>
                        <TextInput
                            style={styles.input}
                            value={formData.descricao}
                            onChangeText={(text) =>
                                setFormData({ ...formData, descricao: text })
                            }
                            placeholder="Nome do item"
                            autoCapitalize="words"
                        />
                    </View>

                    {/* Código de Barras */}
                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Código de Barras</Text>
                        <View style={styles.barcodeContainer}>
                            <TextInput
                                style={[styles.input, styles.barcodeInput]}
                                value={formData.codigo_barras}
                                onChangeText={(text) =>
                                    setFormData({ ...formData, codigo_barras: text })
                                }
                                placeholder="Digite ou escaneie"
                                keyboardType="numeric"
                            />
                            <TouchableOpacity
                                style={styles.scanButton}
                                onPress={handleScanBarcode}
                            >
                                <Text style={styles.scanButtonText}>📷</Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                    {/* Categoria */}
                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Categoria</Text>
                        <View style={styles.chipContainer}>
                            {categorias.map((cat) => (
                                <TouchableOpacity
                                    key={cat}
                                    style={[
                                        styles.chip,
                                        formData.categoria === cat && styles.chipSelected,
                                    ]}
                                    onPress={() => setFormData({ ...formData, categoria: cat })}
                                >
                                    <Text
                                        style={[
                                            styles.chipText,
                                            formData.categoria === cat && styles.chipTextSelected,
                                        ]}
                                    >
                                        {cat}
                                    </Text>
                                </TouchableOpacity>
                            ))}
                        </View>
                    </View>

                    {/* Localização */}
                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Localização</Text>
                        <TextInput
                            style={styles.input}
                            value={formData.localizacao}
                            onChangeText={(text) =>
                                setFormData({ ...formData, localizacao: text })
                            }
                            placeholder="Ex: Prateleira A1, Sala 2"
                            autoCapitalize="words"
                        />
                    </View>

                    {/* Marca */}
                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Marca/Fabricante</Text>
                        <TextInput
                            style={styles.input}
                            value={formData.marca}
                            onChangeText={(text) =>
                                setFormData({ ...formData, marca: text })
                            }
                            placeholder="Nome da marca"
                            autoCapitalize="words"
                        />
                    </View>

                    {/* Quantidade e Unidade */}
                    <View style={styles.row}>
                        <View style={[styles.inputGroup, styles.flex2]}>
                            <Text style={styles.label}>Quantidade *</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.quantidade}
                                onChangeText={(text) =>
                                    setFormData({ ...formData, quantidade: text })
                                }
                                placeholder="0"
                                keyboardType="numeric"
                            />
                        </View>

                        <View style={[styles.inputGroup, styles.flex1]}>
                            <Text style={styles.label}>Unidade</Text>
                            <View style={styles.unidadeContainer}>
                                {unidades.slice(0, 4).map((un) => (
                                    <TouchableOpacity
                                        key={un}
                                        style={[
                                            styles.unidadeChip,
                                            formData.unidade === un && styles.unidadeChipSelected,
                                        ]}
                                        onPress={() => setFormData({ ...formData, unidade: un })}
                                    >
                                        <Text
                                            style={[
                                                styles.unidadeText,
                                                formData.unidade === un && styles.unidadeTextSelected,
                                            ]}
                                        >
                                            {un}
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </View>
                    </View>

                    {/* Botões */}
                    <View style={styles.buttonContainer}>
                        <TouchableOpacity
                            style={styles.cancelButton}
                            onPress={() => navigation.goBack()}
                        >
                            <Text style={styles.cancelButtonText}>Cancelar</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                            style={[styles.submitButton, loading && styles.buttonDisabled]}
                            onPress={handleSubmit}
                            disabled={loading}
                        >
                            {loading ? (
                                <ActivityIndicator color="#fff" />
                            ) : (
                                <Text style={styles.submitButtonText}>Cadastrar</Text>
                            )}
                        </TouchableOpacity>
                    </View>
                </View>
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
    scrollContent: {
        padding: 20,
    },
    form: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    inputGroup: {
        marginBottom: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#333',
        marginBottom: 8,
    },
    input: {
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
        backgroundColor: '#f9f9f9',
    },
    barcodeContainer: {
        flexDirection: 'row',
        gap: 10,
    },
    barcodeInput: {
        flex: 1,
    },
    scanButton: {
        backgroundColor: '#6610f2',
        borderRadius: 8,
        paddingHorizontal: 20,
        justifyContent: 'center',
        alignItems: 'center',
    },
    scanButtonText: {
        fontSize: 24,
    },
    chipContainer: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    chip: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: '#ddd',
        backgroundColor: '#f9f9f9',
    },
    chipSelected: {
        backgroundColor: '#0d6efd',
        borderColor: '#0d6efd',
    },
    chipText: {
        fontSize: 14,
        color: '#666',
    },
    chipTextSelected: {
        color: '#fff',
        fontWeight: '600',
    },
    row: {
        flexDirection: 'row',
        gap: 15,
    },
    flex1: {
        flex: 1,
    },
    flex2: {
        flex: 2,
    },
    unidadeContainer: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 5,
    },
    unidadeChip: {
        flex: 1,
        minWidth: 40,
        paddingVertical: 10,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: '#ddd',
        backgroundColor: '#f9f9f9',
        alignItems: 'center',
    },
    unidadeChipSelected: {
        backgroundColor: '#0d6efd',
        borderColor: '#0d6efd',
    },
    unidadeText: {
        fontSize: 12,
        color: '#666',
        fontWeight: '600',
    },
    unidadeTextSelected: {
        color: '#fff',
    },
    buttonContainer: {
        flexDirection: 'row',
        gap: 10,
        marginTop: 10,
    },
    cancelButton: {
        flex: 1,
        padding: 15,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#dc3545',
        alignItems: 'center',
    },
    cancelButtonText: {
        color: '#dc3545',
        fontSize: 16,
        fontWeight: '600',
    },
    submitButton: {
        flex: 1,
        padding: 15,
        borderRadius: 8,
        backgroundColor: '#198754',
        alignItems: 'center',
    },
    submitButtonText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '600',
    },
    buttonDisabled: {
        opacity: 0.6,
    },
});
