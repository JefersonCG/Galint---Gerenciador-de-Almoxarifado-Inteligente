/**
 * Formata quantidade de estoque com visualização inteligente de embalagens
 * Baseado em EmbalagemService.formatar_estoque() do backend Flask
 */

/**
 * @param {number} quantidade - Quantidade total em unidades base
 * @param {object} item - Objeto item com metadados de embalagem
 * @returns {string} Quantidade formatada (ex: "2 Latas + 16,67Kg")
 */
export function formatQuantityWithPackaging(quantidade, item) {
    if (!item || quantidade == null) {
        return `${quantidade || 0}`;
    }

    const qtd = Number(quantidade);
    if (!Number.isFinite(qtd)) return '0';

    // Sistema fracionado legacy (rolos com grandeza_referencia)
    if (item.grandeza_referencia && item.grandeza_referencia > 0 && 
        item.unidade && item.unidade.toLowerCase() === 'rolo') {
        const totalMetros = qtd * item.grandeza_referencia;
        const nomeRolo = qtd === 1 ? 'rolo' : 'rolos';
        return `${formatNumber(totalMetros)} metros (${formatNumber(qtd)} ${nomeRolo})`;
    }

    // Sistema de embalagens com volume em litros (lata/balde/bombona)
    if (item.litros_por_embalagem && item.litros_por_embalagem > 0 &&
        (item.tipo_embalagem_novo || item.unidade) &&
        ['lata', 'litro', 'balde', 'bombona'].includes((item.tipo_embalagem_novo || item.unidade || '').toLowerCase())) {
        
        const usaSistemaNovo = Boolean(item.tipo_embalagem_novo && item.unidades_por_embalagem);
        const qtdeEmbalagens = usaSistemaNovo ? (item.estoque_embalagens || 0) : qtd;
        const volumeTotal = qtdeEmbalagens * item.litros_por_embalagem;
        const nomeEmb = getNomeEmbalagem(item, qtdeEmbalagens);

        if (qtdeEmbalagens === 0) return '0 litros';
        if (qtdeEmbalagens === 1) return `${formatNumber(volumeTotal, 1)} litros (1 ${getNomeEmbalagemSingular(item)})`;
        return `${formatNumber(volumeTotal, 1)} litros (${formatNumber(qtdeEmbalagens)} ${nomeEmb})`;
    }

    // Sistema de embalagens com peso em kg (lata/balde/bombona com grandeza_referencia)
    if (item.grandeza_referencia && item.grandeza_referencia > 0 &&
        (item.tipo_embalagem_novo || item.unidade) &&
        ['lata', 'balde', 'bombona'].includes((item.tipo_embalagem_novo || item.unidade || '').toLowerCase())) {
        
        const usaSistemaNovo = Boolean(item.tipo_embalagem_novo && item.unidades_por_embalagem);
        const qtdeEmbalagens = usaSistemaNovo ? (item.estoque_embalagens || 0) : qtd;
        const pesoTotal = qtdeEmbalagens * item.grandeza_referencia;
        const nomeEmb = getNomeEmbalagem(item, qtdeEmbalagens);

        if (qtdeEmbalagens === 0) return '0 kg';
        if (qtdeEmbalagens === 1) return `${formatNumber(pesoTotal, 1)} kg (1 ${getNomeEmbalagemSingular(item)})`;
        return `${formatNumber(pesoTotal, 1)} kg (${formatNumber(qtdeEmbalagens)} ${nomeEmb})`;
    }

    // Sistema novo de embalagens (tipo_embalagem_novo + unidades_por_embalagem)
    if (item.tipo_embalagem_novo && item.unidades_por_embalagem && item.unidades_por_embalagem > 0) {
        const embalagens = item.estoque_embalagens || 0;
        const soltas = item.estoque_unidades_soltas || 0;
        const nomeEmb = getNomeEmbalagem(item, embalagens);
        const tipoLower = (item.tipo_embalagem_novo || '').toLowerCase();

        // Para rolos: mostrar em metros
        if (tipoLower === 'rolo') {
            const metrosPorRolo = item.unidades_por_embalagem;
            const totalMetros = (embalagens * metrosPorRolo) + soltas;

            if (embalagens === 0) return `${formatNumber(totalMetros)} metros`;
            if (soltas > 0) return `${formatNumber(totalMetros)} metros (${formatNumber(embalagens)} ${nomeEmb} + ${formatNumber(soltas)} metros)`;
            return `${formatNumber(totalMetros)} metros (${formatNumber(embalagens)} ${nomeEmb})`;
        }

        // Para pacotes/caixas: mostrar total de unidades
        if (['pacote', 'caixa'].includes(tipoLower)) {
            const unidadesPorEmb = item.unidades_por_embalagem;
            const totalUnidades = (embalagens * unidadesPorEmb) + soltas;

            if (embalagens === 0) return `${formatNumber(totalUnidades)} unidades`;
            if (soltas > 0) return `${formatNumber(totalUnidades)} unidades (${formatNumber(embalagens)} ${nomeEmb} + ${formatNumber(soltas)} unidades)`;
            return `${formatNumber(totalUnidades)} unidades (${formatNumber(embalagens)} ${nomeEmb})`;
        }

        // Sistema genérico de embalagens
        if (embalagens === 0) return `${formatNumber(soltas)} unidades`;
        if (soltas > 0) return `${formatNumber(embalagens)} ${nomeEmb} + ${formatNumber(soltas)} unidades`;
        return `${formatNumber(embalagens)} ${nomeEmb}`;
    }

    // Sistema legacy: rolo/pacote/caixa no campo unidade
    const unidadeLower = (item.unidade || '').toLowerCase().trim();
    if (['rolo', 'pacote', 'caixa'].includes(unidadeLower) && item.unidades_por_embalagem) {
        const saldoEmbalagens = qtd;
        const unidadesInternas = item.unidades_por_embalagem;
        const totalInterno = saldoEmbalagens * unidadesInternas;
        const nomeEmb = getNomeEmbalagemLegacy(unidadeLower, saldoEmbalagens);

        if (unidadeLower === 'rolo') {
            if (saldoEmbalagens === 0) return '0 metros';
            return `${formatNumber(totalInterno)} metros (${formatNumber(saldoEmbalagens)} ${nomeEmb})`;
        } else {
            if (saldoEmbalagens === 0) return '0 unidades';
            return `${formatNumber(totalInterno)} unidades (${formatNumber(saldoEmbalagens)} ${nomeEmb})`;
        }
    }

    // Fallback: apenas quantidade + unidade
    return `${formatNumber(qtd)} ${item.unidade || 'unidades'}`;
}

