// Compartilhar uma saída ou devolução no WhatsApp (2.2.1, pedido do usuário em 21/11/2026: "todas
// as saídas com a opção de compartilhar para o WhatsApp"). Desde a 2.2.2 vai a FOTO do item com o
// texto como legenda, pelo módulo nativo GalintShare (android/.../GalintShareModule.kt); sem o
// módulo, sem foto ou sem WhatsApp, cai no texto pelo link do WhatsApp ou no compartilhar do Android.
import { Linking, NativeModules, Share } from 'react-native';

function nowLabel() {
    try {
        return new Date().toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
        });
    } catch (error) {
        return new Date().toISOString().slice(0, 16).replace('T', ' ');
    }
}

export function unitLabel(quantity, unit) {
    const base = String(unit || 'unidade').trim().toLowerCase() || 'unidade';
    if (Number(quantity) === 1) return base;
    if (base === 'unidade') return 'unidades';
    return base;
}

// items: [{ descricao, codigo, quantidade (texto pronto) }]
export function withdrawalMessage({ items, retiradoPor, local, custodia, registradoPor }) {
    const list = Array.isArray(items) ? items : [];
    const tools = list.some((entry) => entry?.ferramenta);
    const lines = [tools && list.length === 1 ? '🔧 *Retirada de ferramenta*' : '📤 *Saída de material*'];
    if (list.length === 1) {
        lines.push(`Item: ${list[0].descricao}`);
        lines.push(`Quantidade: ${list[0].quantidade}`);
    } else {
        lines.push(`Itens (${list.length}):`);
        list.forEach((entry) => lines.push(`• ${entry.descricao} — ${entry.quantidade}`));
    }
    if (retiradoPor) lines.push(`Retirado por: ${retiradoPor}`);
    if (local) lines.push(`Local: ${local}`);
    if (custodia) lines.push(`Custódia: ${custodia}`);
    lines.push(`Data: ${nowLabel()}`);
    if (registradoPor) lines.push(`Registrado por: ${registradoPor}`);
    return lines.join('\n');
}

export function returnMessage({ descricao, quantidade, devolvidoPor, ferramenta, registradoPor }) {
    const lines = [ferramenta ? '🔧 *Devolução de ferramenta*' : '📥 *Devolução de material*'];
    lines.push(`Item: ${descricao}`);
    lines.push(`Quantidade: ${quantidade}`);
    if (devolvidoPor) lines.push(`Devolvido por: ${devolvidoPor}`);
    lines.push(`Data: ${nowLabel()}`);
    if (registradoPor) lines.push(`Registrado por: ${registradoPor}`);
    return lines.join('\n');
}

// photoUrl: endereço completo da foto do item (http://servidor/static/...), ou vazio.
// photoUrls (2.5.0): várias fotos numa mensagem só (saída de vários itens), com o texto junto.
export async function shareOnWhatsApp(text, photoUrl = null, photoUrls = null) {
    const message = String(text || '');
    const nativeShare = NativeModules?.GalintShare;
    const fotos = Array.isArray(photoUrls) ? photoUrls.filter(Boolean) : [];
    if (fotos.length > 1 && nativeShare?.shareManyToWhatsApp) {
        try {
            await nativeShare.shareManyToWhatsApp(message, fotos);
            return true;
        } catch (error) {
            // segue para uma foto só
        }
    }
    if (nativeShare?.shareToWhatsApp) {
        try {
            await nativeShare.shareToWhatsApp(message, photoUrl || null);
            return true;
        } catch (error) {
            // segue para o texto puro
        }
    }
    try {
        await Linking.openURL(`whatsapp://send?text=${encodeURIComponent(message)}`);
        return true;
    } catch (error) {
        try {
            await Share.share({ message });
            return true;
        } catch (shareError) {
            return false;
        }
    }
}
