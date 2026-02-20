/**
 * Sistema de verificação automática de atualizações OTA
 * Polling contínuo que verifica atualizações em background
 */
import * as Updates from 'expo-updates';
import { Alert, AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const UPDATE_CHECK_INTERVAL = 30000; // 30 segundos
const STORAGE_KEY = '@galint_last_update_check';

class UpdateChecker {
    constructor() {
        this.intervalId = null;
        this.appStateSubscription = null;
        this.isChecking = false;
        this.lastCheckTime = 0;
    }

    /**
     * Inicia o polling automático de atualizações
     */
    start() {
        console.log('[UpdateChecker] Iniciando verificação automática de atualizações...');
        
        // Verifica imediatamente ao iniciar
        this.checkForUpdates(true);
        
        // Inicia intervalo de verificação
        this.intervalId = setInterval(() => {
            this.checkForUpdates(false);
        }, UPDATE_CHECK_INTERVAL);

        // Monitora mudanças no estado do app (foreground/background)
        this.appStateSubscription = AppState.addEventListener('change', (nextAppState) => {
            if (nextAppState === 'active') {
                console.log('[UpdateChecker] App voltou para foreground, verificando atualizações...');
                this.checkForUpdates(false);
            }
        });

        console.log('[UpdateChecker] Sistema de auto-update ativo! Verificando a cada 30s.');
    }

    /**
     * Para o polling automático
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('[UpdateChecker] Polling de atualizações parado.');
        }

        if (this.appStateSubscription) {
            this.appStateSubscription.remove();
            this.appStateSubscription = null;
        }
    }

    /**
     * Verifica se há atualizações disponíveis
     * @param {boolean} showNoUpdateMessage - Se deve mostrar mensagem quando não há atualização
     */
    async checkForUpdates(showNoUpdateMessage = false) {
        // Evita verificações simultâneas
        if (this.isChecking) {
            console.log('[UpdateChecker] Verificação já em andamento, pulando...');
            return;
        }

        // Throttle: evita verificações muito frequentes (min 10s entre checks)
        const now = Date.now();
        if (now - this.lastCheckTime < 10000) {
            return;
        }

        try {
            this.isChecking = true;
            this.lastCheckTime = now;

            // Salva timestamp da última verificação
            await AsyncStorage.setItem(STORAGE_KEY, now.toString());

            // Verifica se estamos em desenvolvimento
            if (__DEV__) {
                console.log('[UpdateChecker] Modo desenvolvimento - verificações OTA desabilitadas');
                return;
            }

            console.log('[UpdateChecker] 🔍 Verificando atualizações OTA...');

            const update = await Updates.checkForUpdateAsync();

            if (update.isAvailable) {
                console.log('[UpdateChecker] ✅ Atualização disponível! Baixando...');
                
                // Baixa a atualização
                await Updates.fetchUpdateAsync();
                
                console.log('[UpdateChecker] ✅ Atualização baixada com sucesso!');

                // Mostra alerta para o usuário
                Alert.alert(
                    '🎉 Atualização Disponível!',
                    'Uma nova versão do app foi baixada. Deseja reiniciar agora para aplicar?',
                    [
                        {
                            text: 'Depois',
                            style: 'cancel',
                            onPress: () => {
                                console.log('[UpdateChecker] Usuário escolheu aplicar depois');
                            }
                        },
                        {
                            text: 'Reiniciar Agora',
                            onPress: async () => {
                                console.log('[UpdateChecker] Aplicando atualização...');
                                await Updates.reloadAsync();
                            }
                        }
                    ],
                    { cancelable: false }
                );
            } else {
                console.log('[UpdateChecker] ⚪ Nenhuma atualização disponível');
                
                if (showNoUpdateMessage) {
                    // Opcional: mostrar toast/mensagem silenciosa
                    // Toast.show('App está atualizado!', { duration: Toast.durations.SHORT });
                }
            }
        } catch (error) {
            console.error('[UpdateChecker] ❌ Erro ao verificar atualizações:', error);
            // Não mostra erro ao usuário para não incomodar
        } finally {
            this.isChecking = false;
        }
    }

    /**
     * Força uma verificação manual de atualizações
     */
    async forceCheck() {
        console.log('[UpdateChecker] Verificação manual forçada pelo usuário');
        await this.checkForUpdates(true);
    }

    /**
     * Retorna informações sobre a última verificação
     */
    async getLastCheckInfo() {
        try {
            const timestamp = await AsyncStorage.getItem(STORAGE_KEY);
            if (timestamp) {
                const date = new Date(parseInt(timestamp, 10));
                return {
                    timestamp: parseInt(timestamp, 10),
                    date: date,
                    formatted: date.toLocaleString('pt-BR')
                };
            }
        } catch (error) {
            console.error('[UpdateChecker] Erro ao buscar última verificação:', error);
        }
        return null;
    }
}

// Exporta instância singleton
export default new UpdateChecker();
