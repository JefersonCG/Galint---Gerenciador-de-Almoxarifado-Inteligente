/**
 * Componente de autocomplete para busca de itens por nome ou código
 * Uso: initItemAutocomplete(inputElement, dropdownElement, apiUrl)
 */

function initItemAutocomplete(inputElement, dropdownElement, apiUrl) {
    if (!inputElement || !dropdownElement) {
        console.error('Autocomplete: elementos não encontrados');
        return;
    }

    let debounceTimer;
    let currentFocus = -1;
    let currentItems = [];

    // Event handler para input
    inputElement.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = this.value.trim();
        
        if (query.length < 2) {
            dropdownElement.classList.remove('show');
            return;
        }
        
        debounceTimer = setTimeout(async function() {
            try {
                const response = await fetch(apiUrl + '?q=' + encodeURIComponent(query));
                const data = await response.json();
                
                if (data.items && data.items.length > 0) {
                    showAutocomplete(data.items);
                } else {
                    dropdownElement.classList.remove('show');
                }
            } catch (error) {
                console.error('Erro ao buscar itens:', error);
                dropdownElement.classList.remove('show');
            }
        }, 300);
    });

    function showAutocomplete(items) {
        currentItems = items;
        currentFocus = -1;
        dropdownElement.innerHTML = '';
        
        items.forEach((item, index) => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = 
                '<div class="autocomplete-item-title">' + escapeHtml(item.descricao) + '</div>' +
                '<div class="autocomplete-item-details">' +
                '  <span class="autocomplete-item-code">Código: ' + escapeHtml(item.codigo) + '</span>' +
                '  | Saldo: ' + item.saldo +
                (item.categoria ? ' | ' + escapeHtml(item.categoria) : '') +
                '</div>';
            
            div.addEventListener('click', function() {
                selectItem(item);
            });
            
            dropdownElement.appendChild(div);
        });
        
        dropdownElement.classList.add('show');
    }

    function selectItem(item) {
        inputElement.value = item.codigo;
        dropdownElement.classList.remove('show');
        
        // Disparar evento change para que outros scripts possam reagir
        inputElement.dispatchEvent(new Event('input', { bubbles: true }));
        inputElement.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Focar no próximo campo (geralmente quantidade)
        const nextInput = inputElement.closest('.row').querySelector('input[name="quantidade"]');
        if (nextInput) {
            nextInput.focus();
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Navegação por teclado
    inputElement.addEventListener('keydown', function(e) {
        const items = dropdownElement.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentFocus++;
            if (currentFocus >= items.length) currentFocus = 0;
            setActive(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentFocus--;
            if (currentFocus < 0) currentFocus = items.length - 1;
            setActive(items);
        } else if (e.key === 'Enter' && currentFocus > -1) {
            e.preventDefault();
            if (items[currentFocus]) {
                selectItem(currentItems[currentFocus]);
            }
        } else if (e.key === 'Escape') {
            dropdownElement.classList.remove('show');
        }
    });

    function setActive(items) {
        items.forEach((item, index) => {
            item.classList.toggle('active', index === currentFocus);
        });
        
        if (items[currentFocus]) {
            items[currentFocus].scrollIntoView({ block: 'nearest' });
        }
    }

    // Fechar dropdown ao clicar fora
    document.addEventListener('click', function(e) {
        if (e.target !== inputElement && !dropdownElement.contains(e.target)) {
            dropdownElement.classList.remove('show');
        }
    });
}

// Exportar para uso global
window.initItemAutocomplete = initItemAutocomplete;
