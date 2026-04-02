import React, { useMemo, useState } from 'react';
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
    Image,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import ApiService from '../services/api';

function toUpper(text) {
    return String(text || '').toUpperCase();
}

function sanitizeIntText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9]/g, '');
}

function isAdminOrManager(user) {
    if (!user) return false;
    if (user.is_admin) return true;
    if (user.is_manager) return true;
    const cargo = (user.cargo || '').toString().trim().toLowerCase();
    return cargo.includes('gerente');
}

export default function EditarItemScreen({ navigation, route }) {
    const user = route.params?.user;
    const item = route.params?.item;

    const numericKeyboardType = Platform.OS === 'ios' ? 'number-pad' : 'numeric';

    const canEdit = useMemo(() => isAdminOrManager(user), [user]);

    const [loading, setLoading] = useState(false);
    const [showCategoriaOptions, setShowCategoriaOptions] = useState(false);
    const [showUnidadeOptions, setShowUnidadeOptions] = useState(false);
    const [fotoSelecionada, setFotoSelecionada] = useState(null);
    const [removerFotoExistente, setRemoverFotoExistente] = useState(false);
    
    const unidades = [
        'Unidade',
        'Galão',
        'Lata',
        'Litro',
        'Quilo',
        'Metro',
        'Caixa',
        'Pacote',
        'Fardo',
        'Rolo',
        'Balde',
        'Tambor',
        'Par',
        'Peça',
    ];
    
    const [formData, setFormData] = useState({
        descricao: item?.descricao || '',
        categoria: item?.categoria || 'Material Elétrico',
        localizacao: item?.localizacao || '',
        marca: item?.marca || '',
        nota_fiscal: item?.nota_fiscal || '',
        quantidade: String(item?.quantidade ?? '0'),
        unidade: item?.unidade || 'Unidade',
    });

    const categorias = [
        'Material Elétrico',
        'Material Hidráulico',
        'Material Piscina',
        'Mat. Pintura e Drywall',
        'Materiais de Limpeza',
        'Material Construção',
        'Ferramentas',
        'Material de EP',
        'Material/Uso geral',
    ];

    const originalQuantidade = useMemo(() => {
        const q = Number(item?.quantidade ?? 0);
        return Number.isFinite(q) ? Math.trunc(q) : 0;
    }, [item]);
    const handleSelecionarFoto = async () => {
        try {
            const permissao = await ImagePicker.requestMediaLibraryPermissionsAsync();
            
            if (!permissao.granted) {
                Alert.alert(
                    'Permissão necessária',
                    'É necessário permitir acesso à galeria de fotos para selecionar uma imagem.'
                );
                return;
            }

            const resultado = await ImagePicker.launchImageLibraryAsync({
                mediaTypes: ImagePicker.MediaTypeOptions.Images,
                allowsEditing: true,
                aspect: [4, 3],
                quality: 0.7,
            });

            if (!resultado.canceled && resultado.assets && resultado.assets.length > 0) {
                setFotoSelecionada(resultado.assets[0]);
                setRemoverFotoExistente(false);
            }
        } catch (error) {
            Alert.alert('Erro', 'Não foi possível selecionar a imagem');
        }
    };

    const handleTirarFoto = async () => {
        try {
            const permissao = await ImagePicker.requestCameraPermissionsAsync();
            
            if (!permissao.granted) {
                Alert.alert(
                    'Permissão necessária',
                    'É necessário permitir acesso à câmera para tirar uma foto.'
                );
                return;
            }

            const resultado = await ImagePicker.launchCameraAsync({
                allowsEditing: true,
                aspect: [4, 3],
                quality: 0.7,
            });

            if (!resultado.canceled && resultado.assets && resultado.assets.length > 0) {
                setFotoSelecionada(resultado.assets[0]);
                setRemoverFotoExistente(false);
            }
        } catch (error) {
            Alert.alert('Erro', 'Não foi possível tirar a foto');
        }
    };

    const handleRemoverFoto = () => {
        setFotoSelecionada(null);
        if (item?.foto_path) {
            setRemoverFotoExistente(true);
        }
    };

    const handleEscolherFoto = () => {
        Alert.alert(
            'Adicionar Foto',
            'Escolha uma opção:',
            [
                {
                    text: 'Tirar Foto',
                    onPress: handleTirarFoto,
                },
                {
                    text: 'Selecionar da Galeria',
                    onPress: handleSelecionarFoto,
                },
                {
                    text: 'Cancelar',
                    style: 'cancel',
                },
            ]
        );
    };
    const handleSubmit = async () => {
        if (!canEdit) {
            Alert.alert('Acesso negado', 'Apenas administrador ou gerente pode editar itens.');
            return;
        }

        if (!item?.id) {
            Alert.alert('Erro', 'Item inválido (sem código).');
            return;
        }

        if (!formData.descricao) {
            Alert.alert('Erro', 'Descrição é obrigatória');
            return;
        }

        const quantidadeInt = parseInt(sanitizeIntText(formData.quantidade) || '0', 10);
        if (Number.isNaN(quantidadeInt) || quantidadeInt < 0) {
            Alert.alert('Erro', 'Saldo em estoque inválido');
            return;
        }

        setLoading(true);
        try {
            const payload = {
                descricao: String(formData.descricao || '').trim(),
                categoria: String(formData.categoria || 'Material Eletrico').trim(),
                localizacao: String(formData.localizacao || '').trim(),
                marca: String(formData.marca || '').trim(),
                unidade: String(formData.unidade || 'Unidade').trim() || 'Unidade',
                nota_fiscal: String(formData.nota_fiscal || '').trim(),
            };

            // Adicionar foto se selecionada
            if (fotoSelecionada) {
                payload.foto = fotoSelecionada;
            } else if (removerFotoExistente) {
                payload.remover_foto = true;
            }

            const result = await ApiService.atualizarItem(item.id, payload);

            if (!result.success) {
                Alert.alert('Erro', result.message);
                return;
            }

            if (quantidadeInt !== originalQuantidade) {
                const saldoResult = await ApiService.ajustarSaldo(item.id, quantidadeInt);
                if (!saldoResult.success) {
                    Alert.alert('Erro', saldoResult.message);
                    return;
                }
            }

            Alert.alert('Sucesso', 'Item atualizado com sucesso', [
                {
                    text: 'OK',
                    onPress: () => navigation.goBack(),
                },
            ]);
        } catch (error) {
            Alert.alert('Erro', 'Falha ao atualizar item');
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async () => {
        if (!canEdit) {
            Alert.alert('Acesso negado', 'Apenas administrador ou gerente pode excluir itens.');
            return;
        }

        if (!item?.id) {
            Alert.alert('Erro', 'Item inválido (sem código).');
            return;
        }

        Alert.alert(
            'Excluir item',
            'Tem certeza que deseja excluir este item? Essa ação não pode ser desfeita.',
            [
                { text: 'Cancelar', style: 'cancel' },
                {
                    text: 'Excluir',
                    style: 'destructive',
                    onPress: async () => {
                        setLoading(true);
                        try {
                            const result = await ApiService.excluirItem(item.id);
                            if (result.success) {
                                Alert.alert('Sucesso', 'Item excluído com sucesso', [
                                    { text: 'OK', onPress: () => navigation.goBack() },
                                ]);
                            } else {
                                Alert.alert('Erro', result.message);
                            }
                        } catch (error) {
                            Alert.alert('Erro', 'Falha ao excluir item');
                        } finally {
                            setLoading(false);
                        }
                    },
                },
            ]
        );
    };

    if (!item) {
        return (
            <View style={styles.centerContainer}>
                <Text style={styles.errorText}>Item não encontrado.</Text>
            </View>
        );
    }

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
                    <View style={styles.infoBox}>
                        <Text style={styles.infoTitle}>Código</Text>
                        <Text style={styles.infoValue}>{item.codigo_barras || item.id}</Text>
                    </View>

                    <View style={styles.sectionCard}>
                        <Text style={styles.sectionTitle}>Identificação</Text>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Produto *</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.descricao}
                                onChangeText={(text) => setFormData({ ...formData, descricao: String(text ?? '') })}
                                placeholder=""
                                autoCapitalize="none"
                                returnKeyType="next"
                                onBlur={() =>
                                    setFormData((prev) => ({ ...prev, descricao: toUpper(prev.descricao) }))
                                }
                                onSubmitEditing={() =>
                                    setFormData((prev) => ({ ...prev, descricao: toUpper(prev.descricao) }))
                                }
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Marca / Fabricante</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.marca}
                                onChangeText={(text) => setFormData({ ...formData, marca: String(text ?? '') })}
                                placeholder=""
                                autoCapitalize="none"
                                returnKeyType="next"
                                onBlur={() =>
                                    setFormData((prev) => ({ ...prev, marca: toUpper(prev.marca) }))
                                }
                                onSubmitEditing={() =>
                                    setFormData((prev) => ({ ...prev, marca: toUpper(prev.marca) }))
                                }
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Foto do Item</Text>
                            {fotoSelecionada ? (
                                <View style={styles.fotoContainer}>
                                    <Image
                                        source={{ uri: fotoSelecionada.uri }}
                                        style={styles.fotoPreview}
                                        resizeMode="cover"
                                    />
                                    <View style={styles.fotoActions}>
                                        <TouchableOpacity
                                            style={styles.fotoButton}
                                            onPress={handleEscolherFoto}
                                        >
                                            <Text style={styles.fotoButtonText}>🔄 Trocar Foto</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={[styles.fotoButton, styles.fotoButtonRemove]}
                                            onPress={handleRemoverFoto}
                                        >
                                            <Text style={styles.fotoButtonText}>🗑️ Remover</Text>
                                        </TouchableOpacity>
                                    </View>
                                </View>
                            ) : item?.foto_path && !removerFotoExistente ? (
                                <View style={styles.fotoContainer}>
                                    <Image
                                        source={{ uri: `${ApiService.baseURL}/static/${item.foto_path}` }}
                                        style={styles.fotoPreview}
                                        resizeMode="cover"
                                    />
                                    <View style={styles.fotoActions}>
                                        <TouchableOpacity
                                            style={styles.fotoButton}
                                            onPress={handleEscolherFoto}
                                        >
                                            <Text style={styles.fotoButtonText}>🔄 Trocar Foto</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={[styles.fotoButton, styles.fotoButtonRemove]}
                                            onPress={handleRemoverFoto}
                                        >
                                            <Text style={styles.fotoButtonText}>🗑️ Remover</Text>
                                        </TouchableOpacity>
                                    </View>
                                </View>
                            ) : (
                                <TouchableOpacity
                                    style={styles.fotoUploadButton}
                                    onPress={handleEscolherFoto}
                                >
                                    <Text style={styles.fotoUploadIcon}>📷</Text>
                                    <Text style={styles.fotoUploadText}>Adicionar Foto</Text>
                                    <Text style={styles.fotoUploadHint}>Toque para tirar ou selecionar</Text>
                                </TouchableOpacity>
                            )}
                            <Text style={styles.hintText}>
                                Opcional: Adicione uma foto para facilitar a identificação do item
                            </Text>
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Número da NF</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.nota_fiscal}
                                onChangeText={(text) => setFormData({ ...formData, nota_fiscal: sanitizeIntText(text) })}
                                placeholder=""
                                keyboardType={numericKeyboardType}
                            />
                        </View>
                    </View>

                    <View style={styles.sectionCard}>
                        <Text style={styles.sectionTitle}>Classificação</Text>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Categoria</Text>
                            <TouchableOpacity
                                style={styles.selectInput}
                                activeOpacity={0.8}
                                onPress={() => setShowCategoriaOptions((v) => !v)}
                            >
                                <Text style={styles.selectText}>{formData.categoria || 'Material Eletrico'}</Text>
                                <Text style={styles.selectChevron}>▾</Text>
                            </TouchableOpacity>
                            {showCategoriaOptions && (
                                <View style={styles.selectDropdown}>
                                    {categorias.map((cat) => (
                                        <TouchableOpacity
                                            key={cat}
                                            style={styles.selectOption}
                                            onPress={() => {
                                                setFormData({ ...formData, categoria: cat });
                                                setShowCategoriaOptions(false);
                                            }}
                                        >
                                            <Text style={styles.selectOptionText}>{cat}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Localização</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.localizacao}
                                onChangeText={(text) => setFormData({ ...formData, localizacao: String(text ?? '') })}
                                placeholder=""
                                autoCapitalize="none"
                                returnKeyType="next"
                                onBlur={() =>
                                    setFormData((prev) => ({ ...prev, localizacao: toUpper(prev.localizacao) }))
                                }
                                onSubmitEditing={() =>
                                    setFormData((prev) => ({ ...prev, localizacao: toUpper(prev.localizacao) }))
                                }
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Saldo em estoque (unidades)</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.quantidade}
                                onChangeText={(text) => setFormData({ ...formData, quantidade: sanitizeIntText(text) })}
                                placeholder="0"
                                keyboardType={numericKeyboardType}
                            />
                            <Text style={styles.hintText}>
                                Ajustes geram eventos de inventário (não criam registros de Entrada/Saída).
                            </Text>
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Unidade de medida</Text>
                            <TouchableOpacity
                                style={[styles.selectInput, !canEdit && styles.inputDisabled]}
                                activeOpacity={canEdit ? 0.8 : 1}
                                onPress={() => canEdit && setShowUnidadeOptions((v) => !v)}
                            >
                                <Text style={[styles.selectText, !canEdit && styles.textDisabled]}>{formData.unidade || 'Unidade'}</Text>
                                {canEdit && <Text style={styles.selectChevron}>▾</Text>}
                            </TouchableOpacity>
                            {showUnidadeOptions && canEdit && (
                                <View style={styles.selectDropdown}>
                                    {unidades.map((uni) => (
                                        <TouchableOpacity
                                            key={uni}
                                            style={styles.selectOption}
                                            onPress={() => {
                                                setFormData({ ...formData, unidade: uni });
                                                setShowUnidadeOptions(false);
                                            }}
                                        >
                                            <Text style={styles.selectOptionText}>{uni}</Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                            <Text style={styles.hintText}>
                                Escolha como você contabiliza este item no estoque.
                            </Text>
                        </View>
                    </View>

                    <View style={styles.buttonContainer}>
                        <TouchableOpacity style={styles.cancelButton} onPress={() => navigation.goBack()} disabled={loading}>
                            <Text style={styles.cancelButtonText}>Cancelar</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                            style={[styles.submitButton, (loading || !canEdit) && styles.buttonDisabled]}
                            onPress={handleSubmit}
                            disabled={loading || !canEdit}
                        >
                            {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitButtonText}>Salvar</Text>}
                        </TouchableOpacity>
                    </View>

                    <TouchableOpacity
                        style={[styles.deleteButton, (loading || !canEdit) && styles.buttonDisabled]}
                        onPress={handleDelete}
                        disabled={loading || !canEdit}
                    >
                        <Text style={styles.deleteButtonText}>Excluir</Text>
                    </TouchableOpacity>

                    {!canEdit && (
                        <Text style={styles.permissionHint}>
                            Somente administrador ou gerente pode editar itens.
                        </Text>
                    )}
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
    centerContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#f5f5f5',
        padding: 20,
    },
    errorText: {
        fontSize: 16,
        color: '#666',
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
    sectionCard: {
        borderWidth: 1,
        borderColor: '#e5e7eb',
        borderRadius: 12,
        padding: 16,
        marginBottom: 16,
        backgroundColor: '#fff',
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 12,
    },
    infoBox: {
        backgroundColor: '#f0f6ff',
        borderRadius: 10,
        padding: 12,
        marginBottom: 18,
        borderWidth: 1,
        borderColor: '#d6e8ff',
    },
    infoTitle: {
        fontSize: 12,
        color: '#0d6efd',
        fontWeight: '700',
        marginBottom: 4,
    },
    infoValue: {
        fontSize: 16,
        color: '#0b2e66',
        fontWeight: '700',
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
    inputDisabled: {
        opacity: 0.9,
    },
    selectInput: {
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 12,
        backgroundColor: '#f9f9f9',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    selectText: {
        fontSize: 16,
        color: '#111827',
    },
    selectChevron: {
        fontSize: 16,
        color: '#374151',
        marginLeft: 10,
    },
    selectDropdown: {
        marginTop: 8,
        borderWidth: 1,
        borderColor: '#ddd',
        borderRadius: 8,
        overflow: 'hidden',
        backgroundColor: '#fff',
    },
    selectOption: {
        paddingHorizontal: 12,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#eee',
    },
    selectOptionText: {
        fontSize: 16,
        color: '#111827',
    },
    hintText: {
        marginTop: 6,
        fontSize: 12,
        color: '#6b7280',
    },
    deleteButton: {
        backgroundColor: '#dc3545',
        padding: 15,
        borderRadius: 10,
        alignItems: 'center',
        marginTop: 12,
    },
    deleteButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    buttonContainer: {
        flexDirection: 'row',
        gap: 10,
        marginTop: 10,
    },
    cancelButton: {
        flex: 1,
        backgroundColor: '#6c757d',
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
    },
    cancelButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    submitButton: {
        flex: 1,
        backgroundColor: '#0d6efd',
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
    },
    submitButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    buttonDisabled: {
        opacity: 0.6,
    },
    permissionHint: {
        marginTop: 12,
        fontSize: 13,
        color: '#dc3545',
        textAlign: 'center',
        fontWeight: '600',
    },
    fotoContainer: {
        gap: 12,
    },
    fotoPreview: {
        width: '100%',
        height: 240,
        borderRadius: 8,
        backgroundColor: '#f1f5f9',
    },
    fotoActions: {
        flexDirection: 'row',
        gap: 12,
    },
    fotoButton: {
        flex: 1,
        backgroundColor: '#3b82f6',
        paddingVertical: 12,
        borderRadius: 8,
        alignItems: 'center',
    },
    fotoButtonRemove: {
        backgroundColor: '#ef4444',
    },
    fotoButtonText: {
        color: '#fff',
        fontSize: 14,
        fontWeight: '600',
    },
    fotoUploadButton: {
        backgroundColor: '#f1f5f9',
        borderWidth: 2,
        borderColor: '#cbd5e1',
        borderStyle: 'dashed',
        borderRadius: 8,
        paddingVertical: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },
    fotoUploadIcon: {
        fontSize: 48,
        marginBottom: 8,
    },
    fotoUploadText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#475569',
        marginBottom: 4,
    },
    fotoUploadHint: {
        fontSize: 12,
        color: '#94a3b8',
    },
});
