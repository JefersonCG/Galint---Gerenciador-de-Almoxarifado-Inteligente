// Prova real do lançamento de NF no app (2.2.8, 24/11/2026). Mesma conta de
// galint_flask/static/js/nf-prova-real.js (site).
//
// Pedido do usuário depois da NF 617377: "uma calculadora em tempo real de prova real e, ao final,
// questionar se o cálculo é realmente aquele". Para item com embalagem, o servidor lê a quantidade da NF
// em embalagens (rolos, caixas): a 2.2.3-2.2.7 mostrava "Quantidade (metro)" e 40 virava 40 rolos.
const PLURAL = {
    rolo: 'rolos', caixa: 'caixas', pacote: 'pacotes', fardo: 'fardos', balde: 'baldes', lata: 'latas',
    bombona: 'bombonas', saco: 'sacos', litro: 'litros', l: 'litros', lt: 'litros', par: 'pares',
    unidade: 'unidades', un: 'unidades', und: 'unidades', metro: 'metros', m: 'metros', quilo: 'quilos', kg: 'kg',
};
const SINGULAR = { l: 'litro', lt: 'litro', un: 'unidade', und: 'unidade', m: 'metro', kg: 'kg' };

export function toNumber(value) {
    if (value === null || value === undefined || value === '') return NaN;
    if (typeof value === 'number') return value;
    let text = String(value).trim();
    if (text.includes(',')) text = text.replace(/\./g, '').replace(',', '.');
    return Number(text);
}

const key = (unit) => String(unit || '').trim().toLowerCase();

export function unitLabel(unit, quantity) {
    const k = key(unit) || 'unidade';
    if (Math.abs(quantity) === 1) return SINGULAR[k] || k;
    return PLURAL[k] || `${k}s`;
}

const fmt = (value) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 4 });
const brl = (value) => `R$ ${Number(value).toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`;

// O servidor manda fator_embalagem/unidade_documental/converte_embalagem (mesma regra da gravação);
// sem eles (antes da 1ª sincronização completa), a mesma regra de resolve_packaging_factor.
export function factorFromItem(item) {
    if (!item) return { factor: 0, docUnit: '', baseUnit: '', packaged: false };
    const baseUnit = item.unidade || '';
    if (item.fator_embalagem !== undefined && item.fator_embalagem !== null) {
        const factor = toNumber(item.fator_embalagem) || 0;
        return { factor, docUnit: item.unidade_documental || baseUnit, baseUnit, packaged: Boolean(item.converte_embalagem) && factor > 0 && factor !== 1 };
    }
    const tipo = key(item.tipo_embalagem_novo);
    const un = toNumber(item.unidades_por_embalagem) || 0;
    const factor = ['pacote', 'caixa', 'fardo', 'rolo', 'lata', 'balde', 'bombona', 'saco', 'litro'].includes(tipo) ? un : 0;
    const noPackaging = ['un', 'unidade', 'par'].includes(key(baseUnit)) && factor <= 1;
    const packaged = !noPackaging && Boolean(tipo) && factor > 0 && factor !== 1;
    return { factor, docUnit: packaged ? tipo : baseUnit, baseUnit, packaged };
}

export function computeProof({ quantity, unitPrice, docUnit, factor, baseUnit, packaged }) {
    const q = toNumber(quantity);
    if (!(q > 0)) return null;
    const f = toNumber(factor) || 0;
    const hasPackaging = Boolean(packaged) && f > 0 && f !== 1;
    const baseQty = hasPackaging ? q * f : q;
    const price = toNumber(unitPrice);
    const total = price >= 0 ? Number((q * price).toFixed(2)) : null;
    const stockText = hasPackaging
        ? `${fmt(q)} ${unitLabel(docUnit, q)} × ${fmt(f)} = ${fmt(baseQty)} ${unitLabel(baseUnit, baseQty)} no estoque`
        : `${fmt(q)} ${unitLabel(baseUnit || docUnit, q)} no estoque`;
    const moneyText = total !== null ? `${fmt(q)} × ${brl(price)} = ${brl(total)}` : '';
    const suspicious = Boolean(hasPackaging && f > 1 && q >= f && Math.abs(q / f - Math.round(q / f)) < 1e-9);
    const hint = suspicious ? `Se a NF diz ${fmt(q)} ${unitLabel(baseUnit, q)}, são ${fmt(q / f)} ${unitLabel(docUnit, q / f)}.` : '';
    return { quantity: q, baseQty, hasPackaging, stockText, moneyText, total, suspicious, hint };
}
