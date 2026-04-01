(function () {
    if (window.__galintSessionActivityInitialized) {
        return;
    }
    window.__galintSessionActivityInitialized = true;

    const config = window.galintSessionConfig || {};
    const keepaliveUrl = config.keepaliveUrl;
    const loginUrl = config.loginUrl;
    const throttleMs = Number(config.throttleMs || (5 * 60 * 1000));

    if (!keepaliveUrl) {
        return;
    }

    const fetchFn = window.galintNativeFetch || window.fetch.bind(window);

    let lastKeepaliveAt = 0;
    let inflight = false;

    async function sendKeepalive() {
        const now = Date.now();
        if (inflight || (now - lastKeepaliveAt) < throttleMs) {
            return;
        }

        inflight = true;
        lastKeepaliveAt = now;

        try {
            const response = await fetchFn(keepaliveUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: '{}',
                keepalive: true,
            });

            if (response.redirected && response.url && response.url.includes('/auth/login')) {
                window.location.href = response.url;
                return;
            }

            if (response.status === 401 || response.status === 403) {
                window.location.href = loginUrl || '/auth/login';
            }
        } catch (error) {
        } finally {
            inflight = false;
        }
    }

    function registerActivity() {
        void sendKeepalive();
    }

    ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'].forEach((eventName) => {
        window.addEventListener(eventName, registerActivity, { passive: true });
    });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            registerActivity();
        }
    });

    if (document.visibilityState !== 'hidden') {
        registerActivity();
    }
})();