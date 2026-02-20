import AsyncStorage from '@react-native-async-storage/async-storage';

export const saveServerConfig = async (serverIP, serverPort) => {
    try {
        await AsyncStorage.setItem('serverIP', serverIP);
        await AsyncStorage.setItem('serverPort', serverPort.toString());
    } catch (error) {
        console.error('Erro ao salvar configuração:', error);
    }
};

export const loadServerConfig = async () => {
    try {
        const serverIP = await AsyncStorage.getItem('serverIP');
        const serverPort = await AsyncStorage.getItem('serverPort');

        if (serverIP && serverPort) {
            return {
                serverIP,
                serverPort: parseInt(serverPort)
            };
        }
        return null;
    } catch (error) {
        console.error('Erro ao carregar configuração:', error);
        return null;
    }
};

export const clearServerConfig = async () => {
    try {
        await AsyncStorage.multiRemove(['serverIP', 'serverPort']);
    } catch (error) {
        console.error('Erro ao limpar configuração:', error);
    }
};

export const saveCredentials = async (username, password, remember) => {
    try {
        if (remember) {
            await AsyncStorage.setItem('savedUsername', username);
            await AsyncStorage.setItem('savedPassword', password);
        } else {
            await AsyncStorage.removeItem('savedUsername');
            await AsyncStorage.removeItem('savedPassword');
        }
    } catch (error) {
        console.error('Erro ao salvar credenciais:', error);
    }
};

export const loadCredentials = async () => {
    try {
        const username = await AsyncStorage.getItem('savedUsername');
        const password = await AsyncStorage.getItem('savedPassword');

        if (username && password) {
            return { username, password };
        }
        return null;
    } catch (error) {
        console.error('Erro ao carregar credenciais:', error);
        return null;
    }
};
