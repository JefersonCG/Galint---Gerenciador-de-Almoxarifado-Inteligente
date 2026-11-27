// Contas da Fila de saída (2.4.0, 25/11/2026), separadas da tela para serem testadas no Node.
// Item com embalagem sai na embalagem ou na unidade base; a rota /api/mobile/retirar_multipla recebe a
// quantidade na unidade base (o saldo do GALINT), como o site mostra: "3 pacotes = 3000 unidades".
import { factorFromItem, unitLabel } from './provaReal';

export const fmt = (value) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 3 });

export const isTool = (categoria) => String(categoria || '').toLowerCase().includes('ferrament');

// O que a fila guarda de cada item: o suficiente para mostrar, conferir o saldo e mandar.
export function snapshot(item) {
    const embalagem = factorFromItem(item);
    return {
        codigo: String(item?.id || item?.codigo_barras || item?.codigo || '').trim(),
        descricao: String(item?.descricao || item?.nome || 'Item').trim(),
        categoria: item?.categoria || '',
        unidade: embalagem.baseUnit || item?.unidade || 'Unidade',
        embalagem: embalagem.packaged ? embalagem.docUnit : '',
        fator: embalagem.packaged ? embalagem.factor : 0,
        saldo: Number(item?.quantidade ?? item?.saldo ?? 0) || 0,
        foto_url: item?.foto_url || null,
    };
}

export const baseQty = (linha) => (linha.modo === 'embalagem' && linha.fator > 0 ? linha.quantidade * linha.fator : linha.quantidade);

export function qtyText(linha) {
    const q = linha.quantidade;
    if (linha.modo === 'embalagem' && linha.fator > 0) {
        const base = baseQty(linha);
        return `${fmt(q)} ${unitLabel(linha.embalagem, q)} = ${fmt(base)} ${unitLabel(linha.unidade, base)}`;
    }
    return `${fmt(q)} ${unitLabel(linha.unidade, q)}`;
}

// A rota só aceita número inteiro na unidade base (metro aceita fração); o resto fica para o site.
export function baseQtyAccepted(linha) {
    const base = baseQty(linha);
    return Number.isInteger(base) || String(linha.unidade || '').trim().toLowerCase() === 'metro';
}

// Item em litro ou quilo com embalagem só sai em embalagem inteira no fluxo comum (o servidor recusa
// "Materiais em kg/L no fluxo comum só podem sair por embalagem completa"); o avulso é a Saída Fracionada do site.
export function onlyWholePackages(linha) {
    return linha.fator > 0 && ['litro', 'litros', 'l', 'quilo', 'quilos', 'kg'].includes(String(linha.unidade || '').trim().toLowerCase());
}

// 2.6.1: quantidade dita no comando de voz ("retirada lâmpada kian 6 unidades", "cimento 2 sacos") na linha do item.
// { quantidade, modo }; { fracionada: true } para "2 e meio" (a Retirada do app só tira inteiro); null quando a
// unidade dita não serve para o item ("2 litros" de tinta que só sai em lata inteira) ou nada foi dito.
// 2.6.2: sem unidade dita ("5 papel toalhas") num item com embalagem (pacote com 1.000), `perguntar: true`: a tela
// pergunta "5 pacotes ou 5 unidades?".
export function quantidadeDaFala(linha, quantidade, modo) {
    const q = Number(quantidade);
    if (quantidade == null || !(q > 0)) return null;
    if (!Number.isInteger(q)) return { fracionada: true };
    if (!(linha?.fator > 0)) return { quantidade: q, modo: 'base' };
    if (modo === 'embalagem') return { quantidade: q, modo: 'embalagem' };
    if (onlyWholePackages(linha)) return modo === 'base' ? null : { quantidade: q, modo: 'embalagem' };
    return { quantidade: q, modo: 'base', perguntar: modo == null };
}

// '' | 'Estoque zera com esta saída' | 'Saldo insuficiente: ...' — soma o mesmo item em toda a fila.
export function stockWarning(pedido, saldo, unidade) {
    if (!(pedido > 0)) return '';
    if (pedido > saldo + 1e-6) return `Saldo insuficiente: tem ${fmt(saldo)} ${unitLabel(unidade, saldo)}`;
    if (Math.abs(pedido - saldo) < 1e-6) return 'Estoque zera com esta saída';
    return '';
}
