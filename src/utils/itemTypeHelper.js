/**
 * Utilitários para determinar tipo de item (Ferramenta vs Material)
 * Alinhado com a lógica do backend Flask (telegram_service.py)
 */

/**
 * Determina se um item é ferramenta baseado na categoria
 * @param {string} categoria - Categoria do item
 * @returns {boolean} true se for ferramenta
 */
export function isFerramenta(categoria) {
    if (!categoria) return false;
    const cat = String(categoria).toLowerCase().trim();
    return cat.includes('ferrament');
}

/**
 * Retorna o tipo do item para exibição
 * @param {string} categoria - Categoria do item
 * @returns {string} "🔧 FERRAMENTA" ou "📦 MATERIAL"
 */
export function getTipoItemDisplay(categoria) {
    return isFerramenta(categoria) ? '🔧 FERRAMENTA' : '📦 MATERIAL';
}

/**
 * Retorna o tipo simplificado
 * @param {string} categoria - Categoria do item
 * @returns {string} "Ferramenta" ou "Material"
 */
export function getTipoItemSimple(categoria) {
    return isFerramenta(categoria) ? 'Ferramenta' : 'Material';
}

/**
 * Retorna o emoji apropriado baseado na categoria
 * @param {string} categoria - Categoria do item
 * @returns {string} Emoji representativo
 */
export function getEmojiCategoria(categoria) {
    if (!categoria) return '📦';
    
    const cat = String(categoria).toLowerCase().trim();
    
    const emojiMap = {
        'ferramentas': '🔧',
        'ferramenta': '🔧',
        'material elétrico': '⚡',
        'material eletrico': '⚡',
        'eletrico': '⚡',
        'elétrico': '⚡',
        'material hidráulico': '🚰',
        'material hidraulico': '🚰',
        'hidraulico': '🚰',
        'hidráulico': '🚰',
        'material piscina': '🏊',
        'piscina': '🏊',
        'equipamento': '⚙️',
        'liquido': '💧',
        'líquido': '💧',
    };
    
    // Busca exata primeiro
    if (emojiMap[cat]) return emojiMap[cat];
    
    // Busca por substring
    for (const [key, emoji] of Object.entries(emojiMap)) {
        if (cat.includes(key)) return emoji;
    }
    
    return '📦';
}

export default {
    isFerramenta,
    getTipoItemDisplay,
    getTipoItemSimple,
    getEmojiCategoria,
};
