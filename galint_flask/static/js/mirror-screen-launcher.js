(function () {
    const WINDOW_NAME = 'galint-operation-mirror-display';
    const MIRROR_STATE_ENDPOINT = '/movimentos/painel-espelho/state';
    let mirrorStateSyncTimer = null;
    let pendingMirrorState = null;

    function toFiniteNumber(value, fallback) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function clampDimension(value, fallback) {
        return Math.max(Math.round(toFiniteNumber(value, fallback)), 640);
    }

    function getBoundsFromScreen(screenLike) {
        const fallbackLeft = toFiniteNumber(window.screenLeft, 0);
        const fallbackTop = toFiniteNumber(window.screenTop, 0);
        const fallbackWidth = clampDimension(window.screen.availWidth || window.outerWidth || 1400, 1400);
        const fallbackHeight = clampDimension(window.screen.availHeight || window.outerHeight || 900, 900);

        return {
            left: Math.round(toFiniteNumber(screenLike?.availLeft, toFiniteNumber(screenLike?.left, fallbackLeft))),
            top: Math.round(toFiniteNumber(screenLike?.availTop, toFiniteNumber(screenLike?.top, fallbackTop))),
            width: clampDimension(screenLike?.availWidth ?? screenLike?.width, fallbackWidth),
            height: clampDimension(screenLike?.availHeight ?? screenLike?.height, fallbackHeight),
        };
    }

    function buildFeatureString(bounds) {
        return [
            'popup=yes',
            'resizable=yes',
            'scrollbars=yes',
            'toolbar=no',
            'menubar=no',
            'location=no',
            'status=no',
            'noopener=no',
            `left=${bounds.left}`,
            `top=${bounds.top}`,
            `width=${bounds.width}`,
            `height=${bounds.height}`,
        ].join(',');
    }

    function normalizeUrl(href) {
        try {
            const url = new URL(href, window.location.href);
            url.searchParams.set('opened_via', 'mirror_launcher');
            return url.toString();
        } catch (error) {
            return href;
        }
    }

    async function syncMirrorStateToServer(payload) {
        if (!payload || typeof payload !== 'object') {
            return false;
        }
        try {
            const response = await window.fetch(MIRROR_STATE_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
                keepalive: true,
                body: JSON.stringify(payload),
            });
            return response.ok;
        } catch (error) {
            console.error('Erro ao sincronizar estado do painel espelho no servidor:', error);
            return false;
        }
    }

    function scheduleMirrorStateSync(payload) {
        pendingMirrorState = payload;
        if (mirrorStateSyncTimer !== null) {
            return;
        }
        mirrorStateSyncTimer = window.setTimeout(function () {
            const nextPayload = pendingMirrorState;
            pendingMirrorState = null;
            mirrorStateSyncTimer = null;
            void syncMirrorStateToServer(nextPayload);
        }, 180);
    }

    function publishMirrorState(payload, options) {
        const config = options || {};
        const storageKey = config.storageKey;
        const channel = config.channel;

        if (storageKey) {
            try {
                window.localStorage.setItem(storageKey, JSON.stringify(payload));
            } catch (error) {
                console.error('Erro ao persistir estado do painel espelho:', error);
            }
        }

        if (channel) {
            try {
                channel.postMessage(payload);
            } catch (error) {
                console.error('Erro ao publicar estado do painel espelho:', error);
            }
        }

        scheduleMirrorStateSync(payload);
    }

    function pickSecondaryScreen(details) {
        const screens = Array.isArray(details?.screens) ? details.screens : [];
        if (!screens.length) {
            return null;
        }

        const current = details?.currentScreen || null;
        const alternatives = screens.filter((screen) => {
            if (!current) {
                return true;
            }
            return (
                screen !== current && (
                    screen.left !== current.left ||
                    screen.top !== current.top ||
                    screen.width !== current.width ||
                    screen.height !== current.height
                )
            );
        });

        return alternatives.find((screen) => screen?.isPrimary === false)
            || alternatives[0]
            || (screens.length > 1 ? screens[1] : null);
    }

    function finalizePopup(popup, bounds) {
        if (!popup) {
            return false;
        }
        try {
            popup.moveTo(bounds.left, bounds.top);
        } catch (error) {
            console.debug('Nao foi possivel mover o painel espelho:', error);
        }
        try {
            popup.resizeTo(bounds.width, bounds.height);
        } catch (error) {
            console.debug('Nao foi possivel redimensionar o painel espelho:', error);
        }
        try {
            popup.focus();
        } catch (error) {
            console.debug('Nao foi possivel focar o painel espelho:', error);
        }
        return true;
    }

    async function openMirrorNatively(anchor) {
        if (!anchor || !anchor.href) {
            return false;
        }

        let targetUrl;
        try {
            targetUrl = new URL(anchor.href, window.location.href);
        } catch (error) {
            return false;
        }

        const nativeUrl = new URL(targetUrl.pathname.replace(/\/$/, '') + '/native-open', targetUrl.origin);
        const mode = String(targetUrl.searchParams.get('mode') || '').trim();

        try {
            const response = await window.fetch(nativeUrl.toString(), {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
                body: JSON.stringify(mode ? { mode } : {}),
            });
            if (!response.ok) {
                return false;
            }
            const data = await response.json();
            return Boolean(data && data.success);
        } catch (error) {
            console.warn('Falha ao abrir o painel espelho nativo:', error);
            return false;
        }
    }

    async function openMirrorWindow(anchor) {
        if (!anchor || !anchor.href) {
            return false;
        }

        if (await openMirrorNatively(anchor)) {
            return true;
        }

        const href = normalizeUrl(anchor.href);

        if (window.isSecureContext && typeof window.getScreenDetails === 'function') {
            try {
                const details = await window.getScreenDetails();
                const secondaryScreen = pickSecondaryScreen(details);
                if (secondaryScreen) {
                    const bounds = getBoundsFromScreen(secondaryScreen);
                    const popup = window.open(href, WINDOW_NAME, buildFeatureString(bounds));
                    if (finalizePopup(popup, bounds)) {
                        return true;
                    }
                }
            } catch (error) {
                console.warn('Falha ao abrir o painel espelho no segundo monitor:', error);
            }
        }

        const fallbackBounds = getBoundsFromScreen(window.screen || {});
        const fallbackPopup = window.open(href, WINDOW_NAME, buildFeatureString(fallbackBounds));
        return finalizePopup(fallbackPopup, fallbackBounds);
    }

    function shouldHandleClick(event) {
        return !(event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey);
    }

    function bindMirrorButtons(root) {
        const scope = root || document;
        scope.querySelectorAll('a.btn-mirror-screen[href]').forEach((anchor) => {
            if (anchor.dataset.mirrorLauncherBound === '1') {
                return;
            }
            anchor.dataset.mirrorLauncherBound = '1';
            anchor.addEventListener('click', function (event) {
                if (!shouldHandleClick(event)) {
                    return;
                }
                event.preventDefault();
                openMirrorWindow(anchor).then((opened) => {
                    if (!opened) {
                        window.open(anchor.href, WINDOW_NAME, 'resizable=yes,scrollbars=yes');
                    }
                }).catch((error) => {
                    console.error('Erro ao abrir painel espelho:', error);
                    window.open(anchor.href, WINDOW_NAME, 'resizable=yes,scrollbars=yes');
                });
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            bindMirrorButtons(document);
        });
    } else {
        bindMirrorButtons(document);
    }

    window.GalintMirrorScreenLauncher = {
        bindMirrorButtons,
        openMirrorWindow,
        publishMirrorState,
    };
})();