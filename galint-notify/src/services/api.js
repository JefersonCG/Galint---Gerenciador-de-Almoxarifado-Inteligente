import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Device from 'expo-device';
import Constants from 'expo-constants';

const STORAGE_KEYS = {
  baseUrl: 'notify_base_url',
  token: 'notify_token',
  user: 'notify_user',
  deviceUuid: 'notify_device_uuid',
};

class NotifyApiService {
  constructor() {
    this.baseURL = null;
    this.client = null;
  }

  async initialize(baseURL) {
    this.baseURL = (baseURL || '').trim().replace(/\/$/, '');
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

    const response = await this.client.post('/api/notify/login', { matricula, senha });
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