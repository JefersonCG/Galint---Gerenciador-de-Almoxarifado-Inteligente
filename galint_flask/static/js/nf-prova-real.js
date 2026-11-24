// Prova real dos lançamentos de NF (24/11/2026).
//
// Pedido do usuário depois da NF 617377: "tem que colocar uma calculadora em tempo real de prova real e
// ao final ela questionar se o cálculo é realmente aquele". Lá, 2.000 parafusos entraram como 2.000
// CAIXAS de 1.000 (2 milhões no estoque) e 4 rolos de fita como 40 rolos: para item com embalagem, o
// servidor sempre lê a quantidade da NF em embalagens, e a tela não deixava isso claro.
//
// - compute(): a conta que o servidor fará: "2 caixas × 1.000 = 2.000 unidades no estoque" e
//   "2 × R$ 80,00 = R$ 160,00"; marca como suspeita a quantidade que é múltiplo exato do conteúdo da
//   embalagem (sinal de que foi digitada em unidades).
// - factorFromItem(): usa fator_embalagem/unidade_documental que o servidor manda (mesma regra da
//   gravação); sem eles, a mesma regra de resolve_packaging_factor, sem a dedução pela descrição.
// - guardSubmit(): ao enviar, abre a janela "Prova real" e só grava depois de "Confirmar".
(function () {
    const PLURAL = {
        rolo: 'rolos', caixa: 'caixas', pacote: 'pacotes', fardo: 'fardos', balde: 'baldes', lata: 'latas',
        bombona: 'bombonas', saco: 'sacos', litro: 'litros', l: 'litros', lt: 'litros', par: 'pares',
        unidade: 'unidades', un: 'unidades', und: 'unidades', metro: 'metros', m: 'metros', quilo: 'quilos', kg: 'kg',
    };
    const SINGULAR = { l: 'litro', lt: 'litro', un: 'unidade', und: 'unidade', m: 'metro', kg: 'kg' };

    const toNumber = (value) => {
        if (value === null || value === undefined || value === '') return NaN;
        if (typeof value === 'number') return value;
        let text = String(value).trim();
        if (text.includes(',')) text = text.replace(/\./g, '').replace(',', '.');
        return Number(text);
    };
    const key = (unit) => String(unit || '').trim().toLowerCase();
    const unitLabel = (unit, quantity) => {
        const k = key(unit) || 'unidade';
        if (Math.abs(quantity) === 1) return SINGULAR[k] || k;
        return PLURAL[k] || `${k}s`;
    };
    const fmt = (value) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 4 });
    const brl = (value) => Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

    function mirrorFactor(item) {
        const tipo = key(item.tipo_embalagem_novo);
        const un = toNumber(item.unidades_por_embalagem) || 0;
        const lt = toNumber(item.litros_por_embalagem) || 0;
        const gr = toNumber(item.grandeza_referencia) || 0;
        if (['pacote', 'caixa', 'fardo', 'rolo'].includes(tipo) && un > 0) return un;
        if (['lata', 'balde', 'bombona', 'litro'].includes(tipo)) return lt || gr || un || 0;
        if (tipo === 'saco') return gr || un || 0;
        return lt || gr || toNumber(item.capacidade_embalagem) || 0;
    }

    function factorFromItem(item) {
        if (!item || typeof item !== 'object') return { factor: 0, docUnit: '', baseUnit: '' };
        const baseUnit = item.unidade_cadastro || item.unidade || '';
        const tipoKey = key(item.tipo_embalagem_novo);
        if (item.fator_embalagem !== undefined && item.fator_embalagem !== null) {
            const factor = toNumber(item.fator_embalagem) || 0;
            const docUnit = item.unidade_documental || '';
            // Item com embalagem cadastrada converte mesmo quando a embalagem tem o nome da unidade
            // (ex.: fita zebrada com unidade "Rolo" e embalagem "rolo" de 200 m).
            const packaged = factor > 0 && factor !== 1 && (item.converte_embalagem !== undefined
                ? Boolean(item.converte_embalagem) && item.converte_embalagem !== 'false'
                : Boolean(tipoKey) && key(docUnit) === tipoKey);
            return { factor, docUnit, baseUnit, packaged };
        }
        const factor = mirrorFactor(item);
        const tipo = key(item.tipo_embalagem_novo);
        const baseKey = key(baseUnit);
        const noPackaging = ['un', 'unidade', 'par'].includes(baseKey) && factor <= 1;
        const packaged = !noPackaging && Boolean(tipo) && factor > 0 && factor !== 1;
        return { factor: noPackaging ? 0 : factor, docUnit: packaged ? tipo : baseUnit, baseUnit, packaged };
    }

    function compute({ quantity, unitPrice, docUnit, factor, baseUnit, packaged }) {
        const q = toNumber(quantity);
        if (!(q > 0)) return null;
        const f = toNumber(factor) || 0;
        const hasPackaging = typeof packaged === 'boolean'
            ? packaged && f > 0 && f !== 1
            : Boolean(f > 0 && f !== 1 && key(docUnit) && key(docUnit) !== key(baseUnit));
        const baseQty = hasPackaging ? q * f : q;
        const price = toNumber(unitPrice);
        const total = price >= 0 ? Number((q * price).toFixed(2)) : null;
        const stockText = hasPackaging
            ? `${fmt(q)} ${unitLabel(docUnit, q)} × ${fmt(f)} = ${fmt(baseQty)} ${unitLabel(baseUnit, baseQty)} no estoque`
            : `${fmt(q)} ${unitLabel(baseUnit || docUnit, q)} no estoque`;
        const moneyText = total !== null ? `${fmt(q)} × ${brl(price)} = ${brl(total)}` : '';
        const suspicious = Boolean(hasPackaging && f > 1 && q >= f && Math.abs(q / f - Math.round(q / f)) < 1e-9);
        const hint = suspicious
            ? `Se a NF diz ${fmt(q)} ${unitLabel(baseUnit, q)}, são ${fmt(q / f)} ${unitLabel(docUnit, q / f)}.`
            : '';
        return { quantity: q, baseQty, hasPackaging, stockText, moneyText, total, suspicious, hint };
    }

    let modal = null;
    function ensureModal() {
        if (modal) return modal;
        const element = document.createElement('div');
        element.className = 'modal fade';
        element.tabIndex = -1;
        element.setAttribute('aria-hidden', 'true');
        element.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content galint-bs-modal galint-bs-modal--amber">
                    <div class="modal-header">
                        <h5 class="modal-title">Prova real</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                    </div>
                    <div class="modal-body"><div data-prova-lines class="d-grid gap-2"></div>
                        <div class="fw-semibold mt-3">O cálculo é este mesmo?</div></div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Corrigir</button>
                        <button type="button" class="btn btn-primary" data-prova-ok>Confirmar</button>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(element);
        modal = { element, instance: window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(element) : null };
        return modal;
    }

    const escapeHtml = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    function ask(lines) {
        const { element, instance } = ensureModal();
        const body = element.querySelector('[data-prova-lines]');
        body.innerHTML = lines.map((line) => `
            <div class="${line.suspicious ? 'alert alert-warning mb-0 py-2' : ''}">
                ${line.label ? `<div class="fw-semibold">${escapeHtml(line.label)}</div>` : ''}
                <div>${escapeHtml(line.stockText)}</div>
                ${line.moneyText ? `<div>${escapeHtml(line.moneyText)}</div>` : ''}
                ${line.suspicious ? `<div class="small mt-1">${escapeHtml(line.hint)}</div>` : ''}
            </div>`).join('');
        if (!instance) {
            const text = lines.map((line) => [line.label, line.stockText, line.moneyText, line.hint].filter(Boolean).join('\n')).join('\n\n');
            return Promise.resolve(window.confirm(`Prova real\n\n${text}\n\nO cálculo é este mesmo?`));
        }
        return new Promise((resolve) => {
            let answered = false;
            const okButton = element.querySelector('[data-prova-ok]');
            const onOk = () => { answered = true; instance.hide(); };
            const onHidden = () => {
                okButton.removeEventListener('click', onOk);
                element.removeEventListener('hidden.bs.modal', onHidden);
                resolve(answered);
            };
            okButton.addEventListener('click', onOk);
            element.addEventListener('hidden.bs.modal', onHidden);
            instance.show();
        });
    }

    // Registre depois das validações do formulário: se alguma já barrou o envio, a prova real não abre.
    function guardSubmit(form, buildLines) {
        if (!form || form.dataset.provaRealBound === '1') return;
        form.dataset.provaRealBound = '1';
        form.addEventListener('submit', (event) => {
            if (event.defaultPrevented) return;
            if (form.dataset.provaRealOk === '1') {
                delete form.dataset.provaRealOk;
                return;
            }
            const lines = (buildLines() || []).filter(Boolean);
            if (!lines.length) return;
            event.preventDefault();
            const submitter = event.submitter || null;
            ask(lines).then((confirmed) => {
                if (!confirmed) return;
                form.dataset.provaRealOk = '1';
                if (typeof form.requestSubmit === 'function') form.requestSubmit(submitter || undefined);
                else form.submit();
            });
        });
    }

    window.GalintProvaReal = { compute, factorFromItem, guardSubmit, ask, unitLabel, toNumber };
})();
