// Entrar com digital ou rosto (2.2.0, pedido do usuário em 21/11/2026).
//
// A pessoa entra uma vez com usuário e senha e aceita "usar a digital/rosto da próxima vez".
// Usuário e senha ficam no cofre do Android (expo-secure-store, cifrado pelo Keystore), ligados ao
// servidor em que foram usados. Para ler o cofre, o app pede a digital ou o rosto
// (expo-local-authentication); o login no servidor continua o mesmo (/api/mobile/login).
//
// Até a 2.1.1 o "Lembrar credenciais" guardava a senha em texto aberto no AsyncStorage
// (savedPassword); forgetPlainPassword() apaga essa cópia.
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';

const VAULT_KEY = 'galint_login_biometria';

export async function biometricAvailability() {
    try {
        const [hardware, enrolled, types] = await Promise.all([
            LocalAuthentication.hasHardwareAsync(),
            LocalAuthentication.isEnrolledAsync(),
            LocalAuthentication.supportedAuthenticationTypesAsync(),
        ]);
        const finger = types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT);
        const face = types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)
            || types.includes(LocalAuthentication.AuthenticationType.IRIS);
        let label = 'digital';
        if (finger && face) label = 'digital ou rosto';
        else if (face) label = 'rosto';
        return { available: Boolean(hardware && enrolled), hardware: Boolean(hardware), label, icon: face && !finger ? '🙂' : '👆' };
    } catch (error) {
        return { available: false, hardware: false, label: 'digital', icon: '👆' };
    }
}

async function readVault() {
    try {
        const raw = await SecureStore.getItemAsync(VAULT_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        return null;
    }
}

// Há login guardado para este servidor? Devolve o usuário (sem a senha) para a tela mostrar.
export async function savedBiometricUser(serverKey) {
    const vault = await readVault();
    if (!vault || vault.servidor !== serverKey || !vault.usuario || !vault.senha) return null;
    return vault.usuario;
}

export async function saveBiometricLogin(serverKey, username, password) {
    await SecureStore.setItemAsync(VAULT_KEY, JSON.stringify({ servidor: serverKey, usuario: username, senha: password }));
}

export async function clearBiometricLogin() {
    try {
        await SecureStore.deleteItemAsync(VAULT_KEY);
    } catch (error) {
        // nada guardado
    }
}

// Pede a digital ou o rosto e, se passar, devolve { usuario, senha } do cofre.
export async function unlockWithBiometrics(serverKey, label = 'digital') {
    const vault = await readVault();
    if (!vault || vault.servidor !== serverKey) {
        return { success: false, message: 'Entre com a senha uma vez para ligar o acesso por biometria.' };
    }
    const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Entrar no GALINT',
        cancelLabel: 'Usar senha',
        disableDeviceFallback: false,
    });
    if (!result.success) {
        const canceled = ['user_cancel', 'system_cancel', 'app_cancel'].includes(result.error);
        return { success: false, canceled, message: canceled ? '' : `Não foi possível confirmar a ${label}.` };
    }
    return { success: true, usuario: vault.usuario, senha: vault.senha };
}

export async function forgetPlainPassword() {
    try {
        await AsyncStorage.removeItem('savedPassword');
    } catch (error) {
        // sem acesso ao armazenamento: nada a apagar
    }
}
