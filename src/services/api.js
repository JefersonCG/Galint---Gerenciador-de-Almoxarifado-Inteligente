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
    initOfflineDb,
    upsertItem,
    upsertItems,
    getItemByCodigo as getOfflineItemByCodigo,
    searchItems as searchOfflineItems,
    addPendingOp,
    listPendingOps,
    markPendingOpSynced,
    markPendingOpFailed,
    incrementPendingRetry,
    adjustLocalSaldo,
} from './offlineDb';

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

async function queueRetiradaOffline(data) {
    await addPendingOp('retirada', data);
    const codigo = String(data?.codigo || data?.item_id || '').trim();
    const quantidadeNum = Number.isFinite(Number(data?.quantidade))
        ? Number(Number(data.quantidade).toFixed(6))
        : 0;
    if (codigo && quantidadeNum > 0) {
        await adjustLocalSaldo(codigo, -quantidadeNum);
    }
}

async function queueDevolucaoFerramentaOffline(data) {
    await addPendingOp('devolucao_ferramenta', data);
    const codigo = String(data?.codigo || '').trim();
    const quantidadeNum = Number.isFinite(Number(data?.quantidade))
        ? Number(Number(data.quantidade).toFixed(6))
        : 0;
    if (codigo && quantidadeNum > 0) {
        await adjustLocalSaldo(codigo, quantidadeNum);
    }
}

async function queueDevolucaoMaterialOffline(data) {
    await addPendingOp('devolucao_material', data);
    const codigo = String(data?.codigo || '').trim();
    const quantidadeNum = Number.isFinite(Number(data?.quantidade))
        ? Number(Number(data.quantidade).toFixed(6))
        : 0;
    if (codigo && quantidadeNum > 0) {
        await adjustLocalSaldo(codigo, quantidadeNum);
    }
}

async function queueCadastroItemOffline(itemData) {
    await addPendingOp('cadastro_item', itemData);
    await upsertItem({
        ...itemData,
        quantidade: itemData?.quantidade ?? 0,
    });
}

async function queueRetiradaMultiplaOffline(data) {
    await addPendingOp('retirada_multipla', data);
    const itens = Array.isArray(data?.itens) ? data.itens : [];
    for (const entry of itens) {
        const codigo = String(entry?.codigo || '').trim();
        const quantidadeNum = Number.isFinite(Number(entry?.quantidade))
            ? Number(Number(entry.quantidade).toFixed(6))
            : 0;
        if (codigo && quantidadeNum > 0) {
            await adjustLocalSaldo(codigo, -quantidadeNum);
        }
    }
    return itens.map((entry) => ({
        success: true,
        codigo: entry?.codigo,
        message: 'Registrado offline',
    }));
}

class ApiService {
    constructor() {
        this.baseURL = null;
        this.token = null;
        this.client = null;
        this.offlineReady = false;
        this.offlineForced = false;
    }

    async setOfflineMode(isOffline) {
        this.offlineForced = Boolean(isOffline);
        try {
            await AsyncStorage.setItem('offline_mode', this.offlineForced ? 'true' : 'false');
        } catch (error) {
            // silencioso
        }
    }

    async loadOfflineMode() {
        try {
            const value = await AsyncStorage.getItem('offline_mode');
            this.offlineForced = value === 'true';
        } catch (error) {
            this.offlineForced = false;
        }
    }

    async ensureOfflineReady() {
        if (this.offlineReady) return;
        await initOfflineDb();
        this.offlineReady = true;
        await this.loadOfflineMode();
    }

