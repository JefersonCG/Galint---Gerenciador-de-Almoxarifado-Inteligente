// Nome padrão no cadastro (24/11/2026).
//
// Pedido do usuário: "quero que o grupo seja o nome padrão para cadastro. Sempre que eu for digitando ele
// vai me sugerindo o nome do item". Em todo campo de descrição marcado com data-nome-padrao="<url>",
// enquanto se digita aparecem até 8 nomes: primeiro os nomes de GRUPO (produto genérico), depois os nomes
// de materiais já cadastrados. Escolher (clique, ou setas + Enter) põe o nome no campo em maiúsculas e
// avisa a página ("input"/"change"), para as conferências que já existem rodarem. Sem rolagem interna:
// a lista tem no máximo 8 linhas.
(function () {
    const escapeHtml = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    function attach(input) {
        if (!input || input.dataset.nomePadraoBound === '1') return;
        input.dataset.nomePadraoBound = '1';
        input.setAttribute('autocomplete', 'off');
        const url = input.dataset.nomePadrao;
        const box = document.createElement('div');
        box.className = 'list-group shadow nome-padrao-lista d-none';
        box.style.cssText = 'position:absolute;z-index:1080;left:0;right:0;top:100%;';
        const holder = input.parentElement;
        if (holder && getComputedStyle(holder).position === 'static') holder.style.position = 'relative';
        holder.appendChild(box);
        let rows = [];
        let active = -1;
        let timer = null;
        let lastQuery = '';
        let choosing = false; // a escolha avisa a página com "input"; esse aviso não reabre a lista

        const close = () => { box.classList.add('d-none'); active = -1; };
        const paint = () => {
            box.querySelectorAll('[data-i]').forEach((el) => el.classList.toggle('active', Number(el.dataset.i) === active));
        };
        const choose = (index) => {
            const row = rows[index];
            if (!row) return;
            input.value = String(row.nome || '').toLocaleUpperCase('pt-BR');
            close();
            choosing = true;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            choosing = false;
        };
        const render = () => {
            if (!rows.length) { close(); return; }
            box.innerHTML = rows.map((row, i) => `
                <button type="button" class="list-group-item list-group-item-action py-1 d-flex justify-content-between align-items-center" data-i="${i}">
                    <span>${escapeHtml(row.nome)}</span>
                    ${row.tipo === 'grupo' ? `<span class="badge bg-warning text-dark">grupo · ${escapeHtml(row.itens)} itens</span>` : `<span class="small text-muted">${escapeHtml(row.unidade || '')}</span>`}
                </button>`).join('');
            box.classList.remove('d-none');
            active = -1;
        };

        input.addEventListener('input', () => {
            if (choosing) return;
            const q = input.value.trim();
            clearTimeout(timer);
            if (q.length < 2) { close(); return; }
            if (q === lastQuery && rows.length) { render(); return; }
            timer = setTimeout(async () => {
                try {
                    const response = await fetch(`${url}?q=${encodeURIComponent(q)}`, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
                    if (!response.ok) return;
                    rows = await response.json();
                    lastQuery = q;
                    if (document.activeElement === input) render();
                } catch (error) { /* sugestão é opcional */ }
            }, 200);
        });
        input.addEventListener('keydown', (event) => {
            if (box.classList.contains('d-none')) return;
            if (event.key === 'ArrowDown') { active = Math.min(rows.length - 1, active + 1); paint(); event.preventDefault(); }
            else if (event.key === 'ArrowUp') { active = Math.max(0, active - 1); paint(); event.preventDefault(); }
            else if (event.key === 'Enter' && active >= 0) { choose(active); event.preventDefault(); event.stopPropagation(); }
            else if (event.key === 'Escape') { close(); }
        });
        box.addEventListener('mousedown', (event) => {
            const button = event.target.closest('[data-i]');
            if (!button) return;
            event.preventDefault();
            choose(Number(button.dataset.i));
        });
        input.addEventListener('blur', () => setTimeout(close, 150));
    }

    function scan(root) {
        (root || document).querySelectorAll('[data-nome-padrao]').forEach(attach);
    }

    window.GalintNomePadrao = { attach, scan };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => scan());
    else scan();
})();
