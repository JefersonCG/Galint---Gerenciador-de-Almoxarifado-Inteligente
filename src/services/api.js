import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Device from 'expo-device';
import * as Application from 'expo-application';
let NetInfoModule = null;
try {
    NetInfoModule = require('@react-native-community/netinfo');
} catch (error) {
    NetInfoModule = null;
}
import {
    initLocalDb,
    clearLocalDb,
    upsertItem,
    upsertItems,
    getItemByCodigo as getLocalItemByCodigo,
    searchItems as searchLocalItems,
} from './localDb';

/**
 * Captura informações do dispositivo Android
 * Gera UUID persistente se não existir
 */
async function getDeviceInfo() {
    try {
        let deviceUuid = await AsyncStorage.getItem('device_uuid');

        const isValidUuid = (value) => {
            return typeof value === 'string'
                && /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/.test(value);
        };
        
        if (!deviceUuid || !isValidUuid(deviceUuid)) {
            const createUuid4 = () => {
                const rnd = (len) => Array.from({ length: len }, () => Math.floor(Math.random() * 16).toString(16)).join('');
                return `${rnd(8)}-${rnd(4)}-4${rnd(3)}-${(8 + Math.floor(Math.random() * 4)).toString(16)}${rnd(3)}-${rnd(12)}`;
            };
            // Gerar UUID válido (fallback) caso androidId não seja UUID
            const androidId = await Application.getAndroidId();
            deviceUuid = androidId && /^[0-9a-fA-F-]{32,36}$/.test(androidId)
                ? androidId
                : createUuid4();
            await AsyncStorage.setItem('device_uuid', deviceUuid);
            console.log('[DeviceInfo] UUID gerado:', deviceUuid);
        }

        const deviceInfo = {
            device_uuid: deviceUuid,
            manufacturer: Device.manufacturer || 'Unknown',
            model: Device.modelName || 'Unknown',
            platform: Device.osName || 'Android',
            os_version: Device.osVersion || 'Unknown',
            apk_version: Application.nativeApplicationVersion || '1.0.0',
            apk_build_number: Application.nativeBuildVersion || '1',
            apk_channel: 'production',
        };

        console.log('[DeviceInfo] Capturado:', deviceInfo.manufacturer, deviceInfo.model);
        return deviceInfo;
    } catch (error) {
        console.warn('[DeviceInfo] Erro ao capturar:', error.message);
        // Retornar dados mínimos se falhar
        return {
            device_uuid: `fallback-${Date.now()}`,
            manufacturer: 'Unknown',
            model: 'Unknown',
            platform: 'Android',
            os_version: 'Unknown',
            apk_version: '1.0.0',
            apk_build_number: '1',
            apk_channel: 'production',
        };
    }
}

// Lista completa do estoque: o servidor pode levar alguns segundos; desistir cedo e pedir de novo
// só acumula trabalho nele. Conferência: um item só, mas com folga se o servidor estiver ocupado.
const FULL_STOCK_TIMEOUT_MS = 60000;
const STOCK_COUNT_TIMEOUT_MS = 20000;

function isTimeoutError(error) {
    if (!error || error.response) return false;
    const code = (error.code || '').toString().toUpperCase();
    const message = (error.message || '').toString().toLowerCase();
    return code === 'ECONNABORTED' || code === 'ETIMEDOUT' || message.includes('timeout');
}

function isNetworkError(error) {
    if (!error) return false;
    if (!error.response) return true;
    const code = (error.code || '').toString().toUpperCase();
    if (['ECONNABORTED', 'ENOTFOUND', 'ECONNREFUSED', 'ETIMEDOUT'].includes(code)) return true;
    const message = (error.message || '').toString().toLowerCase();
    if (message.includes('network error') || message.includes('timeout')) return true;
    return false;
}

function normalizeEstoquePayload(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.data)) return payload.data;
    if (Array.isArray(payload?.items)) return payload.items;
    return [];
}

// Sem modo offline (desde a 2.2.0). Até a 2.1.1, sem rede (ou com o servidor demorando mais de
// 10 s) a operação "entrava na fila" e o app dizia "registrada offline, sincronização pendente".
// A fila gravava numa base que nunca abria: a retirada ou devolução se perdia sem aviso. Agora,
// sem conexão, a operação não é feita e a tela diz isso.
const OFFLINE_NOT_DONE_MESSAGE = 'Sem conexão com o servidor. A operação NÃO foi feita: tente de novo.';
const TIMEOUT_UNKNOWN_MESSAGE = 'O servidor demorou a responder. Confira no histórico se a operação entrou antes de repetir.';

function notDone(error) {
    return {
        success: false,
        offline: true,
        message: error && isTimeoutError(error) ? TIMEOUT_UNKNOWN_MESSAGE : OFFLINE_NOT_DONE_MESSAGE,
    };
}

