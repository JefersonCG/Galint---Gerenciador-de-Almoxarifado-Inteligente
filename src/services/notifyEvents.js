const listeners = new Set();

export function subscribeNotifyInboxChanged(listener) {
    if (typeof listener !== 'function') {
        return () => {};
    }
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

export function emitNotifyInboxChanged(payload = {}) {
    listeners.forEach((listener) => {
        try {
            listener(payload);
        } catch (error) {
            console.warn('[NotifyEvents] Falha ao notificar listener:', error?.message || error);
        }
    });
}