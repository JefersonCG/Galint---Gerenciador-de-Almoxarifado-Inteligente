(function () {
    const config = window.GALINT_BARCODE_STUDIO;
    if (!config) {
        return;
    }

    const PAGE_PRESETS = {
        portrait: { label: 'A4 retrato', widthMm: 210, heightMm: 297 },
        landscape: { label: 'A4 paisagem', widthMm: 297, heightMm: 210 },
    };

    const state = {
        items: [],
        selectedId: null,
        savedLayouts: [],
        currentLayoutFilename: null,
        search: {
            mode: 'item',
            selectedCategory: null,
            selectedCategoryItems: [],
        },
        page: {
            orientation: 'portrait',
            columns: 3,
            rows: 8,
            gapMm: 6,
            marginMm: 10,
            gridAlignX: 'center',
            snapEnabled: true,
            defaultItemSize: null,
        },
    };

    const elements = {
        searchPanelTitle: document.getElementById('barcodeStudioSearchPanelTitle'),
        searchPanelSubtitle: document.getElementById('barcodeStudioSearchPanelSubtitle'),
        searchFilterGroup: document.getElementById('barcodeStudioSearchFilterGroup'),
        searchInputLabel: document.getElementById('barcodeStudioSearchInputLabel'),
        searchMode: document.getElementById('barcodeStudioSearchMode'),
        searchUnlockNote: document.getElementById('barcodeStudioSearchUnlockNote'),
        searchInput: document.getElementById('barcodeStudioSearchInput'),
        searchClear: document.getElementById('barcodeStudioSearchClear'),
        searchResults: document.getElementById('barcodeStudioSearchResults'),
        searchStatus: document.getElementById('barcodeStudioSearchStatus'),
        categoryToolbar: document.getElementById('barcodeStudioCategoryToolbar'),
        selectedCategoryName: document.getElementById('barcodeStudioSelectedCategoryName'),
        selectedCategoryMeta: document.getElementById('barcodeStudioSelectedCategoryMeta'),
        addCategoryBtn: document.getElementById('barcodeStudioAddCategoryBtn'),
        categoryItems: document.getElementById('barcodeStudioCategoryItems'),
        addQuantity: document.getElementById('barcodeStudioAddQuantity'),
        orientation: document.getElementById('barcodeStudioOrientation'),
        columns: document.getElementById('barcodeStudioColumns'),
        rows: document.getElementById('barcodeStudioRows'),
        gap: document.getElementById('barcodeStudioGap'),
        margin: document.getElementById('barcodeStudioMargin'),
        gridAlignInput: document.getElementById('barcodeStudioGridAlignInput'),
        snapToggle: document.getElementById('barcodeStudioSnapToggle'),
        copies: document.getElementById('barcodeStudioCopies'),
        duplicateBtn: document.getElementById('barcodeStudioDuplicateBtn'),
        gridBtn: document.getElementById('barcodeStudioGridBtn'),
        clearBtn: document.getElementById('barcodeStudioClearBtn'),
        printBtn: document.getElementById('barcodeStudioPrintBtn'),
        pdfBtn: document.getElementById('barcodeStudioPdfBtn'),
        removeBtn: document.getElementById('barcodeStudioRemoveBtn'),
        sheetsContainer: document.getElementById('barcodeStudioSheetsContainer'),
        feedback: document.getElementById('barcodeStudioFeedback'),
        itemCount: document.getElementById('barcodeStudioItemCount'),
        pageCount: document.getElementById('barcodeStudioPageCount'),
        pageInfo: document.getElementById('barcodeStudioPageInfo'),
        gridInfo: document.getElementById('barcodeStudioGridInfo'),
        layoutName: document.getElementById('barcodeStudioLayoutName'),
        savedLayouts: document.getElementById('barcodeStudioSavedLayouts'),
        layoutsDirNote: document.getElementById('barcodeStudioLayoutsDirNote'),
        saveLayoutBtn: document.getElementById('barcodeStudioSaveLayoutBtn'),
        saveAsFileBtn: document.getElementById('barcodeStudioSaveAsFileBtn'),
        importFileBtn: document.getElementById('barcodeStudioImportFileBtn'),
        importFileInput: document.getElementById('barcodeStudioImportFileInput'),
        loadLayoutBtn: document.getElementById('barcodeStudioLoadLayoutBtn'),
        deleteLayoutBtn: document.getElementById('barcodeStudioDeleteLayoutBtn'),
        propertiesEmpty: document.getElementById('barcodeStudioPropertiesEmpty'),
        dimensionPresetStatus: document.getElementById('barcodeStudioDimensionPresetStatus'),
        presetWidthInput: document.getElementById('barcodeStudioPresetWidthInput'),
        presetHeightInput: document.getElementById('barcodeStudioPresetHeightInput'),
        applyPresetBtn: document.getElementById('barcodeStudioApplyPresetBtn'),
        lockDimensionsBtn: document.getElementById('barcodeStudioLockDimensionsBtn'),
        clearDimensionsBtn: document.getElementById('barcodeStudioClearDimensionsBtn'),
        propertiesForm: document.getElementById('barcodeStudioPropertiesForm'),
        selectedCode: document.getElementById('barcodeStudioSelectedCode'),
        selectedCategory: document.getElementById('barcodeStudioSelectedCategory'),
        selectedBrand: document.getElementById('barcodeStudioSelectedBrand'),
        selectedEditLink: document.getElementById('barcodeStudioSelectedEditLink'),
        titleInput: document.getElementById('barcodeStudioTitleInput'),
        widthInput: document.getElementById('barcodeStudioWidthInput'),
        heightInput: document.getElementById('barcodeStudioHeightInput'),
        xInput: document.getElementById('barcodeStudioXInput'),
        yInput: document.getElementById('barcodeStudioYInput'),
        barcodeHeightInput: document.getElementById('barcodeStudioBarcodeHeightInput'),
        paddingInput: document.getElementById('barcodeStudioPaddingInput'),
        titleSizeInput: document.getElementById('barcodeStudioTitleSizeInput'),
        codeSizeInput: document.getElementById('barcodeStudioCodeSizeInput'),
        alignInput: document.getElementById('barcodeStudioAlignInput'),
        showNameInput: document.getElementById('barcodeStudioShowNameInput'),
        showCodeInput: document.getElementById('barcodeStudioShowCodeInput'),
        nudgeLeftBtn: document.getElementById('barcodeStudioNudgeLeftBtn'),
        nudgeRightBtn: document.getElementById('barcodeStudioNudgeRightBtn'),
        nudgeUpBtn: document.getElementById('barcodeStudioNudgeUpBtn'),
        nudgeDownBtn: document.getElementById('barcodeStudioNudgeDownBtn'),
    };

    let interaction = null;
    let searchTimer = null;
    let searchAbortController = null;
    let lastSearchResults = [];
    let lastSearchMode = 'item';
    let lastSearchReady = null;
    let guideState = null;

    function getLayoutListUrl() {
        return String(config.layoutListApiUrl || '').trim();
    }

    function getCategoriesUrl() {
        return String(config.categoriesApiUrl || '').trim();
    }

    function getCategoryItemsUrl() {
        return String(config.categoryItemsApiUrl || '').trim();
    }

    function getLayoutDetailUrl(filename) {
        return String(config.layoutDetailUrlTemplate || '').replace('__FILENAME__', encodeURIComponent(String(filename || '').trim()));
    }

    function getLayoutImportUrl(token) {
        return String(config.layoutImportUrlTemplate || '').replace('__TOKEN__', encodeURIComponent(String(token || '').trim()));
    }

    function getLayoutFileExtension() {
        return String(config.layoutFileExtension || '.galintetq').trim() || '.galintetq';
    }

    function getLayoutFormat() {
        return String(config.layoutFormat || 'galint-label-layout').trim() || 'galint-label-layout';
    }

    function getLayoutVersion() {
        const numeric = Number(config.layoutVersion || 1);
        return Number.isFinite(numeric) && numeric > 0 ? numeric : 1;
    }

    function createId() {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return window.crypto.randomUUID();
        }
        return 'label-' + Date.now() + '-' + Math.random().toString(16).slice(2, 8);
    }

    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    function normalizeLookup(value) {
        return String(value == null ? '' : value)
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .trim()
            .toLowerCase();
    }

    function mmToPx(value) {
        return Number(value || 0) * 3.7795275591;
    }

    function pxToMm(value) {
        return Number(value || 0) / 3.7795275591;
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function getPagePreset() {
        return PAGE_PRESETS[state.page.orientation] || PAGE_PRESETS.portrait;
    }

    function getSearchMode() {
        return state.search.mode === 'category' ? 'category' : 'item';
    }

    function getSelectedSearchOptionValue() {
        return String(elements.searchMode ? elements.searchMode.value : '').trim();
    }

    function getSelectedCategoryNameFromSearchOption() {
        const rawValue = getSelectedSearchOptionValue();
        if (!rawValue || !rawValue.startsWith('category:')) {
            return '';
        }
        return rawValue.slice('category:'.length).trim();
    }

    function isSearchReady() {
        return Boolean(getFixedItemSize());
    }

    function resetSearchModeToItem() {
        state.search.mode = 'item';
        if (elements.searchMode) {
            elements.searchMode.value = 'item';
        }
    }

    function getEmptySearchStatus() {
        if (!isSearchReady()) {
            return 'Primeiro salve o tamanho predefinido em Propriedades para habilitar a busca.';
        }
        return getSearchMode() === 'category'
            ? 'Escolha uma categoria no menu acima. Ao selecionar, todos os itens entram automaticamente na folha.'
            : 'Busque um item para comecar.';
    }

    function getSearchPlaceholder() {
        if (!isSearchReady()) {
            return 'Salve o tamanho predefinido para habilitar a busca';
        }
        return getSearchMode() === 'category'
            ? 'Ex.: material eletrico, ferramentas, limpeza'
            : 'Ex.: ITEM-0283, cabo, furadeira';
    }

    function syncSearchModeUI() {
        const searchReady = isSearchReady();
        const isCategory = searchReady && getSearchMode() === 'category';
        if (elements.searchPanelTitle) {
            elements.searchPanelTitle.textContent = isCategory ? 'Escolher categoria' : 'Buscar item';
        }
        if (elements.searchPanelSubtitle) {
            elements.searchPanelSubtitle.textContent = !searchReady
                ? 'Primeiro defina e salve o tamanho predefinido da etiqueta. Depois a busca por item ou categoria sera liberada.'
                : isCategory
                ? 'Escolha a categoria direto na lista acima. Ao clicar, todos os itens entram automaticamente na folha.'
                : 'Digite codigo, descricao ou marca e adicione o resultado direto na folha.';
        }
        if (elements.searchFilterGroup) {
            elements.searchFilterGroup.classList.toggle('d-none', isCategory);
        }
        if (elements.searchInputLabel) {
            elements.searchInputLabel.textContent = 'Termo de busca';
        }
        if (elements.searchInput) {
            elements.searchInput.placeholder = getSearchPlaceholder();
        }
    }

    function syncSearchAvailabilityUI() {
        const searchReady = isSearchReady();
        const changed = lastSearchReady !== searchReady;
        lastSearchReady = searchReady;

        if (!searchReady && changed) {
            resetSearchModeToItem();
            if (elements.searchInput) {
                elements.searchInput.value = '';
            }
            clearSearchResults();
            clearSelectedCategory({ silent: true });
        }

        if (elements.searchUnlockNote) {
            elements.searchUnlockNote.classList.toggle('d-none', searchReady);
        }
        if (elements.searchMode) {
            elements.searchMode.disabled = !searchReady;
        }
        if (elements.searchInput) {
            elements.searchInput.disabled = !searchReady;
        }
        if (elements.searchClear) {
            elements.searchClear.disabled = !searchReady;
        }

        syncSearchModeUI();
        if (!searchReady) {
            setSearchStatus(getEmptySearchStatus(), 'warning');
            return;
        }
        if (changed) {
            setSearchStatus(getEmptySearchStatus(), 'muted');
        }
    }

    function roundMm(value) {
        return Math.round(Number(value || 0) * 10) / 10;
    }

    function normalizeFixedItemSize(rawSize, presetOverride) {
        if (!rawSize || typeof rawSize !== 'object') {
            return null;
        }
        const preset = presetOverride || getPagePreset();
        const widthValue = Number(rawSize.widthMm);
        const heightValue = Number(rawSize.heightMm);
        if (!Number.isFinite(widthValue) || !Number.isFinite(heightValue)) {
            return null;
        }
        return {
            widthMm: roundMm(clamp(widthValue, 24, Math.max(24, preset.widthMm - 4))),
            heightMm: roundMm(clamp(heightValue, 20, Math.max(20, preset.heightMm - 4))),
        };
    }

    function getFixedItemSize() {
        return normalizeFixedItemSize(state.page.defaultItemSize, getPagePreset());
    }

    function setFixedItemSize(rawSize) {
        state.page.defaultItemSize = normalizeFixedItemSize(rawSize, getPagePreset());
        return state.page.defaultItemSize;
    }

    function getNewItemSize() {
        return getFixedItemSize() || { widthMm: 72, heightMm: 40 };
    }

    function isValidEan8(raw) {
        if (!/^\d{8}$/.test(raw)) {
            return false;
        }
        const digits = raw.split('').map(function (digit) {
            return Number(digit);
        });
        const checksum = (10 - (((digits[0] + digits[2] + digits[4] + digits[6]) * 3) + digits[1] + digits[3] + digits[5]) % 10) % 10;
        return checksum === digits[7];
    }

    function isValidEan13(raw) {
        if (!/^\d{13}$/.test(raw)) {
            return false;
        }
        const digits = raw.split('').map(function (digit) {
            return Number(digit);
        });
        const checksum = (10 - ((digits[0] + digits[2] + digits[4] + digits[6] + digits[8] + digits[10]) + ((digits[1] + digits[3] + digits[5] + digits[7] + digits[9] + digits[11]) * 3)) % 10) % 10;
        return checksum === digits[12];
    }

    function readAddQuantity() {
        return clamp(parseInt(elements.addQuantity ? elements.addQuantity.value : '1', 10) || 1, 1, 60);
    }

    function readPageConfigInputs() {
        state.page.columns = clamp(parseInt(elements.columns ? elements.columns.value : String(state.page.columns), 10) || 3, 1, 8);
        state.page.rows = clamp(parseInt(elements.rows ? elements.rows.value : String(state.page.rows), 10) || 8, 1, 12);
        state.page.gapMm = clamp(parseFloat(elements.gap ? elements.gap.value : String(state.page.gapMm)) || 0, 0, 30);
        state.page.marginMm = clamp(parseFloat(elements.margin ? elements.margin.value : String(state.page.marginMm)) || 10, 4, 30);
        state.page.gridAlignX = elements.gridAlignInput && elements.gridAlignInput.value === 'left' ? 'left' : 'center';
    }

    function syncDimensionPresetInputs(options) {
        const force = Boolean(options && options.force);
        const fixedItemSize = getFixedItemSize();
        const fallback = fixedItemSize || { widthMm: 72, heightMm: 40 };
        if (elements.presetWidthInput && (force || document.activeElement !== elements.presetWidthInput)) {
            elements.presetWidthInput.value = String(roundMm(fallback.widthMm));
        }
        if (elements.presetHeightInput && (force || document.activeElement !== elements.presetHeightInput)) {
            elements.presetHeightInput.value = String(roundMm(fallback.heightMm));
        }
    }

    function readPresetSizeFromInputs() {
        const widthValue = parseFloat(elements.presetWidthInput ? elements.presetWidthInput.value : '0');
        const heightValue = parseFloat(elements.presetHeightInput ? elements.presetHeightInput.value : '0');
        return normalizeFixedItemSize({ widthMm: widthValue, heightMm: heightValue }, getPagePreset());
    }

    function getUsedPageCount() {
        if (!state.items.length) {
            return 1;
        }
        return state.items.reduce(function (maxPage, item) {
            return Math.max(maxPage, Math.max(0, parseInt(item.pageIndex, 10) || 0));
        }, 0) + 1;
    }

    function getPageIndices() {
        return Array.from({ length: getUsedPageCount() }, function (_, index) {
            return index;
        });
    }

    function getItemsForPage(pageIndex) {
        return state.items.filter(function (item) {
            return Math.max(0, parseInt(item.pageIndex, 10) || 0) === pageIndex;
        });
    }

    function resolveGridMetrics() {
        readPageConfigInputs();
        const preset = getPagePreset();
        const gapMm = state.page.gapMm;
        const marginMm = state.page.marginMm;
        const preferFixedSize = Boolean(getFixedItemSize());
        let columns = state.page.columns;
        let rows = state.page.rows;
        let cellWidth = 0;
        let cellHeight = 0;

        function fitAxis(pageSizeMm, itemSizeMm) {
            const safeMarginMm = clamp(Number(marginMm || 0), 0, Math.max(0, (pageSizeMm - itemSizeMm) / 2));
            const usableSizeMm = Math.max(0, pageSizeMm - (safeMarginMm * 2));
            if (!(itemSizeMm > 0) || itemSizeMm > usableSizeMm) {
                throw new Error('A dimensao fixa nao cabe na area util da folha atual.');
            }
            const count = Math.max(1, Math.floor(usableSizeMm / itemSizeMm));
            const freeSizeMm = Math.max(0, usableSizeMm - (count * itemSizeMm));
            let actualGapMm = 0;
            let extraSpaceMm = freeSizeMm;
            if (count > 1) {
                const maxGapMm = freeSizeMm / (count - 1);
                actualGapMm = Math.min(Math.max(0, gapMm), maxGapMm);
                extraSpaceMm = Math.max(0, freeSizeMm - (actualGapMm * (count - 1)));
            }
            return {
                count: count,
                marginMm: safeMarginMm,
                usableSizeMm: usableSizeMm,
                gapMm: actualGapMm,
                extraSpaceMm: extraSpaceMm,
            };
        }

        if (preferFixedSize) {
            const fixedItemSize = getFixedItemSize();
            if (!fixedItemSize) {
                throw new Error('A dimensao fixa nao esta disponivel para montar a grade.');
            }
            const fitX = fitAxis(preset.widthMm, fixedItemSize.widthMm);
            const fitY = fitAxis(preset.heightMm, fixedItemSize.heightMm);
            columns = fitX.count;
            rows = fitY.count;
            cellWidth = fixedItemSize.widthMm;
            cellHeight = fixedItemSize.heightMm;
            state.page.columns = columns;
            state.page.rows = rows;
            syncPageInputs();
            return {
                preset: preset,
                gapMm: gapMm,
                marginMm: marginMm,
                columns: columns,
                rows: rows,
                cellWidth: cellWidth,
                cellHeight: cellHeight,
                capacity: Math.max(1, columns * rows),
                fixedSizeMode: true,
                fitX: fitX,
                fitY: fitY,
                gridAlignX: state.page.gridAlignX,
            };
        } else {
            const usableWidth = preset.widthMm - (marginMm * 2) - ((columns - 1) * gapMm);
            const usableHeight = preset.heightMm - (marginMm * 2) - ((rows - 1) * gapMm);
            if (usableWidth <= 0 || usableHeight <= 0) {
                throw new Error('A grade ficou maior que a area util da folha. Revise margens e espacamentos.');
            }
            cellWidth = usableWidth / columns;
            cellHeight = usableHeight / rows;
        }

        return {
            preset: preset,
            gapMm: gapMm,
            marginMm: marginMm,
            columns: columns,
            rows: rows,
            cellWidth: cellWidth,
            cellHeight: cellHeight,
            capacity: Math.max(1, columns * rows),
            fixedSizeMode: false,
            gridAlignX: state.page.gridAlignX,
        };
    }

    function layoutItemsInGrid(itemsToLayout, options) {
        const items = Array.isArray(itemsToLayout) ? itemsToLayout : [];
        if (!items.length) {
            return { capacity: 0, columns: state.page.columns, rows: state.page.rows, usedPages: 0 };
        }

        const metrics = resolveGridMetrics();
        const startPage = Math.max(0, parseInt(options && options.startPageIndex, 10) || 0);
        items.forEach(function (item, index) {
            const pageOffset = Math.floor(index / metrics.capacity);
            const indexWithinPage = index % metrics.capacity;
            const itemsOnPage = Math.min(metrics.capacity, items.length - (pageOffset * metrics.capacity));
            const row = Math.floor(indexWithinPage / metrics.columns);
            const column = indexWithinPage % metrics.columns;
            item.pageIndex = startPage + pageOffset;
            if (metrics.fixedSizeMode) {
                const itemsBeforeRow = row * metrics.columns;
                const itemsInRow = Math.max(1, Math.min(metrics.columns, itemsOnPage - itemsBeforeRow));
                const rowWidthMm = (itemsInRow * metrics.cellWidth) + (Math.max(0, itemsInRow - 1) * metrics.fitX.gapMm);
                const rowRemainingMm = Math.max(0, metrics.fitX.usableSizeMm - rowWidthMm);
                const rowStartMm = metrics.fitX.marginMm + (metrics.gridAlignX === 'center' ? (rowRemainingMm / 2) : 0);
                item.xMm = rowStartMm + (column * (metrics.cellWidth + metrics.fitX.gapMm));
                item.yMm = metrics.fitY.marginMm + (row * (metrics.cellHeight + metrics.fitY.gapMm));
            } else {
                item.xMm = metrics.marginMm + (column * (metrics.cellWidth + metrics.gapMm));
                item.yMm = metrics.marginMm + (row * (metrics.cellHeight + metrics.gapMm));
            }
            item.widthMm = metrics.cellWidth;
            item.heightMm = metrics.cellHeight;
            item.barcodeHeightMm = clamp(metrics.cellHeight * 0.46, 10, Math.max(10, metrics.cellHeight - 6));
            item.paddingMm = clamp(metrics.cellWidth * 0.05, 1.5, 4);
            item.isSnapping = false;
            normalizeLabel(item);
        });
        return {
            capacity: metrics.capacity,
            columns: metrics.columns,
            rows: metrics.rows,
            usedPages: Math.ceil(items.length / metrics.capacity),
        };
    }

    function readSnapThresholdMm() {
        return state.page.snapEnabled ? 3 : 0;
    }

    function inferBarcodeFormat(value) {
        const raw = String(value || '').trim();
        if (isValidEan13(raw)) {
            return 'EAN13';
        }
        if (isValidEan8(raw)) {
            return 'EAN8';
        }
        return 'CODE128';
    }

    function setFeedback(message, tone) {
        if (!elements.feedback) {
            return;
        }
        elements.feedback.textContent = message;
        elements.feedback.dataset.tone = tone || 'muted';
    }

    function setSearchStatus(message, tone) {
        if (!elements.searchStatus) {
            return;
        }
        elements.searchStatus.textContent = message;
        elements.searchStatus.dataset.tone = tone || 'muted';
    }

    function createGuideState() {
        if (!elements.sheetsContainer) {
            return null;
        }
        return null;
    }

    function hideGuides() {
        if (!guideState) {
            return;
        }
        guideState.vertical.classList.remove('is-visible');
        guideState.horizontal.classList.remove('is-visible');
    }

    function showGuide(axis, positionMm) {
        if (!guideState) {
            return;
        }
        if (axis === 'x') {
            guideState.vertical.style.left = mmToPx(positionMm) + 'px';
            guideState.vertical.classList.add('is-visible');
        }
        if (axis === 'y') {
            guideState.horizontal.style.top = mmToPx(positionMm) + 'px';
            guideState.horizontal.classList.add('is-visible');
        }
    }

    function cloneSerializableItems(items) {
        return JSON.parse(JSON.stringify(items || []));
    }

    function slugifyFileName(value) {
        const normalized = String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-zA-Z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .toLowerCase();
        return normalized || 'layout-etiquetas';
    }

    function getLayoutSnapshot() {
        return {
            page: JSON.parse(JSON.stringify(state.page)),
            items: cloneSerializableItems(state.items),
        };
    }

    function buildLayoutDocument(name, snapshot) {
        return {
            format: getLayoutFormat(),
            version: getLayoutVersion(),
            name: String(name || '').trim(),
            saved_at: new Date().toISOString(),
            page: snapshot.page,
            items: snapshot.items,
        };
    }

    function extractLayoutSnapshot(documentData) {
        if (!documentData || typeof documentData !== 'object') {
            throw new Error('Arquivo de layout invalido.');
        }
        if (!documentData.page || typeof documentData.page !== 'object' || !Array.isArray(documentData.items)) {
            throw new Error('Arquivo de layout invalido. Estrutura ausente.');
        }
        return {
            name: String(documentData.name || '').trim() || 'Layout importado',
            snapshot: {
                page: documentData.page,
                items: documentData.items,
            },
        };
    }

    function readQueryParam(name) {
        try {
            const url = new URL(window.location.href);
            return String(url.searchParams.get(name) || '').trim();
        } catch (error) {
            return '';
        }
    }

    function clearQueryParam(name) {
        try {
            const url = new URL(window.location.href);
            if (!url.searchParams.has(name)) {
                return;
            }
            url.searchParams.delete(name);
            window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
        } catch (error) {
        }
    }

    async function fetchJson(url, options) {
        const response = await window.fetch(url, Object.assign({
            headers: { Accept: 'application/json' },
        }, options || {}));
        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            payload = null;
        }
        if (!response.ok || !payload || payload.success === false) {
            const message = payload && payload.message ? payload.message : 'Falha ao processar a operacao.';
            throw new Error(message);
        }
        return payload;
    }

    function updateLayoutsDirNote(internalDir) {
        if (!elements.layoutsDirNote) {
            return;
        }
        const text = String(internalDir || config.internalLayoutsDir || '').trim();
        elements.layoutsDirNote.textContent = text ? 'Pasta interna do sistema: ' + text : 'Pasta interna do sistema indisponivel no momento.';
    }

    function renderSavedLayouts(selectedFilename) {
        if (!elements.savedLayouts) {
            return;
        }
        const currentValue = String(selectedFilename || elements.savedLayouts.value || state.currentLayoutFilename || '').trim();
        elements.savedLayouts.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = state.savedLayouts.length ? 'Selecione um layout salvo' : 'Nenhum layout salvo';
        elements.savedLayouts.appendChild(placeholder);
        state.savedLayouts.forEach(function (layout) {
            const option = document.createElement('option');
            option.value = layout.filename;
            option.textContent = layout.name;
            elements.savedLayouts.appendChild(option);
        });
        if (currentValue && state.savedLayouts.some(function (layout) { return layout.filename === currentValue; })) {
            elements.savedLayouts.value = currentValue;
        }
    }

    async function refreshSavedLayouts(selectedFilename) {
        const url = getLayoutListUrl();
        if (!url) {
            return;
        }
        try {
            const payload = await fetchJson(url);
            state.savedLayouts = Array.isArray(payload.layouts) ? payload.layouts : [];
            updateLayoutsDirNote(payload.internal_dir || config.internalLayoutsDir || '');
            renderSavedLayouts(selectedFilename);
        } catch (error) {
            updateLayoutsDirNote(config.internalLayoutsDir || '');
            setFeedback(error.message || 'Nao foi possivel consultar os layouts salvos.', 'danger');
        }
    }

    async function saveCurrentLayout() {
        const listUrl = getLayoutListUrl();
        if (!listUrl) {
            setFeedback('API de layouts indisponivel no momento.', 'danger');
            return;
        }
        const name = String(elements.layoutName ? elements.layoutName.value : '').trim();
        if (!name) {
            setFeedback('Informe um nome para o layout antes de salvar.', 'warning');
            return;
        }
        const matchedLayout = state.savedLayouts.find(function (layout) {
            return String(layout.name || '').trim().toLowerCase() === name.toLowerCase();
        });
        let targetFilename = state.currentLayoutFilename;
        if (!targetFilename && matchedLayout) {
            if (!window.confirm('Ja existe um layout com esse nome. Deseja sobrescrever o arquivo salvo?')) {
                setFeedback('Salvamento cancelado.', 'warning');
                return;
            }
            targetFilename = matchedLayout.filename;
        }
        try {
            const requestUrl = targetFilename ? getLayoutDetailUrl(targetFilename) : listUrl;
            const payload = await fetchJson(requestUrl, {
                method: targetFilename ? 'PUT' : 'POST',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    name: name,
                    snapshot: getLayoutSnapshot(),
                }),
            });
            const layout = payload.layout || null;
            state.currentLayoutFilename = layout && layout.filename ? layout.filename : targetFilename;
            await refreshSavedLayouts(state.currentLayoutFilename);
            if (elements.savedLayouts && state.currentLayoutFilename) {
                elements.savedLayouts.value = state.currentLayoutFilename;
            }
            setFeedback(payload.message || ('Layout salvo: ' + name + '.'), 'muted');
        } catch (error) {
            setFeedback(error.message || 'Nao foi possivel salvar o layout.', 'danger');
        }
    }

    function applyLayoutSnapshot(snapshot) {
        if (!snapshot || typeof snapshot !== 'object') {
            return;
        }
        const incomingPage = snapshot.page && typeof snapshot.page === 'object' ? snapshot.page : {};
        state.page = Object.assign({}, state.page, incomingPage);
        if (!Object.prototype.hasOwnProperty.call(incomingPage, 'defaultItemSize')) {
            state.page.defaultItemSize = null;
        }
        state.page.defaultItemSize = normalizeFixedItemSize(state.page.defaultItemSize, getPagePreset());
        state.items = cloneSerializableItems(snapshot.items || []);
        state.items.forEach(function (item) {
            normalizeLabel(item);
        });
        state.selectedId = state.items.length ? state.items[0].id : null;
        syncPageInputs();
        renderPage();
        renderProperties();
        updateSheetMetrics();
    }

    async function loadSelectedLayout() {
        const filename = String(elements.savedLayouts ? elements.savedLayouts.value : '').trim();
        if (!filename) {
            setFeedback('Selecione um layout salvo para carregar.', 'warning');
            return;
        }
        try {
            const payload = await fetchJson(getLayoutDetailUrl(filename));
            const layout = payload.layout || null;
            if (!layout || !layout.snapshot) {
                throw new Error('Layout salvo nao encontrado.');
            }
            applyLayoutSnapshot(layout.snapshot);
            state.currentLayoutFilename = layout.filename;
            renderSavedLayouts(layout.filename);
            if (elements.layoutName) {
                elements.layoutName.value = layout.name;
            }
            setFeedback('Layout carregado: ' + layout.name + '.', 'muted');
        } catch (error) {
            setFeedback(error.message || 'Nao foi possivel carregar o layout.', 'danger');
        }
    }

    async function deleteSelectedLayout() {
        const filename = String(elements.savedLayouts ? elements.savedLayouts.value : '').trim();
        if (!filename) {
            setFeedback('Selecione um layout salvo para excluir.', 'warning');
            return;
        }
        const layout = state.savedLayouts.find(function (entry) {
            return entry.filename === filename;
        });
        if (!layout) {
            setFeedback('Layout salvo nao encontrado.', 'danger');
            return;
        }
        if (!window.confirm('Excluir o layout salvo "' + layout.name + '"?')) {
            return;
        }
        try {
            const payload = await fetchJson(getLayoutDetailUrl(filename), { method: 'DELETE' });
            if (state.currentLayoutFilename === filename) {
                state.currentLayoutFilename = null;
            }
            await refreshSavedLayouts('');
            if (elements.layoutName && elements.layoutName.value.trim() === layout.name) {
                elements.layoutName.value = '';
            }
            setFeedback(payload.message || ('Layout excluido: ' + layout.name + '.'), 'muted');
        } catch (error) {
            setFeedback(error.message || 'Nao foi possivel excluir o layout.', 'danger');
        }
    }

    async function saveLayoutAsFile() {
        const name = String(elements.layoutName ? elements.layoutName.value : '').trim() || 'Layout de etiquetas';
        const documentData = buildLayoutDocument(name, getLayoutSnapshot());
        const serialized = JSON.stringify(documentData, null, 2) + '\n';
        const suggestedName = slugifyFileName(name) + getLayoutFileExtension();

        try {
            if (typeof window.showSaveFilePicker === 'function') {
                const handle = await window.showSaveFilePicker({
                    suggestedName: suggestedName,
                    types: [
                        {
                            description: 'Layout do Editor de Etiquetas',
                            accept: { 'application/json': [getLayoutFileExtension()] },
                        },
                    ],
                });
                const writable = await handle.createWritable();
                await writable.write(serialized);
                await writable.close();
            } else {
                const blob = new Blob([serialized], { type: 'application/json' });
                const url = window.URL.createObjectURL(blob);
                const anchor = document.createElement('a');
                anchor.href = url;
                anchor.download = suggestedName;
                document.body.appendChild(anchor);
                anchor.click();
                anchor.remove();
                window.setTimeout(function () {
                    window.URL.revokeObjectURL(url);
                }, 0);
            }
            setFeedback('Arquivo exportado. Voce pode guardar esse layout em outra pasta.', 'muted');
        } catch (error) {
            if (error && error.name === 'AbortError') {
                setFeedback('Salvar como cancelado.', 'warning');
                return;
            }
            setFeedback('Nao foi possivel exportar o arquivo agora.', 'danger');
        }
    }

    async function importLayoutFile(file) {
        if (!file) {
            return;
        }
        try {
            const rawText = await file.text();
            const documentData = JSON.parse(String(rawText || '').replace(/^\uFEFF/, ''));
            const imported = extractLayoutSnapshot(documentData);
            applyLayoutSnapshot(imported.snapshot);
            state.currentLayoutFilename = null;
            renderSavedLayouts('');
            if (elements.layoutName) {
                elements.layoutName.value = imported.name;
            }
            setFeedback('Arquivo carregado com sucesso. Se quiser, agora voce pode salvar no sistema.', 'muted');
        } catch (error) {
            setFeedback(error.message || 'Nao foi possivel abrir esse arquivo.', 'danger');
        }
    }

    async function importPendingLayoutFromQuery() {
        const token = readQueryParam('layout_import_token');
        if (!token) {
            return;
        }
        try {
            const payload = await fetchJson(getLayoutImportUrl(token));
            const layout = payload.layout || null;
            if (!layout || !layout.snapshot) {
                throw new Error('Arquivo pendente invalido.');
            }
            applyLayoutSnapshot(layout.snapshot);
            state.currentLayoutFilename = null;
            renderSavedLayouts('');
            if (elements.layoutName) {
                elements.layoutName.value = layout.name || 'Layout importado';
            }
            setFeedback(payload.message || 'Arquivo aberto no Editor de Etiquetas.', 'muted');
        } catch (error) {
            setFeedback(error.message || 'Nao foi possivel abrir o arquivo enviado ao editor.', 'danger');
        } finally {
            clearQueryParam('layout_import_token');
        }
    }

    function syncPageInputs() {
        if (elements.orientation) {
            elements.orientation.value = state.page.orientation;
        }
        if (elements.columns) {
            elements.columns.value = String(state.page.columns);
        }
        if (elements.rows) {
            elements.rows.value = String(state.page.rows);
        }
        if (elements.gap) {
            elements.gap.value = String(state.page.gapMm);
        }
        if (elements.margin) {
            elements.margin.value = String(state.page.marginMm);
        }
        if (elements.gridAlignInput) {
            elements.gridAlignInput.value = state.page.gridAlignX === 'left' ? 'left' : 'center';
        }
        if (elements.snapToggle) {
            elements.snapToggle.checked = state.page.snapEnabled !== false;
        }
    }

    function snapValue(valueMm, candidatesMm, thresholdMm) {
        let snappedValue = valueMm;
        let snappedGuide = null;
        let smallestDistance = thresholdMm;
        candidatesMm.forEach(function (candidate) {
            const distance = Math.abs(candidate - valueMm);
            if (distance <= smallestDistance) {
                snappedValue = candidate;
                snappedGuide = candidate;
                smallestDistance = distance;
            }
        });
        return { value: snappedValue, guide: snappedGuide };
    }

    function buildSnapCandidates(currentItem, mode) {
        const preset = getPagePreset();
        const xCandidates = [0, state.page.marginMm, preset.widthMm / 2, preset.widthMm - state.page.marginMm, preset.widthMm];
        const yCandidates = [0, state.page.marginMm, preset.heightMm / 2, preset.heightMm - state.page.marginMm, preset.heightMm];
        const gridXStep = state.page.columns > 0 ? (preset.widthMm - (state.page.marginMm * 2)) / state.page.columns : 0;
        const gridYStep = state.page.rows > 0 ? (preset.heightMm - (state.page.marginMm * 2)) / state.page.rows : 0;

        if (gridXStep > 0) {
            for (let index = 0; index <= state.page.columns; index += 1) {
                xCandidates.push(state.page.marginMm + (index * gridXStep));
            }
        }
        if (gridYStep > 0) {
            for (let index = 0; index <= state.page.rows; index += 1) {
                yCandidates.push(state.page.marginMm + (index * gridYStep));
            }
        }

        state.items.forEach(function (item) {
            if (item.id === currentItem.id) {
                return;
            }
            xCandidates.push(item.xMm, item.xMm + item.widthMm / 2, item.xMm + item.widthMm);
            yCandidates.push(item.yMm, item.yMm + item.heightMm / 2, item.yMm + item.heightMm);
        });

        if (mode === 'drag') {
            xCandidates.push(currentItem.widthMm / 2, preset.widthMm - currentItem.widthMm, preset.widthMm - (currentItem.widthMm / 2));
            yCandidates.push(currentItem.heightMm / 2, preset.heightMm - currentItem.heightMm, preset.heightMm - (currentItem.heightMm / 2));
        }

        return { xCandidates: xCandidates, yCandidates: yCandidates };
    }

    function applySnapping(item, mode) {
        const thresholdMm = readSnapThresholdMm();
        if (!thresholdMm) {
            hideGuides();
            item.isSnapping = false;
            return;
        }
        const candidates = buildSnapCandidates(item, mode);
        const leftSnap = snapValue(item.xMm, candidates.xCandidates, thresholdMm);
        const topSnap = snapValue(item.yMm, candidates.yCandidates, thresholdMm);
        const widthSnap = snapValue(item.xMm + item.widthMm, candidates.xCandidates, thresholdMm);
        const heightSnap = snapValue(item.yMm + item.heightMm, candidates.yCandidates, thresholdMm);

        hideGuides();
        item.isSnapping = false;

        if (mode === 'drag') {
            if (leftSnap.guide != null) {
                item.xMm = leftSnap.value;
                showGuide('x', leftSnap.guide);
                item.isSnapping = true;
            }
            if (topSnap.guide != null) {
                item.yMm = topSnap.value;
                showGuide('y', topSnap.guide);
                item.isSnapping = true;
            }
        } else if (mode === 'resize') {
            if (widthSnap.guide != null) {
                item.widthMm = Math.max(24, widthSnap.value - item.xMm);
                showGuide('x', widthSnap.guide);
                item.isSnapping = true;
            }
            if (heightSnap.guide != null) {
                item.heightMm = Math.max(20, heightSnap.value - item.yMm);
                showGuide('y', heightSnap.guide);
                item.isSnapping = true;
            }
        }
    }

    function getSelectedItem() {
        return state.items.find(function (item) {
            return item.id === state.selectedId;
        }) || null;
    }

    function normalizeLabel(item) {
        const preset = getPagePreset();
        item.pageIndex = Math.max(0, parseInt(item.pageIndex, 10) || 0);
        item.widthMm = clamp(Number(item.widthMm || 72), 24, preset.widthMm - 4);
        item.heightMm = clamp(Number(item.heightMm || 40), 20, preset.heightMm - 4);
        item.xMm = clamp(Number(item.xMm || state.page.marginMm), 0, Math.max(0, preset.widthMm - item.widthMm));
        item.yMm = clamp(Number(item.yMm || state.page.marginMm), 0, Math.max(0, preset.heightMm - item.heightMm));
        item.barcodeHeightMm = clamp(Number(item.barcodeHeightMm || 18), 8, Math.max(8, item.heightMm - 4));
        item.paddingMm = clamp(Number(item.paddingMm || 3), 1, 12);
        item.fontSizePx = clamp(Number(item.fontSizePx || 14), 8, 30);
        item.codeFontSizePx = clamp(Number(item.codeFontSizePx || 11), 8, 24);
        item.align = ['left', 'center', 'right'].includes(item.align) ? item.align : 'center';
        item.showName = item.showName !== false;
        item.showCode = item.showCode !== false;
        item.customTitle = String(item.customTitle || item.descricao || item.codigo || '').slice(0, 120);
    }

    function updateSheetMetrics() {
        const preset = getPagePreset();
        if (elements.itemCount) {
            elements.itemCount.textContent = String(state.items.length);
        }
        if (elements.pageCount) {
            elements.pageCount.textContent = String(getUsedPageCount());
        }
        if (elements.pageInfo) {
            elements.pageInfo.textContent = preset.label;
        }
        if (elements.gridInfo) {
            elements.gridInfo.textContent = 'Grade ' + state.page.columns + ' x ' + state.page.rows;
        }
    }

    function renderCategorySelection() {
        const category = state.search.selectedCategory;
        const items = state.search.selectedCategoryItems || [];
        const hasCategory = Boolean(category);
        if (elements.categoryToolbar) {
            elements.categoryToolbar.classList.toggle('d-none', !hasCategory);
        }
        if (elements.categoryItems) {
            elements.categoryItems.classList.toggle('d-none', !hasCategory);
        }
        if (!hasCategory) {
            if (elements.categoryItems) {
                elements.categoryItems.innerHTML = '';
            }
            return;
        }

        const totalItems = Number(category.item_count || items.length || 0);
        if (elements.selectedCategoryName) {
            elements.selectedCategoryName.textContent = category.name || category.label || 'Categoria';
        }
        if (elements.selectedCategoryMeta) {
            elements.selectedCategoryMeta.textContent = totalItems + ' item(ns) disponivel(is) para a folha';
        }
        if (elements.addCategoryBtn) {
            elements.addCategoryBtn.disabled = !items.length;
        }
        if (!elements.categoryItems) {
            return;
        }
        elements.categoryItems.innerHTML = '';
        items.forEach(function (item) {
            elements.categoryItems.appendChild(buildSearchResultCard(item));
        });
    }

    function clearSelectedCategory(options) {
        state.search.selectedCategory = null;
        state.search.selectedCategoryItems = [];
        renderCategorySelection();
        if (!options || options.silent !== true) {
            setFeedback('Selecao de categoria limpa.', 'muted');
        }
    }

    function buildSearchResultCard(item) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'barcode-studio-result';
        button.innerHTML = '' +
            '<div class="barcode-studio-result__top">' +
                '<span class="barcode-studio-result__code"><i class="bi bi-upc"></i>' + escapeHtml(item.codigo || '-') + '</span>' +
                '<span class="badge text-bg-dark">Adicionar</span>' +
            '</div>' +
            '<p class="barcode-studio-result__title">' + escapeHtml(item.descricao || item.codigo || 'Item sem descricao') + '</p>' +
            '<div class="barcode-studio-result__meta">' +
                '<span><strong>Marca:</strong> ' + escapeHtml(item.marca || 'Sem marca') + '</span>' +
                '<span><strong>Categoria:</strong> ' + escapeHtml(item.categoria || 'Sem categoria') + '</span>' +
                '<span><strong>Saldo:</strong> ' + escapeHtml(item.saldo_display || '-') + '</span>' +
            '</div>';
        button.addEventListener('click', function () {
            addItemToSheet(item);
        });
        return button;
    }

    function buildCategoryResultCard(category) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'barcode-studio-result barcode-studio-result--category';
        const icon = escapeHtml(category.icon || '🏷️');
        const name = escapeHtml(category.name || category.label || 'Categoria');
        const description = escapeHtml(category.descricao || 'Abra a categoria para carregar todos os itens na folha.');
        const total = Number(category.item_count || 0);
        button.innerHTML = '' +
            '<div class="barcode-studio-result__top">' +
                '<span class="barcode-studio-result__code"><span class="barcode-studio-result__emoji">' + icon + '</span>Categoria</span>' +
                '<span class="badge text-bg-dark">' + total + ' item(ns)</span>' +
            '</div>' +
            '<p class="barcode-studio-result__title">' + name + '</p>' +
            '<div class="barcode-studio-result__meta">' +
                '<span>' + description + '</span>' +
                '<span>Clique para abrir os itens dessa categoria.</span>' +
            '</div>';
        button.addEventListener('click', function () {
            loadCategoryItems(category);
        });
        return button;
    }

    function renderSearchResults(items) {
        if (!elements.searchResults) {
            return;
        }
        elements.searchResults.innerHTML = '';
        lastSearchResults = items.slice();
        lastSearchMode = getSearchMode();
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'barcode-studio-result';
            if (getSearchMode() === 'category') {
                empty.innerHTML = '<p class="barcode-studio-result__title">Nenhuma categoria encontrada</p><div class="barcode-studio-result__meta"><span>Tente outro trecho do nome da categoria.</span></div>';
            } else {
                empty.innerHTML = '<p class="barcode-studio-result__title">Nenhum item encontrado</p><div class="barcode-studio-result__meta"><span>Tente outro trecho do nome, codigo ou marca.</span></div>';
            }
            elements.searchResults.appendChild(empty);
            return;
        }
        items.forEach(function (item) {
            elements.searchResults.appendChild(getSearchMode() === 'category' ? buildCategoryResultCard(item) : buildSearchResultCard(item));
        });
    }

    function clearSearchResults() {
        lastSearchResults = [];
        if (elements.searchResults) {
            elements.searchResults.innerHTML = '';
        }
    }

    async function fetchSearchResults(query) {
        const trimmed = String(query || '').trim();
        if (!trimmed) {
            lastSearchResults = [];
            renderSearchResults([]);
            setSearchStatus(getEmptySearchStatus(), 'muted');
            return;
        }

        if (searchAbortController) {
            searchAbortController.abort();
        }

        searchAbortController = new AbortController();
        setSearchStatus('Buscando itens...', 'muted');

        try {
            const url = new URL(config.searchApiUrl, window.location.origin);
            url.searchParams.set('q', trimmed);
            url.searchParams.set('limit', '12');
            const response = await window.fetch(url.toString(), {
                headers: { Accept: 'application/json' },
                signal: searchAbortController.signal,
            });
            if (!response.ok) {
                throw new Error('Falha ao buscar itens (' + response.status + ')');
            }
            const payload = await response.json();
            const items = Array.isArray(payload.items) ? payload.items : [];
            renderSearchResults(items);
            setSearchStatus(items.length + ' resultado(s) encontrado(s).', items.length ? 'muted' : 'warning');
        } catch (error) {
            if (error && error.name === 'AbortError') {
                return;
            }
            renderSearchResults([]);
            setSearchStatus('Nao foi possivel consultar os itens agora.', 'danger');
        }
    }

    async function fetchCategoryResults(query) {
        const urlBase = getCategoriesUrl();
        if (!urlBase) {
            setSearchStatus('API de categorias indisponivel no momento.', 'danger');
            return;
        }

        if (searchAbortController) {
            searchAbortController.abort();
        }

        searchAbortController = new AbortController();
        setSearchStatus('Buscando categorias...', 'muted');

        try {
            const url = new URL(urlBase, window.location.origin);
            const trimmed = String(query || '').trim();
            if (trimmed) {
                url.searchParams.set('q', trimmed);
            }
            url.searchParams.set('limit', '40');
            const response = await window.fetch(url.toString(), {
                headers: { Accept: 'application/json' },
                signal: searchAbortController.signal,
            });
            if (!response.ok) {
                throw new Error('Falha ao buscar categorias (' + response.status + ')');
            }
            const payload = await response.json();
            const categories = Array.isArray(payload.categories) ? payload.categories : [];
            renderSearchResults(categories);
            if (!trimmed) {
                setSearchStatus(categories.length + ' categoria(s) disponivel(is) no estoque.', categories.length ? 'muted' : 'warning');
            } else {
                setSearchStatus(categories.length + ' categoria(s) encontrada(s).', categories.length ? 'muted' : 'warning');
            }
        } catch (error) {
            if (error && error.name === 'AbortError') {
                return;
            }
            renderSearchResults([]);
            setSearchStatus('Nao foi possivel consultar as categorias agora.', 'danger');
        }
    }

    async function loadCategoryItems(category, options) {
        const settings = options || {};
        if (!category || !category.name) {
            setFeedback('Categoria invalida para carregamento.', 'danger');
            return;
        }
        const urlBase = getCategoryItemsUrl();
        if (!urlBase) {
            setFeedback('API de itens por categoria indisponivel.', 'danger');
            return;
        }
        try {
            const url = new URL(urlBase, window.location.origin);
            url.searchParams.set('category', category.name);
            const payload = await fetchJson(url.toString());
            state.search.selectedCategory = payload.category || category;
            state.search.selectedCategoryItems = Array.isArray(payload.items) ? payload.items : [];
            if (settings.autoAdd) {
                addSelectedCategoryToSheet({ autoAdded: true, clearSelection: true });
                return;
            }
            renderCategorySelection();
            setFeedback('Categoria carregada: ' + (state.search.selectedCategory.name || category.name) + '.', 'muted');
        } catch (error) {
            clearSelectedCategory({ silent: true });
            setFeedback(error.message || 'Nao foi possivel carregar os itens da categoria.', 'danger');
        }
    }

    function scheduleSearch() {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(function () {
            if (getSearchMode() === 'category') {
                fetchCategoryResults(elements.searchInput ? elements.searchInput.value : '');
                return;
            }
            fetchSearchResults(elements.searchInput ? elements.searchInput.value : '');
        }, 180);
    }

    function addItemToSheet(item, options) {
        if (!isSearchReady()) {
            setFeedback('Salve um tamanho predefinido antes de adicionar etiquetas do estoque.', 'warning');
            return null;
        }
        const preset = getPagePreset();
        const itemSize = getNewItemSize();
        const quantity = clamp(parseInt(options && options.quantity ? options.quantity : readAddQuantity(), 10) || 1, 1, 60);
        let lastCreated = null;
        for (let index = 0; index < quantity; index += 1) {
            const offset = (state.items.length + index) % 6;
            const maxX = Math.max(0, preset.widthMm - itemSize.widthMm);
            const maxY = Math.max(0, preset.heightMm - itemSize.heightMm);
            const startX = Math.min(state.page.marginMm, maxX);
            const startY = Math.min(state.page.marginMm, maxY);
            const label = {
                id: createId(),
                codigo: String(item.codigo || '').trim(),
                descricao: String(item.descricao || item.codigo || '').trim(),
                categoria: String(item.categoria || '').trim(),
                marca: String(item.marca || '').trim(),
                unidade: String(item.unidade || '').trim(),
                saldoDisplay: String(item.saldo_display || '').trim(),
                customTitle: String(item.descricao || item.codigo || '').trim(),
                pageIndex: Math.max(0, parseInt(options && options.pageIndex, 10) || 0),
                widthMm: itemSize.widthMm,
                heightMm: itemSize.heightMm,
                xMm: clamp(state.page.marginMm + (offset * 8), startX, maxX),
                yMm: clamp(state.page.marginMm + (offset * 8), startY, maxY),
                barcodeHeightMm: clamp(18, 8, Math.max(8, itemSize.heightMm - 4)),
                paddingMm: 3,
                fontSizePx: 14,
                codeFontSizePx: 11,
                align: 'center',
                showName: true,
                showCode: true,
                editUrl: item.edit_url || null,
                isSnapping: false,
            };
            normalizeLabel(label);
            state.items.push(label);
            lastCreated = label;
        }
        if (lastCreated && (!options || options.selectLast !== false)) {
            state.selectedId = lastCreated.id;
        }
        if (!options || options.render !== false) {
            renderPage();
            renderProperties();
        }
        if (!options || options.silent !== true) {
            setFeedback(quantity + ' etiqueta(s) adicionada(s) para ' + String(item.codigo || '') + '.', 'muted');
        }
        return lastCreated;
    }

    function removeSelectedItem() {
        if (!state.selectedId) {
            setFeedback('Selecione uma etiqueta para remover.', 'warning');
            return;
        }
        const current = getSelectedItem();
        state.items = state.items.filter(function (item) {
            return item.id !== state.selectedId;
        });
        state.selectedId = state.items.length ? state.items[Math.max(0, state.items.length - 1)].id : null;
        renderPage();
        renderProperties();
        setFeedback(current ? 'Etiqueta ' + current.codigo + ' removida da folha.' : 'Etiqueta removida.', 'muted');
    }

    function duplicateSelectedItem() {
        const base = getSelectedItem();
        if (!base) {
            setFeedback('Selecione uma etiqueta para duplicar.', 'warning');
            return;
        }
        const copies = clamp(parseInt(elements.copies ? elements.copies.value : '1', 10) || 1, 1, 24);
        const preset = getPagePreset();
        let created = null;
        for (let index = 0; index < copies; index += 1) {
            const clone = JSON.parse(JSON.stringify(base));
            clone.id = createId();
            clone.pageIndex = Math.max(0, parseInt(base.pageIndex, 10) || 0);
            clone.xMm = clamp(base.xMm + ((index + 1) * 6), 0, Math.max(0, preset.widthMm - base.widthMm));
            clone.yMm = clamp(base.yMm + ((index + 1) * 6), 0, Math.max(0, preset.heightMm - base.heightMm));
            clone.isSnapping = false;
            normalizeLabel(clone);
            state.items.push(clone);
            created = clone;
        }
        if (created) {
            state.selectedId = created.id;
        }
        renderPage();
        renderProperties();
        setFeedback(copies + ' copia(s) criada(s) para ' + base.codigo + '.', 'muted');
    }

    function applyGridLayout() {
        try {
            const result = layoutItemsInGrid(state.items, { startPageIndex: 0 });
            renderPage();
            renderProperties();
            setFeedback(
                'Grade ' + result.columns + ' x ' + result.rows + ' aplicada em ' + getUsedPageCount() + ' folha(s).',
                'muted'
            );
        } catch (error) {
            setFeedback(error.message || 'Nao foi possivel aplicar a grade agora.', 'danger');
        }
    }

    function addSelectedCategoryToSheet(options) {
        const settings = options || {};
        const category = state.search.selectedCategory;
        const items = state.search.selectedCategoryItems || [];
        if (!isSearchReady()) {
            setFeedback('Salve um tamanho predefinido antes de adicionar categorias inteiras na folha.', 'warning');
            return false;
        }
        if (!category) {
            setFeedback('Selecione uma categoria valida antes de adicionar em lote.', 'warning');
            return false;
        }
        if (!items.length) {
            setFeedback('A categoria ' + (category.name || category.label || '') + ' nao possui itens disponiveis para adicionar.', 'warning');
            if (settings.clearSelection) {
                clearSelectedCategory({ silent: true });
            }
            return false;
        }
        const startPageIndex = state.items.length ? getUsedPageCount() : 0;
        const newItems = [];
        let lastCreated = null;
        items.forEach(function (item) {
            lastCreated = addItemToSheet(item, {
                quantity: 1,
                render: false,
                silent: true,
                selectLast: false,
                pageIndex: startPageIndex,
            }) || lastCreated;
            if (lastCreated) {
                newItems.push(lastCreated);
            }
        });
        if (lastCreated) {
            state.selectedId = lastCreated.id;
        }
        try {
            layoutItemsInGrid(newItems, { startPageIndex: startPageIndex });
            renderPage();
            renderProperties();
            setFeedback(
                'Categoria ' + (category.name || category.label || '') + (settings.autoAdded ? ' adicionada automaticamente' : ' adicionada') + ' com ' + items.length + ' etiqueta(s) em ' + getUsedPageCount() + ' folha(s), sem mexer nas etiquetas ja montadas.',
                'muted'
            );
            if (settings.clearSelection) {
                clearSelectedCategory({ silent: true });
            }
            return true;
        } catch (error) {
            state.items = state.items.filter(function (item) {
                return newItems.indexOf(item) === -1;
            });
            state.selectedId = state.items.length ? state.items[state.items.length - 1].id : null;
            renderPage();
            renderProperties();
            if (settings.clearSelection) {
                clearSelectedCategory({ silent: true });
            }
            setFeedback(error.message || 'Nao foi possivel adicionar a categoria inteira agora.', 'danger');
            return false;
        }
    }

    function clearSheet() {
        if (!state.items.length) {
            return;
        }
        if (!window.confirm('Limpar toda a folha A4 atual?')) {
            return;
        }
        state.items = [];
        state.selectedId = null;
        renderPage();
        renderProperties();
        setFeedback('Folha A4 limpa.', 'muted');
    }

    function updateDimensionPresetStatus() {
        const fixedItemSize = getFixedItemSize();
        state.page.defaultItemSize = fixedItemSize;
        if (elements.dimensionPresetStatus) {
            elements.dimensionPresetStatus.textContent = fixedItemSize
                ? 'Dimensao fixa ativa: ' + fixedItemSize.widthMm.toFixed(1) + ' x ' + fixedItemSize.heightMm.toFixed(1) + ' mm. Novas etiquetas entram nesse tamanho.'
                : 'Nenhuma dimensao fixa ativa. Ajuste uma etiqueta e fixe o tamanho para reaproveitar nas proximas.';
        }
        if (elements.lockDimensionsBtn) {
            elements.lockDimensionsBtn.disabled = !getSelectedItem();
        }
        if (elements.clearDimensionsBtn) {
            elements.clearDimensionsBtn.disabled = !fixedItemSize;
        }
        syncSearchAvailabilityUI();
    }

    function applyDimensionPresetFromInputs() {
        const presetSize = readPresetSizeFromInputs();
        if (!presetSize) {
            setFeedback('Informe largura e altura validas para salvar o tamanho predefinido.', 'warning');
            return;
        }
        setFixedItemSize(presetSize);
        syncDimensionPresetInputs({ force: true });
        renderProperties();
        setFeedback(
            'Tamanho predefinido salvo: ' + presetSize.widthMm.toFixed(1) + ' x ' + presetSize.heightMm.toFixed(1) + ' mm. Novas etiquetas vao entrar nesse tamanho.',
            'muted'
        );
    }

    function fixSelectedDimensions() {
        const item = getSelectedItem();
        if (!item) {
            setFeedback('Selecione uma etiqueta para fixar a dimensao.', 'warning');
            updateDimensionPresetStatus();
            return;
        }
        const fixedItemSize = setFixedItemSize({ widthMm: item.widthMm, heightMm: item.heightMm });
        if (!fixedItemSize) {
            setFeedback('Nao foi possivel fixar a dimensao selecionada.', 'danger');
            return;
        }
        state.items.forEach(function (entry) {
            entry.widthMm = fixedItemSize.widthMm;
            entry.heightMm = fixedItemSize.heightMm;
            entry.barcodeHeightMm = clamp(Number(entry.barcodeHeightMm || 18), 8, Math.max(8, fixedItemSize.heightMm - 4));
            entry.isSnapping = false;
            normalizeLabel(entry);
        });
        syncDimensionPresetInputs({ force: true });
        renderPage();
        renderProperties();
        setFeedback('Dimensao ' + fixedItemSize.widthMm.toFixed(1) + ' x ' + fixedItemSize.heightMm.toFixed(1) + ' mm fixada para as etiquetas atuais e futuras.', 'muted');
    }

    function clearFixedDimensions() {
        if (!getFixedItemSize()) {
            setFeedback('Nenhuma dimensao fixa esta ativa.', 'warning');
            updateDimensionPresetStatus();
            return;
        }
        state.page.defaultItemSize = null;
        syncDimensionPresetInputs({ force: true });
        renderProperties();
        setFeedback('Dimensao fixa removida. Novas etiquetas voltam ao tamanho padrao.', 'muted');
    }

    function updateSelectedFromForm() {
        const item = getSelectedItem();
        if (!item) {
            return;
        }
        item.customTitle = String(elements.titleInput ? elements.titleInput.value : item.customTitle).slice(0, 120);
        item.widthMm = parseFloat(elements.widthInput ? elements.widthInput.value : item.widthMm) || item.widthMm;
        item.heightMm = parseFloat(elements.heightInput ? elements.heightInput.value : item.heightMm) || item.heightMm;
        item.xMm = parseFloat(elements.xInput ? elements.xInput.value : item.xMm) || item.xMm;
        item.yMm = parseFloat(elements.yInput ? elements.yInput.value : item.yMm) || item.yMm;
        item.barcodeHeightMm = parseFloat(elements.barcodeHeightInput ? elements.barcodeHeightInput.value : item.barcodeHeightMm) || item.barcodeHeightMm;
        item.paddingMm = parseFloat(elements.paddingInput ? elements.paddingInput.value : item.paddingMm) || item.paddingMm;
        item.fontSizePx = parseFloat(elements.titleSizeInput ? elements.titleSizeInput.value : item.fontSizePx) || item.fontSizePx;
        item.codeFontSizePx = parseFloat(elements.codeSizeInput ? elements.codeSizeInput.value : item.codeFontSizePx) || item.codeFontSizePx;
        item.align = elements.alignInput ? elements.alignInput.value : item.align;
        item.showName = Boolean(elements.showNameInput && elements.showNameInput.checked);
        item.showCode = Boolean(elements.showCodeInput && elements.showCodeInput.checked);
        item.isSnapping = false;
        normalizeLabel(item);
        renderPage();
        renderProperties();
    }

    function renderProperties() {
        const item = getSelectedItem();
        const hasSelection = Boolean(item);
        if (elements.propertiesEmpty) {
            elements.propertiesEmpty.classList.toggle('d-none', hasSelection);
        }
        if (elements.propertiesForm) {
            elements.propertiesForm.classList.toggle('d-none', !hasSelection);
        }
        updateDimensionPresetStatus();
        if (!item) {
            return;
        }

        elements.selectedCode.textContent = item.codigo || '-';
        elements.selectedCategory.textContent = item.categoria || 'Sem categoria';
        elements.selectedBrand.textContent = item.marca || 'Sem marca';
        if (item.editUrl) {
            elements.selectedEditLink.href = item.editUrl;
            elements.selectedEditLink.classList.remove('disabled');
            elements.selectedEditLink.removeAttribute('aria-disabled');
        } else {
            elements.selectedEditLink.href = '#';
            elements.selectedEditLink.classList.add('disabled');
            elements.selectedEditLink.setAttribute('aria-disabled', 'true');
        }

        elements.titleInput.value = item.customTitle || '';
        elements.widthInput.value = item.widthMm.toFixed(1);
        elements.heightInput.value = item.heightMm.toFixed(1);
        elements.xInput.value = item.xMm.toFixed(1);
        elements.yInput.value = item.yMm.toFixed(1);
        elements.barcodeHeightInput.value = item.barcodeHeightMm.toFixed(1);
        elements.paddingInput.value = item.paddingMm.toFixed(1);
        elements.titleSizeInput.value = String(Math.round(item.fontSizePx));
        elements.codeSizeInput.value = String(Math.round(item.codeFontSizePx));
        elements.alignInput.value = item.align;
        elements.showNameInput.checked = item.showName;
        elements.showCodeInput.checked = item.showCode;
    }

    function renderBarcode(labelElement, item) {
        const svg = labelElement.querySelector('svg');
        if (!svg || typeof window.JsBarcode === 'undefined') {
            return;
        }
        try {
            window.JsBarcode(svg, item.codigo, {
                format: inferBarcodeFormat(item.codigo),
                displayValue: false,
                margin: 0,
                width: item.widthMm < 48 ? 1 : 1.35,
                height: Math.max(20, Math.round(mmToPx(item.barcodeHeightMm))),
                background: '#ffffff',
                lineColor: '#111827',
            });
            svg.style.width = '100%';
            svg.style.height = '100%';
        } catch (error) {
            const wrap = labelElement.querySelector('.barcode-studio-label__barcode');
            if (wrap) {
                wrap.innerHTML = '<div class="barcode-studio-barcode-fallback">' + escapeHtml(item.codigo) + '</div>';
            }
        }
    }

    function renderPage() {
        if (!elements.sheetsContainer) {
            return;
        }

        const preset = getPagePreset();
        elements.sheetsContainer.innerHTML = '';

        getPageIndices().forEach(function (pageIndex) {
            const pageShell = document.createElement('section');
            pageShell.className = 'barcode-studio-sheet-page';
            const pageCaption = document.createElement('div');
            pageCaption.className = 'barcode-studio-sheet-caption';
            pageCaption.textContent = 'Folha ' + (pageIndex + 1);
            pageShell.appendChild(pageCaption);

            const sheetWrap = document.createElement('div');
            sheetWrap.className = 'barcode-studio-sheet-wrap';
            const sheet = document.createElement('div');
            sheet.className = 'barcode-studio-sheet';
            sheet.dataset.pageIndex = String(pageIndex);
            sheet.setAttribute('aria-label', 'Folha A4 ' + (pageIndex + 1) + ' para montagem de etiquetas');
            sheet.style.width = mmToPx(preset.widthMm) + 'px';
            sheet.style.height = mmToPx(preset.heightMm) + 'px';

            const pageItems = getItemsForPage(pageIndex);
            if (!pageItems.length && pageIndex === 0 && !state.items.length) {
                const empty = document.createElement('div');
                empty.className = 'barcode-studio-sheet-empty';
                empty.innerHTML = '<i class="bi bi-bounding-box-circles"></i><h3>Nenhuma etiqueta na folha</h3><p>Busque um item ou uma categoria na coluna lateral e adicione para comecar a montar a impressao.</p>';
                sheet.appendChild(empty);
            }

            pageItems.forEach(function (item) {
                normalizeLabel(item);
                const label = document.createElement('article');
                label.className = 'barcode-studio-label' + (item.id === state.selectedId ? ' is-selected' : '') + (item.isSnapping ? ' is-snapping' : '');
                label.dataset.labelId = item.id;
                label.dataset.pageIndex = String(item.pageIndex || 0);
                label.style.left = mmToPx(item.xMm) + 'px';
                label.style.top = mmToPx(item.yMm) + 'px';
                label.style.width = mmToPx(item.widthMm) + 'px';
                label.style.height = mmToPx(item.heightMm) + 'px';
                label.innerHTML = '' +
                    '<div class="barcode-studio-label__chrome">' +
                        '<span class="barcode-studio-label__tag"><i class="bi bi-upc"></i>' + escapeHtml(item.codigo) + '</span>' +
                        '<span>' + item.widthMm.toFixed(1) + ' x ' + item.heightMm.toFixed(1) + ' mm</span>' +
                    '</div>' +
                    '<div class="barcode-studio-label__body" style="padding:' + item.paddingMm + 'mm;text-align:' + item.align + ';">' +
                        (item.showName ? '<div class="barcode-studio-label__title" style="font-size:' + item.fontSizePx + 'px;">' + escapeHtml(item.customTitle) + '</div>' : '') +
                        '<div class="barcode-studio-label__barcode" style="height:' + mmToPx(item.barcodeHeightMm) + 'px;"><svg aria-hidden="true"></svg></div>' +
                        (item.showCode ? '<div class="barcode-studio-label__code" style="font-size:' + item.codeFontSizePx + 'px;">' + escapeHtml(item.codigo) + '</div>' : '') +
                    '</div>' +
                    '<div class="barcode-studio-resize-handle" aria-hidden="true"></div>';
                label.addEventListener('pointerdown', onLabelPointerDown);
                sheet.appendChild(label);
                renderBarcode(label, item);
            });

            sheetWrap.appendChild(sheet);
            pageShell.appendChild(sheetWrap);
            elements.sheetsContainer.appendChild(pageShell);
        });

        updateSheetMetrics();
    }

    function onLabelPointerDown(event) {
        const label = event.currentTarget;
        const item = state.items.find(function (entry) {
            return entry.id === label.dataset.labelId;
        });
        if (!item) {
            return;
        }
        state.selectedId = item.id;
        renderProperties();
        renderPage();

        const isResize = event.target && event.target.classList && event.target.classList.contains('barcode-studio-resize-handle');
        interaction = {
            mode: isResize ? 'resize' : 'drag',
            id: item.id,
            startClientX: event.clientX,
            startClientY: event.clientY,
            startXMm: item.xMm,
            startYMm: item.yMm,
            startWidthMm: item.widthMm,
            startHeightMm: item.heightMm,
        };

        window.addEventListener('pointermove', onPointerMove);
        window.addEventListener('pointerup', onPointerUp);
        event.preventDefault();
    }

    function onPointerMove(event) {
        if (!interaction) {
            return;
        }
        const item = state.items.find(function (entry) {
            return entry.id === interaction.id;
        });
        if (!item) {
            return;
        }
        const deltaX = pxToMm(event.clientX - interaction.startClientX);
        const deltaY = pxToMm(event.clientY - interaction.startClientY);
        if (interaction.mode === 'resize') {
            item.widthMm = interaction.startWidthMm + deltaX;
            item.heightMm = interaction.startHeightMm + deltaY;
        } else {
            item.xMm = interaction.startXMm + deltaX;
            item.yMm = interaction.startYMm + deltaY;
        }
        applySnapping(item, interaction.mode);
        normalizeLabel(item);
        renderPage();
        renderProperties();
    }

    function onPointerUp() {
        state.items.forEach(function (item) {
            item.isSnapping = false;
        });
        hideGuides();
        interaction = null;
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', onPointerUp);
        renderPage();
    }

    function nudgeSelected(deltaX, deltaY) {
        const item = getSelectedItem();
        if (!item) {
            return;
        }
        item.xMm += deltaX;
        item.yMm += deltaY;
        applySnapping(item, 'drag');
        item.isSnapping = false;
        hideGuides();
        normalizeLabel(item);
        renderPage();
        renderProperties();
    }

    function buildPrintableMarkup() {
        return getPageIndices().map(function (pageIndex) {
            const pageMarkup = getItemsForPage(pageIndex).map(function (item) {
                const current = elements.sheetsContainer.querySelector('[data-label-id="' + item.id + '"]');
                const svgElement = current ? current.querySelector('svg') : null;
                const svgMarkup = svgElement ? svgElement.outerHTML : '';
                return '' +
                    '<article class="barcode-print-label" style="left:' + item.xMm + 'mm;top:' + item.yMm + 'mm;width:' + item.widthMm + 'mm;height:' + item.heightMm + 'mm;padding:' + item.paddingMm + 'mm;text-align:' + item.align + ';">' +
                        (item.showName ? '<div class="barcode-print-label__title" style="font-size:' + item.fontSizePx + 'px;">' + escapeHtml(item.customTitle) + '</div>' : '') +
                        '<div class="barcode-print-label__barcode" style="height:' + item.barcodeHeightMm + 'mm;">' + (svgMarkup || ('<div>' + escapeHtml(item.codigo) + '</div>')) + '</div>' +
                        (item.showCode ? '<div class="barcode-print-label__code" style="font-size:' + item.codeFontSizePx + 'px;">' + escapeHtml(item.codigo) + '</div>' : '') +
                    '</article>';
            }).join('');
            return '<section class="barcode-print-sheet">' + pageMarkup + '</section>';
        }).join('');
    }

    function printSheet() {
        if (!state.items.length) {
            setFeedback('Adicione pelo menos uma etiqueta antes de imprimir.', 'warning');
            return;
        }
        const preset = getPagePreset();
        const printWindow = window.open('', '_blank', 'noopener,noreferrer');
        if (!printWindow) {
            setFeedback('Nao foi possivel abrir a janela de impressao.', 'danger');
            return;
        }
        const html = '' +
            '<!doctype html>' +
            '<html lang="pt-BR">' +
            '<head>' +
                '<meta charset="utf-8">' +
                '<title>Impressao de codigos</title>' +
                '<style>' +
                    '@page { size: A4 ' + state.page.orientation + '; margin: 8mm; }' +
                    'html, body { margin: 0; padding: 0; background: #ffffff; }' +
                    'body { font-family: Arial, sans-serif; }' +
                    '.barcode-print-sheet { position: relative; width: ' + preset.widthMm + 'mm; height: ' + preset.heightMm + 'mm; margin: 0 auto; background: #ffffff; break-after: page; page-break-after: always; }' +
                    '.barcode-print-sheet:last-child { break-after: auto; page-break-after: auto; }' +
                    '.barcode-print-label { position: absolute; box-sizing: border-box; overflow: hidden; background: #ffffff; color: #111827; display: flex; flex-direction: column; justify-content: center; line-height: 1.15; }' +
                    '.barcode-print-label__title { font-weight: 700; margin-bottom: 1.6mm; }' +
                    '.barcode-print-label__barcode { display: flex; align-items: center; justify-content: center; width: 100%; }' +
                    '.barcode-print-label__barcode svg { display: block; width: 100%; height: 100%; }' +
                    '.barcode-print-label__code { margin-top: 1.5mm; color: #334155; word-break: break-all; }' +
                '</style>' +
            '</head>' +
            '<body>' +
                '<div class="barcode-print-document">' + buildPrintableMarkup() + '</div>' +
                '<script>' +
                    'window.addEventListener("load", function () {' +
                        'window.setTimeout(function () { window.print(); window.close(); }, 180);' +
                    '});' +
                '<\/script>' +
            '</body>' +
            '</html>';
        printWindow.document.open();
        printWindow.document.write(html);
        printWindow.document.close();
    }

    async function exportSheetPdf() {
        if (!state.items.length) {
            setFeedback('Adicione pelo menos uma etiqueta antes de exportar PDF.', 'warning');
            return;
        }
        if (!elements.sheetsContainer || !window.html2canvas || !window.jspdf || !window.jspdf.jsPDF) {
            setFeedback('Biblioteca de PDF indisponivel no momento.', 'danger');
            return;
        }
        try {
            setFeedback('Gerando PDF da folha...', 'muted');
            const preset = getPagePreset();
            const sheets = Array.from(elements.sheetsContainer.querySelectorAll('.barcode-studio-sheet'));
            const orientation = state.page.orientation === 'landscape' ? 'l' : 'p';
            const pdf = new window.jspdf.jsPDF({
                orientation: orientation,
                unit: 'mm',
                format: 'a4',
                compress: true,
            });
            for (let index = 0; index < sheets.length; index += 1) {
                const canvas = await window.html2canvas(sheets[index], {
                    backgroundColor: '#ffffff',
                    scale: 2,
                    useCORS: true,
                    logging: false,
                });
                if (index > 0) {
                    pdf.addPage('a4', orientation);
                }
                const imageData = canvas.toDataURL('image/png');
                pdf.addImage(imageData, 'PNG', 0, 0, preset.widthMm, preset.heightMm, undefined, 'FAST');
            }
            const fileName = 'barcode-studio-' + new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-') + '.pdf';
            pdf.save(fileName);
            setFeedback('PDF exportado com sucesso.', 'muted');
        } catch (error) {
            setFeedback('Nao foi possivel exportar o PDF agora.', 'danger');
        }
    }

    function wireProperties() {
        [
            elements.titleInput,
            elements.widthInput,
            elements.heightInput,
            elements.xInput,
            elements.yInput,
            elements.barcodeHeightInput,
            elements.paddingInput,
            elements.titleSizeInput,
            elements.codeSizeInput,
            elements.alignInput,
            elements.showNameInput,
            elements.showCodeInput,
        ].forEach(function (element) {
            if (!element) {
                return;
            }
            element.addEventListener('input', updateSelectedFromForm);
            element.addEventListener('change', updateSelectedFromForm);
        });
    }

    function wirePageControls() {
        elements.orientation && elements.orientation.addEventListener('change', function () {
            state.page.orientation = elements.orientation.value;
            renderPage();
            renderProperties();
        });
        elements.columns && elements.columns.addEventListener('change', function () {
            state.page.columns = clamp(parseInt(elements.columns.value, 10) || 3, 1, 8);
            updateSheetMetrics();
        });
        elements.rows && elements.rows.addEventListener('change', function () {
            state.page.rows = clamp(parseInt(elements.rows.value, 10) || 8, 1, 12);
            updateSheetMetrics();
        });
        elements.gap && elements.gap.addEventListener('change', function () {
            state.page.gapMm = clamp(parseFloat(elements.gap.value) || 0, 0, 30);
            updateSheetMetrics();
        });
        elements.margin && elements.margin.addEventListener('change', function () {
            state.page.marginMm = clamp(parseFloat(elements.margin.value) || 10, 4, 30);
            updateSheetMetrics();
        });
        elements.gridAlignInput && elements.gridAlignInput.addEventListener('change', function () {
            state.page.gridAlignX = elements.gridAlignInput.value === 'left' ? 'left' : 'center';
            updateSheetMetrics();
        });
        elements.snapToggle && elements.snapToggle.addEventListener('change', function () {
            state.page.snapEnabled = Boolean(elements.snapToggle.checked);
            hideGuides();
        });
        elements.gridBtn && elements.gridBtn.addEventListener('click', applyGridLayout);
        elements.clearBtn && elements.clearBtn.addEventListener('click', clearSheet);
        elements.printBtn && elements.printBtn.addEventListener('click', printSheet);
        elements.pdfBtn && elements.pdfBtn.addEventListener('click', exportSheetPdf);
        elements.removeBtn && elements.removeBtn.addEventListener('click', removeSelectedItem);
        elements.duplicateBtn && elements.duplicateBtn.addEventListener('click', duplicateSelectedItem);
        elements.applyPresetBtn && elements.applyPresetBtn.addEventListener('click', applyDimensionPresetFromInputs);
        elements.lockDimensionsBtn && elements.lockDimensionsBtn.addEventListener('click', fixSelectedDimensions);
        elements.clearDimensionsBtn && elements.clearDimensionsBtn.addEventListener('click', clearFixedDimensions);
        elements.addCategoryBtn && elements.addCategoryBtn.addEventListener('click', addSelectedCategoryToSheet);
        elements.nudgeLeftBtn && elements.nudgeLeftBtn.addEventListener('click', function () { nudgeSelected(-1, 0); });
        elements.nudgeRightBtn && elements.nudgeRightBtn.addEventListener('click', function () { nudgeSelected(1, 0); });
        elements.nudgeUpBtn && elements.nudgeUpBtn.addEventListener('click', function () { nudgeSelected(0, -1); });
        elements.nudgeDownBtn && elements.nudgeDownBtn.addEventListener('click', function () { nudgeSelected(0, 1); });
        elements.saveLayoutBtn && elements.saveLayoutBtn.addEventListener('click', saveCurrentLayout);
        elements.saveAsFileBtn && elements.saveAsFileBtn.addEventListener('click', saveLayoutAsFile);
        elements.importFileBtn && elements.importFileBtn.addEventListener('click', function () {
            if (elements.importFileInput) {
                elements.importFileInput.click();
            }
        });
        elements.loadLayoutBtn && elements.loadLayoutBtn.addEventListener('click', loadSelectedLayout);
        elements.deleteLayoutBtn && elements.deleteLayoutBtn.addEventListener('click', deleteSelectedLayout);
        elements.importFileInput && elements.importFileInput.addEventListener('change', function () {
            const file = elements.importFileInput.files && elements.importFileInput.files[0] ? elements.importFileInput.files[0] : null;
            importLayoutFile(file);
            elements.importFileInput.value = '';
        });
        elements.savedLayouts && elements.savedLayouts.addEventListener('change', function () {
            const layout = state.savedLayouts.find(function (entry) {
                return entry.filename === elements.savedLayouts.value;
            });
            if (layout && elements.layoutName) {
                elements.layoutName.value = layout.name;
            }
        });
    }

    function wireSearch() {
        elements.searchMode && elements.searchMode.addEventListener('change', function () {
            if (!isSearchReady()) {
                syncSearchAvailabilityUI();
                return;
            }
            const categoryName = getSelectedCategoryNameFromSearchOption();
            state.search.mode = categoryName ? 'category' : 'item';
            syncSearchModeUI();
            clearSearchResults();
            clearSelectedCategory({ silent: true });
            if (categoryName) {
                loadCategoryItems({ name: categoryName }, { autoAdd: true });
                return;
            }
            if (elements.searchInput) {
                elements.searchInput.value = '';
                elements.searchInput.focus();
            }
            setSearchStatus(getEmptySearchStatus(), 'muted');
        });
        elements.searchInput && elements.searchInput.addEventListener('input', scheduleSearch);
        elements.searchInput && elements.searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && lastSearchResults.length) {
                event.preventDefault();
                if (lastSearchMode === 'category') {
                    loadCategoryItems(lastSearchResults[0]);
                    return;
                }
                addItemToSheet(lastSearchResults[0], { quantity: readAddQuantity() });
            }
        });
        elements.searchClear && elements.searchClear.addEventListener('click', function () {
            if (elements.searchInput) {
                elements.searchInput.value = '';
                elements.searchInput.focus();
            }
            clearSearchResults();
            clearSelectedCategory({ silent: true });
            if (getSearchMode() === 'category') {
                fetchCategoryResults('');
                return;
            }
            setSearchStatus('Busca limpa. Digite outro termo.', 'muted');
        });
    }

    function wireKeyboardShortcuts() {
        document.addEventListener('keydown', function (event) {
            const tagName = String(document.activeElement && document.activeElement.tagName || '').toLowerCase();
            if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
                return;
            }
            if ((event.key === 'Delete' || event.key === 'Backspace') && state.selectedId) {
                event.preventDefault();
                removeSelectedItem();
            }
        });
    }

    function init() {
        if (elements.searchMode) {
            elements.searchMode.value = state.search.mode;
        }
        syncSearchAvailabilityUI();
        wireSearch();
        wireProperties();
        wirePageControls();
        wireKeyboardShortcuts();
        updateLayoutsDirNote(config.internalLayoutsDir || '');
        refreshSavedLayouts('');
        syncPageInputs();
        syncDimensionPresetInputs({ force: true });
        renderPage();
        renderProperties();
        renderCategorySelection();
        updateSheetMetrics();
        guideState = createGuideState();
        hideGuides();
        importPendingLayoutFromQuery();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();