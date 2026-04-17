import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import * as Updates from 'expo-updates';
import ApiService from '../services/api';
import HeartbeatService from '../services/heartbeatService';
import InactivityService from '../services/inactivityService';
import HeroScreen from '../components/HeroScreen';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

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
        <HeroScreen
            eyebrow="Shell hero"
            title="Configurações do aparelho"
            subtitle="Atualizações OTA, manutenção do aplicativo e saída segura da sessão."
            heroContent={
                <View style={styles.heroMetaRow}>
                    <View style={styles.heroMetaCard}>
                        <Text style={styles.heroMetaLabel}>Update OTA</Text>
                        <Text style={styles.heroMetaValue}>{checking ? 'Verificando' : 'Pronto'}</Text>
                    </View>
                    <View style={styles.heroMetaCard}>
                        <Text style={styles.heroMetaLabel}>Sessão</Text>
                        <Text style={styles.heroMetaValue}>Protegida</Text>
                    </View>
                </View>
            }
        >
            <View style={styles.card}>
                <Text style={styles.sectionTitle}>Atualização do aplicativo</Text>
                <Text style={styles.hint}>Use este botão para verificar atualizações OTA manualmente.</Text>
                <TouchableOpacity
                    style={[styles.button, checking && styles.buttonDisabled]}
                    onPress={handleCheckUpdates}
                    disabled={checking}
                    activeOpacity={0.88}
                >
                    {checking ? (
                        <ActivityIndicator color={heroPalette.bg} />
                    ) : (
                        <Text style={styles.buttonText}>🔄 Buscar atualização</Text>
                    )}
                </TouchableOpacity>
            </View>

            <View style={styles.card}>
                <Text style={styles.sectionTitle}>Sessão atual</Text>
                <Text style={styles.hint}>Finalize o acesso com logout limpo para parar heartbeat, inatividade e limpeza local da pilha.</Text>
                <TouchableOpacity
                    style={styles.logoutButton}
                    onPress={handleLogout}
                    activeOpacity={0.88}
                >
                    <Text style={styles.logoutButtonText}>🚪 Sair do aplicativo</Text>
                </TouchableOpacity>
            </View>
        </HeroScreen>
    );
}

const styles = StyleSheet.create({
    heroMetaRow: {
        flexDirection: 'row',
        gap: 12,
    },
    heroMetaCard: {
        flex: 1,
        borderRadius: 18,
        paddingHorizontal: 14,
        paddingVertical: 14,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    heroMetaLabel: {
        color: heroPalette.textMuted,
        fontSize: 11,
        fontWeight: '800',
        textTransform: 'uppercase',
        letterSpacing: 0.8,
    },
    heroMetaValue: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
    },
    card: {
        backgroundColor: heroPalette.panel,
        borderRadius: 24,
        padding: 18,
        marginBottom: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    sectionTitle: {
        fontSize: 18,
        fontWeight: '800',
        color: heroPalette.text,
        marginBottom: 8,
    },
    button: {
        backgroundColor: heroPalette.primaryStrong,
        paddingVertical: 14,
        borderRadius: 16,
        alignItems: 'center',
        marginTop: 8,
    },
    buttonDisabled: {
        opacity: 0.7,
    },
    buttonText: {
        color: heroPalette.bg,
        fontSize: 16,
        fontWeight: '800',
    },
    hint: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    logoutButton: {
        backgroundColor: 'rgba(251, 113, 133, 0.14)',
        paddingVertical: 14,
        borderRadius: 16,
        alignItems: 'center',
        marginTop: 10,
        borderWidth: 1,
        borderColor: 'rgba(251, 113, 133, 0.34)',
    },
    logoutButtonText: {
        color: heroPalette.text,
        fontSize: 16,
        fontWeight: '800',
    },
});
