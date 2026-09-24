/**
 * GalintCore — utilitários compartilhados pelas telas do GALINT.
 *
 * Antes deste arquivo, funções como escapeHtml, normalizeAutocompleteText e
 * formatCurrencyBR estavam copiadas em mais de dez templates, cada cópia com
 * pequenas diferenças (algumas imprimiam "undefined" quando o valor vinha
 * nulo). Aqui existe uma versão só, carregada pelo layout base.
 */
(function (window, document) {
    'use strict';

    var LOCALE = 'pt-BR';

    /** Escapa texto para interpolação segura em HTML. Null e undefined viram string vazia. */
    function escapeHtml(value) {
        var elemento = document.createElement('div');
        elemento.textContent = value === null || value === undefined ? '' : String(value);
        return elemento.innerHTML;
    }

    /** Texto comparável em buscas: sem acento, minúsculo e sem espaços nas pontas. */
    function normalizeText(value) {
        return String(value === null || value === undefined ? '' : value)
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .toLowerCase()
            .trim();
    }

    /** Valor em reais. Por padrão devolve vazio para zero/negativo, como as telas de saída esperam. */
    function formatCurrencyBR(value, options) {
        var config = options || {};
        var numero = Number(value);
        if (!Number.isFinite(numero)) {
            return '';
        }
        if (numero <= 0 && config.allowZero !== true) {
            return '';
        }
        return numero.toLocaleString(LOCALE, {
            style: 'currency',
            currency: 'BRL',
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    /** Número com separador brasileiro, escondendo casas decimais desnecessárias. */
    function formatNumberBR(value, maxDecimals) {
        var numero = Number(value);
        if (!Number.isFinite(numero)) {
            return '0';
        }
        var casas = Number.isFinite(Number(maxDecimals)) ? Number(maxDecimals) : 2;
        var precisaDecimal = Math.abs(numero - Math.round(numero)) > 1e-6;
        return numero.toLocaleString(LOCALE, {
            minimumFractionDigits: 0,
            maximumFractionDigits: precisaDecimal ? casas : 0
        });
    }

    /**
     * Foca um elemento sem arrastar a página.
     * Usado depois de redesenhar listas: sem preventScroll o navegador rola até
     * o campo focado e o operador perde o lugar onde estava trabalhando.
     */
    function focusWithoutScroll(element) {
        if (!element || typeof element.focus !== 'function') {
            return false;
        }
        try {
            element.focus({ preventScroll: true });
        } catch (error) {
            element.focus();
        }
        return true;
    }

    /** Data/hora no formato usado pelas telas (24/09/2026 09:42). */
    function formatDateTimeBR(value) {
        if (!value) {
            return '';
        }
        var data = value instanceof Date ? value : new Date(value);
        if (Number.isNaN(data.getTime())) {
            return '';
        }
        return data.toLocaleString(LOCALE, {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    window.GalintCore = {
        escapeHtml: escapeHtml,
        normalizeText: normalizeText,
        formatCurrencyBR: formatCurrencyBR,
        formatNumberBR: formatNumberBR,
        formatDateTimeBR: formatDateTimeBR,
        focusWithoutScroll: focusWithoutScroll
    };
}(window, document));
