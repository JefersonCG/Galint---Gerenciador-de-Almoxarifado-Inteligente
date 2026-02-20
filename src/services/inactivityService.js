/**
 * Serviço de monitoramento de inatividade
 * Desloga automaticamente o usuário após 6 minutos sem atividade
 */
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ApiService from './api';

const INACTIVITY_TIMEOUT = 6 * 60 * 1000; // 6 minutos em milissegundos
const LAST_ACTIVITY_KEY = '@galint:last_activity';

class InactivityService {
    constructor() {
        this.isMonitoring = false;
        this.inactivityTimer = null;
        this.appStateSubscription = null;
        this.logoutCallback = null;
        this.lastActivity = Date.now();
    }

    /**
     * Inicia o monitoramento de inatividade
     * @param {Function} logoutCallback - Função a ser chamada quando o timeout expirar
     */
    start(logoutCallback) {
        if (this.isMonitoring) {
            console.log('[InactivityService] Já está monitorando');
            return;
        }

        console.log('[InactivityService] Iniciando monitoramento de inatividade (6 minutos)');
        this.logoutCallback = logoutCallback;
        this.isMonitoring = true;
        
        // Registra atividade inicial
        this.recordActivity();

        // Monitora mudanças no estado do app (foreground/background)
        this.appStateSubscription = AppState.addEventListener('change', this._handleAppStateChange);

        // Inicia o timer
        this.resetTimer();
    }

    /**
     * Para o monitoramento
     */
    stop() {
        console.log('[InactivityService] Parando monitoramento');
        this.isMonitoring = false;
        
        if (this.inactivityTimer) {
            clearTimeout(this.inactivityTimer);
            this.inactivityTimer = null;
        }

        if (this.appStateSubscription) {
            this.appStateSubscription.remove();
            this.appStateSubscription = null;
        }

        this.logoutCallback = null;
    }

    /**
     * Registra uma atividade do usuário e reseta o timer
     */
    recordActivity() {
        if (!this.isMonitoring) return;

        this.lastActivity = Date.now();
        AsyncStorage.setItem(LAST_ACTIVITY_KEY, this.lastActivity.toString()).catch(() => {});
        this.resetTimer();
    }

    /**
     * Reseta o timer de inatividade
     */
    resetTimer() {
        if (!this.isMonitoring) return;

        // Limpa o timer anterior
        if (this.inactivityTimer) {
            clearTimeout(this.inactivityTimer);
        }

        // Cria novo timer
        this.inactivityTimer = setTimeout(() => {
            this._handleInactivityTimeout();
        }, INACTIVITY_TIMEOUT);
    }

    /**
     * Verifica se há inatividade ao voltar do background
     */
    async checkInactivityOnResume() {
        if (!this.isMonitoring) return;

        try {
            const storedActivity = await AsyncStorage.getItem(LAST_ACTIVITY_KEY);
            if (storedActivity) {
                const lastActivityTime = parseInt(storedActivity, 10);
                const now = Date.now();
                const elapsed = now - lastActivityTime;

                console.log(`[InactivityService] Tempo inativo: ${Math.floor(elapsed / 1000)}s`);

                if (elapsed >= INACTIVITY_TIMEOUT) {
                    console.log('[InactivityService] Inatividade detectada ao retomar app');
                    this._handleInactivityTimeout();
                    return;
                }
            }
        } catch (error) {
            console.warn('[InactivityService] Erro ao verificar inatividade:', error);
        }

        // Se não expirou, registra atividade e reseta timer
        this.recordActivity();
    }

    /**
     * Handler para mudanças no estado do app
     */
    _handleAppStateChange = (nextAppState) => {
        if (!this.isMonitoring) return;

        console.log(`[InactivityService] AppState mudou para: ${nextAppState}`);

        if (nextAppState === 'active') {
            // App voltou ao foreground - verifica inatividade
            this.checkInactivityOnResume();
        } else if (nextAppState === 'background' || nextAppState === 'inactive') {
            // App foi para background - salva timestamp
            AsyncStorage.setItem(LAST_ACTIVITY_KEY, Date.now().toString()).catch(() => {});
        }
    };

    /**
     * Handler quando o timeout de inatividade é atingido
     */
    _handleInactivityTimeout() {
        console.log('[InactivityService] ⏰ Timeout de inatividade atingido - fazendo logout');
        
        this.stop(); // Para o monitoramento

        if (this.logoutCallback && typeof this.logoutCallback === 'function') {
            this.logoutCallback('inactivity');
        }
    }

    /**
     * Verifica se o serviço está ativo
     */
    isActive() {
        return this.isMonitoring;
    }

    /**
     * Retorna o tempo restante até o logout (em milissegundos)
     */
    getRemainingTime() {
        if (!this.isMonitoring) return 0;
        
        const elapsed = Date.now() - this.lastActivity;
        const remaining = INACTIVITY_TIMEOUT - elapsed;
        return Math.max(0, remaining);
    }
}

export default new InactivityService();
