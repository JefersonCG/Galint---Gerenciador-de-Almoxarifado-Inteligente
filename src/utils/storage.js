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

// Só o usuário fica lembrado aqui. Desde a 2.2.0 a senha não vai mais para o AsyncStorage (ela
// ficava em texto aberto em 'savedPassword'): quem quiser entrar sem digitar usa a digital ou o
// rosto, e a senha fica no cofre do Android (services/biometricLogin.js).
export const saveLastUsername = async (username) => {
    try {
        await AsyncStorage.setItem('savedUsername', String(username || '').trim());
    } catch (error) {
        console.error('Erro ao salvar usuário:', error);
    }
};

export const loadLastUsername = async () => {
    try {
        return (await AsyncStorage.getItem('savedUsername')) || '';
    } catch (error) {
        return '';
    }
};
