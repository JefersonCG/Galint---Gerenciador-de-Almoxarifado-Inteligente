import AsyncStorage from '@react-native-async-storage/async-storage';
import ApiService from './api';

/**
 * FeatureFlagsService - Gerencia feature flags do backend
 * Busca flags do servidor e mantém cache local
 */
class FeatureFlagsService {
    constructor() {
        this.flags = {};
        this.lastFetch = null;
        this.CACHE_DURATION = 5 * 60 * 1000; // 5 minutos
        this.isFetching = false;
    }

    /**
     * Busca feature flags do backend
     * Usa cache se disponível e não expirado
     */
    async fetchFlags() {
        try {
            const now = Date.now();
            
            // Usar cache se válido
            if (this.lastFetch && (now - this.lastFetch) < this.CACHE_DURATION) {
                console.log('[FeatureFlags] Usando cache');
                return this.flags;
            }

            // Evitar múltiplas requisições simultâneas
            if (this.isFetching) {
                console.log('[FeatureFlags] Fetch já em andamento');
                return this.flags;
            }

            const token = await AsyncStorage.getItem('token');
            if (!token) {
                console.log('[FeatureFlags] Sem token, usando flags vazias');
                return this.flags;
            }

            if (!ApiService.client) {
                console.log('[FeatureFlags] API não inicializada');
                return this.flags;
            }

            this.isFetching = true;
            const response = await ApiService.client.get('/features');
            
            // Backend retorna { features: { flag_key: { enabled, value, ... } } }
            if (response.data && response.data.features) {
                this.flags = response.data.features;
                this.lastFetch = now;
                console.log('[FeatureFlags] Atualizadas:', Object.keys(this.flags).length, 'flags');
            }

            return this.flags;
        } catch (error) {
            console.warn('[FeatureFlags] Falha ao buscar:', error.message);
            // Retornar cache antigo mesmo se expirado
            return this.flags;
        } finally {
            this.isFetching = false;
        }
    }

    /**
     * Verifica se uma feature flag está habilitada
     * @param {string} flagKey - Chave da flag (ex: 'new_scanner_ui')
     * @param {boolean} defaultValue - Valor padrão se flag não existir
     * @returns {Promise<boolean>}
     */
    async isEnabled(flagKey, defaultValue = false) {
        if (!this.lastFetch) {
            await this.fetchFlags();
        }

        if (!this.flags[flagKey]) {
            return defaultValue;
        }

        return this.flags[flagKey].enabled ?? defaultValue;
    }

    /**
     * Obtém o valor de uma feature flag
     * @param {string} flagKey - Chave da flag
     * @param {any} defaultValue - Valor padrão se flag não existir
     * @returns {any}
     */
    getValue(flagKey, defaultValue = null) {
        if (!this.flags[flagKey]) {
            return defaultValue;
        }

        return this.flags[flagKey].value ?? defaultValue;
    }

    /**
     * Força atualização das flags (ignora cache)
     */
    async refresh() {
        this.lastFetch = null;
        return await this.fetchFlags();
    }

    /**
     * Limpa cache de flags
     */
    clear() {
        this.flags = {};
        this.lastFetch = null;
        console.log('[FeatureFlags] Cache limpo');
    }

    /**
     * Retorna todas as flags carregadas
     */
    getAllFlags() {
        return { ...this.flags };
    }

    /**
     * Retorna informações de debug
     */
    getDebugInfo() {
        return {
            flagCount: Object.keys(this.flags).length,
            lastFetch: this.lastFetch ? new Date(this.lastFetch).toLocaleString() : null,
            cacheAge: this.lastFetch ? Date.now() - this.lastFetch : null,
            isExpired: this.lastFetch ? (Date.now() - this.lastFetch) > this.CACHE_DURATION : true,
        };
    }
}

// Exportar instância singleton
export default new FeatureFlagsService();
