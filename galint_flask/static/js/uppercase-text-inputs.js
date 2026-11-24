// Texto sempre em MAIÚSCULAS no site (desde 13/11/2026). Vale para toda página que usa o base.html ou o
// base.mako, inclusive os campos criados depois pelos modais: o aviso de "input" é ouvido no documento.
//
// Revisto em 24/11/2026, quando o usuário pediu "sempre que escrever, letras em maiúsculo, tanto no APK
// quanto no site". Na conferência, este script também convertia campos em que a caixa importa, e isso
// quebrava o que era salvo neles:
// - link de foto do item e outros endereços (type="url" e campos de texto como base_url): em maiúsculas
//   o caminho do arquivo muda e o link dá 404;
// - token do bot do Telegram (campo de texto comum): o bot para de responder;
// - e-mail.
// Agora esses ficam como digitados, assim como qualquer campo em que se cole um endereço (http://,
// https://, www.) e os marcados com data-keep-case. Senha nunca foi convertida (type="password").
(function () {
    const textInputTypes = new Set(['text', 'search', 'tel']);
    const keepCaseNames = /(url|link|e-?mail|token|secret|webhook|site|host)/i;

    function keepsCase(field) {
        if (field.closest('[data-keep-case]')) return true;
        if (field instanceof HTMLInputElement && !textInputTypes.has(field.type)) return true;
        const names = `${field.name || ''} ${field.id || ''} ${field.getAttribute('autocomplete') || ''}`;
        if (keepCaseNames.test(names)) return true;
        const value = field.value.trim();
        return value.includes('://') || /^www\./i.test(value);
    }

    document.addEventListener('input', (event) => {
        const field = event.target;
        if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement)) return;
        if (event.isComposing || field.readOnly || keepsCase(field)) return;

        const originalValue = field.value;
        const uppercaseValue = originalValue.toLocaleUpperCase('pt-BR');
        if (uppercaseValue === originalValue) return;

        const start = typeof field.selectionStart === 'number' ? field.selectionStart : null;
        const end = typeof field.selectionEnd === 'number' ? field.selectionEnd : null;
        field.value = uppercaseValue;

        if (start !== null && end !== null) {
            field.setSelectionRange(
                originalValue.slice(0, start).toLocaleUpperCase('pt-BR').length,
                originalValue.slice(0, end).toLocaleUpperCase('pt-BR').length,
            );
        }
    });
})();
