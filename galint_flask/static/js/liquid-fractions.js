(function (global) {
    "use strict";

    const PLACEHOLDER = "__codigo__";

    function writeValue(element, value) {
        if (!element) {
            return;
        }
        const tag = element.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") {
            element.value = value;
        } else {
            element.textContent = value;
        }
    }

    function inferUnit(value) {
        if (!value) {
            return "";
        }
        const normalized = value.toString().trim().toLowerCase();
        if (!normalized) {
            return "";
        }
        // Normaliza acentos, espaços e remove números
        const clean = normalized
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/\s+/g, "")
            .replace(/[0-9]/g, "");

        if (!clean) {
            return "";
        }
        // Verifica quilos
        if (clean.includes("kg") || clean.includes("quilo") || clean === "quilos" || clean === "kilo") {
            return "quilo";
        }
        // Verifica litros
        if (clean.includes("litro") || clean === "litros" || clean === "l" || clean === "lt" || clean === "lts") {
            return "litro";
        }
        return normalized;
    }

    function unitLabel(value) {
        const normalized = inferUnit(value);
        if (!normalized) {
            return "";
        }
        if (normalized === "litro") {
            return "L";
        }
        if (normalized === "quilo") {
            return "kg";
        }
        return "";
    }

    function setSummary(outputs, data) {
        const { litros, quilos, fracaoText, restanteText } = data || {};
        writeValue(outputs.litros, typeof litros === "number" && !Number.isNaN(litros)
            ? `${litros.toFixed(3)} L`
            : "-");
        writeValue(outputs.quilos, typeof quilos === "number" && !Number.isNaN(quilos)
            ? `${quilos.toFixed(3)} kg`
            : "-");
        writeValue(outputs.fracao, fracaoText || "-");
        writeValue(outputs.restante, restanteText || "-");
    }

    function resetSummary(outputs) {
        writeValue(outputs.litros, "-");
        writeValue(outputs.quilos, "-");
        writeValue(outputs.fracao, "-");
        writeValue(outputs.restante, "-");
    }

    function fetchItemInfo(template, codigo) {
        if (!codigo) {
            return Promise.resolve(null);
        }
        const url = template.replace(PLACEHOLDER, encodeURIComponent(codigo));
        return fetch(url, {
            headers: {
                Accept: "application/json",
            },
            credentials: "same-origin",
        }).then((response) => {
            if (!response.ok) {
                return null;
            }
            return response.json();
        }).catch(() => null);
    }

    function getSelectedType(select, types) {
        if (!select) {
            return null;
        }
        return types.find((entry) => entry.id === select.value) || null;
    }

    function setupForm(form, options) {
        const toggleBtn = form.querySelector("[data-liquid-toggle]");
        const panel = form.querySelector("[data-liquid-panel]");
        const disableBtn = form.querySelector("[data-liquid-disable]");
        const toggleHint = form.querySelector('[data-liquid-hint="toggle"]');
        const enabledField = form.querySelector('[data-liquid-field="enabled"]');
        const numeratorField = form.querySelector('[data-liquid-field="numerator"]');
        const denominatorField = form.querySelector('[data-liquid-field="denominator"]');
        const quantityInput = form.querySelector('[data-liquid-element="quantity"]');
        const typeSelect = form.querySelector('[data-liquid-element="type-select"]');
        const totalInput = form.querySelector('[data-liquid-element="total"]');
        const fractionsContainer = form.querySelector('[data-liquid-element="fractions"]');
        const fractionButtons = fractionsContainer
            ? Array.from(fractionsContainer.querySelectorAll('[data-liquid-fraction]'))
            : [];
        const outputs = {
            produto: form.querySelector('[data-liquid-output="produto"]'),
            litros: form.querySelector('[data-liquid-output="litros"]'),
            quilos: form.querySelector('[data-liquid-output="quilos"]'),
            fracao: form.querySelector('[data-liquid-output="fracao"]'),
            restante: form.querySelector('[data-liquid-output="restante"]'),
        };
        const unidadeHint = form.querySelector('[data-liquid-output="embalagem-unidade"]');
        const itemInput = form.querySelector('input[name="codigo"]');

        if (!toggleBtn || !panel || !enabledField || !quantityInput || !typeSelect || !totalInput) {
            return;
        }


        const isCheckboxToggle = toggleBtn.tagName === "INPUT" && toggleBtn.type === "checkbox";
        const toggleTextTarget = form.querySelector('[data-liquid-toggle-label]') || (isCheckboxToggle ? null : toggleBtn);
        const originalToggleText = toggleTextTarget ? (toggleTextTarget.textContent || "") : "";
        const defaultHintText = toggleHint ? toggleHint.textContent : "";
        let suppressToggleEvent = false;
        let lastToggleChecked = isCheckboxToggle ? toggleBtn.checked : false;

        function setToggleText(text) {
            if (toggleTextTarget) {
                toggleTextTarget.textContent = text;
            }
        }

        function setToggleChecked(value) {
            if (!isCheckboxToggle) {
                return;
            }
            suppressToggleEvent = true;
            toggleBtn.checked = Boolean(value);
            suppressToggleEvent = false;
        }

        let state = {
            enabled: false,
            manualQuantity: quantityInput.value,
            selectedFraction: null,
            itemInfo: null,
            unitType: "",
            lastCode: "",
        };

        function disableFractionMode() {
            state.enabled = false;
            enabledField.value = "0";
            panel.hidden = true;
            setToggleText(originalToggleText);
            setToggleChecked(false);
            quantityInput.readOnly = false;
            numeratorField.value = "";
            denominatorField.value = "";
            fractionButtons.forEach((btn) => {
                btn.classList.remove("active");
                btn.classList.remove("selecionada");
            });
            resetSummary(outputs);
            writeValue(outputs.produto, "-");
            if (toggleHint) {
                toggleHint.textContent = defaultHintText || "Opcional: ative o seletor quando quiser calcular frações.";
                toggleHint.classList.remove("text-danger", "text-warning");
            }
            if (state.manualQuantity !== undefined) {
                quantityInput.value = state.manualQuantity || quantityInput.value;
            }
        }

        function recalc() {
            if (!state.enabled) {
                return;
            }
            const type = options.types.find((entry) => entry.id === typeSelect.value);
            const total = Number(totalInput.value);
            let num = Number(numeratorField.value);
            let den = Number(denominatorField.value);
            if ((!num || !den) && fractionButtons.length) {
                const firstBtn = fractionButtons[0];
                fractionButtons.forEach((inner) => {
                    inner.classList.remove("active");
                    inner.classList.remove("selecionada");
                });
                firstBtn.classList.add("active");
                firstBtn.classList.add("selecionada");
                num = Number(firstBtn.getAttribute("data-num"));
                den = Number(firstBtn.getAttribute("data-den"));
                numeratorField.value = Number.isFinite(num) ? String(num) : "";
                denominatorField.value = Number.isFinite(den) ? String(den) : "";
            }
            if (!type || !total || total <= 0 || !num || !den || num <= 0 || den <= 0) {
                resetSummary(outputs);
                return;
            }
            let unitType = state.unitType;
            if (state.itemInfo) {
                unitType = unitType || inferUnit(state.itemInfo.unidade) || inferUnit(type.default_unit);
            } else {
                unitType = unitType || inferUnit(type && type.default_unit);
            }
            
            // Se ainda não detectou, usa o padrão do tipo selecionado
            if (!unitType || (unitType !== "litro" && unitType !== "quilo")) {
                unitType = type && type.default_unit ? inferUnit(type.default_unit) : "litro";
            }
            
            if (!state.itemInfo) {
                state.unitType = unitType;
            }
            const fractionValue = total * (num / den);
            if (!fractionValue || fractionValue <= 0) {
                resetSummary(outputs);
                return;
            }
            
            // Validação final: se não é litro nem quilo, aplica fallback seguro
            if (unitType !== "litro" && unitType !== "quilo") {
                unitType = "litro";
            }
            
            let litros = 0;
            let quilos = 0;
            let restante = Math.max(total - fractionValue, 0);
            const unidadeItemRaw = state.itemInfo ? (state.itemInfo.unidade || "") : "";
            const unidadeItem = inferUnit(unidadeItemRaw);
            const isUnitStock = Boolean(unidadeItemRaw) && unidadeItem !== "litro" && unidadeItem !== "quilo";
            let quantidadeEstoque = isUnitStock ? (num / den) : fractionValue;
            if (unitType === "litro") {
                litros = fractionValue;
            } else if (unitType === "quilo") {
                quilos = fractionValue;
            }
            quantityInput.value = quantidadeEstoque.toFixed(3);
            const unidadeDescricao = state.itemInfo
                ? (state.itemInfo.unidade || unitType)
                : unitType;
            const unidadeLbl = unitLabel(unitType) || unitLabel(unidadeDescricao);
            setSummary(outputs, {
                litros,
                quilos,
                fracaoText: `${num}/${den}`,
                restanteText: `${restante.toFixed(3)} ${unidadeLbl || ""}`.trim(),
            });
        }

        function enableFractionMode() {
            state.manualQuantity = quantityInput.value;
            state.enabled = true;
            enabledField.value = "1";
            panel.hidden = false;
            setToggleChecked(true);
            if (!isCheckboxToggle) {
                setToggleText("Desativar cálculo por frações");
            }
            quantityInput.readOnly = true;
            if (state.itemInfo && state.itemInfo.tipo_id) {
                typeSelect.value = state.itemInfo.tipo_id;
            }
            const selectedType = getSelectedType(typeSelect, options.types);
            if (state.itemInfo) {
                writeValue(outputs.produto, state.itemInfo.descricao || state.itemInfo.codigo || "-");
            } else if (selectedType) {
                writeValue(outputs.produto, selectedType.label);
                state.unitType = inferUnit(selectedType.default_unit) || state.unitType || "litro";
            } else {
                writeValue(outputs.produto, "-");
            }
            numeratorField.value = "";
            denominatorField.value = "";
            fractionButtons.forEach((btn) => {
                btn.classList.remove("active");
                btn.classList.remove("selecionada");
            });
            resetSummary(outputs);
            totalInput.focus();
            if (toggleHint) {
                toggleHint.textContent = "Calculadora fracionada ativa.";
                toggleHint.classList.remove("text-danger", "text-warning");
            }
        }

        function handleToggleChange() {
            if (suppressToggleEvent) {
                return;
            }
            if (isCheckboxToggle && toggleBtn.checked === lastToggleChecked) {
                return;
            }
            if (isCheckboxToggle) {
                lastToggleChecked = toggleBtn.checked;
            }
            if (toggleBtn.checked || !isCheckboxToggle) {
                enableFractionMode();
            } else {
                disableFractionMode();
            }
        }

        if (isCheckboxToggle) {
            toggleBtn.addEventListener("change", handleToggleChange);
            toggleBtn.addEventListener("click", handleToggleChange);
        } else {
            toggleBtn.addEventListener("click", () => {
                if (!state.enabled) {
                    enableFractionMode();
                } else {
                    disableFractionMode();
                }
            });
        }

        if (disableBtn) {
            disableBtn.addEventListener("click", () => disableFractionMode());
        }

        if (typeSelect) {
            typeSelect.addEventListener("change", () => {
                const selectedType = getSelectedType(typeSelect, options.types);
                if (!state.itemInfo) {
                    writeValue(outputs.produto, selectedType ? selectedType.label : "-");
                    state.unitType = inferUnit(selectedType && selectedType.default_unit) || state.unitType;
                }
                recalc();
            });
        }

        totalInput.addEventListener("input", () => recalc());

        quantityInput.addEventListener("blur", () => {
            if (state.enabled) {
                return;
            }
            const value = Number(quantityInput.value);
            if (!Number.isFinite(value)) {
                return;
            }
            quantityInput.value = String(Math.round(value));
        });

        fractionButtons.forEach((btn) => {
            btn.addEventListener("click", () => {
                if (!state.enabled) {
                    return;
                }
                fractionButtons.forEach((inner) => {
                    inner.classList.remove("active");
                    inner.classList.remove("selecionada");
                });
                btn.classList.add("active");
                btn.classList.add("selecionada");
                const num = Number(btn.getAttribute("data-num"));
                const den = Number(btn.getAttribute("data-den"));
                numeratorField.value = Number.isFinite(num) ? String(num) : "";
                denominatorField.value = Number.isFinite(den) ? String(den) : "";
                recalc();
            });
        });

        function applyItemInfo(info) {
            state.itemInfo = info;
            state.unitType = inferUnit(info.unidade);
            const supported = Boolean(info.tipo_id);
            if (!supported) {
                if (toggleHint) {
                    toggleHint.textContent = "Item sem configuração automática; selecione o tipo manualmente.";
                    toggleHint.classList.remove("text-danger");
                    toggleHint.classList.add("text-warning");
                }
            } else if (state.enabled) {
                typeSelect.value = info.tipo_id;
                recalc();
            } else {
                if (toggleHint) {
                    toggleHint.textContent = "Ative o seletor para habilitar o cálculo por frações.";
                    toggleHint.classList.remove("text-danger", "text-warning");
                }
            }
            if (unidadeHint) {
                if (state.unitType === "litro") {
                    unidadeHint.textContent = "Informe na unidade do item (Litros).";
                } else if (state.unitType === "quilo") {
                    unidadeHint.textContent = "Informe na unidade do item (Quilos).";
                } else {
                    unidadeHint.textContent = "Informe na unidade do item.";
                }
            }
            writeValue(outputs.produto, info.descricao || info.codigo || "-");
        }

        function resetItemInfo() {
            state.itemInfo = null;
            state.unitType = "";
            setToggleChecked(false);
            disableFractionMode();
            if (unidadeHint) {
                unidadeHint.textContent = "Informe na unidade do item.";
            }
            if (toggleHint) {
                toggleHint.textContent = defaultHintText || "Opcional: ative o seletor quando quiser calcular frações.";
                toggleHint.classList.remove("text-danger", "text-warning");
            }
            writeValue(outputs.produto, "-");
        }

        if (itemInput) {
            const handleChange = () => {
                const codigo = (itemInput.value || "").trim();
                if (!codigo) {
                    state.lastCode = "";
                    resetItemInfo();
                    return;
                }
                if (codigo === state.lastCode) {
                    return;
                }
                state.lastCode = codigo;
                fetchItemInfo(options.itemInfoUrlTemplate, codigo).then((info) => {
                    if (!info || !info.found) {
                        resetItemInfo();
                        return;
                    }
                    applyItemInfo(info);
                }).catch(() => {
                    resetItemInfo();
                });
            };
            itemInput.addEventListener("change", handleChange);
            itemInput.addEventListener("blur", handleChange);
        }

        // Se houver tipo padrão, atualiza o rótulo do produto quando não há item carregado.
        const selectedType = getSelectedType(typeSelect, options.types);
        if (selectedType && !state.itemInfo) {
            writeValue(outputs.produto, selectedType.label);
        }
    }

    function initLiquidFractionForms(options) {
        if (!options || !options.types || !options.fractions || !options.itemInfoUrlTemplate) {
            return;
        }
        const forms = document.querySelectorAll('[data-liquid-form="true"]');
        forms.forEach((form) => setupForm(form, options));
    }

    global.initLiquidFractionForms = initLiquidFractionForms;
}(window));
