<%inherit file="/base.mako"/>

<%block name="title">Registro de Saídas</%block>

<%block name="extra_css">
<style>
    .hub-container {
        max-width: 1360px;
        margin: 0 auto;
        padding: 1rem;
    }

    .hub-shell {
        background: linear-gradient(180deg, #eef2f7 0%, var(--galint-neutro-050, #f8fafc) 100%);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 30px;
        padding: 1rem;
        box-shadow: 0 24px 54px rgba(15, 23, 42, 0.1);
    }

    .saida-mode-picker {
        margin: 0 auto 0.75rem;
        max-width: 820px;
    }

    .saida-mode-label {
        display: block;
        margin-bottom: 0.65rem;
        color: var(--galint-neutro-700, #334155);
        font-weight: 700;
    }

    .saida-mode-track {
        --mode-shift: 0px;
        --mode-width: 0px;
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        position: relative;
        width: 100%;
        gap: 0;
        padding: 4px;
        border-radius: 999px;
        background: #f4f1ea;
        isolation: isolate;
    }

    .saida-mode-track::before {
        content: "";
        position: absolute;
        z-index: -1;
        top: 4px;
        bottom: 4px;
        left: 4px;
        width: var(--mode-width);
        border-radius: 999px;
        background: #fff;
        box-shadow: 0 1px 5px rgba(0, 0, 0, 0.16);
        transform: translateX(var(--mode-shift));
        transition: transform 320ms cubic-bezier(.3, .8, .25, 1);
    }

    .saida-mode-button {
        min-width: 0;
        padding: 0.55rem 1rem;
        border: 0;
        border-radius: 999px;
        background: transparent;
        color: #64748b;
        font-weight: 700;
        line-height: 1.2;
        white-space: nowrap;
        transition: color 250ms ease;
    }

    .saida-mode-button[aria-checked="true"] {
        color: #1e293b;
    }

    .saida-mode-button:focus-visible {
        outline: 2px solid #1e293b;
        outline-offset: 3px;
    }

    .saida-mode-description {
        margin: 0.35rem 0 0;
        color: #475569;
        text-align: center;
        font-size: 0.92rem;
    }

    .saida-form-panel {
        overflow: hidden;
        min-height: 320px;
        border-radius: 18px;
        background: var(--galint-neutro-050, #f8fafc);
    }

    .saida-form-frame {
        display: block;
        width: 100%;
        min-height: 320px;
        border: 0;
        background: transparent;
    }

    .saida-form-frame[hidden] {
        display: none !important;
    }

    .saida-form-loading {
        padding: 3rem 1rem;
        color: #475569;
        text-align: center;
    }

    .saida-form-loading[hidden] {
        display: none !important;
    }

    @media (prefers-reduced-motion: reduce) {
        .saida-mode-track::before,
        .saida-mode-button {
            transition: none;
        }
    }
    @media (max-width: 768px) {
        .hub-shell {
            padding: 0.75rem;
            border-radius: 22px;
        }

        .saida-mode-button {
            padding: 0.45rem 0.25rem;
            font-size: 0.72rem;
            white-space: normal;
        }

        .saida-mode-button i {
            display: block;
            margin: 0 0 0.2rem !important;
        }
    }
</style>
</%block>

<%block name="content">
<div class="hub-container">
    <div class="hub-shell">
        <section class="saida-mode-picker" aria-label="Tipo de operação">
            <span class="saida-mode-label" id="saida-mode-label">Tipo de operação</span>
            <div class="saida-mode-track" id="saida-mode-track" role="radiogroup" aria-labelledby="saida-mode-label">
                <button class="saida-mode-button" type="button" role="radio" aria-checked="true" data-mode="materiais">
                    <i class="bi bi-box-seam me-1" aria-hidden="true"></i>Materiais
                </button>
                <button class="saida-mode-button" type="button" role="radio" aria-checked="false" data-mode="ferramentas" tabindex="-1">
                    <i class="bi bi-tools me-1" aria-hidden="true"></i>Ferramentas
                </button>
                <button class="saida-mode-button" type="button" role="radio" aria-checked="false" data-mode="fracionados" tabindex="-1">
                    <i class="bi bi-droplet-half me-1" aria-hidden="true"></i>Fracionados
                </button>
                <button class="saida-mode-button" type="button" role="radio" aria-checked="false" data-mode="devolucoes" tabindex="-1">
                    <i class="bi bi-arrow-return-left me-1" aria-hidden="true"></i>Devoluções
                </button>
            </div>
            <p class="saida-mode-description" id="saida-mode-description" aria-live="polite"></p>
        </section>

        <div class="saida-form-panel" id="saida-form-panel" aria-busy="true">
            <div class="saida-form-loading" id="saida-form-loading" role="status">
                <span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
                Carregando formulário...
            </div>
            <iframe class="saida-form-frame" title="Formulário de saída" data-mode="materiais"
                data-src="${url_for('movements.saida_page')}" aria-label="Formulário de saída de materiais"></iframe>
            <iframe class="saida-form-frame" title="Formulário de retirada de ferramentas" data-mode="ferramentas"
                data-src="${url_for('ferramentas.retirar_page')}" aria-label="Formulário de retirada de ferramentas" hidden></iframe>
            <iframe class="saida-form-frame" title="Formulário de saída de itens fracionados" data-mode="fracionados"
                data-src="${url_for('movements.saida_fracionada_page')}" aria-label="Formulário de saída de itens fracionados" hidden></iframe>
            <iframe class="saida-form-frame" title="Formulário de devolução" data-mode="devolucoes"
                data-src="${url_for('movements.entrada_page')}" aria-label="Formulário de devolução" hidden></iframe>
        </div>
    </div>
</div>
</%block>

<%block name="scripts">
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const track = document.getElementById('saida-mode-track');
        const panel = document.getElementById('saida-form-panel');
        const loading = document.getElementById('saida-form-loading');
        const description = document.getElementById('saida-mode-description');
        const buttons = Array.from(track.querySelectorAll('[data-mode]'));
        const frames = Array.from(panel.querySelectorAll('iframe[data-mode]'));
        const labels = {
            materiais: 'Materiais comuns e ferramentas disponíveis, em uma lista de retirada.',
            ferramentas: 'Retirada especial de ferramentas com controle de custódia.',
            fracionados: 'Retirada de itens fracionados com informação de peso ou volume.',
            devolucoes: 'Registro de materiais e itens devolvidos ao estoque.'
        };
        let activeMode = null;
        const frameStylesBeforeModal = new WeakMap();

        function updateIndicator(button) {
            const first = buttons[0].getBoundingClientRect();
            const current = button.getBoundingClientRect();
            track.style.setProperty('--mode-shift', (current.left - first.left) + 'px');
            track.style.setProperty('--mode-width', first.width + 'px');
        }

        function setFrameHeight(frame) {
            if (frameStylesBeforeModal.has(frame)) return;
            const doc = frame.contentDocument;
            if (!doc || !doc.body || !doc.documentElement) return;
            const height = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight, 320);
            frame.style.height = height + 'px';
        }

        function prepareLoadedFrame(frame) {
            try {
                const loadedUrl = new URL(frame.contentWindow.location.href);
                if (loadedUrl.protocol === 'about:' && loadedUrl.pathname === 'blank') return;
                if (loadedUrl.origin !== window.location.origin) {
                    throw new Error('O formulário foi carregado em uma origem inesperada.');
                }
                frame.dataset.loaded = 'true';
                delete frame.dataset.loading;
                prepareFrame(frame);
            } catch (error) {
                if (activeMode === frame.dataset.mode) {
                    panel.setAttribute('aria-busy', 'false');
                    loading.textContent = 'Não foi possível exibir este formulário. Atualize a página e tente novamente.';
                    loading.hidden = false;
                }
            }
        }

        function showModalOnScreen(frame) {
            if (frameStylesBeforeModal.has(frame)) return;
            frameStylesBeforeModal.set(frame, {
                position: frame.style.position,
                top: frame.style.top,
                right: frame.style.right,
                bottom: frame.style.bottom,
                left: frame.style.left,
                width: frame.style.width,
                height: frame.style.height,
                zIndex: frame.style.zIndex,
                margin: frame.style.margin,
                maxWidth: frame.style.maxWidth
            });
            Object.assign(frame.style, {
                position: 'fixed',
                top: '0',
                right: '0',
                bottom: '0',
                left: '0',
                width: '100vw',
                height: '100vh',
                zIndex: '2000',
                margin: '0',
                maxWidth: 'none'
            });
        }

        function restoreFrameAfterModal(frame) {
            const previousStyles = frameStylesBeforeModal.get(frame);
            if (!previousStyles) return;
            Object.assign(frame.style, previousStyles);
            frameStylesBeforeModal.delete(frame);
            setFrameHeight(frame);
        }

        function prepareFrame(frame) {
            try {
                const doc = frame.contentDocument;
                if (!doc || !doc.head || !doc.body) throw new Error('O formulário não está disponível.');

                if (!doc.getElementById('saida-hub-embedded-style')) {
                    const style = doc.createElement('style');
                    style.id = 'saida-hub-embedded-style';
                    style.textContent = [
                        'html,body{height:auto!important;min-height:0!important;margin:0!important;}',
                        'body.layout-shell{display:block!important;min-height:0!important;overflow:visible!important;}',
                        '.topbar,#sidebar-column,.content-panel>.page-header{display:none!important;}',
                        '.app-body{display:block!important;min-height:0!important;margin:0!important;padding:0!important;}',
                        '.content-panel{width:100%!important;min-height:0!important;margin:0!important;padding:0!important;overflow:visible!important;}',
                        '.modal{position:fixed!important;inset:0!important;box-sizing:border-box!important;width:100vw!important;height:100vh!important;max-width:none!important;margin:0!important;}',
                        '.modal.show{display:block!important;}',
                        '.modal-dialog{margin:var(--bs-modal-margin,1rem) auto!important;}',
                        '.modal-dialog-centered{display:flex!important;align-items:center!important;min-height:calc(100vh - 2 * var(--bs-modal-margin,1rem))!important;}'
                    ].join('');
                    doc.head.appendChild(style);
                }

                if (!doc.documentElement.dataset.saidaHubModalEvents) {
                    doc.addEventListener('show.bs.modal', function () {
                        showModalOnScreen(frame);
                    });
                    doc.addEventListener('hidden.bs.modal', function () {
                        if (!doc.querySelector('.modal.show')) restoreFrameAfterModal(frame);
                    });
                    doc.documentElement.dataset.saidaHubModalEvents = 'true';
                }

                setFrameHeight(frame);
                if (typeof ResizeObserver !== 'undefined' && !frame.dataset.observing) {
                    const observer = new ResizeObserver(function () { setFrameHeight(frame); });
                    observer.observe(doc.body);
                    frame.dataset.observing = 'true';
                }
                if (activeMode === frame.dataset.mode) {
                    panel.setAttribute('aria-busy', 'false');
                    loading.hidden = true;
                }
            } catch (error) {
                if (activeMode === frame.dataset.mode) {
                    panel.setAttribute('aria-busy', 'false');
                    loading.textContent = 'Não foi possível exibir este formulário. Atualize a página e tente novamente.';
                    loading.hidden = false;
                }
            }
        }

        function activate(mode, updateAddress) {
            const button = buttons.find(function (item) { return item.dataset.mode === mode; });
            const frame = frames.find(function (item) { return item.dataset.mode === mode; });
            if (!button || !frame) return;

            activeMode = mode;
            updateIndicator(button);
            buttons.forEach(function (item) {
                const selected = item === button;
                item.setAttribute('aria-checked', String(selected));
                item.tabIndex = selected ? 0 : -1;
            });
            frames.forEach(function (item) {
                item.hidden = item !== frame;
            });
            description.textContent = labels[mode];

            const loaded = frame.dataset.loaded === 'true';
            panel.setAttribute('aria-busy', String(!loaded));
            loading.hidden = loaded;
            if (!loaded) {
                loading.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Carregando formulário...';
                if (frame.dataset.loading !== 'true') {
                    frame.dataset.loading = 'true';
                    if (frame.dataset.loadListener !== 'true') {
                        frame.dataset.loadListener = 'true';
                        frame.addEventListener('load', function () {
                            prepareLoadedFrame(frame);
                        });
                    }
                    frame.src = frame.dataset.src;
                } else {
                    prepareLoadedFrame(frame);
                }
            } else {
                setFrameHeight(frame);
            }

            if (updateAddress) history.replaceState(null, '', '#' + mode);
        }

        buttons.forEach(function (button, index) {
            button.addEventListener('click', function () { activate(button.dataset.mode, true); });
            button.addEventListener('keydown', function (event) {
                let nextIndex = index;
                if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % buttons.length;
                else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + buttons.length) % buttons.length;
                else if (event.key === 'Home') nextIndex = 0;
                else if (event.key === 'End') nextIndex = buttons.length - 1;
                else return;
                event.preventDefault();
                buttons[nextIndex].focus();
                activate(buttons[nextIndex].dataset.mode, true);
            });
        });
        window.addEventListener('resize', function () {
            const button = buttons.find(function (item) { return item.dataset.mode === activeMode; });
            if (button) updateIndicator(button);
        });

        const requestedMode = window.location.hash.slice(1);
        activate(labels[requestedMode] ? requestedMode : 'materiais', false);
    });
</script>
${parent.scripts()}
</%block>
