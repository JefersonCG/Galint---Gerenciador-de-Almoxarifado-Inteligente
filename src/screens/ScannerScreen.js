import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Alert,
    Keyboard,
    Vibration,
    Dimensions,
    KeyboardAvoidingView,
    Platform,
} from 'react-native';
import TextInput from '../components/UpperTextInput';
import { useIsFocused } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import ApiService from '../services/api';
import { isRegistrableCode } from '../utils/itemCode';
import { useEscutaVoz } from '../components/EscutaVoz';

const { width } = Dimensions.get('window');

// "Item não encontrado" só quando o servidor respondeu que não existe; se ele não respondeu e o
// item também não está na base do celular, a mensagem diz isso (antes as duas eram iguais).
function itemNotFoundMessage(code) {
    if (ApiService.lastItemLookupFailure === 'network') {
        return 'O servidor não respondeu e este item não está na base do celular. Tente ler de novo.';
    }
    return code ? `O código ${code} não está cadastrado no GALINT.` : 'Item não encontrado.';
}

// Depois de um erro, o mesmo código fica ignorado por um tempo: até a 2.2.0 a câmera lia de novo na
// hora, o erro voltava em seguida e o botão azul "Escanear" ficava preso na tela (print de 21/11/2026).
const SAME_CODE_PAUSE_MS = 2500;