    async isOnline() {
        try {
            if (this.offlineForced) return false;
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
        this.offlineForced = false;
        await this.setOfflineMode(false);

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

        // Salvar configuração
        await AsyncStorage.setItem('serverIP', serverIP);
        await AsyncStorage.setItem('serverPort', serverPort.toString());
        await this.ensureOfflineReady();
    }

    async loadSavedConfig() {
        const serverIP = await AsyncStorage.getItem('serverIP');
        const serverPort = await AsyncStorage.getItem('serverPort');

        if (serverIP && serverPort) {
            await this.initialize(serverIP, parseInt(serverPort));
            return { serverIP, serverPort: parseInt(serverPort) };
        }
        await this.ensureOfflineReady();
        return null;
    }

    async getToken() {
        return AsyncStorage.getItem('token');
    }

    async getNotifyInbox(page = 1, perPage = 20) {
        try {
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get('/api/notify/inbox', {
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
                `/api/notify/inbox/${messageId}/read`,
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

    getReportUrl(type, params = {}) {
        if (!this.baseURL) {
            throw new Error('Servidor não configurado');
        }

        const query = Object.entries(params)
            .filter(([, value]) => value !== undefined && value !== null)
            .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
            .join('&');

        if (type === 'daily') {
            return `${this.baseURL}/api/mobile/reports/daily${query ? `?${query}` : ''}`;
        }
        if (type === 'monthly') {
            return `${this.baseURL}/api/mobile/reports/monthly${query ? `?${query}` : ''}`;
        }

        throw new Error('Tipo de relatório inválido');
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
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                await queueRetiradaOffline(data);
                return {
                    success: true,
                    offline: true,
                    message: 'Retirada registrada offline. Sincronização pendente.'
                };
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
                await queueRetiradaOffline(data);
                return {
                    success: true,
                    offline: true,
                    message: 'Retirada registrada offline. Sincronização pendente.'
                };
            }

            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao registrar retirada',
            };
        }
    }

    async registrarDevolucaoFerramenta(data) {
        try {
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                await queueDevolucaoFerramentaOffline(data);
                return {
                    success: true,
                    offline: true,
                    message: 'Devolução registrada offline. Sincronização pendente.'
                };
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
                await queueDevolucaoFerramentaOffline(data);
                return {
                    success: true,
                    offline: true,
                    message: 'Devolução registrada offline. Sincronização pendente.'
                };
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
            await this.ensureOfflineReady();
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

    /**
     * Registra devolução múltipla de ferramentas
     * @param {Object} data - { itens: [{ codigo, quantidade }], matricula, observacao }
     * @returns {Promise<{success: boolean, message?: string, resultados?: Array}>}
     */
    async registrarDevolucaoMultiplaFerramentas(data) {
        try {
            await this.ensureOfflineReady();
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
            await this.ensureOfflineReady();
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
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                await queueDevolucaoMaterialOffline(data);
                return {
                    success: true,
                    offline: true,
                    message: 'Devolução registrada offline. Sincronização pendente.'
                };
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
                await queueDevolucaoMaterialOffline(data);
                return {
                    success: true,
                    offline: true,
                    message: 'Devolução registrada offline. Sincronização pendente.'
                };
            }

            return {
                success: false,
                message: error.response?.data?.message || error.response?.data?.error || 'Erro ao devolver material',
            };
        }
    }

    async buscarItemPorCodigo(codigo) {
        try {
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                return await getOfflineItemByCodigo(codigo);
            }
            const token = await AsyncStorage.getItem('token');
            if (!token) {
                throw new Error('Token não encontrado');
            }

            const response = await this.client.get(
                `/api/mobile/itens/${codigo}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );

            const item = response.data?.data || null;
            if (item) {
                await upsertItem(item);
            }
            return item;
        } catch (error) {
            console.error('Erro ao buscar item:', error);
            if (isNetworkError(error)) {
                return await getOfflineItemByCodigo(codigo);
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
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                const items = await searchOfflineItems(search);
                return { success: true, data: items, items, offline: true };
            }
            const response = await this.client.get('/api/mobile/estoque', {
                params: { search }
            });
            const items = normalizeEstoquePayload(response.data);
            await upsertItems(items);
            return { success: true, data: items, items };
        } catch (error) {
            if (isNetworkError(error)) {
                const items = await searchOfflineItems(search);
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
                params: { search: '' }
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
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                const item = await getOfflineItemByCodigo(barcode);
                if (item) {
                    return { success: true, data: item, offline: true };
                }
                return { success: false, notFound: true, offline: true };
            }
            const response = await this.client.get(`/api/mobile/estoque/barcode/${barcode}`);
            const item = response.data;
            if (item) {
                await upsertItem(item);
            }
            return { success: true, data: response.data };
        } catch (error) {
            if (isNetworkError(error)) {
                const item = await getOfflineItemByCodigo(barcode);
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
            await this.ensureOfflineReady();
            const online = await this.isOnline();
            if (!online) {
                const resultados = await queueRetiradaMultiplaOffline(data);
                return {
                    success: true,
                    offline: true,
                    resultados,
                    message: 'Retirada múltipla registrada offline. Sincronização pendente.'
                };
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
                const resultados = await queueRetiradaMultiplaOffline(data);
                return {
                    success: true,
                    offline: true,
                    resultados,
                    message: 'Retirada múltipla registrada offline. Sincronização pendente.'
                };
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

    async syncPendingOps() {
        await this.ensureOfflineReady();
        if (!this.client || !this.baseURL) {
            return { success: false, message: 'Servidor não configurado' };
        }
        const online = await this.isOnline();
        if (!online) {
            return { success: false, message: 'Sem conexão' };
        }

        const token = await AsyncStorage.getItem('token');
        if (!token) {
            return { success: false, message: 'Token não encontrado' };
        }

        const pendentes = await listPendingOps();
        let synced = 0;

        for (const op of pendentes) {
            let payload = {};
            try {
                payload = JSON.parse(op.payload || '{}');
            } catch (error) {
                payload = {};
            }

            try {
                let response;
                if (op.type === 'retirada') {
                    response = await this.client.post('/api/mobile/retirar', payload);
                } else if (op.type === 'retirada_multipla') {
                    response = await this.client.post('/api/mobile/retirar_multipla', payload);
                } else if (op.type === 'devolucao_ferramenta') {
                    response = await this.client.post('/api/mobile/devolver', payload);
                } else if (op.type === 'devolucao_material') {
                    response = await this.client.post('/api/mobile/devolver_material', payload);
                } else if (op.type === 'cadastro_item') {
                    await markPendingOpSynced(op.id);
                    synced += 1;
                    continue;
                }

                const success = response?.data?.success !== false;
                if (success) {
                    await markPendingOpSynced(op.id);
                    synced += 1;

                    const item = response?.data?.data?.item || response?.data?.data || null;
                    if (item) {
                        await upsertItem(item);
                    }
                } else {
                    await markPendingOpFailed(op.id);
                    await incrementPendingRetry(op.id);
                }
            } catch (error) {
                await markPendingOpFailed(op.id);
                await incrementPendingRetry(op.id);
            }
        }

        return { success: true, synced };
    }
}

export default new ApiService();
