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
    Image,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import DateTimePicker from '@react-native-community/datetimepicker';
import * as ImagePicker from 'expo-image-picker';
import ApiService from '../services/api';

function toUpper(text) {
    return String(text || '').toUpperCase();
}

function sanitizeIntText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9]/g, '');
}

export default function CadastroScreen({ navigation, route }) {
    const [loading, setLoading] = useState(false);
    const [showCategoriaOptions, setShowCategoriaOptions] = useState(false);
    const [showUnidadeOptions, setShowUnidadeOptions] = useState(false);

    const numericKeyboardType = Platform.OS === 'ios' ? 'number-pad' : 'numeric';

    const [formData, setFormData] = useState({
        codigo_barras: route.params?.barcode || '',
        nota_fiscal: '',
        descricao: '',
        marca: '',
        categoria: 'Material Elétrico',
        localizacao: '',
        quantidade: '',
        unidade: 'Unidade',
        numero_serie: '',
        modelo: '',
        // Campos de rastreabilidade
        data_entrada: '',
        data_fabricacao: '',
        data_validade: '',
        tipo_embalagem: '',
        grandeza_referencia: '',
        grandeza_tipo: 'kg',
    });

    const [habilitarSerieModelo, setHabilitarSerieModelo] = useState(false);
    const [fotoSelecionada, setFotoSelecionada] = useState(null);
    const [showDatePicker, setShowDatePicker] = useState({
        data_entrada: false,
        data_fabricacao: false,
        data_validade: false,
    });
    const [user, setUser] = useState(route.params?.user || null);
    const [userReady, setUserReady] = useState(Boolean(route.params?.user));

    const isAdminOrManager = (currentUser) => {
        if (!currentUser) return false;
        // Admin: is_admin pode vir como boolean, number ou string
        const isAdmin = currentUser.is_admin === true || 
                        currentUser.is_admin === 1 || 
                        String(currentUser.is_admin || '').trim() === '1';
        if (isAdmin) return true;
        // Manager
        if (currentUser.is_manager === true) return true;
        // Cargo/Setor
        const cargo = (currentUser.cargo || '').toString().trim().toLowerCase();
        const setor = (currentUser.setor || '').toString().trim().toLowerCase();
        if (cargo.includes('almoxarif')) return true;
        return cargo.includes('gerente') || 
               setor.includes('gerente') || 
               cargo.includes('supervisor') || 
               setor.includes('supervisor');
    };

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
                    setUserReady(true);
                })
                .catch(() => {
                    setUserReady(true);
                });
        } else {
            setUserReady(true);
        }
    }, [route.params?.user]);

    useEffect(() => {
        if (!userReady) return;

        console.log('========================================');
        console.log('[CADASTRO] DEBUGGING PERMISSÕES');
        console.log('[CADASTRO] User completo:', JSON.stringify(user, null, 2));
        console.log('[CADASTRO] is_admin tipo:', typeof user?.is_admin);
        console.log('[CADASTRO] is_admin valor:', user?.is_admin);
        console.log('[CADASTRO] is_manager:', user?.is_manager);
        console.log('[CADASTRO] cargo:', user?.cargo);
        console.log('[CADASTRO] setor:', user?.setor);
        console.log('[CADASTRO] isAdminOrManager resultado:', isAdminOrManager(user));
        console.log('========================================');
        
        if (!isAdminOrManager(user)) {
            console.log('[CADASTRO] ❌ PERMISSÃO NEGADA - Voltando para tela anterior');
            Alert.alert(
                'Sem permissão', 
                `Apenas administrador, supervisor ou gerente pode cadastrar itens.\\n\\nSeu perfil atual:\\nCargo: ${user?.cargo || 'N/A'}\\nSetor: ${user?.setor || 'N/A'}\\nis_admin: ${user?.is_admin}`, 
                [
                    {
                        text: 'OK',
                        onPress: () => navigation.goBack()
                    }
                ]
            );
        } else {
            console.log('[CADASTRO] ✅ PERMISSÃO OK - Usuário pode cadastrar');
        }
    }, [user, navigation, userReady]);

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

    const unidades = [
        'Unidade',
        'Lata',
        'Litro',
        'Quilo',
        'Caixa',
        'Pacote',
        'Fardo',
        'Rolo',
        'Balde',
        'Par',
        'Peça',
    ];

    // Funções para Date Picker
    const formatDateForDisplay = (dateString) => {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('pt-BR');
    };

    const handleDateChange = (field, event, selectedDate) => {
        setShowDatePicker({ ...showDatePicker, [field]: false });
        if (selectedDate) {
            const isoDate = selectedDate.toISOString().split('T')[0];
            setFormData({ ...formData, [field]: isoDate });
        }
    };

    const calcularDiasValidade = () => {
        if (!formData.data_validade) return null;
        const hoje = new Date();
        const validade = new Date(formData.data_validade);
        const diffTime = validade - hoje;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        if (diffDays < 0) return { texto: `⚠️ Vencido há ${Math.abs(diffDays)} dias`, cor: '#dc2626' };
        if (diffDays <= 30) return { texto: `⚠️ Vence em ${diffDays} dias`, cor: '#d97706' };
        return { texto: `✓ Vence em ${diffDays} dias`, cor: '#059669' };
    };

    const calcularConversao = () => {
        const quantidade = parseInt(sanitizeIntText(formData.quantidade) || '0', 10);
        const grandeza = parseFloat(formData.grandeza_referencia || '0');
        
        if (quantidade === 0 || grandeza === 0) return null;

        if (formData.unidade === 'Lata' || formData.unidade === 'Balde') {
            const grandezaTipo = formData.grandeza_tipo || 'kg';
            if (grandezaTipo === 'l') {
                const litros = quantidade * grandeza;
                return `${quantidade} ${formData.tipo_embalagem || 'embalagens'} = ${litros.toFixed(2)} L`;
            } else {
                const quilos = quantidade * grandeza;
                return `${quantidade} ${formData.tipo_embalagem || 'embalagens'} = ${quilos.toFixed(2)} kg`;
            }
        }

        if (formData.unidade === 'Rolo') {
            const metros = quantidade * grandeza;
            const centimetros = metros * 100;
            return `${quantidade} rolos = ${metros.toFixed(2)} m = ${centimetros.toFixed(0)} cm`;
        }

        if (formData.unidade === 'Pacote' || formData.unidade === 'Caixa' || formData.unidade === 'Fardo') {
            const unidades = quantidade * grandeza;
            const tipo = formData.unidade === 'Pacote' ? 'pacotes' : (formData.unidade === 'Fardo' ? 'fardos' : 'caixas');
            return `${quantidade} ${tipo} = ${unidades.toFixed(0)} unidades`;
        }

        return null;
    };

    const validadeInfo = calcularDiasValidade();
    const conversaoPreview = calcularConversao();

    const handleSubmit = async () => {
        if (!formData.codigo_barras) {
            Alert.alert('Erro', 'Código de barras é obrigatório');
            return;
        }

        if (!formData.descricao) {
            Alert.alert('Erro', 'Produto é obrigatório');
            return;
        }

        const quantidadeInt = parseInt(sanitizeIntText(formData.quantidade) || '0', 10);
        if (Number.isNaN(quantidadeInt) || quantidadeInt < 0) {
            Alert.alert('Erro', 'Saldo em estoque inválido');
            return;
        }
        const isEmbalagem = formData.unidade === 'Lata' || formData.unidade === 'Balde';
        const grandezaFloat = parseFloat(formData.grandeza_referencia || '0');

        setLoading(true);

        try {
            const dataToSend = {
                codigo_barras: String(formData.codigo_barras || '').trim(),
                descricao: String(formData.descricao || '').trim(),
                categoria: String(formData.categoria || 'Material Eletrico').trim(),
                localizacao: String(formData.localizacao || '').trim(),
                marca: String(formData.marca || '').trim(),
                nota_fiscal: String(formData.nota_fiscal || '').trim(),
                quantidade: quantidadeInt,
                unidade: String(formData.unidade || 'Unidade').trim() || 'Unidade',
            };

            // Adicionar foto se selecionada
            if (fotoSelecionada) {
                dataToSend.foto = fotoSelecionada;
            }

            // Adicionar campos de rastreabilidade
            if (formData.data_entrada) dataToSend.data_entrada = formData.data_entrada;
            if (formData.data_fabricacao) dataToSend.data_fabricacao = formData.data_fabricacao;
            if (formData.data_validade) dataToSend.data_validade = formData.data_validade;
            if (isEmbalagem) {
                dataToSend.tipo_embalagem = formData.unidade;
            } else if (formData.tipo_embalagem) {
                dataToSend.tipo_embalagem = formData.tipo_embalagem;
            }

            if (formData.grandeza_referencia) {
                dataToSend.grandeza_referencia = grandezaFloat;
            }

            // Adicionar numero_serie e modelo se categoria for Ferramentas
            if (formData.categoria === 'Ferramentas' && habilitarSerieModelo) {
                if (formData.numero_serie) {
                    dataToSend.numero_serie = String(formData.numero_serie).trim();
                }
                if (formData.modelo) {
                    dataToSend.modelo = String(formData.modelo).trim();
                }
            }

            const result = await ApiService.cadastrarItem(dataToSend);

            if (result.success && result.offline) {
                Alert.alert(
                    'Registrado Offline',
                    'Cadastro salvo localmente. Ele será sincronizado quando houver conexão.',
                    [
                        {
                            text: 'Cadastrar Outro',
                            onPress: () => {
                                setFormData({
                                    codigo_barras: '',
                                    nota_fiscal: formData.nota_fiscal,
                                    descricao: '',
                                    marca: '',
                                    categoria: formData.categoria,
                                    localizacao: formData.localizacao,
                                    quantidade: '0',
                                    unidade: formData.unidade || 'Unidade',
                                    numero_serie: '',
                                    modelo: '',
                                    tipo_embalagem: '',
                                    grandeza_referencia: '',
                                    grandeza_tipo: 'kg',
                                });
                                setFotoSelecionada(null);
                                setHabilitarSerieModelo(false);
                            },
                        },
                        {
                            text: 'Voltar',
                            onPress: () => navigation.goBack(),
                        },
                    ]
                );
                return;
            }

            if (result.success) {
                Alert.alert(
                    'Sucesso!',
                    'Item cadastrado com sucesso',
                    [
                        {
                            text: 'Cadastrar Outro',
                            onPress: () => {
                                setFormData({
                                    codigo_barras: '',
                                    nota_fiscal: formData.nota_fiscal,
                                    descricao: '',
                                    marca: '',
                                    categoria: formData.categoria,
                                    localizacao: formData.localizacao,
                                    quantidade: '0',
                                    unidade: formData.unidade || 'Unidade',
                                    numero_serie: '',
                                    modelo: '',
                                    tipo_embalagem: '',
                                    grandeza_referencia: '',
                                    grandeza_tipo: 'kg',
                                });
                                setFotoSelecionada(null);
                                setHabilitarSerieModelo(false);
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
            }
        } catch (error) {
            Alert.alert('Erro', 'Não foi possível tirar a foto');
        }
    };

    const handleRemoverFoto = () => {
        setFotoSelecionada(null);
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
                    <View style={styles.sectionCard}>
                        <Text style={styles.sectionTitle}>Identificação</Text>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Código de barras *</Text>
                            <View style={styles.barcodeContainer}>
                                <TextInput
                                    style={[styles.input, styles.barcodeInput]}
                                    value={formData.codigo_barras}
                                    onChangeText={(text) =>
                                        setFormData({ ...formData, codigo_barras: text })
                                    }
                                    placeholder=""
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

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Número da NF</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.nota_fiscal}
                                onChangeText={(text) =>
                                    setFormData({ ...formData, nota_fiscal: sanitizeIntText(text) })
                                }
                                placeholder=""
                                keyboardType={numericKeyboardType}
                            />
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Produto *</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.descricao}
                                onChangeText={(text) =>
                                    setFormData({ ...formData, descricao: String(text ?? '') })
                                }
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
                                onChangeText={(text) =>
                                    setFormData({ ...formData, marca: String(text ?? '') })
                                }
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
                                            <Text style={styles.selectOptionText}>
                                                {cat === formData.categoria ? `✓ ${cat}` : cat}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                        </View>

                        {/* Campos extras para Ferramentas */}
                        {formData.categoria === 'Ferramentas' && (
                            <View style={styles.ferramentasExtra}>
                                <TouchableOpacity
                                    style={styles.checkboxContainer}
                                    onPress={() => setHabilitarSerieModelo(!habilitarSerieModelo)}
                                >
                                    <View style={[styles.checkbox, habilitarSerieModelo && styles.checkboxChecked]}>
                                        {habilitarSerieModelo && <Text style={styles.checkmark}>✓</Text>}
                                    </View>
                                    <Text style={styles.checkboxLabel}>Adicionar número de série e modelo</Text>
                                </TouchableOpacity>

                                {habilitarSerieModelo && (
                                    <View style={styles.serieModeloFields}>
                                        <View style={styles.inputGroup}>
                                            <Text style={styles.label}>Número de Série</Text>
                                            <TextInput
                                                style={styles.input}
                                                value={formData.numero_serie}
                                                onChangeText={(text) =>
                                                    setFormData({ ...formData, numero_serie: String(text ?? '') })
                                                }
                                                placeholder="Digite o número de série"
                                                autoCapitalize="characters"
                                                returnKeyType="next"
                                            />
                                        </View>

                                        <View style={styles.inputGroup}>
                                            <Text style={styles.label}>Modelo</Text>
                                            <TextInput
                                                style={styles.input}
                                                value={formData.modelo}
                                                onChangeText={(text) =>
                                                    setFormData({ ...formData, modelo: String(text ?? '') })
                                                }
                                                placeholder="Digite o modelo do equipamento"
                                                autoCapitalize="characters"
                                                returnKeyType="next"
                                            />
                                        </View>
                                    </View>
                                )}
                            </View>
                        )}

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Localização</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.localizacao}
                                onChangeText={(text) =>
                                    setFormData({ ...formData, localizacao: String(text ?? '') })
                                }
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
                                onChangeText={(text) =>
                                    setFormData({ ...formData, quantidade: sanitizeIntText(text) })
                                }
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
                                style={styles.selectInput}
                                activeOpacity={0.8}
                                onPress={() => setShowUnidadeOptions((v) => !v)}
                            >
                                <Text style={styles.selectText}>{formData.unidade || 'Unidade'}</Text>
                                <Text style={styles.selectChevron}>▾</Text>
                            </TouchableOpacity>
                            {showUnidadeOptions && (
                                <View style={styles.selectDropdown}>
                                    {unidades.map((uni) => (
                                        <TouchableOpacity
                                            key={uni}
                                            style={styles.selectOption}
                                            onPress={() => {
                                                const next = { ...formData, unidade: uni };
                                                if (uni === 'Lata' || uni === 'Balde') {
                                                    next.tipo_embalagem = uni;
                                                    next.grandeza_tipo = next.grandeza_tipo || 'kg';
                                                } else {
                                                    next.tipo_embalagem = '';
                                                }
                                                setFormData(next);
                                                setShowUnidadeOptions(false);
                                            }}
                                        >
                                            <Text style={styles.selectOptionText}>
                                                {uni === formData.unidade ? `✓ ${uni}` : uni}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                            <Text style={styles.hintText}>
                                Escolha como você contabiliza este item no estoque.
                            </Text>
                            {/* Backup input style for compatibility */}
                            <TextInput
                                style={[styles.input, { display: 'none' }]}
                                value={formData.unidade}
                                editable={false}
                            />
                        </View>
                    </View>

                    {/* SEÇÃO: RASTREABILIDADE */}
                    <View style={styles.sectionCard}>
                        <Text style={styles.sectionTitle}>Rastreabilidade</Text>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Data de Entrada</Text>
                            <TouchableOpacity
                                style={styles.dateInput}
                                onPress={() => setShowDatePicker({ ...showDatePicker, data_entrada: true })}
                            >
                                <Text style={formData.data_entrada ? styles.dateText : styles.datePlaceholder}>
                                    {formData.data_entrada ? formatDateForDisplay(formData.data_entrada) : 'Selecione a data'}
                                </Text>
                                <Text style={styles.dateIcon}>📅</Text>
                            </TouchableOpacity>
                            {showDatePicker.data_entrada && (
                                <DateTimePicker
                                    value={formData.data_entrada ? new Date(formData.data_entrada) : new Date()}
                                    mode="date"
                                    display="default"
                                    onChange={(event, date) => handleDateChange('data_entrada', event, date)}
                                />
                            )}
                            <Text style={styles.hintText}>Data em que o item entrou no estoque</Text>
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Lote</Text>
                            <TextInput
                                style={[styles.input, styles.inputDisabled]}
                                value="Gerado automaticamente"
                                editable={false}
                            />
                            <Text style={styles.hintText}>Formato: LOTE-YYYYMMDD-XXXX (gerado pelo backend)</Text>
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Data de Fabricação</Text>
                            <TouchableOpacity
                                style={styles.dateInput}
                                onPress={() => setShowDatePicker({ ...showDatePicker, data_fabricacao: true })}
                            >
                                <Text style={formData.data_fabricacao ? styles.dateText : styles.datePlaceholder}>
                                    {formData.data_fabricacao ? formatDateForDisplay(formData.data_fabricacao) : 'Selecione a data'}
                                </Text>
                                <Text style={styles.dateIcon}>📅</Text>
                            </TouchableOpacity>
                            {showDatePicker.data_fabricacao && (
                                <DateTimePicker
                                    value={formData.data_fabricacao ? new Date(formData.data_fabricacao) : new Date()}
                                    mode="date"
                                    display="default"
                                    onChange={(event, date) => handleDateChange('data_fabricacao', event, date)}
                                />
                            )}
                        </View>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Data de Validade</Text>
                            <TouchableOpacity
                                style={styles.dateInput}
                                onPress={() => setShowDatePicker({ ...showDatePicker, data_validade: true })}
                            >
                                <Text style={formData.data_validade ? styles.dateText : styles.datePlaceholder}>
                                    {formData.data_validade ? formatDateForDisplay(formData.data_validade) : 'Selecione a data'}
                                </Text>
                                <Text style={styles.dateIcon}>📅</Text>
                            </TouchableOpacity>
                            {showDatePicker.data_validade && (
                                <DateTimePicker
                                    value={formData.data_validade ? new Date(formData.data_validade) : new Date()}
                                    mode="date"
                                    display="default"
                                    onChange={(event, date) => handleDateChange('data_validade', event, date)}
                                />
                            )}
                            {validadeInfo && (
                                <Text style={[styles.validadeStatus, { color: validadeInfo.cor }]}>
                                    {validadeInfo.texto}
                                </Text>
                            )}
                        </View>

                        <View style={styles.alertBox}>
                            <Text style={styles.alertText}>
                                💡 <Text style={styles.alertBold}>Barcode automático:</Text> Ao salvar, o sistema gera automaticamente uma imagem PNG do código de barras no formato Code128.
                            </Text>
                        </View>
                    </View>

                    {/* SEÇÃO: LÓGICA DINÂMICA DE UNIDADES */}
                    <View style={styles.sectionCard}>
                        <Text style={styles.sectionTitle}>Lógica Dinâmica de Unidades</Text>

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Unidade de medida</Text>
                            <TouchableOpacity
                                style={styles.selectInput}
                                activeOpacity={0.8}
                                onPress={() => setShowUnidadeOptions((v) => !v)}
                            >
                                <Text style={styles.selectText}>{formData.unidade || 'Unidade'}</Text>
                                <Text style={styles.selectChevron}>▾</Text>
                            </TouchableOpacity>
                            {showUnidadeOptions && (
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
                                            <Text style={styles.selectOptionText}>
                                                {uni === formData.unidade ? `✓ ${uni}` : uni}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </View>
                            )}
                            <Text style={styles.hintText}>Como você contabiliza este item no estoque</Text>
                        </View>

                        {/* Campos condicionais: Lata/Balde */}
                        {(formData.unidade === 'Lata' || formData.unidade === 'Balde') && (
                            <View style={styles.conditionalFields}>
                                <View style={styles.inputGroup}>
                                    <Text style={styles.label}>Unidade de referência</Text>
                                    <View style={styles.radioGroup}>
                                        <TouchableOpacity
                                            style={styles.radioOption}
                                            onPress={() => setFormData({ ...formData, grandeza_tipo: 'kg' })}
                                        >
                                            <View style={styles.radioCircle}>
                                                {formData.grandeza_tipo === 'kg' && <View style={styles.radioSelected} />}
                                            </View>
                                            <Text style={styles.radioLabel}>Kg</Text>
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={styles.radioOption}
                                            onPress={() => setFormData({ ...formData, grandeza_tipo: 'l' })}
                                        >
                                            <View style={styles.radioCircle}>
                                                {formData.grandeza_tipo === 'l' && <View style={styles.radioSelected} />}
                                            </View>
                                            <Text style={styles.radioLabel}>Litros</Text>
                                        </TouchableOpacity>
                                    </View>
                                </View>

                                <View style={styles.inputGroup}>
                                    <Text style={styles.label}>
                                        {formData.grandeza_tipo === 'l'
                                            ? 'Quantidade por embalagem (litros)'
                                            : 'Quantidade por embalagem (kg)'}
                                    </Text>
                                    <TextInput
                                        style={styles.input}
                                        value={formData.grandeza_referencia}
                                        onChangeText={(text) =>
                                            setFormData({ ...formData, grandeza_referencia: text.replace(/[^0-9.]/g, '') })
                                        }
                                        placeholder="Ex: 18"
                                        keyboardType="decimal-pad"
                                    />
                                    <Text style={styles.hintText}>
                                        {formData.grandeza_tipo === 'l'
                                            ? `Ex: 18 L por ${formData.unidade.toLowerCase()}`
                                            : `Ex: 18 kg por ${formData.unidade.toLowerCase()}`}
                                    </Text>
                                </View>
                            </View>
                        )}

                        {/* Campos condicionais: Rolo */}
                        {formData.unidade === 'Rolo' && (
                            <View style={styles.conditionalFields}>
                                <View style={styles.inputGroup}>
                                    <Text style={styles.label}>Comprimento por rolo (metros)</Text>
                                    <TextInput
                                        style={styles.input}
                                        value={formData.grandeza_referencia}
                                        onChangeText={(text) => {
                                            setFormData({ 
                                                ...formData, 
                                                grandeza_referencia: text.replace(/[^0-9.]/g, ''),
                                                tipo_embalagem: 'Rolo'
                                            });
                                        }}
                                        placeholder="Ex: 100"
                                        keyboardType="decimal-pad"
                                    />
                                    <Text style={styles.hintText}>Ex: 100 metros por rolo</Text>
                                </View>
                            </View>
                        )}

                        {/* Campos condicionais: Pacote/Caixa */}
                        {(formData.unidade === 'Pacote' || formData.unidade === 'Caixa' || formData.unidade === 'Fardo') && (
                            <View style={styles.conditionalFields}>
                                <View style={styles.inputGroup}>
                                    <Text style={styles.label}>
                                        Unidades por {formData.unidade === 'Pacote' ? 'pacote' : (formData.unidade === 'Fardo' ? 'fardo' : 'caixa')}
                                    </Text>
                                    <TextInput
                                        style={styles.input}
                                        value={formData.grandeza_referencia}
                                        onChangeText={(text) => {
                                            setFormData({ 
                                                ...formData, 
                                                grandeza_referencia: text.replace(/[^0-9]/g, ''),
                                                tipo_embalagem: formData.unidade
                                            });
                                        }}
                                        placeholder={formData.unidade === 'Pacote' ? 'Ex: 50' : (formData.unidade === 'Fardo' ? 'Ex: 12' : 'Ex: 100')}
                                        keyboardType="number-pad"
                                    />
                                    <Text style={styles.hintText}>
                                        Ex: {formData.unidade === 'Pacote' ? '50 unidades por pacote' : (formData.unidade === 'Fardo' ? '12 unidades por fardo' : '100 unidades por caixa')}
                                    </Text>
                                </View>
                            </View>
                        )}

                        {/* Preview de conversão */}
                        {conversaoPreview && (
                            <View style={styles.conversionPreview}>
                                <Text style={styles.conversionText}>{conversaoPreview}</Text>
                            </View>
                        )}

                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>Saldo em estoque (unidades)</Text>
                            <TextInput
                                style={styles.input}
                                value={formData.quantidade}
                                onChangeText={(text) =>
                                    setFormData({ ...formData, quantidade: sanitizeIntText(text) })
                                }
                                placeholder="0"
                                keyboardType={numericKeyboardType}
                            />
                            <Text style={styles.hintText}>
                                Ajustes geram eventos de inventário (não criam registros de Entrada/Saída).
                            </Text>
                        </View>

                        <View style={styles.alertBox}>
                            <Text style={styles.alertText}>
                                O estoque mínimo é calculado automaticamente em 5% do saldo atual e alimenta os alertas do dashboard.
                            </Text>
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
                                <Text style={styles.submitButtonText}>Salvar</Text>
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
        backgroundColor: '#ffffff',
    },
    scrollView: {
        flex: 1,
    },
    scrollContent: {
        padding: 16,
    },
    form: {
        gap: 0,
    },
    // SOFT DEPTH: Cards de seção
    sectionCard: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 18,
        marginBottom: 16,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.1,
        shadowRadius: 6,
        elevation: 3,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#1e293b',
        marginBottom: 16,
        letterSpacing: -0.3,
    },
    inputGroup: {
        marginBottom: 16,
    },
    label: {
        fontSize: 13,
        fontWeight: '600',
        color: '#475569',
        marginBottom: 6,
    },
    input: {
        borderWidth: 1,
        borderColor: '#cbd5e1',
        borderRadius: 8,
        padding: 12,
        fontSize: 15,
        backgroundColor: '#ffffff',
        color: '#1e293b',
    },
    inputDisabled: {
        backgroundColor: '#f1f5f9',
        color: '#64748b',
    },
    // Date picker
    dateInput: {
        borderWidth: 1,
        borderColor: '#cbd5e1',
        borderRadius: 8,
        padding: 12,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: '#ffffff',
    },
    dateText: {
        fontSize: 15,
        color: '#1e293b',
    },
    datePlaceholder: {
        fontSize: 15,
        color: '#94a3b8',
    },
    dateIcon: {
        fontSize: 20,
    },
    // Status de validade
    validadeStatus: {
        marginTop: 6,
        fontSize: 12,
        fontWeight: '600',
    },
    // SOFT DEPTH: Campos condicionais destacados
    conditionalFields: {
        backgroundColor: '#f9fafb',
        borderWidth: 1.5,
        borderColor: '#e5e7eb',
        borderRadius: 8,
        padding: 14,
        marginTop: 12,
        marginBottom: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.06,
        shadowRadius: 3,
        elevation: 1,
    },
    // Radio buttons
    radioGroup: {
        flexDirection: 'row',
        gap: 20,
        marginTop: 8,
    },
    radioOption: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    radioCircle: {
        width: 20,
        height: 20,
        borderRadius: 10,
        borderWidth: 2,
        borderColor: '#3b82f6',
        marginRight: 8,
        justifyContent: 'center',
        alignItems: 'center',
    },
    radioSelected: {
        width: 10,
        height: 10,
        borderRadius: 5,
        backgroundColor: '#3b82f6',
    },
    radioLabel: {
        fontSize: 14,
        color: '#475569',
    },
    // SOFT DEPTH: Preview de conversão
    conversionPreview: {
        backgroundColor: '#dbeafe',
        borderLeftWidth: 4,
        borderLeftColor: '#3b82f6',
        borderRadius: 6,
        padding: 12,
        marginTop: 12,
        marginBottom: 12,
    },
    conversionText: {
        fontSize: 13,
        color: '#1e40af',
        fontWeight: '600',
    },
    // Alert box
    alertBox: {
        backgroundColor: '#eff6ff',
        borderLeftWidth: 3,
        borderLeftColor: '#3b82f6',
        borderRadius: 6,
        padding: 12,
        marginTop: 12,
    },
    alertText: {
        fontSize: 12.5,
        color: '#1e40af',
        lineHeight: 18,
    },
    alertBold: {
        fontWeight: '700',
    },
    selectInput: {
        borderWidth: 1,
        borderColor: '#cbd5e1',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 12,
        backgroundColor: '#ffffff',
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
        borderColor: '#cbd5e1',
        borderRadius: 8,
        overflow: 'hidden',
        backgroundColor: '#fff',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 2,
    },
    selectOption: {
        paddingHorizontal: 12,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#f1f5f9',
    },
    selectOptionText: {
        fontSize: 15,
        color: '#1e293b',
    },
    hintText: {
        marginTop: 4,
        fontSize: 12,
        color: '#64748b',
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
    buttonContainer: {
        flexDirection: 'row',
        gap: 12,
        marginTop: 8,
    },
    cancelButton: {
        flex: 1,
        backgroundColor: '#64748b',
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 3,
        elevation: 2,
    },
    cancelButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    submitButton: {
        flex: 1,
        backgroundColor: '#3b82f6',
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
        shadowColor: '#3b82f6',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.3,
        shadowRadius: 4,
        elevation: 3,
    },
    submitButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    buttonDisabled: {
        opacity: 0.6,
    },
    ferramentasExtra: {
        marginTop: 10,
        paddingTop: 16,
        borderTopWidth: 1,
        borderTopColor: '#e5e7eb',
    },
    checkboxContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 16,
    },
    checkbox: {
        width: 24,
        height: 24,
        borderWidth: 2,
        borderColor: '#3b82f6',
        borderRadius: 4,
        marginRight: 10,
        justifyContent: 'center',
        alignItems: 'center',
    },
    checkboxChecked: {
        backgroundColor: '#3b82f6',
    },
    checkmark: {
        color: '#fff',
        fontSize: 16,
        fontWeight: 'bold',
    },
    checkboxLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: '#475569',
    },
    serieModeloFields: {
        gap: 0,
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
