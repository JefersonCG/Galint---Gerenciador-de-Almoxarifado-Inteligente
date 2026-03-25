import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    TextInput,
    StyleSheet,
    TouchableOpacity,
    Alert,
    Vibration,
    Dimensions,
    KeyboardAvoidingView,
    Platform,
} from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import ApiService from '../services/api';

const { width } = Dimensions.get('window');

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
    
    // Ref para controlar debounce de scans
    const lastScanTime = React.useRef(0);

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

        // Debounce: evitar múltiplos scans em menos de 500ms
        const now = Date.now();
        if (now - lastScanTime.current < 500) {
            return;
        }
        lastScanTime.current = now;

        setScanned(true);
        setIsProcessing(true);
        Vibration.vibrate(100);

        try {
            if (mode === 'withdraw_multi') {
                const item = await ApiService.buscarItemPorCodigo(data);
                if (!item) {
                    Alert.alert('Erro', 'Item não encontrado');
                    setScanned(false);
                    return;
                }
                // Retornar item escaneado para RetiradaScreen
                if (route?.params?.multiCallback) {
                    navigation.navigate('Retirada', { 
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
                    Alert.alert('Erro', 'Item não encontrado');
                    setScanned(false);
                    return;
                }

                const categoriaLower = (item?.categoria || '').toString().trim().toLowerCase();
                const isFerramenta = categoriaLower === 'ferramentas' || categoriaLower.includes('ferrament');

                if (mode === 'tool_withdraw') {
                    if (!isFerramenta) {
                        Alert.alert('Atenção', 'Este item não é da categoria Ferramentas.');
                        setScanned(false);
                        return;
                    }
                    navigation.navigate('Retirada', { item, user, tipo: 'ferramenta', defaultQuantity: 1 });
                    return;
                }

                // Mode 'return' unificado - suporta material e ferramenta
                if (mode === 'return' || mode === 'tool_return' || mode === 'material_return') {
                    navigation.navigate('Devolver', { item, user });
                    return;
                }

                if (mode === 'withdraw_fraction') {
                    if (isFerramenta) {
                        Alert.alert('Atenção', 'Retirada fracionada é apenas para materiais líquidos.');
                        setScanned(false);
                        return;
                    }
                    navigation.navigate('Retirada', { item, user, fracionada: true });
                    return;
                }

                navigation.navigate('Retirada', { item, user });
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
                Alert.alert(
                    'Item Não Encontrado',
                    `Código: ${data}\n\nO cadastro mobile foi removido. Cadastre o item pela interface web em Documentos Fiscais.`,
                    [
                        {
                            text: 'OK',
                            onPress: () => setScanned(false),
                        },
                    ]
                );
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
                        <Text style={styles.controlText}>Flash</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                        style={styles.controlButton}
                        onPress={() => setShowManualInput((prev) => !prev)}
                    >
                        <Text style={styles.controlIcon}>⌨️</Text>
                        <Text style={styles.controlText}>Digitar</Text>
                    </TouchableOpacity>

                    {scanned && (
                        <TouchableOpacity
                            style={[styles.controlButton, styles.rescanButton]}
                            onPress={() => {
                                setScanned(false);
                                setIsProcessing(false);
                            }}
                        >
                            <Text style={styles.controlIcon}>🔄</Text>
                            <Text style={styles.controlText}>Escanear</Text>
                        </TouchableOpacity>
                    )}

                    <TouchableOpacity
                        style={styles.controlButton}
                        onPress={() => navigation.goBack()}
                    >
                        <Text style={styles.controlIcon}>✖️</Text>
                        <Text style={styles.controlText}>Fechar</Text>
                    </TouchableOpacity>
                </View>
            </CameraView>
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
        bottom: 40,
        left: 0,
        right: 0,
        flexDirection: 'row',
        justifyContent: 'space-around',
        paddingHorizontal: 40,
    },
    controlButton: {
        alignItems: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
        padding: 15,
        borderRadius: 10,
        minWidth: 80,
    },
    rescanButton: {
        backgroundColor: 'rgba(13, 110, 253, 0.8)',
    },
    controlIcon: {
        fontSize: 24,
        marginBottom: 5,
    },
    controlText: {
        color: '#000',
        fontSize: 12,
        fontWeight: '600',
    },
});
