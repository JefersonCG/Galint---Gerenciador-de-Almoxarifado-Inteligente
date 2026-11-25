// Fila de saída guardada no celular (2.4.0, 25/11/2026). Pedido do usuário: "caso o apk feche ele restaure
// o que estava sendo retirado". Mesmo combinado do rascunho do site (saida.mako, galint.saidaDraftState.v1):
// a fila fica só neste aparelho, some ao dar a saída e, se ficar parada mais de 24 h, é descartada.
// Uma fila por usuário logado, para o próximo login no mesmo celular não herdar a do anterior.
import AsyncStorage from '@react-native-async-storage/async-storage';

const PREFIX = 'galint_fila_saida_v1';
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function storageKey(user) {
    return `${PREFIX}:${String(user?.matricula || '').trim() || 'sem-login'}`;
}

function countLines(grupos) {
    return (Array.isArray(grupos) ? grupos : []).reduce((total, grupo) => total + (Array.isArray(grupo?.itens) ? grupo.itens.length : 0), 0);
}

// { grupos, atual } ou null (sem fila, ilegível ou vencida).
export async function lerFila(user) {
    try {
        const raw = await AsyncStorage.getItem(storageKey(user));
        if (!raw) return null;
        const data = JSON.parse(raw);
        const savedAt = Date.parse(String(data?.savedAt || ''));
        if (Number.isFinite(savedAt) && Date.now() - savedAt > MAX_AGE_MS) {
            await AsyncStorage.removeItem(storageKey(user));
            return null;
        }
        const grupos = (Array.isArray(data?.grupos) ? data.grupos : []).filter((grupo) => Array.isArray(grupo?.itens) && grupo.itens.length);
        return { grupos, atual: data?.atual || null };
    } catch (error) {
        return null;
    }
}

export async function gravarFila(user, grupos, atual) {
    try {
        const temAlgo = countLines(grupos) > 0 || Boolean(atual?.retirante) || Boolean(String(atual?.local || '').trim());
        if (!temAlgo) {
            await AsyncStorage.removeItem(storageKey(user));
            return;
        }
        await AsyncStorage.setItem(storageKey(user), JSON.stringify({ version: 1, savedAt: new Date().toISOString(), grupos, atual }));
    } catch (error) {
        // sem espaço ou sem acesso: a fila continua na tela
    }
}

export async function apagarFila(user) {
    try {
        await AsyncStorage.removeItem(storageKey(user));
    } catch (error) {
        // nada a fazer
    }
}

export async function contarFila(user) {
    const fila = await lerFila(user);
    return fila ? countLines(fila.grupos) : 0;
}
