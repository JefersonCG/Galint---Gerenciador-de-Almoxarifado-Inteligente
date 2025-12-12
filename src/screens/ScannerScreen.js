import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Alert,
    Vibration,
    Dimensions,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import ApiService from '../services/api';

const { width } = Dimensions.get('window');

export default function ScannerScreen({ navigation }) {
    const [permission, requestPermission] = useCameraPermissions();
    const [scanned, setScanned] = useState(false);
    const [flashEnabled, setFlashEnabled] = useState(false);

    useEffect(() => {
        if (!permission?.granted) {
            requestPermission();
        }
    }, []);

    const handleBarCodeScanned = async ({ type, data }) => {
        if (scanned) return;

        setScanned(true);
        Vibration.vibrate(100);

        try {
            const result = await ApiService.getItemByBarcode(data);

            if (result.success) {
                Alert.alert(
                    'Item Encontrado',
                    `${result.data.descricao || result.data.nome}\nQuantidade: ${result.data.quantidade}`,
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
                    `Código: ${data}\n\nDeseja cadastrar este item?`,
                    [
                        {
                            text: 'Não',
                            style: 'cancel',
                            onPress: () => setScanned(false),
                        },
                        {
                            text: 'Sim',
                            onPress: () => {
                                navigation.replace('Cadastro', { barcode: data });
                            },
                        },
                    ]
                );
            } else {
                Alert.alert('Erro', result.message, [
                    { text: 'OK', onPress: () => setScanned(false) },
                ]);
            }
        } catch (error) {
            Alert.alert('Erro', 'Falha ao buscar item', [
                { text: 'OK', onPress: () => setScanned(false) },
            ]);
        }
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
        <View style={styles.container}>
            <CameraView
                style={styles.camera}
                facing="back"
                onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
                barcodeScannerSettings={{
                    barcodeTypes: [
                        'qr',
                        'ean13',
                        'ean8',
                        'code128',
                        'code39',
                        'code93',
                        'codabar',
                        'upc_e',
                        'upc_a',
                        'itf14',
                    ],
                }}
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

                    {scanned && (
                        <TouchableOpacity
                            style={[styles.controlButton, styles.rescanButton]}
                            onPress={() => setScanned(false)}
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
        </View>
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
        color: '#fff',
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
        justifyContent: 'center',
        alignItems: 'center',
    },
    instructionText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '600',
        textAlign: 'center',
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
        color: '#fff',
        fontSize: 12,
        fontWeight: '600',
    },
});