// Gravações de estoque feitas pelo app: depois de cada uma (deu certo, deu erro ou demorou), a base
// do celular é sincronizada na hora (dbSync.js se inscreve em onStockWrite).
const STOCK_WRITE_PATH = /\/api\/mobile\/(retirar|retirar_multipla|devolver|devolver_material|devolver_multipla_ferramentas|devolver_multipla_materiais|conferencia-estoque\/ajuste|documentos-fiscais|estoque)(\/|$|\?)/;

function isStockWrite(config) {
    const method = String(config?.method || 'get').toLowerCase();
    return method !== 'get' && STOCK_WRITE_PATH.test(String(config?.url || ''));
}

class ApiService {
    constructor() {
        this.baseURL = null;
        this.token = null;
        this.client = null;
        this.localReady = false;
        this.stockWriteListeners = [];
    }

    // Abre a base do celular. Um erro aqui fica no log (até a 2.1.1 ele era engolido).
    async ensureLocalReady() {
        if (this.localReady) return;
        try {
            await initLocalDb();
            this.localReady = true;
        } catch (error) {
            console.warn('[LocalDb] Falha ao abrir a base do celular:', error?.message || error);
        }
    }

    onStockWrite(callback) {
        this.stockWriteListeners.push(callback);
        return () => {
            this.stockWriteListeners = this.stockWriteListeners.filter((entry) => entry !== callback);
        };
    }

    notifyStockWrite(config) {
        if (!isStockWrite(config)) return;
        this.stockWriteListeners.forEach((callback) => {
            try {
                callback();
            } catch (error) {
                // um ouvinte com erro não impede os outros
            }
        });
    }

    async isOnline() {
        try {
            if (!this.client || !this.baseURL) return false;
            if (!NetInfoModule) return true;
            const state = await NetInfoModule.fetch();
            if (!state?.isConnected) return false;
            if (state.isInternetReachable === false) {
                // Allow LAN-only setups (server on local IP without internet).
                return this.isLikelyLocalServer();
            }
            return true;
        } catch (error) {
            return true;
        }
    }

