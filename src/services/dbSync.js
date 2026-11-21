// Sincronização da base do celular com o servidor (desde a 2.2.0).
//
// Regra pedida pelo usuário em 21/11/2026: o celular guarda o estoque inteiro, e toda
// atualização do estoque chega aos dois lados, sempre.
// - O app nunca grava só no celular: retirada, devolução e contagem vão direto ao servidor.
//   Logo depois, a tela chama SyncService.syncNow() e a base do celular recebe o saldo novo.
// - Mudanças feitas no site ou em outro celular chegam pela pergunta "o que mudou?"
//   (/api/mobile/estoque/mudancas), feita a cada 15 s com o app aberto e sempre que ele volta
//   para a frente. Sem mudança, a resposta custa milissegundos no servidor.
// - A cada 30 min, e na primeira vez, a lista vem inteira e substitui a base (cobre item
//   apagado no site ou mudança que o cursor não pega).
//
// Até a 2.1.1 a base nunca abria e a lista inteira descia de tempos em tempos (em 21/11/2026,
// a cada 5 s, entupindo o servidor).
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import ApiService from './api';
import { countItems, getMeta, replaceAllItems, setMeta, upsertItems } from './localDb';

const POLL_INTERVAL_MS = 15 * 1000;
const FULL_REFRESH_MS = 30 * 60 * 1000;

let pollTimer = null;
let appStateSubscription = null;
let running = null; // promessa da sincronização em andamento
let rerunRequested = false;
let rerunFull = false;
let listeners = [];
const status = {
    online: true,
    lastSyncAt: 0,
    lastError: null,
    count: 0,
};

function notify(event) {
    listeners.forEach((callback) => {
        try {
            callback(event);
        } catch (error) {
            console.warn('[Sync] Falha num ouvinte:', error?.message || error);
        }
    });
}

async function syncOnce(forceFull) {
    const net = await NetInfo.fetch().catch(() => null);
    if (net && net.isConnected === false) {
        status.online = false;
        notify({ ok: false, offline: true, changed: false });
        return;
    }

    const lastFull = Number(await getMeta('ultima_completa')) || 0;
    const full = forceFull || Date.now() - lastFull > FULL_REFRESH_MS;
    const cursor = full ? null : await getMeta('cursor');
    const result = await ApiService.getEstoqueMudancas(cursor);
    if (!result?.success) {
        status.online = !result?.offline;
        status.lastError = result?.message || 'Falha ao sincronizar.';
        notify({ ok: false, offline: Boolean(result?.offline), changed: false });
        return;
    }

    const items = Array.isArray(result.items) ? result.items : [];
    if (result.full) {
        await replaceAllItems(items);
        await setMeta('ultima_completa', Date.now());
    } else if (items.length > 0) {
        await upsertItems(items);
    }
    await setMeta('cursor', result.cursor || '');
    status.online = true;
    status.lastError = null;
    status.lastSyncAt = Date.now();
    status.count = await countItems();
    notify({ ok: true, changed: Boolean(result.full) || items.length > 0, full: Boolean(result.full), count: status.count });
}

export const SyncService = {
    start() {
        if (pollTimer) return;
        SyncService.syncNow();
        pollTimer = setInterval(() => SyncService.syncNow(), POLL_INTERVAL_MS);
        appStateSubscription = AppState.addEventListener('change', (state) => {
            if (state === 'active') SyncService.syncNow();
        });
    },

    stop() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = null;
        if (appStateSubscription) appStateSubscription.remove();
        appStateSubscription = null;
    },

    addListener(callback) {
        listeners.push(callback);
        return () => {
            listeners = listeners.filter((entry) => entry !== callback);
        };
    },

    getStatus() {
        return { ...status };
    },

    // Chamada depois de cada gravação no servidor e no "Atualizar agora". Se já houver uma
    // sincronização rodando, roda de novo quando ela acabar (a mudança pode ter chegado depois).
    async syncNow({ full = false } = {}) {
        if (running) {
            rerunRequested = true;
            rerunFull = rerunFull || full;
            return running;
        }
        running = (async () => {
            let nextFull = full;
            do {
                rerunRequested = false;
                try {
                    await syncOnce(nextFull);
                } catch (error) {
                    status.lastError = error?.message || String(error);
                    console.warn('[Sync] Erro:', status.lastError);
                    notify({ ok: false, changed: false });
                }
                nextFull = rerunFull;
                rerunFull = false;
            } while (rerunRequested);
        })();
        try {
            await running;
        } finally {
            running = null;
        }
        return undefined;
    },
};

// Toda gravação de estoque feita pelo app (api.js) traz o saldo novo para a base do celular na hora.
ApiService.onStockWrite(() => {
    SyncService.syncNow();
});

export default SyncService;
