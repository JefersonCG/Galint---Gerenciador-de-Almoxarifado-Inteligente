import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Device from 'expo-device';
import Constants from 'expo-constants';

const STORAGE_KEYS = {
  baseUrl: 'notify_base_url',
  serverHost: 'notify_server_host',
  serverPort: 'notify_server_port',
  token: 'notify_token',
  user: 'notify_user',
  deviceUuid: 'notify_device_uuid',
};

class NotifyApiService {
  constructor() {
    this.baseURL = null;
    this.client = null;
  }

  normalizeBaseUrl(baseURL) {
    let value = (baseURL || '').trim();
    if (!value) {
      return '';
    }

    if (!/^https?:\/\//i.test(value)) {
      value = `http://${value}`;
    }

    try {
      const parsed = new URL(value);
      const protocol = parsed.protocol || 'http:';
      const hostname = parsed.hostname;
      const port = parsed.port || '';
      return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
    } catch {
      return value.replace(/\/$/, '');
    }
  }

  isPrivateHost(hostname) {
    const host = String(hostname || '').trim().toLowerCase();
    if (!host) {
      return false;
    }
    if (host === 'localhost' || host === '127.0.0.1' || host.endsWith('.local')) {
      return true;
    }
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
      return false;
    }
    const parts = host.split('.').map((entry) => Number(entry));
    if (parts[0] === 10) return true;
    if (parts[0] === 127) return true;
    if (parts[0] === 192 && parts[1] === 168) return true;
    if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
    return false;
  }

  buildNetworkHint(baseURL) {
    const normalized = this.normalizeBaseUrl(baseURL || '');
    if (!normalized) {
      return 'Defina a URL do servidor antes de testar ou entrar.';
    }

    try {
      const parsed = new URL(normalized);
      if (this.isPrivateHost(parsed.hostname)) {
        return 'Este endereço é de rede local. Ele só funciona se o celular estiver na mesma rede Wi-Fi/VPN do servidor e se o IP da máquina não tiver mudado.';
      }
      if (parsed.protocol === 'http:') {
        return 'Se o aparelho estiver fora da rede local, use um endereço HTTPS válido para evitar falha de comunicação.';
      }
      return 'Confirme se o domínio e o certificado usados por esta URL continuam válidos no aparelho.';
    } catch {
      return 'Revise a URL do servidor e teste novamente.';
    }
  }

  formatRequestError(error, baseURL) {
    const effectiveBaseUrl = this.normalizeBaseUrl(baseURL || this.baseURL || '');
    if (error?.response?.data?.message) {
      return error.response.data.message;
    }
    if (error?.response?.status) {
      return `Servidor respondeu com status ${error.response.status}.`;
    }
    if ((error?.code || '').toString().toUpperCase() === 'ECONNABORTED') {
      return `O servidor em ${effectiveBaseUrl || 'URL não configurada'} demorou demais para responder. ${this.buildNetworkHint(effectiveBaseUrl)}`;
    }
    if (error?.message === 'Network Error') {
      return `Falha de rede ao acessar ${effectiveBaseUrl || 'a URL configurada'}. ${this.buildNetworkHint(effectiveBaseUrl)}`;
    }
    return error?.message || 'Erro de comunicação com o servidor.';
  }

  async initialize(baseURL) {
    this.baseURL = this.normalizeBaseUrl(baseURL);
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 15000,
      headers: { 'Content-Type': 'application/json' },
    });
    this.client.interceptors.request.use(async (config) => {
      const token = await AsyncStorage.getItem(STORAGE_KEYS.token);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
    await AsyncStorage.setItem(STORAGE_KEYS.baseUrl, this.baseURL);
    const parsed = this.parseServerConfig(this.baseURL);
    await AsyncStorage.multiSet([
      [STORAGE_KEYS.serverHost, parsed.host],
      [STORAGE_KEYS.serverPort, parsed.port],
    ]);
  }

  parseServerConfig(baseURL) {
    const normalized = this.normalizeBaseUrl(baseURL);
    if (!normalized) {
      return { scheme: 'http', host: '', port: '', baseUrl: '' };
    }

    try {
      const parsed = new URL(normalized);
      return {
        scheme: (parsed.protocol || 'http:').replace(':', ''),
        host: parsed.hostname || '',
        port: parsed.port || '',
        baseUrl: normalized,
      };
    } catch {
      return { scheme: 'http', host: '', port: '', baseUrl: normalized };
    }
  }

  async getServerConfig() {
    const entries = await AsyncStorage.multiGet([
      STORAGE_KEYS.serverHost,
      STORAGE_KEYS.serverPort,
      STORAGE_KEYS.baseUrl,
    ]);
    const values = Object.fromEntries(entries);
    const storedBase = values[STORAGE_KEYS.baseUrl] || Constants.expoConfig?.extra?.defaultServerUrl || '';
    const parsed = this.parseServerConfig(storedBase);
    return {
      scheme: parsed.scheme || 'http',
      host: values[STORAGE_KEYS.serverHost] || parsed.host || '',
      port: values[STORAGE_KEYS.serverPort] || parsed.port || '',
      baseUrl: parsed.baseUrl || this.normalizeBaseUrl(`http://${values[STORAGE_KEYS.serverHost] || ''}${values[STORAGE_KEYS.serverPort] ? `:${values[STORAGE_KEYS.serverPort]}` : ''}`),
    };
  }

  async saveServerConfig({ baseUrl, host, port, scheme }) {
    let resolvedBaseUrl = this.normalizeBaseUrl(baseUrl || '');
    if (!resolvedBaseUrl) {
      const protocol = (scheme || 'http').trim() || 'http';
      const hostValue = (host || '').trim();
      const portValue = (port || '').trim();
      resolvedBaseUrl = this.normalizeBaseUrl(`${protocol}://${hostValue}${portValue ? `:${portValue}` : ''}`);
    }
    if (!resolvedBaseUrl) {
      throw new Error('Informe uma URL base válida.');
    }
    const parsed = this.parseServerConfig(resolvedBaseUrl);
    await AsyncStorage.multiSet([
      [STORAGE_KEYS.serverHost, parsed.host || ''],
      [STORAGE_KEYS.serverPort, parsed.port || ''],
    ]);
    await this.initialize(resolvedBaseUrl);
    return this.getServerConfig();
  }

  async clearServerConfig() {
    await AsyncStorage.multiRemove([
      STORAGE_KEYS.serverHost,
      STORAGE_KEYS.serverPort,
      STORAGE_KEYS.baseUrl,
    ]);
    const fallback = this.normalizeBaseUrl(Constants.expoConfig?.extra?.defaultServerUrl || '');
    if (fallback) {
      await this.initialize(fallback);
    } else {
      this.baseURL = '';
      this.client = null;
    }
    return this.getServerConfig();
  }

  async restoreSession() {
    const savedBase = await AsyncStorage.getItem(STORAGE_KEYS.baseUrl);
    const defaultUrl = Constants.expoConfig?.extra?.defaultServerUrl;
    const baseUrl = savedBase || defaultUrl;
    if (baseUrl) {
      await this.initialize(baseUrl);
    }

    const token = await AsyncStorage.getItem(STORAGE_KEYS.token);
    const userRaw = await AsyncStorage.getItem(STORAGE_KEYS.user);
    if (!token || !userRaw || !baseUrl) {
      return null;
    }
    return { token, user: JSON.parse(userRaw), baseUrl };
  }

  async getOrCreateDeviceUuid() {
    const existing = await AsyncStorage.getItem(STORAGE_KEYS.deviceUuid);
    if (existing) return existing;
    const random = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const uuid = `notify-${random}`;
    await AsyncStorage.setItem(STORAGE_KEYS.deviceUuid, uuid);
    return uuid;
  }

  async login({ matricula, senha }) {
    if (!this.client) {
      const restored = await this.restoreSession();
      if (!restored?.baseUrl) {
        throw new Error('Defina a URL do servidor antes de entrar.');
      }
    }

    let response;
    try {
      response = await this.client.post('/api/notify/login', { matricula, senha });
    } catch (error) {
      throw new Error(this.formatRequestError(error, this.baseURL));
    }
    const payload = response.data || {};
    if (!payload.success || !payload.token || !payload.user) {
      throw new Error(payload.message || 'Falha ao fazer login');
    }
    await AsyncStorage.setItem(STORAGE_KEYS.token, payload.token);
    await AsyncStorage.setItem(STORAGE_KEYS.user, JSON.stringify(payload.user));
    return { token: payload.token, user: payload.user, baseUrl: this.baseURL };
  }

  async saveBaseUrl(baseUrl) {
    await this.initialize(baseUrl);
  }

  async testConnection(baseUrl) {
    const normalized = this.normalizeBaseUrl(baseUrl || this.baseURL);
    if (!normalized) {
      throw new Error('Informe a URL base do servidor.');
    }

    try {
      await axios.get(`${normalized}/api/notify/status`, { timeout: 6000 });
      return { success: true, baseUrl: normalized };
    } catch (error) {
      if (error?.response?.status === 401 || error?.response?.status === 403) {
        return { success: true, baseUrl: normalized };
      }
      throw new Error(this.formatRequestError(error, normalized));
    }
  }

  async logout() {
    await AsyncStorage.multiRemove([STORAGE_KEYS.token, STORAGE_KEYS.user]);
  }

  async fetchInbox(page = 1) {
    const response = await this.client.get('/api/notify/inbox', { params: { page } });
    return response.data;
  }

  async markRead(messageId) {
    const response = await this.client.post(`/api/notify/inbox/${messageId}/read`);
    return response.data;
  }

  async registerPushToken(token, provider = 'expo') {
    const deviceUuid = await this.getOrCreateDeviceUuid();
    const response = await this.client.post('/api/notify/push/register', {
      device_uuid: deviceUuid,
      token,
      provider,
      platform: Device.osName || 'Android',
    });
    return response.data;
  }

  async fetchReports() {
    const response = await this.client.get('/api/notify/reports');
    return response.data;
  }

  async buildDownloadConfig(reportId, format, params = {}) {
    const token = await AsyncStorage.getItem(STORAGE_KEYS.token);
    if (!token || !this.baseURL) {
      throw new Error('Sessão inválida.');
    }
    const query = new URLSearchParams({ format, ...params }).toString();
    return {
      url: `${this.baseURL}/api/notify/reports/${reportId}/download?${query}`,
      token,
    };
  }

  resolveAssetUrl(assetUrl) {
    const value = (assetUrl || '').trim();
    if (!value) {
      return null;
    }
    if (/^https?:\/\//i.test(value)) {
      return value;
    }
    if (!this.baseURL) {
      return value;
    }
    if (value.startsWith('/')) {
      return `${this.baseURL}${value}`;
    }
    return `${this.baseURL}/static/${value.replace(/^static\//i, '')}`;
  }

  async searchToolItems(query) {
    const response = await this.client.get('/api/notify/tools/items/search', { params: { q: query } });
    return response.data;
  }

  async convertToolUnits({ codigoItem, quantity, fromUnit }) {
    const response = await this.client.post('/api/notify/tools/convert', {
      codigo_item: codigoItem,
      quantity,
      from_unit: fromUnit,
    });
    return response.data;
  }
}

const api = new NotifyApiService();
export default api;