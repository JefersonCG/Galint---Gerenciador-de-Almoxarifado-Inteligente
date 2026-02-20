import React, { useState, useEffect, useMemo } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Alert,
    ScrollView,
    FlatList,
    ActivityIndicator,
    KeyboardAvoidingView,
    Platform,
} from 'react-native';
import ApiService from '../services/api';

export default function CadastroMultiploScreen({ navigation, route }) {
    const user = route.params?.user;
    const scannedItem = route.params?.scannedItem;

    const [itensCadastro, setItensCadastro] = useState([]);
    const [itemAtualId, setItemAtualId] = useState(0);
    const [showCategoriaOptions, setShowCategoriaOptions] = useState(false);
    const [showUnidadeOptions, setShowUnidadeOptions] = useState(false);
    
    // Formulário do item atual
    const [codigoBarras, setCodigoBarras] = useState('');
    const [descricao, setDescricao] = useState('');
    const [categoria, setCategoria] = useState('Material Elétrico');
    const [unidade, setUnidade] = useState('Unidade');
    const [marca, setMarca] = useState('');
    const [localizacao, setLocalizacao] = useState('');
    const [quantidade, setQuantidade] = useState('1');
    
    const [loading, setLoading] = useState(false);

    const isPrivilegedUser = (currentUser) => {
        if (!currentUser) return false;
        if (currentUser.is_admin || String(currentUser.is_admin || '').trim() === '1') return true;
        const cargo = (currentUser.cargo || '').toString().trim().toLowerCase();
        const setor = (currentUser.setor || '').toString().trim().toLowerCase();
        return cargo.includes('supervisor') || 
               cargo.includes('gerente') || 
               setor.includes('supervisor') || 
               setor.includes('gerente');
    };

    const categorias = [
        'Material Elétrico',
        'Material Hidráulico',
        'Material Piscina',
        'Material de Pintura/Drywall',
        'Materiais de Limpeza',
        'Material Construção',
        'Ferramentas',
        'Material de EP',
        'Material/Uso geral',
    ];

    const unidades = [
        'Unidade',
        'Galão',
        'Lata',
        'Litro',
        'Quilo',
        'Metro',
        'Caixa',
        'Pacote',
        'Rolo',
        'Balde',
        'Tambor',
        'Par',
        'Peça',
    ];

    useEffect(() => {
        if (scannedItem) {
            setCodigoBarras(scannedItem.codigo || scannedItem.codigo_barras || '');
            navigation.setParams({ scannedItem: null });
        }
    }, [scannedItem]);

    useEffect(() => {
        if (!isPrivilegedUser(user)) {
            Alert.alert('Sem permissão', 'Apenas administrador ou supervisor pode cadastrar itens.');
            navigation.goBack();
        }
    }, [user]);

    const handleAdicionarItem = () => {
        const codigo = codigoBarras.trim();
        const desc = descricao.trim();
        const qty = parseInt(quantidade, 10);

        if (!codigo) {
            Alert.alert('Erro', 'Informe o código de barras.');
            return;
        }

        if (!desc) {
            Alert.alert('Erro', 'Informe a descrição do item.');
            return;
        }

        if (Number.isNaN(qty) || qty <= 0) {
            Alert.alert('Erro', 'Informe uma quantidade válida.');
            return;
        }

        const novoItem = {
            id: itemAtualId,
            codigo_barras: codigo,
            descricao: desc,
            categoria: categoria.trim() || 'Material Elétrico',
            unidade: unidade.trim() || 'Unidade',
            marca: marca.trim() || '',
            localizacao: localizacao.trim() || '',
            quantidade: qty,
        };

        setItensCadastro([...itensCadastro, novoItem]);
        setItemAtualId(itemAtualId + 1);

        // Resetar formulário
        setCodigoBarras('');
        setDescricao('');
        setCategoria('Material Elétrico');
        setUnidade('Unidade');
        setMarca('');
        setLocalizacao('');
        setQuantidade('1');

        Alert.alert('Sucesso', 'Item adicionado! Escaneie ou digite o próximo.');
    };

    const handleRemoverItem = (id) => {
        setItensCadastro(itensCadastro.filter(item => item.id !== id));
    };

    const handleEscanear = () => {
        navigation.navigate('Scanner', {
            mode: 'cadastro_multiplo',
            user,
            returnTo: 'CadastroMultiplo',
        });
    };

    const handleFinalizar = async () => {
        if (itensCadastro.length === 0) {
            Alert.alert('Erro', 'Adicione ao menos um item para finalizar.');
            return;
        }

        Alert.alert(
            'Confirmar Cadastro',
            `Cadastrar ${itensCadastro.length} item(ns)?`,
            [
                { text: 'Cancelar', style: 'cancel' },
                {
                    text: 'Confirmar',
                    onPress: async () => {
                        setLoading(true);
                        try {
                            const result = await ApiService.cadastrarItensMultiplos({
                                itens: itensCadastro,
                                matricula: user?.matricula || '',
                            });

                            if (result.success && result.offline) {
                                Alert.alert(
                                    'Registrado Offline',
                                    'Cadastros salvos localmente. Serão sincronizados quando houver conexão.',
                                    [
                                        {
                                            text: 'Novo Cadastro',
                                            onPress: () => setItensCadastro([]),
                                        },
                                        { text: 'Voltar', onPress: () => navigation.goBack() },
                                    ]
                                );
                                return;
                            }

                            if (!result.success) {
                                Alert.alert('Erro', result.message || 'Falha ao cadastrar itens');
                                return;
                            }

                            Alert.alert(
                                'Sucesso',
                                `${itensCadastro.length} item(ns) cadastrado(s) com sucesso!`,
                                [
                                    {
                                        text: 'Novo Cadastro',
                                        onPress: () => setItensCadastro([]),
                                    },
                                    { text: 'Voltar', onPress: () => navigation.goBack() },
                                ]
                            );
                        } catch (error) {
                            Alert.alert('Erro', 'Falha ao cadastrar itens');
                        } finally {
                            setLoading(false);
                        }
                    },
                },
            ]
        );
    };

    const renderItem = ({ item }) => (
        <View style={styles.itemCard}>
            <View style={styles.itemHeader}>
                <Text style={styles.itemTitulo}>{item.descricao}</Text>
                <TouchableOpacity
                    style={styles.btnRemover}
                    onPress={() => handleRemoverItem(item.id)}
                >
                    <Text style={styles.btnRemoverText}>✕</Text>
                </TouchableOpacity>
            </View>
            <Text style={styles.itemCodigo}>📊 {item.codigo_barras}</Text>
            <Text style={styles.itemInfo}>🏷️ {item.categoria}</Text>
            <Text style={styles.itemInfo}>📦 {item.quantidade} {item.unidade}</Text>
            {item.marca && <Text style={styles.itemInfo}>🏭 {item.marca}</Text>}
            {item.localizacao && <Text style={styles.itemInfo}>📍 {item.localizacao}</Text>}
        </View>
    );

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
        >
            <ScrollView style={styles.scrollContainer}>
                <View style={styles.formSection}>
                    <Text style={styles.sectionTitle}>📝 Formulário do Item</Text>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Código de Barras *</Text>
                        <View style={styles.inputWithButton}>
                            <TextInput
                                style={[styles.input, styles.inputFlex]}
                                value={codigoBarras}
                                onChangeText={setCodigoBarras}
                                placeholder="Digite ou escaneie"
                            />
                            <TouchableOpacity style={styles.btnScan} onPress={handleEscanear}>
                                <Text style={styles.btnScanText}>📷</Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Descrição *</Text>
                        <TextInput
                            style={styles.input}
                            value={descricao}
                            onChangeText={setDescricao}
                            placeholder="Nome do item"
                        />
                    </View>

                    <View style={styles.row}>
                        <View style={[styles.inputGroup, styles.flex1]}>
                            <Text style={styles.label}>Categoria</Text>
                            <TouchableOpacity
                                style={styles.selectInput}
                                activeOpacity={0.8}
                                onPress={() => setShowCategoriaOptions((v) => !v)}
                            >
                                <Text style={styles.selectText}>{categoria || 'Material Elétrico'}</Text>
                                <Text style={styles.selectChevron}>▾</Text>
                            </TouchableOpacity>
                            {showCategoriaOptions && (
                                <View style={styles.selectDropdown}>
                                    {categorias.map((cat) => (
                                        <TouchableOpacity
                                            key={cat}
                                            style={styles.selectOption}
                                            onPress={() => {
                                                setCategoria(cat);
                                                setShowCategoriaOptions(false);
                                            }}
                                        >
                                            <Text style={styles.selectOptionText}>
                                                {cat === categoria ? `✓ ${cat}` : cat}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                        </View>
                        <View style={[styles.inputGroup, styles.flex1]}>
                            <Text style={styles.label}>Unidade</Text>
                            <TouchableOpacity
                                style={styles.selectInput}
                                activeOpacity={0.8}
                                onPress={() => setShowUnidadeOptions((v) => !v)}
                            >
                                <Text style={styles.selectText}>{unidade || 'Unidade'}</Text>
                                <Text style={styles.selectChevron}>▾</Text>
                            </TouchableOpacity>
                            {showUnidadeOptions && (
                                <View style={styles.selectDropdown}>
                                    {unidades.map((uni) => (
                                        <TouchableOpacity
                                            key={uni}
                                            style={styles.selectOption}
                                            onPress={() => {
                                                setUnidade(uni);
                                                setShowUnidadeOptions(false);
                                            }}
                                        >
                                            <Text style={styles.selectOptionText}>
                                                {uni === unidade ? `✓ ${uni}` : uni}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                        </View>
                    </View>

                    <View style={styles.row}>
                        <View style={[styles.inputGroup, styles.flex1]}>
                            <Text style={styles.label}>Marca</Text>
                            <TextInput
                                style={styles.input}
                                value={marca}
                                onChangeText={setMarca}
                                placeholder="Opcional"
                            />
                        </View>
                        <View style={[styles.inputGroup, styles.flex1]}>
                            <Text style={styles.label}>Localização</Text>
                            <TextInput
                                style={styles.input}
                                value={localizacao}
                                onChangeText={setLocalizacao}
                                placeholder="Ex: Galpão A"
                            />
                        </View>
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Quantidade Inicial *</Text>
                        <TextInput
                            style={styles.input}
                            value={quantidade}
                            onChangeText={setQuantidade}
                            keyboardType="numeric"
                            placeholder="1"
                        />
                    </View>

                    <TouchableOpacity style={styles.btnAdicionar} onPress={handleAdicionarItem}>
                        <Text style={styles.btnAdicionarText}>➕ Adicionar à Lista</Text>
                    </TouchableOpacity>
                </View>

                {itensCadastro.length > 0 && (
                    <View style={styles.listaSection}>
                        <Text style={styles.sectionTitle}>
                            📋 Itens Adicionados ({itensCadastro.length})
                        </Text>
                        <FlatList
                            data={itensCadastro}
                            renderItem={renderItem}
                            keyExtractor={(item) => item.id.toString()}
                            scrollEnabled={false}
                        />
                    </View>
                )}
            </ScrollView>

            {itensCadastro.length > 0 && (
                <View style={styles.footer}>
                    <TouchableOpacity
                        style={styles.btnFinalizar}
                        onPress={handleFinalizar}
                        disabled={loading}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.btnFinalizarText}>
                                ✅ Finalizar Cadastro ({itensCadastro.length})
                            </Text>
                        )}
                    </TouchableOpacity>
                </View>
            )}
        </KeyboardAvoidingView>
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
    formSection: {
        backgroundColor: '#fff',
        padding: 16,
        margin: 12,
        borderRadius: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#1e293b',
        marginBottom: 16,
    },
    inputGroup: {
        marginBottom: 12,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#475569',
        marginBottom: 6,
    },
    input: {
        backgroundColor: '#f8fafc',
        borderWidth: 1,
        borderColor: '#e2e8f0',
        borderRadius: 8,
        padding: 12,
        fontSize: 15,
        color: '#1e293b',
    },
    selectInput: {
        borderWidth: 1,
        borderColor: '#e2e8f0',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 12,
        backgroundColor: '#f8fafc',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    selectText: {
        fontSize: 15,
        color: '#1e293b',
    },
    selectChevron: {
        fontSize: 16,
        color: '#475569',
        marginLeft: 10,
    },
    selectDropdown: {
        marginTop: 8,
        borderWidth: 1,
        borderColor: '#e2e8f0',
        borderRadius: 8,
        overflow: 'hidden',
        backgroundColor: '#fff',
    },
    selectOption: {
        paddingHorizontal: 12,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#f1f5f9',
    },
    selectOptionText: {
        fontSize: 15,
        color: '#0f172a',
    },
    inputWithButton: {
        flexDirection: 'row',
        gap: 8,
    },
    inputFlex: {
        flex: 1,
    },
    btnScan: {
        backgroundColor: '#3b82f6',
        borderRadius: 8,
        paddingHorizontal: 16,
        justifyContent: 'center',
        alignItems: 'center',
    },
    btnScanText: {
        fontSize: 24,
    },
    row: {
        flexDirection: 'row',
        gap: 12,
    },
    flex1: {
        flex: 1,
    },
    btnAdicionar: {
        backgroundColor: '#10b981',
        borderRadius: 10,
        padding: 14,
        alignItems: 'center',
        marginTop: 8,
    },
    btnAdicionarText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '700',
    },
    listaSection: {
        backgroundColor: '#fff',
        padding: 16,
        margin: 12,
        marginTop: 0,
        borderRadius: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    itemCard: {
        backgroundColor: '#f8fafc',
        borderRadius: 8,
        padding: 12,
        marginBottom: 10,
        borderLeftWidth: 4,
        borderLeftColor: '#10b981',
    },
    itemHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
    },
    itemTitulo: {
        fontSize: 16,
        fontWeight: '700',
        color: '#1e293b',
        flex: 1,
    },
    btnRemover: {
        backgroundColor: '#ef4444',
        width: 28,
        height: 28,
        borderRadius: 14,
        justifyContent: 'center',
        alignItems: 'center',
    },
    btnRemoverText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '700',
    },
    itemCodigo: {
        fontSize: 13,
        color: '#64748b',
        marginBottom: 4,
    },
    itemInfo: {
        fontSize: 13,
        color: '#475569',
        marginBottom: 2,
    },
    footer: {
        backgroundColor: '#fff',
        borderTopWidth: 1,
        borderTopColor: '#e2e8f0',
        padding: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: -2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 5,
    },
    btnFinalizar: {
        backgroundColor: '#22c55e',
        borderRadius: 12,
        padding: 16,
        alignItems: 'center',
    },
    btnFinalizarText: {
        color: '#000',
        fontSize: 18,
        fontWeight: '700',
    },
});
