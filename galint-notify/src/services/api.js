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
      const port = parsed.port || (protocol === 'https:' ? '443' : '5000');
      return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
    } catch {
      return value.replace(/\/$/, '');
    }
  }

  formatRequestError(error) {
    if (error?.response?.data?.message) {
      return error.response.data.message;
    }
    if (error?.response?.status) {
      return `Servidor respondeu com status ${error.response.status}.`;
    }
    if (error?.message === 'Network Error') {
      return 'Falha de rede ao acessar o servidor. Verifique IP, porta e se o Android pode acessar HTTP local.';
    }
    return error?.message || 'Erro de comunicação com o servidor.';
  }

  async initialize(baseURL) {
    this.baseURL = this.normalizeBaseUrl(baseURL);
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: 10000,
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
      return { host: '', port: '5000', baseUrl: '' };
    }

    try {
      const parsed = new URL(normalized);
      return {
        host: parsed.hostname || '',
        port: parsed.port || (parsed.protocol === 'https:' ? '443' : '5000'),
        baseUrl: normalized,
      };
    } catch {
      return { host: '', port: '5000', baseUrl: normalized };
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
      host: values[STORAGE_KEYS.serverHost] || parsed.host || '192.168.1.41',
      port: values[STORAGE_KEYS.serverPort] || parsed.port || '5000',
      baseUrl: parsed.baseUrl || this.normalizeBaseUrl(`http://${values[STORAGE_KEYS.serverHost] || '192.168.1.41'}:${values[STORAGE_KEYS.serverPort] || '5000'}`),
    };
  }

  async saveServerConfig({ host, port }) {
    const baseUrl = this.normalizeBaseUrl(`http://${(host || '').trim()}:${(port || '').trim() || '5000'}`);
    await this.initialize(baseUrl);
    return this.getServerConfig();
  }

  async clearServerConfig() {
    await AsyncStorage.multiRemove([
      STORAGE_KEYS.serverHost,
      STORAGE_KEYS.serverPort,
      STORAGE_KEYS.baseUrl,
    ]);
    const fallback = Constants.expoConfig?.extra?.defaultServerUrl || 'http://192.168.1.41:5000';
    await this.initialize(fallback);
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
      throw new Error(this.formatRequestError(error));
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
      throw new Error('Informe IP e porta do servidor.');
    }

    try {
      await axios.get(`${normalized}/api/notify/status`, { timeout: 6000 });
      return { success: true, baseUrl: normalized };
    } catch (error) {
      if (error?.response?.status === 401 || error?.response?.status === 403) {
        return { success: true, baseUrl: normalized };
      }
      throw new Error(this.formatRequestError(error));
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
}

const api = new NotifyApiService();
export default api;