/**
 * Formata número removendo decimais desnecessários
 */
function formatNumber(value, decimals = null) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '0';
    
    if (decimals !== null) {
        return num.toFixed(decimals).replace(/\.?0+$/, '');
    }
    
    // Remove decimais se for inteiro
    if (Number.isInteger(num)) return num.toString();
    
    // Mantém até 2 decimais
    return num.toFixed(2).replace(/\.?0+$/, '');
}

/**
 * Retorna nome da embalagem (singular ou plural)
 */
function getNomeEmbalagem(item, quantidade) {
    if (quantidade === 1) return getNomeEmbalagemSingular(item);
    return getNomeEmbalagemPlural(item);
}

/**
 * Retorna nome singular da embalagem
 */
function getNomeEmbalagemSingular(item) {
    const tipo = (item.tipo_embalagem_novo || item.unidade || '').toLowerCase();
    const nomes = {
        'lata': 'lata',
        'bombona': 'bombona',
        'rolo': 'rolo',
        'pacote': 'pacote',
        'caixa': 'caixa',
        'litro': 'litro',
        'balde': 'balde',
    };
    return nomes[tipo] || 'embalagem';
}

/**
 * Retorna nome plural da embalagem
 */
function getNomeEmbalagemPlural(item) {
    const tipo = (item.tipo_embalagem_novo || item.unidade || '').toLowerCase();
    const nomes = {
        'lata': 'latas',
        'bombona': 'bombonas',
        'rolo': 'rolos',
        'pacote': 'pacotes',
        'caixa': 'caixas',
        'litro': 'litros',
        'balde': 'baldes',
    };
    return nomes[tipo] || 'embalagens';
}

/**
 * Retorna nome de embalagem legacy (sistema antigo)
 */
function getNomeEmbalagemLegacy(unidadeLower, quantidade) {
    const nomes = {
        'rolo': quantidade === 1 ? 'rolo' : 'rolos',
        'pacote': quantidade === 1 ? 'pacote' : 'pacotes',
        'caixa': quantidade === 1 ? 'caixa' : 'caixas',
    };
    return nomes[unidadeLower] || unidadeLower;
}

/**
 * Calcula embalagens completas + resto de uma quantidade
 * Exemplo: 66.67kg com 25kg/embalagem = "2 Latas + 16,67Kg"
 */
export function calcularEmbalagemEResto(quantidade, unidadesPorEmbalagem, nomeEmbalagem, unidade) {
    if (!unidadesPorEmbalagem || unidadesPorEmbalagem <= 0) {
        return `${formatNumber(quantidade)} ${unidade || ''}`;
    }

    const qtd = Number(quantidade);
    if (!Number.isFinite(qtd) || qtd <= 0) {
        return `0 ${unidade || ''}`;
    }

    const embalagemCompletas = Math.floor(qtd / unidadesPorEmbalagem);
    const resto = qtd - (embalagemCompletas * unidadesPorEmbalagem);

    const nomeEmb = embalagemCompletas === 1 ? 
        (nomeEmbalagem || 'embalagem') : 
        getNomeEmbalagemPlural({ tipo_embalagem_novo: nomeEmbalagem });

    if (resto < 0.01) {
        // Sem resto significativo
        return `${embalagemCompletas} ${nomeEmb}`;
    }

    if (embalagemCompletas === 0) {
        // Só resto
        return `${formatNumber(resto, 2)} ${unidade || ''}`;
    }

    // Embalagens + resto
    return `${embalagemCompletas} ${nomeEmb} + ${formatNumber(resto, 2)}${unidade || ''}`;
}