    isLikelyLocalServer() {
        try {
            if (!this.baseURL) return false;
            const url = new URL(this.baseURL);
            const host = (url.hostname || '').toLowerCase();
            if (host === 'localhost' || host.endsWith('.local') || host === '127.0.0.1') return true;
            if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
                const parts = host.split('.').map((part) => Number(part));
                if (parts[0] === 10) return true;
                if (parts[0] === 192 && parts[1] === 168) return true;
                if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
                if (parts[0] === 127) return true;
            }
        } catch (error) {
            // Ignore URL parse errors.
        }
        return false;
    }

    async initialize(serverIP, serverPort) {
        const nextBaseURL = `http://${serverIP}:${serverPort}`;
        const changedServer = this.baseURL && this.baseURL !== nextBaseURL;
        this.baseURL = nextBaseURL;

        if (changedServer) {
            // Limpar token/usuário ao trocar de servidor
            await AsyncStorage.removeItem('token');
            await AsyncStorage.removeItem('user');
            this.token = null;
        }

        this.client = axios.create({
            baseURL: this.baseURL,
            timeout: 10000,
            headers: {
                'Content-Type': 'application/json',
            }
        });

        // Adicionar token em todas as requisições
        this.client.interceptors.request.use(
            async (config) => {
                const token = await AsyncStorage.getItem('token');
                if (token) {
                    config.headers.Authorization = `Bearer ${token}`;
                }
                return config;
            },
            (error) => Promise.reject(error)
        );

        // Toda gravação de estoque dispara a sincronização da base do celular, mesmo com erro ou
        // demora (a gravação pode ter entrado no servidor).
        this.client.interceptors.response.use(
            (response) => {
                this.notifyStockWrite(response?.config);
                return response;
            },
            (error) => {
                this.notifyStockWrite(error?.config);
                // Rota que o servidor ainda não tem (servidor não religado depois de uma atualização):
                // o Flask responde "The requested URL was not found on the server..." em inglês, e o
                // app mostrava esse texto (prints de 23/11/2026 na foto por link e na chave da NF).
                const data = error?.response?.data;
                if (error?.response?.status === 404 && data && typeof data === 'object'
                    && /requested URL was not found/i.test(String(data.message || ''))) {
                    data.message = 'O servidor do GALINT ainda não tem esta função. Religue o GALINT.';
                }
                return Promise.reject(error);
            }
        );

        // Salvar configuração
        await AsyncStorage.setItem('serverIP', serverIP);
        await AsyncStorage.setItem('serverPort', serverPort.toString());
        await this.ensureLocalReady();
        if (changedServer) {
            // A base do outro servidor não vale aqui.
            await clearLocalDb().catch(() => {});
        }
    }

    async loadSavedConfig() {
        const serverIP = await AsyncStorage.getItem('serverIP');
        const serverPort = await AsyncStorage.getItem('serverPort');

        if (serverIP && serverPort) {
            await this.initialize(serverIP, parseInt(serverPort));
            return { serverIP, serverPort: parseInt(serverPort) };
        }
        await this.ensureLocalReady();
        return null;
    }

    async getToken() {
        return AsyncStorage.getItem('token');
    }

    async getNotifySummary() {
        const result = await this.getNotifyInbox(1, 1);
        return {
            success: Boolean(result?.success),
            unread_count: Number(result?.unread_count || 0),
            total: Number(result?.total || 0),
            message: result?.message,
        };
    }

    async getErpOverview() {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get('/api/mobile/erp/overview', {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao carregar central mobile',
            };
        }
    }

    async registerNotifyPushToken(pushToken, provider = 'expo') {
        try {
            if (!this.client || !this.baseURL) {
                throw new Error('Servidor não configurado');
            }

            const authToken = await AsyncStorage.getItem('token');
            if (!authToken) {
                throw new Error('Token não encontrado');
            }

            const normalizedToken = String(pushToken || '').trim();
            if (!normalizedToken) {
                throw new Error('Push token ausente');
            }

            const deviceInfo = await getDeviceInfo();
            const registrationFingerprint = JSON.stringify({
                baseURL: this.baseURL,
                device_uuid: deviceInfo.device_uuid,
                provider,
                token: normalizedToken,
            });
            const previousFingerprint = await AsyncStorage.getItem('notify_push_registration');
            if (previousFingerprint === registrationFingerprint) {
                return { success: true, skipped: true, provider };
            }

            const response = await this.client.post(
                '/api/mobile/notifications/push/register',
                {
                    device_uuid: deviceInfo.device_uuid,
                    token: normalizedToken,
                    provider,
                },
                {
                    headers: {
                        Authorization: `Bearer ${authToken}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            if (response.data?.success) {
                await AsyncStorage.setItem('notify_push_registration', registrationFingerprint);
            }
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || error.message || 'Erro ao registrar push token',
            };
        }
    }

    async getNotifyInbox(page = 1, perPage = 20) {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get('/api/mobile/notifications/inbox', {
                params: { page, per_page: perPage },
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao carregar notificações',
                items: [],
            };
        }
    }

    async markNotifyRead(messageId) {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.post(
                `/api/mobile/notifications/inbox/${messageId}/read`,
                {},
                {
                    headers: {
                        Authorization: `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao marcar notificação como lida',
            };
        }
    }

    // Relatórios (2.2.5, 23/11/2026): uma rota só no servidor, /api/mobile/relatorios/<dia|mes|consumo>.
    // formato=resumo devolve o que a tela mostra; pdf e xlsx devolvem o arquivo que vai no WhatsApp
    // (baixado pelo módulo nativo GalintShare, com o token).
    async getRelatorio(tipo, params = {}) {
        try {
            const response = await this.client.get(`/api/mobile/relatorios/${tipo}`, { params: { ...params, formato: 'resumo' } });
            return response.data;
        } catch (error) {
            if (!error.response) {
                return { success: false, message: 'Sem conexão com o servidor.' };
            }
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Não foi possível carregar o relatório.',
            };
        }
    }

    getRelatorioUrl(tipo, params = {}) {
        if (!this.baseURL) {
            throw new Error('Servidor não configurado');
        }
        const query = Object.entries(params)
            .filter(([, value]) => value !== undefined && value !== null && value !== '')
            .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
            .join('&');
        return `${this.baseURL}/api/mobile/relatorios/${tipo}${query ? `?${query}` : ''}`;
    }

    async testConnection() {
        try {
            if (!this.client) {
                return { success: false, message: 'Servidor não configurado' };
            }
            const response = await this.client.get('/api/mobile/health', { timeout: 5000 });
            return { success: true, message: 'Conexão OK!' };
        } catch (error) {
            const url = this.baseURL ? `${this.baseURL}/api/mobile/health` : null;
            if (error.code === 'ECONNABORTED') {
                return { success: false, message: `Timeout: Servidor não respondeu${url ? ` (${url})` : ''}` };
            }
            if (error.code === 'ECONNREFUSED') {
                return { success: false, message: `Servidor recusou conexão${url ? ` (${url})` : ''}` };
            }

            // No React Native/Android, axios costuma retornar apenas "Network Error".
            // Se o endpoint abre no navegador do celular mas o app falha, é bem provável ser
            // bloqueio de HTTP (cleartext) em APK/produção.
            if ((error?.message || '').toLowerCase() === 'network error') {
                return {
                    success: false,
                    message: [
                        'Network Error',
                        url ? `URL: ${url}` : null,
                        'Se essa URL abrir no navegador do celular, mas aqui falhar, provavelmente é bloqueio de HTTP (cleartext) no Android.',
                        'Solução: gere/reinstale o APK com android.usesCleartextTraffic=true (Expo) ou use HTTPS no servidor.'
                    ].filter(Boolean).join('\n')
                };
            }

            return {
                success: false,
                message: error.response?.data?.message || error.message || (url ? `Erro ao conectar (${url})` : 'Erro ao conectar')
            };
        }
    }

    async login(username, password) {
        try {
            // Capturar informações do dispositivo
            const deviceInfo = await getDeviceInfo();

            const response = await this.client.post('/api/mobile/login', {
                matricula: username,
                senha: password,
                ...deviceInfo, // Adicionar device info ao payload
            });

            // Compatível com retorno antigo e com o retorno do guia (data.token/data.user)
            const payload = response.data || {};
            const token = payload?.data?.token || payload?.token;
            const user = payload?.data?.user || payload?.user;
            const success = payload?.success !== false;

            if (!success || !token || !user) {
                return { success: false, message: payload?.message || payload?.error || 'Erro ao fazer login' };
            }

            // Normalizar is_admin para boolean (corrige problema de cadastro)
            if (user) {
                console.log('[Login] User original:', JSON.stringify(user, null, 2));
                user.is_admin = user.is_admin === true || 
                                user.is_admin === 1 || 
                                user.is_admin === '1' || 
                                String(user.is_admin || '').trim() === '1';
                console.log('[Login] is_admin normalizado:', user.is_admin);
            }

            await AsyncStorage.setItem('token', token);
            await AsyncStorage.setItem('user', JSON.stringify(user));

            this.token = token;
            console.log('[Login] Device registrado:', deviceInfo.device_uuid);
            console.log('[Login] Token salvo:', token ? 'presente' : 'ausente');
            return { success: true, user };
        } catch (error) {
            const status = error.response?.status;
            const payload = error.response?.data;

            // A API do GALINT normalmente retorna { success: false, message: "..." } em erros.
            let message = payload?.message || payload?.error || error.message || 'Erro ao fazer login';

            // Caso especial: login por nome pode ser ambíguo.
            if (payload?.ambiguous && Array.isArray(payload?.matches) && payload.matches.length > 0) {
                const matches = payload.matches
                    .slice(0, 6)
                    .map((m) => `${m?.matricula || 'N/D'} - ${m?.nome || 'N/D'}`)
                    .join('\n');
                message = `${message}\n\nSugestões (use a matrícula):\n${matches}`;
            }

            // Ajuda diagnóstico sem expor dados sensíveis.
            if (status) {
                message = `${message} (HTTP ${status})`;
            }

            return { success: false, message };
        }
    }

    async registrarRetirada(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            if (!online) {
                return notDone();
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado. Faça login novamente.');
            }

            const response = await this.client.post(
                '/api/mobile/retirar',
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            return response.data;
        } catch (error) {
            console.error('Erro ao registrar retirada:', error);

            if (error.response?.status === 401) {
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            if (isNetworkError(error)) {
                return notDone(error);
            }

            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao registrar retirada',
            };
        }
    }

    async registrarDevolucaoFerramenta(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            if (!online) {
                return notDone();
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado. Faça login novamente.');
            }

            const response = await this.client.post(
                '/api/mobile/devolver',
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            return response.data;
        } catch (error) {
            console.error('Erro ao registrar devolução:', error);

            if (error.response?.status === 401) {
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            if (isNetworkError(error)) {
                return notDone(error);
            }

            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao registrar devolução',
            };
        }
    }

    /**
     * Busca ferramentas ativas de um funcionário específico
     * @param {string} matricula - Matrícula do funcionário
     * @returns {Promise<{success: boolean, data?: Array, message?: string}>}
     */
    async getFerramentasAtivas(matricula) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            
            if (!online) {
                return {
                    success: false,
                    offline: true,
                    message: 'Função requer conexão online'
                };
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get(
                `/api/mobile/ferramentas_ativas/${matricula}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );

            return response.data;
        } catch (error) {
            console.error('[getFerramentasAtivas] Erro:', error);
            return {
                success: false,
                message: error.response?.data?.message || 'Erro ao buscar ferramentas ativas'
            };
        }
    }

    async getDailyCustodyFeed() {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();

            if (!online) {
                return {
                    success: false,
                    offline: true,
                    message: 'Custodia diaria requer conexao online',
                };
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get('/api/mobile/custodia-diaria', {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            return response.data;
        } catch (error) {
            console.error('[getDailyCustodyFeed] Erro:', error);
            return {
                success: false,
                status: error.response?.status,
                message: error.response?.data?.message || 'Erro ao carregar custodia diaria',
            };
        }
    }

    async returnDailyCustodyTool(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();

            if (!online) {
                return {
                    success: false,
                    offline: true,
                    message: 'Baixa da custodia diaria requer conexao online',
                };
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const payload = {
                codigo: data?.codigo,
                quantidade: data?.quantidade || 1,
                saida_id: data?.saida_id || null,
                matricula_devolvedor: data?.matricula,
            };

            const response = await this.client.post('/api/mobile/devolver', payload, {
                headers: {
                    Authorization: `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });

            return response.data;
        } catch (error) {
            console.error('[returnDailyCustodyTool] Erro:', error);
            return {
                success: false,
                status: error.response?.status,
                message: error.response?.data?.message || 'Erro ao dar baixa na custodia diaria',
            };
        }
    }

    /**
     * Registra devolução múltipla de ferramentas
     * @param {Object} data - { itens: [{ codigo, quantidade }], matricula, observacao }
     * @returns {Promise<{success: boolean, message?: string, resultados?: Array}>}
     */
    async registrarDevolucaoMultiplaFerramentas(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            
            if (!online) {
                // TODO: Implementar fila offline para devolução múltipla
                return {
                    success: false,
                    offline: true,
                    message: 'Devolução múltipla requer conexão online'
                };
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.post(
                '/api/mobile/devolver_multipla_ferramentas',
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            return response.data;
        } catch (error) {
            console.error('[registrarDevolucaoMultiplaFerramentas] Erro:', error);
            return {
                success: false,
                message: error.response?.data?.message || 'Erro ao registrar devoluções'
            };
        }
    }

    /**
     * Registra devolução múltipla de materiais
     * @param {Object} data - { itens: [{ codigo, quantidade }], matricula, observacao }
     * @returns {Promise<{success: boolean, message?: string, resultados?: Array}>}
     */
    async registrarDevolucaoMultiplaMateriais(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            
            if (!online) {
                // TODO: Implementar fila offline para devolução múltipla
                return {
                    success: false,
                    offline: true,
                    message: 'Devolução múltipla requer conexão online'
                };
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.post(
                '/api/mobile/devolver_multipla_materiais',
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            return response.data;
        } catch (error) {
            console.error('[registrarDevolucaoMultiplaMateriais] Erro:', error);
            return {
                success: false,
                message: error.response?.data?.message || 'Erro ao registrar devoluções'
            };
        }
    }

    /**
     * Busca informações do último responsável que retirou o item
     * @param {string} codigo - Código do item
     * @returns {Promise<Object|null>} Dados do último responsável ou null se não houver retirada
     */
    // Última NF em que o item entrou (número e data) para o cartão do "Lançar entrada" (2.2.9,
    // 24/11/2026). Sem conexão ou servidor sem a rota (antes de religar): null, e o cartão não mostra nada.
    async getUltimaEntrada(codigo) {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) return null;
            const response = await this.client.get(
                `/api/mobile/itens/${encodeURIComponent(String(codigo || ''))}/ultima_entrada`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            return response.data?.data || null;
        } catch (error) {
            return null;
        }
    }

    async getUltimaRetirada(codigo) {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado. Faça login novamente.');
            }

            const response = await this.client.get(
                `/api/mobile/itens/${codigo}/ultima_retirada`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );

            return response.data?.data || null;
        } catch (error) {
            console.error('Erro ao buscar última retirada:', error);
            
            if (error.response?.status === 401) {
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            // Se não encontrar ou erro de rede, retornar null
            return null;
        }
    }


    async devolverMaterial(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            if (!online) {
                return notDone();
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado. Faça login novamente.');
            }

            const response = await this.client.post(
                '/api/mobile/devolver_material',
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                }
            );

            return response.data;
        } catch (error) {
            console.error('Erro ao devolver material:', error);

            if (error.response?.status === 401) {
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            if (isNetworkError(error)) {
                return notDone(error);
            }

            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao devolver material',
            };
        }
    }

    // Devolve o item ou null. Procura primeiro na base do celular (sempre sincronizada com o
    // servidor), que responde na hora; só pergunta ao servidor quando o código não está nela.
    // lastItemLookupFailure = 'network' quando o servidor não respondeu e o item não está na
    // base: a tela não deve dizer "Item não encontrado" se o problema foi a conexão.
    async buscarItemPorCodigo(codigo) {
        this.lastItemLookupFailure = null;
        const code = String(codigo || '').trim();
        if (!code) return null;
        await this.ensureLocalReady();
        const local = await getLocalItemByCodigo(code).catch(() => null);
        if (local) return local;
        try {
            const online = await this.isOnline();
            if (!online) {
                this.lastItemLookupFailure = 'network';
                return null;
            }
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }
            const response = await this.client.get(
                `/api/mobile/itens/${encodeURIComponent(code)}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );
            const item = response.data?.data || null;
            if (item) {
                await upsertItem(item).catch(() => {});
            }
            return item;
        } catch (error) {
            console.error('Erro ao buscar item:', error);
            if (isNetworkError(error)) {
                this.lastItemLookupFailure = 'network';
            }
            return null;
        }
    }

    async getUsuarios() {
        try {
            const online = await this.isOnline();
            if (!online || !this.client) {
                return [];
            }
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get(
                '/api/mobile/usuarios',
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );

            return response.data?.data || [];
        } catch (error) {
            console.error('Erro ao buscar usuários:', error);
            return [];
        }
    }

    async logout() {
        try {
            // Notificar backend sobre logout
            const deviceUuid = await AsyncStorage.getItem('device_uuid');
            if (deviceUuid && this.client) {
                try {
                    await this.client.post('/logout', { device_uuid: deviceUuid });
                    console.log('[Logout] Backend notificado');
                } catch (error) {
                    console.warn('[Logout] Falha ao notificar backend:', error.message);
                }
            }
        } catch (error) {
            console.warn('[Logout] Erro ao processar logout:', error.message);
        } finally {
            // Limpar storage sempre, independente de erro
            await AsyncStorage.removeItem('token');
            await AsyncStorage.removeItem('user');
            this.token = null;
        }
    }

    async getEstoque(search = '') {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            if (!online) {
                const items = await searchLocalItems(search);
                return { success: true, data: items, items, offline: true };
            }
            // Lista completa: espera até 60 s em vez de desistir em 10 s e pedir de novo.
            const response = await this.client.get('/api/mobile/estoque', {
                params: { search },
                timeout: FULL_STOCK_TIMEOUT_MS,
            });
            const items = normalizeEstoquePayload(response.data);
            await upsertItems(items);
            return { success: true, data: items, items };
        } catch (error) {
            if (isNetworkError(error)) {
                const items = await searchLocalItems(search);
                return { success: true, data: items, items, offline: true };
            }
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao buscar estoque'
            };
        }
    }

    async getEstoqueResumo() {
        try {
            const online = await this.isOnline();
            if (!online) {
                return { success: false, offline: true };
            }
            const response = await this.client.get('/api/mobile/estoque/resumo');
            return response.data?.success
                ? { success: true, data: response.data.data }
                : { success: false, message: response.data?.message || 'Erro ao obter resumo' };
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao obter resumo'
            };
        }
    }

    async getDocumentosFiscaisConfig() {
        try {
            const online = await this.isOnline();
            if (!online) {
                return {
                    success: false,
                    offline: true,
                    message: 'Documentos Fiscais requer conexao online'
                };
            }

            const response = await this.client.get('/api/mobile/documentos-fiscais/config');
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao carregar configuracao documental',
            };
        }
    }

    async searchDocumentosFiscaisItems(search, limit = 12) {
        try {
            const term = String(search || '').trim();
            if (term.length < 2) {
                return { success: true, data: [] };
            }

            const online = await this.isOnline();
            if (!online) {
                return {
                    success: false,
                    offline: true,
                    data: [],
                    message: 'Busca documental requer conexao online'
                };
            }

            const response = await this.client.get('/api/mobile/documentos-fiscais/itens', {
                params: { search: term, limit }
            });
            return response.data;
        } catch (error) {
            return {
                success: false,
                data: [],
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao buscar itens para documento',
            };
        }
    }

    async registrarDocumentoFiscal(payload) {
        try {
            const online = await this.isOnline();
            if (!online) {
                return {
                    success: false,
                    offline: true,
                    message: 'Lancamento documental requer conexao online'
                };
            }

            const response = await this.client.post('/api/mobile/documentos-fiscais', payload, {
                headers: {
                    'Content-Type': 'application/json',
                },
                timeout: 30000,
            });
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao registrar documento fiscal',
                warnings: error.response?.data?.warnings || [],
            };
        }
    }

    /**
     * Pre-load completo do estoque para cache SQLite
     * Deve ser chamado após login bem-sucedido
     * @returns {Promise<{success: boolean, totalItens?: number, message?: string}>}
     */
    async preloadEstoqueCompleto() {
        try {
            console.log('[PreLoad] Iniciando carregamento completo do estoque...');
            const online = await this.isOnline();
            if (!online) {
                console.log('[PreLoad] Offline - pulando pre-load');
                return { success: false, offline: true };
            }

            // Buscar estoque completo (sem filtro)
            const response = await this.client.get('/api/mobile/estoque', {
                params: { search: '' },
                timeout: FULL_STOCK_TIMEOUT_MS,
            });

            const items = normalizeEstoquePayload(response.data);
            console.log(`[PreLoad] Recebeu ${items.length} itens do servidor`);

            // Salvar no SQLite
            if (items.length > 0) {
                await upsertItems(items);
                console.log(`[PreLoad] ${items.length} itens salvos no cache SQLite`);
            }

            // Salvar snapshot timestamp
            await AsyncStorage.setItem('last_preload_snapshot', JSON.stringify({
                timestamp: Date.now(),
                totalItens: items.length
            }));

            return { success: true, totalItens: items.length };
        } catch (error) {
            console.error('[PreLoad] Erro:', error.message);
            if (isNetworkError(error)) {
                return { success: false, offline: true };
            }
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao carregar estoque completo'
            };
        }
    }

    async getItemByBarcode(barcode) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            if (!online) {
                const item = await getLocalItemByCodigo(barcode);
                if (item) {
                    return { success: true, data: item, offline: true };
                }
                return { success: false, notFound: true, offline: true };
            }
            const response = await this.client.get(`/api/mobile/estoque/barcode/${encodeURIComponent(String(barcode || '').trim())}`);
            const item = response.data;
            if (item) {
                await upsertItem(item);
            }
            return { success: true, data: response.data };
        } catch (error) {
            if (isNetworkError(error)) {
                const item = await getLocalItemByCodigo(barcode);
                if (item) {
                    return { success: true, data: item, offline: true };
                }
                return { success: false, notFound: true, offline: true };
            }
            if (error.response?.status === 404) {
                return { success: false, notFound: true };
            }
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao buscar item'
            };
        }
    }

    // Conferência física (mesma contagem do site): só online, porque grava o saldo na hora.
    async buscarItemContagem(codigo) {
        const code = String(codigo || '').trim();
        if (!code) {
            return { success: false, message: 'Leia ou digite o código de barras.' };
        }
        const online = await this.isOnline();
        if (!online || !this.client) {
            return { success: false, offline: true, message: 'Sem conexão com o servidor. A conferência precisa estar online.' };
        }
        try {
            const token = await AsyncStorage.getItem('token');
            const response = await this.client.get('/api/mobile/conferencia-estoque/item', {
                params: { codigo: code },
                headers: token ? { Authorization: `Bearer ${token}` } : {},
                timeout: STOCK_COUNT_TIMEOUT_MS,
            });
            return { success: true, item: response.data?.item || null };
        } catch (error) {
            if (isTimeoutError(error)) {
                return { success: false, offline: true, message: 'O servidor demorou a responder. Leia o código de novo.' };
            }
            if (isNetworkError(error)) {
                return { success: false, offline: true, message: 'Sem conexão com o servidor. A conferência precisa estar online.' };
            }
            const status = error.response?.status;
            const message = error.response?.data?.message || error.response?.data?.error;
            if (status === 404) {
                return { success: false, notFound: true, message: message || 'Item não encontrado.' };
            }
            if (status === 401 || status === 403) {
                return { success: false, authError: true, message: message || 'Sessão expirada. Faça login novamente.' };
            }
            return { success: false, message: message || 'Falha ao buscar o item.' };
        }
    }

    async salvarContagem(payload) {
        if (!this.client) {
            return { success: false, offline: true, message: 'Sem conexão com o servidor.' };
        }
        try {
            const token = await AsyncStorage.getItem('token');
            const response = await this.client.post('/api/mobile/conferencia-estoque/ajuste', payload, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
                timeout: STOCK_COUNT_TIMEOUT_MS,
            });
            return { success: true, ...(response.data || {}) };
        } catch (error) {
            if (isTimeoutError(error)) {
                // A gravação pode ter chegado ao servidor: quem conta confere o saldo ao ler de novo.
                return { success: false, offline: true, message: 'O servidor demorou a responder. Leia o código de novo para ver se a contagem foi gravada.' };
            }
            if (isNetworkError(error)) {
                return { success: false, offline: true, message: 'Sem conexão com o servidor. A contagem não foi salva.' };
            }
            const message = error.response?.data?.message || error.response?.data?.error;
            return { success: false, message: message || 'Não foi possível salvar a contagem.' };
        }
    }

    async cadastrarItem(itemData) {
        return {
            success: false,
            disabled: true,
            message: 'Cadastro de itens foi removido do app mobile. Utilize a interface web de Documentos Fiscais.'
        };
    }

    async cadastrarItensMultiplos({ itens, matricula }) {
        return {
            success: false,
            disabled: true,
            message: 'Cadastro em lote foi removido do app mobile. Utilize a interface web de Documentos Fiscais.'
        };
    }

    async atualizarItem(itemId, itemData) {
        return {
            success: false,
            disabled: true,
            message: 'Edição de itens foi removida do app mobile. Utilize a interface web administrativa.'
        };
    }

    async ajustarSaldo(itemId, saldo) {
        return {
            success: false,
            disabled: true,
            message: 'Ajuste de saldo foi removido do app mobile. Utilize Documentos Fiscais para entradas e os fluxos operacionais para movimentações.'
        };
    }

    async registrarRetiradaMultipla(data) {
        try {
            await this.ensureLocalReady();
            const online = await this.isOnline();
            if (!online) {
                return { ...notDone(), resultados: [] };
            }
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado. Faça login novamente.');
            }

            const response = await this.client.post(
                '/api/mobile/retirar_multipla',
                data,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                    timeout: 30000, // 30 segundos para múltiplos itens
                }
            );

            return response.data;
        } catch (error) {
            console.error('Erro ao registrar retirada múltipla:', error);

            if (error.response?.status === 401) {
                throw new Error('Sessão expirada. Faça login novamente.');
            }

            if (isNetworkError(error)) {
                return { ...notDone(error), resultados: [] };
            }

            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao registrar retiradas',
                resultados: error.response?.data?.resultados || [],
            };
        }
    }

    async excluirItem(itemId) {
        return {
            success: false,
            disabled: true,
            message: 'Exclusão de itens foi removida do app mobile. Utilize a interface web administrativa.'
        };
    }

    // "O que mudou?" no estoque desde o cursor (dbSync.js). Sem cursor, a lista inteira.
    async getEstoqueMudancas(cursor = null) {
        if (!this.client) {
            return { success: false, offline: true, message: 'Servidor não configurado.' };
        }
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                return { success: false, message: 'Sessão não iniciada.' };
            }
            const response = await this.client.get('/api/mobile/estoque/mudancas', {
                params: cursor ? { cursor } : {},
                headers: { Authorization: `Bearer ${token}` },
                timeout: cursor ? 20000 : FULL_STOCK_TIMEOUT_MS,
            });
            return response.data?.success ? response.data : { success: false, message: response.data?.message || 'Resposta inválida.' };
        } catch (error) {
            if (isNetworkError(error)) {
                return { success: false, offline: true, message: 'Sem conexão com o servidor.' };
            }
            return {
                success: false,
                status: error.response?.status,
                message: error.response?.data?.message || 'Falha ao sincronizar a base.',
            };
        }
    }

    // Chave de acesso lida pela câmera → número da NF, série, CNPJ e fornecedor (lançar entrada, 2.2.3).
    async lerChaveAcesso(chave) {
        if (!this.client) {
            return { success: false, message: 'Servidor não configurado.' };
        }
        try {
            const response = await this.client.get('/api/mobile/chave-acesso', { params: { chave }, timeout: 15000 });
            return response.data;
        } catch (error) {
            if (isNetworkError(error)) {
                return { success: false, offline: true, message: 'Sem conexão com o servidor.' };
            }
            return { success: false, message: error.response?.data?.message || 'Não foi possível ler a chave.' };
        }
    }

    // Atualização sozinha (2.2.4): o GALINT publica o APK em instance/apks e responde se há versão nova.
    async verificarAtualizacao(versionCode) {
        if (!this.client) return { success: false };
        try {
            const response = await this.client.get('/api/mobile/app/atualizacao', { params: { code: versionCode }, timeout: 8000 });
            return response.data || { success: false };
        } catch (error) {
            return { success: false };
        }
    }

    // Foto do item pelo link copiado da busca de imagens (2.2.4, só administradores).
    async salvarFotoItemPorLink(codigo, url) {
        if (!this.client) return { success: false, message: 'Servidor não configurado.' };
        try {
            const response = await this.client.post(
                `/api/mobile/itens/${encodeURIComponent(String(codigo || '').trim())}/foto/url`,
                { url },
                { timeout: 30000 }
            );
            return response.data;
        } catch (error) {
            if (isNetworkError(error)) {
                return { success: false, offline: true, message: 'Sem conexão com o servidor.' };
            }
            return { success: false, message: error.response?.data?.message || 'Não foi possível salvar a foto.' };
        }
    }

    async markAllNotifyRead() {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }
            const response = await this.client.post('/api/mobile/notifications/inbox/read-all', {}, {
                headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            });
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.message || 'Não foi possível marcar os avisos como lidos.',
            };
        }
    }

    // Cores da Aparência (Configurações do site). Sem login: a abertura e o login também usam.
    async getTema() {
        if (!this.client) return { success: false };
        try {
            const response = await this.client.get('/api/mobile/tema', { timeout: 2500 });
            return response.data?.success ? { success: true, tema: response.data.tema } : { success: false };
        } catch (error) {
            return { success: false };
        }
    }
}

export default new ApiService();
