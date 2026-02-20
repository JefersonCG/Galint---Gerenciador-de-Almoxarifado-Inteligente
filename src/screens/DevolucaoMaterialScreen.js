import React, { useMemo, useState, useEffect } from 'react';
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

function sanitizeIntText(text) {
    if (text == null) return '';
    return String(text).replace(/[^0-9]/g, '');
}

export default function DevolucaoMaterialScreen({ navigation, route }) {
    const user = route.params?.user;
    const item = route.params?.item;

    const [quantidade, setQuantidade] = useState('1');
    const [loading, setLoading] = useState(false);
    const [usuarios, setUsuarios] = useState([]);
    const [devolvedorBusca, setDevolvedorBusca] = useState('');
    const [devolvedorSelecionado, setDevolvedorSelecionado] = useState(null);
    const [showAutocompleteLista, setShowAutocompleteLista] = useState(false);
    const [ultimoResponsavel, setUltimoResponsavel] = useState(null);
    const [loadingUltimoResponsavel, setLoadingUltimoResponsavel] = useState(true);

    const saldoAtual = useMemo(() => {
        const q = Number(item?.quantidade ?? 0);
        return Number.isFinite(q) ? Number(q.toFixed(6)) : 0;
    }, [item]);

    const canChooseDevolvedor = useMemo(() => {
        if (!user) return false;
        if (user.is_admin) return true;
        if (user.is_manager) return true;
        const cargo = (user.cargo || '').toString().trim().toLowerCase();
        return cargo.includes('gerente');
    }, [user]);

    const userMatricula = useMemo(() => {
        return (user?.matricula || '').toString().trim();
    }, [user]);

    const userNome = useMemo(() => {
        return (user?.nome || user?.username || '').toString().trim();
    }, [user]);

    // Buscar último responsável que retirou o item
    useEffect(() => {
        const buscarUltimoResponsavel = async () => {
            try {
                setLoadingUltimoResponsavel(true);
                const codigo = String(item?.id || item?.codigo_barras || '').trim();
                if (!codigo) return;

                const ultimaRetirada = await ApiService.getUltimaRetirada(codigo);
                if (ultimaRetirada) {
                    setUltimoResponsavel(ultimaRetirada);
                }
            } catch (error) {
                console.error('Erro ao buscar último responsável:', error);
            } finally {
                setLoadingUltimoResponsavel(false);
            }
        };

        buscarUltimoResponsavel();
    }, [item]);

    useEffect(() => {
        if (!canChooseDevolvedor) {
            if (userMatricula) {
                const selfUser = {
                    matricula: userMatricula,
                    nome: userNome || userMatricula,
                    cargo: user?.cargo || null,
                    setor: user?.setor || null,
                };
                setDevolvedorSelecionado(selfUser);
                setDevolvedorBusca(selfUser.nome);
                setShowAutocompleteLista(false);
            }
            return;
        }

        const carregarUsuarios = async () => {
            const lista = await ApiService.getUsuarios();
            setUsuarios(lista);
        };

        carregarUsuarios();
    }, [canChooseDevolvedor, userMatricula, userNome, user]);

    const usuariosFiltrados = useMemo(() => {
        if (!devolvedorBusca.trim()) return usuarios;
        const busca = devolvedorBusca.toLowerCase();
        return usuarios.filter((u) =>
            u.nome.toLowerCase().includes(busca) ||
            (u.matricula || '').toString().includes(busca)
        );
    }, [devolvedorBusca, usuarios]);

    const handleSubmit = async () => {
        const quantidadeInt = parseInt(sanitizeIntText(quantidade), 10);
        if (Number.isNaN(quantidadeInt) || quantidadeInt <= 0) {
            Alert.alert('Erro', 'Informe uma quantidade válida (inteiro > 0).');
            return;
        }

        if (!devolvedorSelecionado) {
            Alert.alert('Erro', 'Selecione quem está devolvendo.');
            return;
        }

        if (!item?.id && !item?.codigo_barras) {
            Alert.alert('Erro', 'Item inválido. Volte e selecione novamente.');
            return;
        }

        setLoading(true);
        try {
            const codigo = String(item.id || item.codigo_barras).trim();
            const result = await ApiService.devolverMaterial({
                codigo,
                quantidade: quantidadeInt,
                matricula_devolvedor: String(devolvedorSelecionado?.matricula || '').trim(),
            });

            if (!result.success) {
                Alert.alert('Erro', result.message);
                return;
            }

            if (result.offline) {
                Alert.alert(
                    'Registrado Offline',
                    'Devolução salva localmente. Ela será sincronizada quando houver conexão.',
                    [
                        { text: 'Nova Devolução', onPress: () => setQuantidade('1') },
                        { text: 'Voltar', onPress: () => navigation.goBack() },
                    ]
                );
                return;
            }

            const novoSaldoRaw = result.data?.item?.saldo;
            const novoSaldo = Number.isFinite(Number(novoSaldoRaw))
                ? Number(Number(novoSaldoRaw).toFixed(6))
                : novoSaldoRaw;

            Alert.alert(
                'Sucesso',
                `Devolução registrada! Material reacrescentado ao estoque.\nNovo saldo: ${novoSaldo ?? 'OK'}`,
                [
                    {
                        text: 'Nova Devolução',
                        onPress: () => setQuantidade('1'),
                    },
                    { text: 'Voltar', onPress: () => navigation.goBack() },
                ]
            );
        } catch (e) {
            Alert.alert('Erro', 'Falha ao registrar devolução');
        } finally {
            setLoading(false);
        }
    };

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
                <View style={styles.card}>
                    <Text style={styles.title}>↩️ Devolução de Material</Text>

                    {loadingUltimoResponsavel && (
                        <View style={styles.loadingBox}>
                            <ActivityIndicator size="small" color="#198754" />
                            <Text style={styles.loadingText}>Verificando último responsável...</Text>
                        </View>
                    )}

                    {ultimoResponsavel && !loadingUltimoResponsavel && (
                        <View style={styles.infoBox}>
                            <Text style={styles.infoTitle}>📋 Última Retirada</Text>
                            <Text style={styles.infoText}>
                                Responsável: {ultimoResponsavel.nome && !ultimoResponsavel.nome.startsWith('Matrícula') 
                                    ? ultimoResponsavel.nome 
                                    : `Funcionário (Mat. ${ultimoResponsavel.matricula})`}
                            </Text>
                            <Text style={styles.infoText}>
                                Data: {new Date(ultimoResponsavel.data_saida).toLocaleDateString('pt-BR')}
                            </Text>
                        </View>
                    )}

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Devolvido por *</Text>
                        <TextInput
                            style={[styles.input, !canChooseDevolvedor && styles.inputDisabled]}
                            value={devolvedorBusca}
                            onChangeText={(text) => {
                                setDevolvedorBusca(text);
                                setShowAutocompleteLista(true);
                                setDevolvedorSelecionado(null);
                            }}
                            placeholder="Digite o nome ou matrícula"
                            editable={canChooseDevolvedor}
                        />

                        {showAutocompleteLista && canChooseDevolvedor && (
                            <View style={styles.autocompleteContainer}>
                                <FlatList
                                    data={usuariosFiltrados.slice(0, 8)}
                                    keyExtractor={(item) => item.matricula}
                                    style={styles.autocompleteList}
                                    keyboardShouldPersistTaps="handled"
                                    renderItem={({ item }) => (
                                        <TouchableOpacity
                                            style={styles.autocompleteItem}
                                            onPress={() => {
                                                setDevolvedorSelecionado(item);
                                                const labelCompleto = item.cargo
                                                    ? `${item.nome} (${item.cargo})`
                                                    : item.nome;
                                                setDevolvedorBusca(labelCompleto);
                                                setShowAutocompleteLista(false);
                                            }}
                                        >
                                            <Text style={styles.autocompleteNome}>{item.nome}</Text>
                                            <Text style={styles.autocompleteDetalhe}>
                                                {item.cargo || item.setor || ''} | Mat: {item.matricula}
                                            </Text>
                                        </TouchableOpacity>
                                    )}
                                />
                            </View>
                        )}
                    </View>

                    <View style={styles.itemBox}>
                        <Text style={styles.itemName}>
                            {(item?.descricao || item?.nome || '').toString().toUpperCase()}
                        </Text>
                        <Text style={styles.itemLine}>
                            📊 Código: {(item?.codigo_barras || item?.id || '').toString()}
                        </Text>
                        <Text style={styles.itemLine}>📦 Saldo atual: {saldoAtual}</Text>
                        {item?.categoria && (
                            <Text style={styles.itemLine}>🏷️ Categoria: {item.categoria}</Text>
                        )}
                    </View>

                    <View style={styles.inputGroup}>
                        <Text style={styles.label}>Quantidade a Devolver *</Text>
                        <TextInput
                            style={styles.input}
                            value={quantidade}
                            onChangeText={(text) => setQuantidade(sanitizeIntText(text))}
                            placeholder="Digite a quantidade"
                            keyboardType="numeric"
                        />
                    </View>

                    <TouchableOpacity
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={handleSubmit}
                        disabled={loading}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>✅ Confirmar Devolução</Text>
                        )}
                    </TouchableOpacity>

                    <Text style={styles.hint}>
                        ℹ️ A quantidade será automaticamente reacrescentada ao estoque.
                    </Text>
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
    scroll: {
        padding: 16,
    },
    card: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 3,
    },
    title: {
        fontSize: 22,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 16,
        textAlign: 'center',
    },
    loadingBox: {
        backgroundColor: '#f0f9ff',
        padding: 12,
        borderRadius: 8,
        marginBottom: 16,
        flexDirection: 'row',
        alignItems: 'center',
        borderLeftWidth: 4,
        borderLeftColor: '#0ea5e9',
    },
    loadingText: {
        fontSize: 14,
        color: '#000',
        marginLeft: 10,
        fontWeight: '600',
    },
    infoBox: {
        backgroundColor: '#f0fdf4',
        padding: 12,
        borderRadius: 8,
        marginBottom: 16,
        borderLeftWidth: 4,
        borderLeftColor: '#22c55e',
    },
    infoTitle: {
        fontSize: 15,
        fontWeight: 'bold',
        color: '#166534',
        marginBottom: 6,
    },
    infoText: {
        fontSize: 14,
        color: '#15803d',
        marginTop: 3,
    },
    userBox: {
        backgroundColor: '#f3f4f6',
        padding: 12,
        borderRadius: 8,
        marginBottom: 16,
    },
    userLine: {
        fontSize: 14,
        color: '#374151',
    },
    itemBox: {
        backgroundColor: '#eff6ff',
        padding: 16,
        borderRadius: 8,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: '#bfdbfe',
    },
    itemName: {
        fontSize: 16,
        fontWeight: '700',
        color: '#1e40af',
        marginBottom: 8,
    },
    itemLine: {
        fontSize: 14,
        color: '#374151',
        marginTop: 4,
    },
    inputGroup: {
        marginBottom: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#374151',
        marginBottom: 8,
    },
    input: {
        borderWidth: 1,
        borderColor: '#d1d5db',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
        backgroundColor: '#fff',
    },
    inputDisabled: {
        backgroundColor: '#f3f4f6',
        color: '#6b7280',
    },
    autocompleteContainer: {
        backgroundColor: '#fff',
        borderWidth: 1,
        borderColor: '#e5e7eb',
        borderRadius: 8,
        marginTop: 6,
        maxHeight: 200,
        overflow: 'hidden',
    },
    autocompleteList: {
        maxHeight: 200,
    },
    autocompleteItem: {
        padding: 10,
        borderBottomWidth: 1,
        borderBottomColor: '#f1f5f9',
    },
    autocompleteNome: {
        fontSize: 14,
        fontWeight: '700',
        color: '#111827',
    },
    autocompleteDetalhe: {
        fontSize: 12,
        color: '#6b7280',
        marginTop: 2,
    },
    button: {
        backgroundColor: '#10b981',
        paddingVertical: 14,
        paddingHorizontal: 20,
        borderRadius: 8,
        alignItems: 'center',
        marginBottom: 12,
    },
    buttonDisabled: {
        backgroundColor: '#9ca3af',
    },
    buttonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    hint: {
        fontSize: 12,
        color: '#6b7280',
        textAlign: 'center',
        marginTop: 8,
    },
});
