import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

class ApiService {
    constructor() {
        this.baseURL = null;
        this.token = null;
        this.client = null;
    }

    async initialize(serverIP, serverPort, useHttps = true) {
        const protocol = useHttps ? 'https' : 'http';
        this.baseURL = `${protocol}://${serverIP}:${serverPort}`;

        this.client = axios.create({
            baseURL: this.baseURL,
            timeout: 10000,
            headers: {
                'Content-Type': 'application/json',
            },
            // Aceitar certificados auto-assinados (apenas para desenvolvimento!)
            httpsAgent: useHttps ? {
                rejectUnauthorized: false
            } : undefined
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
        await AsyncStorage.setItem('useHttps', useHttps.toString());
    }

    async loadSavedConfig() {
        const serverIP = await AsyncStorage.getItem('serverIP');
        const serverPort = await AsyncStorage.getItem('serverPort');
        const useHttps = (await AsyncStorage.getItem('useHttps')) === 'true';

        if (serverIP && serverPort) {
            await this.initialize(serverIP, parseInt(serverPort), useHttps);
            return { serverIP, serverPort: parseInt(serverPort), useHttps };
        }
        return null;
    }

    async testConnection() {
        try {
            const response = await this.client.get('/api/mobile/health', { timeout: 5000 });
            return { success: true, message: 'Conexão OK!' };
        } catch (error) {
            if (error.code === 'ECONNABORTED') {
                return { success: false, message: 'Timeout: Servidor não respondeu' };
            }
            if (error.code === 'ECONNREFUSED') {
                return { success: false, message: 'Servidor recusou conexão' };
            }
            return {
                success: false,
                message: error.response?.data?.message || 'Erro ao conectar'
            };
        }
    }

    async login(username, password) {
        try {
            const response = await this.client.post('/api/mobile/login', {
                matricula: username,
                senha: password
            });

            const { token, user } = response.data;
            await AsyncStorage.setItem('token', token);
            await AsyncStorage.setItem('user', JSON.stringify(user));

            this.token = token;
            return { success: true, user };
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao fazer login'
            };
        }
    }

    async logout() {
        await AsyncStorage.removeItem('token');
        await AsyncStorage.removeItem('user');
        this.token = null;
    }

    async getEstoque(search = '') {
        try {
            const response = await this.client.get('/api/mobile/estoque', {
                params: { search }
            });
            return { success: true, data: response.data };
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao buscar estoque'
            };
        }
    }

    async getItemByBarcode(barcode) {
        try {
            const response = await this.client.get(`/api/mobile/estoque/barcode/${barcode}`);
            return { success: true, data: response.data };
        } catch (error) {
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
        try {
            const response = await this.client.post('/api/mobile/estoque', itemData);
            return { success: true, data: response.data };
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao cadastrar item'
            };
        }
    }

    async atualizarItem(itemId, itemData) {
        try {
            const response = await this.client.put(`/api/mobile/estoque/${itemId}`, itemData);
            return { success: true, data: response.data };
        } catch (error) {
            return {
                success: false,
                message: error.response?.data?.error || 'Erro ao atualizar item'
            };
        }
    }
}

export default new ApiService();
