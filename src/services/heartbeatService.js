import AsyncStorage from '@react-native-async-storage/async-storage';
import ApiService from './api';

/**
 * HeartbeatService - Envia sinais periódicos ao backend para indicar que o device está online
 * Executa POST /api/mobile/heartbeat a cada 3 minutos
 */
class HeartbeatService {
    constructor() {
        this.intervalId = null;
        this.HEARTBEAT_INTERVAL = 3 * 60 * 1000; // 3 minutos
        this.isRunning = false;
    }

    /**
     * Inicia o serviço de heartbeat
     * Envia heartbeat inicial e configura polling periódico
     */
    async start() {
        if (this.isRunning) {
            console.log('[Heartbeat] Já está em execução');
            return;
        }

        console.log('[Heartbeat] Iniciando serviço...');
        this.isRunning = true;

        // Enviar heartbeat inicial
        await this.sendHeartbeat();

        // Iniciar polling periódico
        this.intervalId = setInterval(async () => {
            await this.sendHeartbeat();
        }, this.HEARTBEAT_INTERVAL);

        console.log(`[Heartbeat] Service ativo (intervalo: ${this.HEARTBEAT_INTERVAL / 60000} min)`);
    }

    /**
     * Para o serviço de heartbeat
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            this.isRunning = false;
            console.log('[Heartbeat] Service parado');
        }
    }

    /**
     * Envia heartbeat para o backend
     * Se falhar, apenas loga o erro (não bloqueia o app)
     */
    async sendHeartbeat() {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                console.log('[Heartbeat] Sem token, não enviando');
                return;
            }

            const deviceUuid = await AsyncStorage.getItem('device_uuid');
            if (!deviceUuid) {
                console.log('[Heartbeat] Sem device_uuid, não enviando');
                return;
            }

            if (!ApiService.client) {
                console.log('[Heartbeat] API não inicializada');
                return;
            }

            const response = await ApiService.client.post('/heartbeat', {
                device_uuid: deviceUuid,
            });

            console.log('[Heartbeat] Enviado com sucesso', new Date().toLocaleTimeString());
        } catch (error) {
            // Não mostrar erro para usuário - heartbeat é transparente
            console.warn('[Heartbeat] Falha ao enviar:', error.message);
        }
    }

    /**
     * Retorna o status atual do serviço
     */
    getStatus() {
        return {
            isRunning: this.isRunning,
            intervalMinutes: this.HEARTBEAT_INTERVAL / 60000,
        };
    }
}

// Exportar instância singleton
export default new HeartbeatService();
