// Contas da devolução (2.4.1, 26/11/2026), separadas da tela para serem testadas no Node.
// Pedido do usuário: "sempre que for devolução, reconheça se é ferramenta, fracionado ou item unitário;
// se devolver uma lata de tinta pela metade, tenho que pôr que foi metade". O servidor diz o tipo
// (/api/mobile/devolucao/tipo/<codigo>); sem resposta dele, vale o palpite local abaixo.
import { factorFromItem, toNumber } from './provaReal';

const SINGULAR = { lata: 'lata', balde: 'balde', bombona: 'bombona', galao: 'galão', 'galão': 'galão', saco: 'saco', rolo: 'rolo', caixa: 'caixa', frasco: 'frasco', pacote: 'pacote' };
const PLURAL = { lata: 'latas', balde: 'baldes', bombona: 'bombonas', galao: 'galões', 'galão': 'galões', saco: 'sacos', rolo: 'rolos', caixa: 'caixas', frasco: 'frascos', pacote: 'pacotes' };
const FRACIONADAS = { litro: 'L', litros: 'L', l: 'L', lt: 'L', quilo: 'kg', quilos: 'kg', kg: 'kg', metro: 'm', metros: 'm', m: 'm', mt: 'm' };
const CODIGO = { L: 'litro', kg: 'quilo', m: 'metro' };

export const fmt = (value) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 3 });

export const isTool = (categoria) => String(categoria || '').toLowerCase().includes('ferrament');

// Palpite sem o servidor: ferramenta pela categoria; fracionado quando a unidade é litro, quilo ou metro.
export function localTipo(item) {
    if (isTool(item?.categoria)) return { tipo: 'ferramenta', unidade: 'unidade', unidade_curta: 'un', decimal: false, embalagem: null, conteudo: null };
    const curta = FRACIONADAS[String(item?.unidade || '').trim().toLowerCase()];
    if (!curta) return { tipo: 'unitario', unidade: 'unidade', unidade_curta: 'un', decimal: false, embalagem: null, conteudo: null };
    const pack = factorFromItem(item);
    const conteudo = pack.packaged && pack.factor > 0 ? pack.factor : null;
    return { tipo: 'fracionado', unidade: CODIGO[curta], unidade_curta: curta, decimal: true, embalagem: conteudo ? String(pack.docUnit || '').toLowerCase() : null, conteudo };
}

// Sem resposta do servidor (sem rede ou GALINT ainda sem a rota nova): só quantidade inteira. O servidor
// antigo fazia int(quantidade) e gravaria 4 L para 4,5 L sem avisar.
export function tipoSemServidor(item) {
    const local = localTipo(item);
    return local.tipo === 'fracionado' ? { ...local, decimal: false, embalagem: null, conteudo: null } : local;
}

export function nomeEmbalagem(embalagem, quantidade) {
    const key = String(embalagem || '').trim().toLowerCase();
    if (Number(quantidade) <= 1) return SINGULAR[key] || key;
    return PLURAL[key] || `${key}s`;
}

// 0,5 → "½"; 1,75 → "1¾"; o resto com vírgula.
export function fracaoTexto(quantidade) {
    const q = Number(quantidade);
    if (!Number.isFinite(q)) return '';
    const inteiro = Math.floor(q + 1e-9);
    const resto = q - inteiro;
    const simbolo = [[0.25, '¼'], [0.5, '½'], [0.75, '¾']].find(([valor]) => Math.abs(resto - valor) < 1e-6);
    if (simbolo) return `${inteiro > 0 ? inteiro : ''}${simbolo[1]}`;
    return fmt(q);
}

export function parseQuantidade(texto, decimal) {
    const limpo = String(texto ?? '').replace(decimal ? /[^0-9.,]/g : /[^0-9]/g, '');
    return { texto: limpo, valor: limpo ? toNumber(limpo) : NaN };
}

// Quantidade que vai ao servidor, na unidade de devolução (½ lata de 18 L = 9).
export function quantidadeBase(tipo, quantidade) {
    const q = Number(quantidade);
    if (!(q > 0)) return NaN;
    if (tipo?.tipo === 'fracionado' && tipo.conteudo > 0) return Number((q * tipo.conteudo).toFixed(3));
    return tipo?.decimal ? Number(q.toFixed(3)) : q;
}

// '' quando pode mandar; senão o que falta (o botão mostra isso).
export function faltaNaQuantidade(tipo, quantidade) {
    const q = Number(quantidade);
    if (!(q > 0)) return 'Falta a quantidade';
    if (!tipo?.decimal && !Number.isInteger(q)) return 'Quantidade inteira';
    return '';
}

// Texto da quantidade para a janela de conclusão e o WhatsApp: "½ lata (9 L)", "2,5 L", "3 unidades".
export function quantidadeTexto(tipo, quantidade, unidadeItem) {
    const q = Number(quantidade);
    if (tipo?.tipo === 'fracionado' && tipo.conteudo > 0) {
        return `${fracaoTexto(q)} ${nomeEmbalagem(tipo.embalagem, q)} (${fmt(quantidadeBase(tipo, q))} ${tipo.unidade_curta})`;
    }
    if (tipo?.tipo === 'fracionado') return `${fmt(q)} ${tipo.unidade_curta}`;
    const unidade = String(unidadeItem || 'unidade').trim().toLowerCase() || 'unidade';
    return `${q} ${q === 1 ? unidade : unidade === 'unidade' ? 'unidades' : unidade}`;
}
