/*
 * Rascunho automático de formulário (26/11/2026).
 *
 * Pedido do usuário: "quando estiver cadastrando itens, a página se auto recuperar de onde parou", se o
 * navegador fechar ou o PC desligar (como a lista da Saída, que já volta sozinha).
 *
 * - Guarda no navegador (localStorage, chave "galint.rascunho.v1:<página>") o que foi digitado ou escolhido, a
 *   cada mudança e quando a aba fecha ou vai para o fundo. Só depois da primeira mexida: abrir a página não grava.
 * - Ao abrir a página de novo, devolve tudo e mostra "RASCUNHO RESTAURADO · DESCARTAR".
 * - Ao enviar: se a próxima página não mostrar aviso de erro (toast vermelho), o rascunho some; com erro, volta.
 *   Formulário com confirmação antes de enviar (prova real) só conta como enviado quando envia de verdade.
 * - Lista que chega depois (ex.: "Já no estoque", carregada do servidor) recebe o valor quando a opção aparecer.
 * - Fica fora: arquivo, senha, botões e campos ocultos (que o próprio sistema preenche). Validade: 3 dias.
 *
 * Uso: GalintRascunho.ligar(form, { chave, ignorar: ['id ou name'], coletarExtra, antesDeRestaurar })
 */
(function () {
    'use strict';

    const PREFIXO = 'galint.rascunho.v1:';
    const VALIDADE_MS = 3 * 24 * 60 * 60 * 1000;
    const TIPOS_FORA = new Set(['file', 'password', 'submit', 'button', 'reset', 'image', 'hidden']);

    const guardado = {
        ler(chave) {
            try {
                return JSON.parse(window.localStorage.getItem(PREFIXO + chave) || 'null');
            } catch (erro) {
                return null;
            }
        },
        gravar(chave, dados) {
            try {
                window.localStorage.setItem(PREFIXO + chave, JSON.stringify(dados));
                return true;
            } catch (erro) {
                return false;
            }
        },
        apagar(chave) {
            try {
                window.localStorage.removeItem(PREFIXO + chave);
            } catch (erro) {
                // navegador sem acesso ao armazenamento: nada a fazer
            }
        },
    };

    function campos(form, ignorar) {
        return Array.from(form.elements).filter((el) => {
            if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) return false;
            if (el instanceof HTMLInputElement && TIPOS_FORA.has(el.type)) return false;
            if (el.closest('[data-rascunho-ignorar]')) return false;
            const nome = el.name || el.id;
            return Boolean(nome) && !ignorar.has(el.name) && !ignorar.has(el.id);
        });
    }

    // Chave de cada campo: nome (ou id); caixa de marcar inclui o valor; nome repetido ganha "#n".
    function chaves(lista) {
        const contagem = {};
        return lista.map((el) => {
            const base = el.name || el.id;
            if (el.type === 'radio') return `r:${base}`;
            const chave = el.type === 'checkbox' ? `c:${base}|${el.value}` : `v:${base}`;
            contagem[chave] = (contagem[chave] || 0) + 1;
            return contagem[chave] > 1 ? `${chave}#${contagem[chave]}` : chave;
        });
    }

    function coletar(form, ignorar) {
        const lista = campos(form, ignorar);
        const nomes = chaves(lista);
        const dados = {};
        lista.forEach((el, indice) => {
            const chave = nomes[indice];
            if (el.type === 'radio') {
                if (el.checked) dados[chave] = el.value;
            } else if (el.type === 'checkbox') {
                dados[chave] = el.checked;
            } else if (el instanceof HTMLSelectElement && el.multiple) {
                dados[chave] = Array.from(el.selectedOptions).map((opcao) => opcao.value);
            } else {
                dados[chave] = el.value;
            }
        });
        return dados;
    }

    function disparar(el) {
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Seleção desenhada em botões (data-visual-select do Registro): marca o botão do valor restaurado.
    function sincronizarVisual(el) {
        if (!(el instanceof HTMLSelectElement) || !el.id || !window.CSS || !CSS.escape) return;
        const botao = document.querySelector(`[data-visual-select="${CSS.escape(el.id)}"] [data-select-value="${CSS.escape(el.value)}"]`);
        if (botao && !botao.classList.contains('is-selected')) botao.click();
    }

    function temOpcao(select, valor) {
        return Array.from(select.options).some((opcao) => opcao.value === valor);
    }

    // Opção que chega depois (carregada do servidor): entra assim que aparecer, por até 20 s.
    function esperarOpcao(select, valor) {
        const observador = new MutationObserver(() => {
            if (temOpcao(select, valor)) {
                observador.disconnect();
                select.value = valor;
                disparar(select);
            }
        });
        observador.observe(select, { childList: true, subtree: true });
        window.setTimeout(() => observador.disconnect(), 20000);
    }

    function aplicar(form, dados, ignorar) {
        const lista = campos(form, ignorar);
        const nomes = chaves(lista);
        lista.forEach((el, indice) => {
            const chave = nomes[indice];
            if (!Object.prototype.hasOwnProperty.call(dados, chave)) return;
            const valor = dados[chave];
            if (el.type === 'radio') {
                if (el.value === valor && !el.checked) {
                    el.checked = true;
                    disparar(el);
                }
                return;
            }
            if (el.type === 'checkbox') {
                if (el.checked !== Boolean(valor)) {
                    el.checked = Boolean(valor);
                    disparar(el);
                }
                return;
            }
            if (el instanceof HTMLSelectElement) {
                if (el.multiple) {
                    const marcados = new Set(Array.isArray(valor) ? valor : []);
                    Array.from(el.options).forEach((opcao) => { opcao.selected = marcados.has(opcao.value); });
                    disparar(el);
                    return;
                }
                if (el.value === valor) return;
                if (temOpcao(el, valor)) {
                    el.value = valor;
                    disparar(el);
                    sincronizarVisual(el);
                } else if (valor) {
                    esperarOpcao(el, valor);
                }
                return;
            }
            if (el.value !== valor) {
                el.value = valor;
                disparar(el);
            }
        });
    }

    function hora(ms) {
        try {
            return new Date(ms).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (erro) {
            return '';
        }
    }

    function criarBarra(form, chave) {
        const barra = document.createElement('div');
        barra.className = 'galint-rascunho small text-muted d-flex align-items-center gap-2 mb-1';
        barra.hidden = true;
        barra.innerHTML = '<i class="bi bi-cloud-check"></i><span data-rascunho-texto></span>'
            + '<button type="button" class="btn btn-link btn-sm p-0 text-danger fw-bold" data-rascunho-descartar hidden>DESCARTAR</button>';
        barra.querySelector('[data-rascunho-descartar]').addEventListener('click', () => {
            guardado.apagar(chave);
            window.location.reload();
        });
        form.insertBefore(barra, form.firstChild);
        return barra;
    }

    function mostrar(barra, tipo, quando) {
        barra.hidden = false;
        barra.querySelector('[data-rascunho-texto]').textContent = tipo === 'restaurado'
            ? `RASCUNHO RESTAURADO (${hora(quando)}) ·`
            : `RASCUNHO SALVO ÀS ${hora(quando)}`;
        barra.querySelector('[data-rascunho-descartar]').hidden = tipo !== 'restaurado';
    }

    function ligar(form, opcoes) {
        const config = opcoes || {};
        if (!(form instanceof HTMLFormElement) || !config.chave) return null;
        const chave = config.chave;
        const ignorar = new Set(config.ignorar || []);
        const barra = criarBarra(form, chave);

        let rascunho = guardado.ler(chave);
        if (rascunho && (!rascunho.salvoEm || Date.now() - rascunho.salvoEm > VALIDADE_MS)) {
            guardado.apagar(chave);
            rascunho = null;
        }
        if (rascunho && rascunho.enviadoEm) {
            // Enviado: aviso vermelho na página = deu erro (o rascunho volta); sem ele, deu certo (o rascunho some).
            if (document.querySelector('.galint-flash-toast.toast-danger')) {
                rascunho.enviadoEm = null;
                guardado.gravar(chave, rascunho);
            } else {
                guardado.apagar(chave);
                rascunho = null;
            }
        }

        let mexeu = false;
        let timer = null;
        const salvar = () => {
            if (!mexeu) return;
            const dados = { salvoEm: Date.now(), campos: coletar(form, ignorar), extra: config.coletarExtra ? config.coletarExtra() : null };
            if (guardado.gravar(chave, dados)) mostrar(barra, 'salvo', dados.salvoEm);
        };
        const agendar = () => {
            mexeu = true;
            window.clearTimeout(timer);
            timer = window.setTimeout(salvar, 400);
        };
        const marcarEnviado = () => {
            window.clearTimeout(timer);
            mexeu = true;
            salvar();
            const dados = guardado.ler(chave);
            if (dados) {
                dados.enviadoEm = Date.now();
                guardado.gravar(chave, dados);
            }
        };

        const vigiar = () => {
            form.addEventListener('input', agendar);
            form.addEventListener('change', agendar);
            window.addEventListener('pagehide', salvar);
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'hidden') salvar();
            });
            // Último a ouvir o envio: se outro script segurou (confirmação), ainda não foi enviado.
            window.addEventListener('submit', (evento) => {
                if (evento.target === form && !evento.defaultPrevented) marcarEnviado();
            });
            // Envio feito por script depois da confirmação (form.submit() não dispara o evento "submit").
            form.submit = function () {
                marcarEnviado();
                return HTMLFormElement.prototype.submit.call(form);
            };
        };

        if (rascunho && rascunho.campos) {
            Promise.resolve()
                .then(() => (config.antesDeRestaurar ? config.antesDeRestaurar(rascunho) : null))
                .catch(() => null)
                .then(() => {
                    aplicar(form, rascunho.campos, ignorar);
                    mostrar(barra, 'restaurado', rascunho.salvoEm);
                    vigiar();
                });
        } else {
            vigiar();
        }
        return { descartar: () => guardado.apagar(chave) };
    }

    window.GalintRascunho = { ligar };
})();
