import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import * as Updates from 'expo-updates';
import ApiService from '../services/api';
import HeartbeatService from '../services/heartbeatService';
import InactivityService from '../services/inactivityService';

export default function ConfigScreen({ navigation }) {
    const [checking, setChecking] = useState(false);

    const handleCheckUpdates = async () => {
        // Só funciona em builds de produção
        if (__DEV__) {
            Alert.alert(
                'Modo Desenvolvimento',
                'As atualizações OTA só funcionam em builds de produção (APK/AAB instalado).'
            );
            return;
        }

        setChecking(true);
        try {
            // Forçar verificação com servidor
            const update = await Updates.checkForUpdateAsync();
            
            // Debug info
            const currentVersion = Updates.runtimeVersion || 'N/A';
            const updateId = Updates.updateId || 'N/A';
            
            if (update.isAvailable) {
                Alert.alert(
                    'Atualização Encontrada!', 
                    'Baixando atualização... O app será reiniciado em 5 segundos.',
                    [{ text: 'OK', onPress: async () => {
                        try {
                            await Updates.fetchUpdateAsync();
                            Alert.alert(
                                'Pronto!',
                                'Atualização baixada. Reiniciando em 5 segundos...',
                                [],
                                { cancelable: false }
                            );
                            setTimeout(async () => {
                                await Updates.reloadAsync();
                            }, 5000);
                        } catch (fetchError) {
                            Alert.alert('Erro', 'Falha ao baixar atualização: ' + fetchError.message);
                            setChecking(false);
                        }
                    }}]
                );
            } else {
                Alert.alert(
                    'Atualização', 
                    `Você está usando a versão mais recente!\n\nRuntime: ${currentVersion}\nUpdate ID: ${updateId.substring(0, 8)}...`
                );
            }
        } catch (error) {
            const errorMsg = error?.message || 'Erro desconhecido';
            
            // Detectar se é erro de expo-updates não habilitado
            if (errorMsg.includes('not supported when expo-updates is not enabled') || 
                errorMsg.includes('checkForUpdateAsync')) {
                Alert.alert(
                    'Verificação de Atualizações Indisponível',
                    'O sistema de atualizações automáticas (OTA) não está disponível neste momento.\n\nVerifique sua conexão com a internet ou reinstale o aplicativo.'
                );
            } else {
                Alert.alert(
                    'Erro ao Verificar Atualizações', 
                    `Não foi possível conectar ao servidor de atualizações.\n\nVerifique sua conexão com a internet.`
                );
            }
        } finally {
            setChecking(false);
        }
    };

    const handleLogout = () => {
        Alert.alert(
            'Sair',
            'Deseja realmente sair do aplicativo?',
            [
                { text: 'Cancelar', style: 'cancel' },
                {
                    text: 'Sair',
                    style: 'destructive',
                    onPress: async () => {
                        // Parar serviços de monitoramento
                        HeartbeatService.stop();
                        InactivityService.stop();
                        console.log('[ConfigScreen] Serviços parados antes do logout');
                        
                        // Fazer logout (notifica backend e limpa storage)
                        await ApiService.logout();
                        
                        // Voltar para login e limpar stack (evita voltar com botão do Android)
                        navigation.reset({
                            index: 0,
                            routes: [{ name: 'Login' }],
                        });
                    },
                },
            ]
        );
    };

    return (
        <View style={styles.container}>
            <Text style={styles.title}>Configurações</Text>
            <TouchableOpacity
                style={[styles.button, checking && styles.buttonDisabled]}
                onPress={handleCheckUpdates}
                disabled={checking}
            >
                {checking ? (
                    <ActivityIndicator color="#fff" />
                ) : (
                    <Text style={styles.buttonText}>🔄 Buscar atualização</Text>
                )}
            </TouchableOpacity>
            <Text style={styles.hint}>Use este botão para verificar atualizações OTA manualmente.</Text>

            <TouchableOpacity
                style={styles.logoutButton}
                onPress={handleLogout}
            >
                <Text style={styles.buttonText}>🚪 Sair do aplicativo</Text>
            </TouchableOpacity>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        padding: 20,
        backgroundColor: '#f5f5f5',
    },
    title: {
        fontSize: 22,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 20,
    },
    button: {
        backgroundColor: '#0d6efd',
        paddingVertical: 14,
        borderRadius: 10,
        alignItems: 'center',
    },
    buttonDisabled: {
        opacity: 0.7,
    },
    buttonText: {
        color: '#000',
        fontSize: 16,
        fontWeight: '600',
    },
    hint: {
        marginTop: 12,
        color: '#6b7280',
        fontSize: 12,
    },
    logoutButton: {
        backgroundColor: '#dc3545',
        paddingVertical: 14,
        borderRadius: 10,
        alignItems: 'center',
        marginTop: 24,
    },
});