export default function ScannerScreen({ navigation, route }) {
    const mode = route?.params?.mode || 'lookup';
    const user = route?.params?.user;
    const [permission, requestPermission] = useCameraPermissions();
    const [scanned, setScanned] = useState(false);
    const [flashEnabled, setFlashEnabled] = useState(false);
    const [manualCode, setManualCode] = useState('');
    const [showManualInput, setShowManualInput] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    const existingItems = route?.params?.items || [];
    const isFocused = useIsFocused();

    // 2.7.1: 🎤 na câmera. Pedido do usuário em 27/11/2026: "quando clico em + um item no apk ele deveria dar a opção
    // do microfone na câmera". A fala volta para a tela que abriu o leitor (Retirada ou Devolução), que faz a mesma
    // busca do 🎤 dela (material, quantidade, quem e local).
    const { ouvir, ouvindo, janela: janelaDaVoz } = useEscutaVoz();
    const destinoDaFala = mode === 'withdraw_multi' && route?.params?.multiCallback
        ? (route?.params?.returnTo || 'FilaSaida')
        : (mode === 'return' ? 'Devolucao' : null);
    const falar = () => ouvir((frase) => navigation.navigate(destinoDaFala, { user, falaRecebida: frase, falaId: Date.now() }));
    
    // Ref para controlar debounce de scans
    const lastScanTime = React.useRef(0);
    const blockedCode = React.useRef({ code: '', until: 0 });

    // Erro na leitura: a câmera só volta a ler depois do OK, e o mesmo código fica ignorado por 2,5 s.
    const releaseAfterError = (code) => {
        blockedCode.current = { code: String(code || ''), until: Date.now() + SAME_CODE_PAUSE_MS };
        setScanned(false);
        setIsProcessing(false);
    };

    const showScanError = (title, message, code) => {
        Vibration.vibrate([0, 80, 80, 80]);
        Alert.alert(title, message, [
            { text: 'OK', onPress: () => releaseAfterError(code) },
        ], { cancelable: false });
    };

    // Código que não existe (23/11/2026, 2.2.6): quem lança entrada pode cadastrar na hora, no mesmo
    // "Lançar entrada" da Conferência. Sem resposta do servidor, só o aviso de sempre.
    const isAdmin = user?.is_admin === true || user?.is_admin === 1 || String(user?.is_admin || '').trim() === '1';
    const showNotFound = (code) => {
        const codigo = String(code || '').trim();
        if (!isAdmin || !isRegistrableCode(codigo) || ApiService.lastItemLookupFailure === 'network') {
            showScanError('Item não encontrado', itemNotFoundMessage(code), code);
            return;
        }
        Vibration.vibrate([0, 80, 80, 80]);
        Alert.alert('Código não encontrado', `${codigo}\n\nDeseja cadastrar?`, [
            { text: 'Não', onPress: () => releaseAfterError(code) },
            {
                text: 'Cadastrar',
                onPress: () => {
                    releaseAfterError(code);
                    navigation.navigate('EntradaNF', { user, codigoNovo: codigo });
                },
            },
        ], { cancelable: false });
    };

    useEffect(() => {
        if (!permission?.granted) {
            requestPermission();
        }
    }, []);

    useEffect(() => {
        if (isFocused) {
            setScanned(false);
            setIsProcessing(false);
        }
    }, [isFocused]);

    const addItemToList = (items, newItem) => {
        const codigo = String(newItem?.id || newItem?.codigo_barras || '').trim();
        if (!codigo) return items;
        const existingIndex = items.findIndex(
            (entry) => String(entry?.item?.id || entry?.item?.codigo_barras || '').trim() === codigo
        );
        if (existingIndex >= 0) {
            const updated = [...items];
            const currentQty = parseInt(updated[existingIndex].quantidade || '1', 10) || 1;
            updated[existingIndex] = {
                ...updated[existingIndex],
                quantidade: String(currentQty + 1),
            };
            return updated;
        }
        return [...items, { item: newItem, quantidade: '1' }];
    };

    const processCode = async (data) => {
        if (!data) return;
        if (scanned || isProcessing) return;
        if (String(data) === blockedCode.current.code && Date.now() < blockedCode.current.until) return;

        // Debounce: evitar múltiplos scans em menos de 500ms
        const now = Date.now();
        if (now - lastScanTime.current < 500) {
            return;
        }
        lastScanTime.current = now;

        setScanned(true);
        setIsProcessing(true);
        Keyboard.dismiss();
        Vibration.vibrate(100);

        try {
            if (mode === 'withdraw_multi') {
                const item = await ApiService.buscarItemPorCodigo(data);
                if (!item) {
                    showNotFound(data);
                    return;
                }
                // Retornar item escaneado para a tela que abriu o leitor (Fila de saída desde a 2.4.0)
                if (route?.params?.multiCallback) {
                    navigation.navigate(route?.params?.returnTo || 'Retirada', {
                        user, 
                        multi: true, 
                        scannedItem: item 
                    });
                } else {
                    const updatedItems = addItemToList(existingItems, item);
                    navigation.navigate('Retirada', { user, multi: true, items: updatedItems });
                }
                return;
            }

            if (mode === 'withdraw' || mode === 'withdraw_fraction' || mode === 'tool_withdraw' || mode === 'tool_return' || mode === 'material_return' || mode === 'return') {
                const item = await ApiService.buscarItemPorCodigo(data);
                if (!item) {
                    showNotFound(data);
                    return;
                }

                const categoriaLower = (item?.categoria || '').toString().trim().toLowerCase();
                const isFerramenta = categoriaLower === 'ferramentas' || categoriaLower.includes('ferrament');

                if (mode === 'tool_withdraw') {
                    if (!isFerramenta) {
                        showScanError('Atenção', 'Este item não é da categoria Ferramentas.', data);
                        return;
                    }
                    // 2.5.0: retirada única (simples e várias juntas) é a tela da Fila.
                    navigation.navigate('FilaSaida', { user, scannedItem: item });
                    return;
                }

                // Mode 'return' unificado - suporta material e ferramenta
                if (mode === 'return' || mode === 'tool_return' || mode === 'material_return') {
                    navigation.navigate('Devolver', { item, user });
                    return;
                }

                if (mode === 'withdraw_fraction') {
                    if (isFerramenta) {
                        showScanError('Atenção', 'Retirada fracionada é apenas para materiais líquidos.', data);
                        return;
                    }
                    navigation.navigate('Retirada', { item, user, fracionada: true });
                    return;
                }

                navigation.navigate('FilaSaida', { user, scannedItem: item });
                return;
            }

            const result = await ApiService.getItemByBarcode(data);

            if (result.success) {
                const qRaw = result.data?.quantidade;
                const qInt = Number.isFinite(Number(qRaw)) ? Math.trunc(Number(qRaw)) : qRaw;
                Alert.alert(
                    'Item Encontrado',
                    `${result.data.descricao || result.data.nome}\nQuantidade: ${qInt}`,
                    [
                        {
                            text: 'Escanear Outro',
                            onPress: () => setScanned(false),
                        },
                        {
                            text: 'Voltar',
                            onPress: () => navigation.goBack(),
                        },
                    ]
                );
            } else if (result.notFound) {
                showNotFound(data);
            } else {
                Alert.alert('Erro', result.message, [
                    { text: 'OK', onPress: () => {
                        setScanned(false);
                        setIsProcessing(false);
                    }},
                ]);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao buscar item', [
                { text: 'OK', onPress: () => {
                    setScanned(false);
                    setIsProcessing(false);
                }},
            ]);
        } finally {
            // Sempre liberar o processamento após conclusão
            setTimeout(() => {
                setIsProcessing(false);
            }, 300);
        }
    };

    const handleBarCodeScanned = async ({ type, data }) => {
        processCode(data);
    };

    if (!permission) {
        return <View style={styles.container} />;
    }

    if (!permission.granted) {
        return (
            <View style={styles.permissionContainer}>
                <Text style={styles.permissionIcon}>📷</Text>
                <Text style={styles.permissionTitle}>Permissão Necessária</Text>
                <Text style={styles.permissionText}>
                    Precisamos de acesso à câmera para escanear códigos de barras
                </Text>
                <TouchableOpacity
                    style={styles.permissionButton}
                    onPress={requestPermission}
                >
                    <Text style={styles.permissionButtonText}>Permitir Acesso</Text>
                </TouchableOpacity>
            </View>
        );
    }

    return (
        <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <CameraView
                style={styles.camera}
                facing="back"
                onBarcodeScanned={(scanned || isProcessing || !isFocused) ? undefined : handleBarCodeScanned}
                autoFocus="on"
                enableTorch={flashEnabled}
            >
                {/* Overlay com moldura */}
                <View style={styles.overlay}>
                    <View style={styles.topOverlay} />

                    <View style={styles.middleRow}>
                        <View style={styles.sideOverlay} />
                        <View style={styles.scanArea}>
                            <View style={[styles.corner, styles.topLeft]} />
                            <View style={[styles.corner, styles.topRight]} />
                            <View style={[styles.corner, styles.bottomLeft]} />
                            <View style={[styles.corner, styles.bottomRight]} />

                            {!scanned && (
                                <View style={styles.scanLine} />
                            )}
                        </View>
                        <View style={styles.sideOverlay} />
                    </View>

                    <View style={styles.bottomOverlay}>
                        <Text style={styles.instructionText}>
                            {scanned ? 'Processando...' : 'Aponte para o código de barras'}
                        </Text>
                        {showManualInput && (
                            <View style={styles.manualInputBox}>
                                <TextInput
                                    style={styles.manualInput}
                                    value={manualCode}
                                    onChangeText={setManualCode}
                                    placeholder="Digite o código"
                                    placeholderTextColor="#9ca3af"
                                    keyboardType={Platform.OS === 'ios' ? 'number-pad' : 'numeric'}
                                />
                                <TouchableOpacity
                                    style={styles.manualButton}
                                    onPress={() => {
                                        const code = String(manualCode || '').trim();
                                        if (!code) {
                                            Alert.alert('Erro', 'Informe um código válido.');
                                            return;
                                        }
                                        setManualCode('');
                                        setShowManualInput(false);
                                        processCode(code);
                                    }}
                                >
                                    <Text style={styles.manualButtonText}>OK</Text>
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                </View>

                {/* Botões de controle */}
                <View style={styles.controls}>
                    <TouchableOpacity
                        style={styles.controlButton}
                        onPress={() => setFlashEnabled(!flashEnabled)}
                    >
                        <Text style={styles.controlIcon}>
                            {flashEnabled ? '🔦' : '💡'}
                        </Text>
                        <Text style={styles.controlText}>Lanterna</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                        style={styles.controlButton}
                        onPress={() => setShowManualInput((prev) => !prev)}
                    >
                        <Text style={styles.controlIcon}>⌨️</Text>
                        <Text style={styles.controlText}>Digitar</Text>
                    </TouchableOpacity>

                    {destinoDaFala ? (
                        <TouchableOpacity
                            style={[styles.controlButton, styles.controlVoz]}
                            onPress={falar}
                            disabled={ouvindo}
                            accessibilityLabel="Falar o material"
                        >
                            <Text style={styles.controlIcon}>🎤</Text>
                            <Text style={styles.controlText}>Falar</Text>
                        </TouchableOpacity>
                    ) : null}

                    <TouchableOpacity
                        style={styles.controlButton}
                        onPress={() => navigation.goBack()}
                    >
                        <Text style={styles.controlIcon}>✖️</Text>
                        <Text style={styles.controlText}>Fechar</Text>
                    </TouchableOpacity>
                </View>
            </CameraView>
            {janelaDaVoz}
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#000',
    },
    camera: {
        flex: 1,
    },
    permissionContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#f5f5f5',
        padding: 20,
    },
    permissionIcon: {
        fontSize: 80,
        marginBottom: 20,
    },
    permissionTitle: {
        fontSize: 24,
        fontWeight: '600',
        color: '#333',
        marginBottom: 10,
    },
    permissionText: {
        fontSize: 16,
        color: '#666',
        textAlign: 'center',
        marginBottom: 30,
        lineHeight: 24,
    },
    permissionButton: {
        backgroundColor: '#0d6efd',
        paddingHorizontal: 30,
        paddingVertical: 15,
        borderRadius: 10,
    },
    permissionButtonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    overlay: {
        ...StyleSheet.absoluteFillObject,
    },
    topOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.6)',
    },
    middleRow: {
        flexDirection: 'row',
        height: width * 0.7,
    },
    sideOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.6)',
    },
    scanArea: {
        width: width * 0.7,
        position: 'relative',
    },
    corner: {
        position: 'absolute',
        width: 30,
        height: 30,
        borderColor: '#0d6efd',
    },
    topLeft: {
        top: 0,
        left: 0,
        borderTopWidth: 4,
        borderLeftWidth: 4,
    },
    topRight: {
        top: 0,
        right: 0,
        borderTopWidth: 4,
        borderRightWidth: 4,
    },
    bottomLeft: {
        bottom: 0,
        left: 0,
        borderBottomWidth: 4,
        borderLeftWidth: 4,
    },
    bottomRight: {
        bottom: 0,
        right: 0,
        borderBottomWidth: 4,
        borderRightWidth: 4,
    },
    scanLine: {
        position: 'absolute',
        top: '50%',
        left: 0,
        right: 0,
        height: 2,
        backgroundColor: '#0d6efd',
    },
    bottomOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.6)',
        justifyContent: 'flex-start',
        alignItems: 'center',
        paddingTop: 30,
        paddingHorizontal: 20,
    },
    instructionText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '600',
        textAlign: 'center',
        marginBottom: 10,
    },
    manualInputBox: {
        width: '100%',
        flexDirection: 'row',
        gap: 10,
        alignItems: 'center',
        backgroundColor: 'rgba(255,255,255,0.15)',
        borderRadius: 12,
        padding: 16,
        marginTop: 20,
        borderWidth: 2,
        borderColor: '#0d6efd',
    },
    manualInput: {
        flex: 1,
        backgroundColor: '#fff',
        borderRadius: 8,
        paddingHorizontal: 16,
        paddingVertical: 14,
        fontSize: 18,
        fontWeight: '600',
        color: '#111827',
        elevation: 4,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.25,
        shadowRadius: 4,
    },
    manualButton: {
        backgroundColor: '#0d6efd',
        paddingHorizontal: 24,
        paddingVertical: 14,
        borderRadius: 8,
        elevation: 4,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.3,
        shadowRadius: 4,
    },
    manualButtonText: {
        color: '#000',
        fontWeight: '700',
        fontSize: 16,
    },
    controls: {
        position: 'absolute',
        bottom: 16,
        left: 0,
        right: 0,
        flexDirection: 'row',
        justifyContent: 'space-evenly',
        paddingHorizontal: 16,
    },
    controlButton: {
        alignItems: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
        padding: 15,
        borderRadius: 10,
        minWidth: 80,
    },
    controlVoz: {
        backgroundColor: 'rgba(34, 211, 238, 0.85)',
    },
    controlIcon: {
        fontSize: 24,
        marginBottom: 5,
    },
    controlText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '600',
    },
});
