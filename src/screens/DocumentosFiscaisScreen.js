import React, { useEffect, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from 'react-native';

import HeroScreen from '../components/HeroScreen';
import ApiService from '../services/api';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

const DEFAULT_CONFIG = {
    today: '',
    categorias: [],
    unidades_base: ['Unidade'],
    unidades_documentais: ['par', 'rolo', 'lata', 'balde', 'bombona', 'caixa', 'pacote', 'fardo', 'saco', 'litro'],
    fornecedores: [],
    tipos_documento: [
        { value: 'nf', label: 'Nota fiscal' },
        { value: 'cupom', label: 'Cupom não fiscal' },
        { value: 'recibo', label: 'Recibo' },
        { value: 'manual', label: 'Manual' },
    ],
    origens_valor: [
        { value: 'compra_nf', label: 'Compra com NF' },
        { value: 'compra_cupom', label: 'Compra com cupom' },
        { value: 'valor_estimado', label: 'Valor estimado' },
        { value: 'inventario_inicial', label: 'Inventário inicial' },
    ],
    comprovacoes: [
        { value: 'comprovado', label: 'Comprovado' },
        { value: 'parcial', label: 'Parcial' },
        { value: 'sem_comprovacao', label: 'Sem comprovação' },
    ],
};

const DOC_MODE_PRESETS = {
    nf: {
        title: 'Nota fiscal',
        subtitle: 'Fluxo completo para lançar compra com número, emissão, fornecedor e classificação financeira.',
        documentType: 'nf',
        origin: 'compra_nf',
        proof: 'comprovado',
        note: 'Use NF quando o documento tiver emissão, fornecedor e chave quando necessário.',
    },
    cupom: {
        title: 'Cupom e comprovantes',
        subtitle: 'Lançamento rápido para cupom, NFC-e simples ou compra presencial com comprovação direta.',
        documentType: 'cupom',
        origin: 'compra_cupom',
        proof: 'comprovado',
        note: 'Cupom mantém o financeiro amarrado sem forçar chave de acesso.',
    },
    recibo: {
        title: 'Recibo e avulsos',
        subtitle: 'Para recibos simples, comprovantes avulsos e compras com documento não fiscalizado como NF.',
        documentType: 'recibo',
        origin: 'compra_cupom',
        proof: 'parcial',
        note: 'Recibo exige fornecedor identificado por nome e não usa CNPJ do emitente.',
    },
    manual: {
        title: 'Manual e estimado',
        subtitle: 'Para entradas sem documento formal ou acerto inicial controlado.',
        documentType: 'manual',
        origin: 'valor_estimado',
        proof: 'sem_comprovacao',
        note: 'Quando o documento não existir, registre a origem do valor e detalhe a observação.',
    },
};

function buildInitialForm(config) {
    const categorias = Array.isArray(config?.categorias) ? config.categorias : [];
    const unidadesBase = Array.isArray(config?.unidades_base) && config.unidades_base.length
        ? config.unidades_base
        : ['Unidade'];
    const today = config?.today || '';

    return {
        quantidade: '1',
        nota_fiscal: '',
        data_emissao: today,
        data_recebimento: today,
        supplier_search: '',
        supplier_cnpj: '',
        chave_acesso: '',
        preco_unitario: '',
        finance_tipo_documento: 'nf',
        finance_origem_valor: 'compra_nf',
        finance_comprovacao_status: 'comprovado',
        finance_observacao: '',
        novo_codigo: '',
        nova_descricao: '',
        nova_marca: '',
        nova_categoria: categorias[0] || 'Material Eletrico',
        nova_unidade: unidadesBase[0] || 'Unidade',
        nova_unidade_documental: '',
        novo_conteudo_embalagem: '',
    };
}

function normalizeNumber(value) {
    const raw = String(value || '').trim();
    if (!raw) return null;
    const normalized = raw.replace(/\s+/g, '').replace(',', '.');
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
}

function getSupplierLabel(supplier) {
    return supplier?.nome_exibicao || supplier?.nome_fantasia || supplier?.razao_social || '';
}

function ChoiceGrid({ options, value, onChange }) {
    return (
        <View style={styles.choiceGrid}>
            {options.map((option) => {
                const normalized = typeof option === 'string'
                    ? { value: option, label: option }
                    : option;
                const selected = normalized.value === value;
                return (
                    <TouchableOpacity
                        key={normalized.value}
                        style={[styles.choicePill, selected && styles.choicePillSelected]}
                        onPress={() => onChange(normalized.value)}
                        activeOpacity={0.85}
                    >
                        <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{normalized.label}</Text>
                    </TouchableOpacity>
                );
            })}
        </View>
    );
}

function FieldCard({ label, helper, children }) {
    return (
        <View style={styles.fieldCard}>
            <Text style={styles.fieldLabel}>{label}</Text>
            {helper ? <Text style={styles.fieldHelper}>{helper}</Text> : null}
            {children}
        </View>
    );
}

function DocumentSection({ title, text, children }) {
    return (
        <View style={styles.sectionCard}>
            <Text style={styles.sectionTitle}>{title}</Text>
            {text ? <Text style={styles.sectionText}>{text}</Text> : null}
            {children}
        </View>
    );
}

export default function DocumentosFiscaisScreen() {
    const [config, setConfig] = useState(DEFAULT_CONFIG);
    const [form, setForm] = useState(buildInitialForm(DEFAULT_CONFIG));
    const [docMode, setDocMode] = useState('nf');
    const [loading, setLoading] = useState(true);
    const [loadMessage, setLoadMessage] = useState('');
    const [saving, setSaving] = useState(false);
    const [useNewItem, setUseNewItem] = useState(false);
    const [itemSearch, setItemSearch] = useState('');
    const [itemResults, setItemResults] = useState([]);
    const [itemSearchLoading, setItemSearchLoading] = useState(false);
    const [selectedItem, setSelectedItem] = useState(null);
    const [selectedSupplier, setSelectedSupplier] = useState(null);

    useEffect(() => {
        let active = true;

        const loadConfig = async () => {
            setLoading(true);
            setLoadMessage('');

            const result = await ApiService.getDocumentosFiscaisConfig();
            if (!active) return;

            if (!result?.success) {
                setLoadMessage(result?.message || 'Não foi possível carregar a configuração documental.');
                setLoading(false);
                return;
            }

            const nextConfig = { ...DEFAULT_CONFIG, ...(result.data || {}) };
            setConfig(nextConfig);
            setForm(buildInitialForm(nextConfig));
            setDocMode('nf');
            setLoading(false);
        };

        loadConfig();

        return () => {
            active = false;
        };
    }, []);

    useEffect(() => {
        let active = true;
        let timer = null;

        if (useNewItem || itemSearch.trim().length < 2) {
            setItemResults([]);
            setItemSearchLoading(false);
            return undefined;
        }

        setItemSearchLoading(true);
        timer = setTimeout(async () => {
            const result = await ApiService.searchDocumentosFiscaisItems(itemSearch, 12);
            if (!active) return;
            setItemResults(result?.success ? (result.data || []) : []);
            setItemSearchLoading(false);
        }, 260);

        return () => {
            active = false;
            if (timer) clearTimeout(timer);
        };
    }, [itemSearch, useNewItem]);

    const preset = DOC_MODE_PRESETS[docMode] || DOC_MODE_PRESETS.nf;
    const quantidadeNumero = useMemo(() => normalizeNumber(form.quantidade), [form.quantidade]);
    const precoNumero = useMemo(() => normalizeNumber(form.preco_unitario), [form.preco_unitario]);
    const totalCalculado = useMemo(() => {
        if (quantidadeNumero == null || precoNumero == null) return null;
        return quantidadeNumero * precoNumero;
    }, [precoNumero, quantidadeNumero]);

    const supplierSuggestions = useMemo(() => {
        if (form.finance_tipo_documento === 'manual') return [];
        const fornecedores = Array.isArray(config.fornecedores) ? config.fornecedores : [];
        const term = String(form.supplier_search || '').trim().toLowerCase();
        if (!term) {
            return selectedSupplier ? [selectedSupplier] : fornecedores.slice(0, 6);
        }

        return fornecedores.filter((supplier) => {
            const display = getSupplierLabel(supplier).toLowerCase();
            const cnpj = String(supplier?.cnpj || '').toLowerCase();
            return display.includes(term) || cnpj.includes(term);
        }).slice(0, 8);
    }, [config.fornecedores, form.finance_tipo_documento, form.supplier_search, selectedSupplier]);

    const documentNumberLabel = useMemo(() => {
        if (form.finance_tipo_documento === 'cupom') return 'Número do cupom';
        if (form.finance_tipo_documento === 'recibo') return 'Número do recibo';
        if (form.finance_tipo_documento === 'manual') return 'Referência do registro';
        return 'Número da NF';
    }, [form.finance_tipo_documento]);
    const supplierCnpjAllowed = form.finance_tipo_documento === 'nf' || form.finance_tipo_documento === 'cupom';

    const applyMode = (mode) => {
        const nextPreset = DOC_MODE_PRESETS[mode] || DOC_MODE_PRESETS.nf;
        setDocMode(mode);
        if (nextPreset.documentType === 'manual') {
            setSelectedSupplier(null);
        }
        setForm((prev) => ({
            ...prev,
            finance_tipo_documento: nextPreset.documentType,
            finance_origem_valor: nextPreset.origin,
            finance_comprovacao_status: nextPreset.proof,
            chave_acesso: mode === 'nf' ? prev.chave_acesso : '',
            supplier_search: nextPreset.documentType === 'manual' ? '' : prev.supplier_search,
            supplier_cnpj: nextPreset.documentType === 'nf' || nextPreset.documentType === 'cupom' ? prev.supplier_cnpj : '',
        }));
    };

    const updateField = (field, value) => {
        setForm((prev) => ({ ...prev, [field]: value }));
    };

    const handleItemMode = (nextValue) => {
        const nextUseNewItem = nextValue === 'novo';
        setUseNewItem(nextUseNewItem);
        if (nextUseNewItem) {
            setSelectedItem(null);
            setItemSearch('');
            setItemResults([]);
            return;
        }
        updateField('novo_codigo', '');
        updateField('nova_descricao', '');
    };

    const handleSelectItem = (item) => {
        setSelectedItem(item);
        setUseNewItem(false);
        setItemSearch(`${item.codigo} - ${item.descricao}`);
        setItemResults([]);
    };

    const handleSupplierSearchChange = (value) => {
        if (selectedSupplier && value !== getSupplierLabel(selectedSupplier)) {
            setSelectedSupplier(null);
        }
        updateField('supplier_search', value);
    };

    const handleSupplierSelect = (supplier) => {
        setSelectedSupplier(supplier);
        setForm((prev) => ({
            ...prev,
            supplier_search: getSupplierLabel(supplier),
            supplier_cnpj: prev.finance_tipo_documento === 'nf' || prev.finance_tipo_documento === 'cupom'
                ? (supplier?.cnpj || prev.supplier_cnpj)
                : '',
        }));
    };

    const resetAfterSave = () => {
        setForm(buildInitialForm(config));
        setDocMode('nf');
        setUseNewItem(false);
        setItemSearch('');
        setItemResults([]);
        setSelectedItem(null);
        setSelectedSupplier(null);
    };

    const validateBeforeSave = () => {
        const supplierNameFilled = Boolean(String(form.supplier_search || '').trim());
        const supplierCnpjFilled = Boolean(String(form.supplier_cnpj || '').trim());
        if (!selectedItem && !useNewItem) {
            return 'Selecione um item existente ou mude para item novo.';
        }
        if (useNewItem) {
            if (!String(form.novo_codigo || '').trim()) {
                return 'Informe o código do novo item.';
            }
            if (!String(form.nova_descricao || '').trim()) {
                return 'Informe a descrição do novo item.';
            }
        }
        if (!String(form.quantidade || '').trim()) {
            return 'Informe a quantidade do documento.';
        }
        if (!String(form.nota_fiscal || '').trim()) {
            return 'Informe o número do documento.';
        }
        if (docMode === 'nf' && !String(form.data_emissao || '').trim()) {
            return 'Informe a data de emissão para NF.';
        }
        if (form.finance_tipo_documento === 'recibo' && !supplierNameFilled) {
            return 'Informe o fornecedor para recibo.';
        }
        if (form.finance_tipo_documento !== 'manual' && form.finance_tipo_documento !== 'recibo' && !supplierNameFilled && !supplierCnpjFilled) {
            return 'Informe o fornecedor ou o CNPJ da loja.';
        }
        if (form.finance_comprovacao_status !== 'comprovado' && !String(form.finance_observacao || '').trim()) {
            return 'Explique a situação financeira quando a comprovação não estiver completa.';
        }
        return null;
    };

    const handleSubmit = async () => {
        const validationMessage = validateBeforeSave();
        if (validationMessage) {
            Alert.alert('Validação', validationMessage);
            return;
        }

        const supplierName = selectedSupplier
            ? getSupplierLabel(selectedSupplier)
            : String(form.supplier_search || '').trim();

        const payload = {
            codigo: useNewItem ? '' : (selectedItem?.codigo || selectedItem?.codigo_barras || ''),
            novo_codigo: useNewItem ? String(form.novo_codigo || '').trim() : '',
            nova_descricao: useNewItem ? String(form.nova_descricao || '').trim() : '',
            nova_marca: useNewItem ? String(form.nova_marca || '').trim() : '',
            nova_categoria: useNewItem ? form.nova_categoria : '',
            nova_unidade: useNewItem ? form.nova_unidade : '',
            nova_unidade_documental: useNewItem ? form.nova_unidade_documental : '',
            novo_conteudo_embalagem: useNewItem ? String(form.novo_conteudo_embalagem || '').trim() : '',
            nota_fiscal: String(form.nota_fiscal || '').trim(),
            finance_supplier_id: selectedSupplier?.id ? String(selectedSupplier.id) : '',
            supplier_name: form.finance_tipo_documento === 'manual' ? '' : supplierName,
            supplier_cnpj: supplierCnpjAllowed ? String(form.supplier_cnpj || '').trim() : '',
            finance_origem_valor: form.finance_origem_valor,
            finance_comprovacao_status: form.finance_comprovacao_status,
            preco_unitario: String(form.preco_unitario || '').trim(),
            finance_observacao: String(form.finance_observacao || '').trim(),
            chave_acesso: form.finance_tipo_documento === 'nf' ? String(form.chave_acesso || '').trim() : '',
            data_emissao: String(form.data_emissao || '').trim(),
            data_recebimento: String(form.data_recebimento || '').trim(),
            quantidade: String(form.quantidade || '').trim(),
            doc_mode: docMode,
            finance_tipo_documento: form.finance_tipo_documento,
        };

        setSaving(true);
        const result = await ApiService.registrarDocumentoFiscal(payload);
        setSaving(false);

        if (!result?.success) {
            Alert.alert('Falha no lançamento', result?.message || 'Não foi possível registrar o documento fiscal.');
            return;
        }

        const warnings = Array.isArray(result?.warnings) ? result.warnings.filter(Boolean) : [];
        const messageParts = [result?.message || 'Documento fiscal registrado no mobile.'];
        if (warnings.length) {
            messageParts.push(warnings.join('\n'));
        }

        Alert.alert('Documento registrado', messageParts.join('\n\n'));
        resetAfterSave();
    };

    if (loading) {
        return (
            <HeroScreen
                eyebrow="Documentos fiscais"
                title="Preparando o lançamento"
                subtitle="Carregando categorias, fornecedores e parâmetros do fluxo documental."
            >
                <View style={styles.loadingCard}>
                    <ActivityIndicator color={heroPalette.primary} />
                    <Text style={styles.loadingText}>Sincronizando a estrutura documental do mobile...</Text>
                </View>
            </HeroScreen>
        );
    }

    if (loadMessage) {
        return (
            <HeroScreen
                eyebrow="Documentos fiscais"
                title="Fluxo indisponível"
                subtitle="O app não conseguiu montar o cadastro documental neste momento."
            >
                <View style={styles.alertCard}>
                    <Text style={styles.alertTitle}>Falha ao carregar</Text>
                    <Text style={styles.alertText}>{loadMessage}</Text>
                </View>
            </HeroScreen>
        );
    }

    return (
        <HeroScreen
            eyebrow="Documentos fiscais"
            title={preset.title}
            subtitle={preset.subtitle}
            heroContent={
                <View style={styles.heroStats}>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Modo ativo</Text>
                        <Text style={styles.heroStatValue}>{preset.title}</Text>
                    </View>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Conferência</Text>
                        <Text style={styles.heroStatValue}>
                            {totalCalculado == null ? 'Aguardando' : `R$ ${totalCalculado.toFixed(2)}`}
                        </Text>
                    </View>
                </View>
            }
        >
            <DocumentSection title="1. Modo do lançamento" text={preset.note}>
                <ChoiceGrid
                    options={[
                        { value: 'nf', label: 'NF' },
                        { value: 'cupom', label: 'Cupom' },
                        { value: 'recibo', label: 'Recibo' },
                        { value: 'manual', label: 'Manual' },
                    ]}
                    value={docMode}
                    onChange={applyMode}
                />
            </DocumentSection>

            <DocumentSection
                title="2. Item existente ou item novo"
                text="A busca continua sendo o primeiro passo. Só crie um item novo quando o material ainda não existir no estoque."
            >
                <ChoiceGrid
                    options={[
                        { value: 'existente', label: 'Item existente' },
                        { value: 'novo', label: 'Item novo' },
                    ]}
                    value={useNewItem ? 'novo' : 'existente'}
                    onChange={handleItemMode}
                />

                {!useNewItem ? (
                    <>
                        <FieldCard label="Buscar item" helper="Digite código, descrição, marca ou categoria.">
                            <TextInput
                                value={itemSearch}
                                onChangeText={setItemSearch}
                                placeholder="Ex.: cabo 2,5 ou 789123"
                                placeholderTextColor={heroPalette.textMuted}
                                style={styles.input}
                                autoCapitalize="none"
                            />
                        </FieldCard>

                        {selectedItem ? (
                            <View style={styles.selectedCard}>
                                <Text style={styles.selectedTitle}>{selectedItem.descricao}</Text>
                                <Text style={styles.selectedMeta}>
                                    {selectedItem.codigo} | {selectedItem.categoria || 'Sem categoria'} | {selectedItem.saldo_display || `${selectedItem.saldo || 0} ${selectedItem.unidade || ''}`}
                                </Text>
                                <TouchableOpacity
                                    style={styles.linkButton}
                                    onPress={() => {
                                        setSelectedItem(null);
                                        setItemSearch('');
                                    }}
                                    activeOpacity={0.8}
                                >
                                    <Text style={styles.linkButtonText}>Trocar item</Text>
                                </TouchableOpacity>
                            </View>
                        ) : null}

                        {itemSearchLoading ? (
                            <View style={styles.inlineLoading}>
                                <ActivityIndicator size="small" color={heroPalette.primary} />
                                <Text style={styles.inlineLoadingText}>Buscando itens...</Text>
                            </View>
                        ) : null}

                        {!itemSearchLoading && itemSearch.trim().length >= 2 && !selectedItem ? (
                            <View style={styles.resultsStack}>
                                {itemResults.length ? itemResults.map((item) => (
                                    <TouchableOpacity
                                        key={item.codigo}
                                        style={styles.resultCard}
                                        onPress={() => handleSelectItem(item)}
                                        activeOpacity={0.85}
                                    >
                                        <Text style={styles.resultTitle}>{item.descricao}</Text>
                                        <Text style={styles.resultMeta}>
                                            {item.codigo} | {item.categoria || 'Sem categoria'} | {item.saldo_display || `${item.saldo || 0} ${item.unidade || ''}`}
                                        </Text>
                                    </TouchableOpacity>
                                )) : (
                                    <View style={styles.emptyHintCard}>
                                        <Text style={styles.emptyHintTitle}>Nenhum item localizado.</Text>
                                        <Text style={styles.emptyHintText}>Se o material ainda não existir, altere para Item novo e registre o pré-cadastro pela própria NF.</Text>
                                    </View>
                                )}
                            </View>
                        ) : null}
                    </>
                ) : (
                    <>
                        <FieldCard label="Código do novo item">
                            <TextInput
                                value={form.novo_codigo}
                                onChangeText={(value) => updateField('novo_codigo', value)}
                                placeholder="Código de barras ou interno"
                                placeholderTextColor={heroPalette.textMuted}
                                style={styles.input}
                                autoCapitalize="none"
                            />
                        </FieldCard>

                        <FieldCard label="Descrição do novo item">
                            <TextInput
                                value={form.nova_descricao}
                                onChangeText={(value) => updateField('nova_descricao', value)}
                                placeholder="Descrição completa do produto"
                                placeholderTextColor={heroPalette.textMuted}
                                style={styles.input}
                            />
                        </FieldCard>

                        <FieldCard label="Categoria inicial">
                            <ChoiceGrid
                                options={config.categorias || []}
                                value={form.nova_categoria}
                                onChange={(value) => updateField('nova_categoria', value)}
                            />
                        </FieldCard>

                        <FieldCard label="Marca">
                            <TextInput
                                value={form.nova_marca}
                                onChangeText={(value) => updateField('nova_marca', value)}
                                placeholder="Marca ou fabricante"
                                placeholderTextColor={heroPalette.textMuted}
                                style={styles.input}
                            />
                        </FieldCard>

                        <FieldCard label="Unidade interna / base">
                            <ChoiceGrid
                                options={config.unidades_base || ['Unidade']}
                                value={form.nova_unidade}
                                onChange={(value) => updateField('nova_unidade', value)}
                            />
                        </FieldCard>

                        <FieldCard label="Unidade da compra / NF" helper="Use sem embalagem quando a NF já vier na mesma unidade do saldo interno.">
                            <ChoiceGrid
                                options={[
                                    { value: '', label: 'Sem embalagem' },
                                    ...((config.unidades_documentais || []).map((value) => ({ value, label: value }))),
                                ]}
                                value={form.nova_unidade_documental}
                                onChange={(value) => updateField('nova_unidade_documental', value)}
                            />
                        </FieldCard>

                        {form.nova_unidade_documental && form.nova_unidade_documental !== 'par' ? (
                            <FieldCard label="Conteúdo por embalagem">
                                <TextInput
                                    value={form.novo_conteudo_embalagem}
                                    onChangeText={(value) => updateField('novo_conteudo_embalagem', value)}
                                    placeholder="Ex.: 3.6, 20, 50"
                                    placeholderTextColor={heroPalette.textMuted}
                                    style={styles.input}
                                    keyboardType="decimal-pad"
                                />
                            </FieldCard>
                        ) : null}
                    </>
                )}
            </DocumentSection>

            <DocumentSection title="3. Dados do documento" text="Quantidade, número, datas e origem comercial do lançamento.">
                <FieldCard label="Quantidade documental">
                    <TextInput
                        value={form.quantidade}
                        onChangeText={(value) => updateField('quantidade', value)}
                        placeholder="1"
                        placeholderTextColor={heroPalette.textMuted}
                        style={styles.input}
                        keyboardType="decimal-pad"
                    />
                </FieldCard>

                <FieldCard label={documentNumberLabel}>
                    <TextInput
                        value={form.nota_fiscal}
                        onChangeText={(value) => updateField('nota_fiscal', value)}
                        placeholder="Número do documento"
                        placeholderTextColor={heroPalette.textMuted}
                        style={styles.input}
                    />
                </FieldCard>

                <FieldCard label="Data de emissão" helper="Formato esperado: AAAA-MM-DD ou DD/MM/AAAA.">
                    <TextInput
                        value={form.data_emissao}
                        onChangeText={(value) => updateField('data_emissao', value)}
                        placeholder="2026-04-15"
                        placeholderTextColor={heroPalette.textMuted}
                        style={styles.input}
                    />
                </FieldCard>

                <FieldCard label="Data de recebimento" helper="Se ficar em branco, o app usa a data atual do servidor.">
                    <TextInput
                        value={form.data_recebimento}
                        onChangeText={(value) => updateField('data_recebimento', value)}
                        placeholder="2026-04-15"
                        placeholderTextColor={heroPalette.textMuted}
                        style={styles.input}
                    />
                </FieldCard>

                {form.finance_tipo_documento !== 'manual' ? (
                    <>
                        <FieldCard label="Fornecedor / loja">
                            <TextInput
                                value={form.supplier_search}
                                onChangeText={handleSupplierSearchChange}
                                placeholder="Digite o nome da loja"
                                placeholderTextColor={heroPalette.textMuted}
                                style={styles.input}
                            />
                        </FieldCard>

                        {supplierSuggestions.length ? (
                            <View style={styles.resultsStack}>
                                {supplierSuggestions.map((supplier) => (
                                    <TouchableOpacity
                                        key={String(supplier.id)}
                                        style={styles.resultCard}
                                        onPress={() => handleSupplierSelect(supplier)}
                                        activeOpacity={0.85}
                                    >
                                        <Text style={styles.resultTitle}>{getSupplierLabel(supplier)}</Text>
                                        <Text style={styles.resultMeta}>{supplier.cnpj || 'Sem CNPJ'}{supplier.endereco_cidade ? ` | ${supplier.endereco_cidade}` : ''}</Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        ) : null}

                        {supplierCnpjAllowed ? (
                            <FieldCard label="CNPJ da loja">
                                <TextInput
                                    value={form.supplier_cnpj}
                                    onChangeText={(value) => updateField('supplier_cnpj', value)}
                                    placeholder="00.000.000/0000-00"
                                    placeholderTextColor={heroPalette.textMuted}
                                    style={styles.input}
                                    keyboardType="number-pad"
                                />
                            </FieldCard>
                        ) : (
                            <View style={styles.inlineNoteCard}>
                                <Text style={styles.inlineNoteText}>Recibo não usa CNPJ. Identifique o fornecedor pelo nome e detalhe a compra na observação.</Text>
                            </View>
                        )}
                    </>
                ) : (
                    <View style={styles.inlineNoteCard}>
                        <Text style={styles.inlineNoteText}>Modo manual permite registrar sem fornecedor formal. Use a observação para explicar a origem.</Text>
                    </View>
                )}

                {form.finance_tipo_documento === 'nf' ? (
                    <FieldCard label="Chave de acesso" helper="Opcional no mobile, mas útil para rastreabilidade da NF-e.">
                        <TextInput
                            value={form.chave_acesso}
                            onChangeText={(value) => updateField('chave_acesso', value)}
                            placeholder="44 dígitos da chave"
                            placeholderTextColor={heroPalette.textMuted}
                            style={styles.input}
                            autoCapitalize="none"
                        />
                    </FieldCard>
                ) : null}
            </DocumentSection>

            <DocumentSection title="4. Classificação financeira" text="O valor do documento alimenta o financeiro e, quando aplicável, a incorporação ao estoque.">
                <FieldCard label="Valor unitário (R$)">
                    <TextInput
                        value={form.preco_unitario}
                        onChangeText={(value) => updateField('preco_unitario', value)}
                        placeholder="0,00"
                        placeholderTextColor={heroPalette.textMuted}
                        style={styles.input}
                        keyboardType="decimal-pad"
                    />
                </FieldCard>

                <View style={styles.calcCard}>
                    <Text style={styles.calcLabel}>Conferência rápida</Text>
                    <Text style={styles.calcFormula}>
                        {quantidadeNumero == null || precoNumero == null
                            ? 'Preencha quantidade e valor unitário para validar a multiplicação.'
                            : `${quantidadeNumero} x R$ ${precoNumero.toFixed(2)} = R$ ${totalCalculado.toFixed(2)}`}
                    </Text>
                </View>

                <FieldCard label="Tipo financeiro do documento">
                    <ChoiceGrid
                        options={config.tipos_documento || DEFAULT_CONFIG.tipos_documento}
                        value={form.finance_tipo_documento}
                        onChange={(value) => {
                            updateField('finance_tipo_documento', value);
                            if (value === 'nf') setDocMode('nf');
                            else if (value === 'cupom') setDocMode('cupom');
                            else if (value === 'recibo') setDocMode('recibo');
                            else setDocMode('manual');
                        }}
                    />
                </FieldCard>

                <FieldCard label="Origem do valor">
                    <ChoiceGrid
                        options={config.origens_valor || DEFAULT_CONFIG.origens_valor}
                        value={form.finance_origem_valor}
                        onChange={(value) => updateField('finance_origem_valor', value)}
                    />
                </FieldCard>

                <FieldCard label="Comprovacao">
                    <ChoiceGrid
                        options={config.comprovacoes || DEFAULT_CONFIG.comprovacoes}
                        value={form.finance_comprovacao_status}
                        onChange={(value) => updateField('finance_comprovacao_status', value)}
                    />
                </FieldCard>

                <FieldCard label="Observação financeira">
                    <TextInput
                        value={form.finance_observacao}
                        onChangeText={(value) => updateField('finance_observacao', value)}
                        placeholder="Ex.: compra emergencial, valor estimado, conferência parcial..."
                        placeholderTextColor={heroPalette.textMuted}
                        style={[styles.input, styles.multilineInput]}
                        multiline
                        textAlignVertical="top"
                    />
                </FieldCard>

                <View style={styles.inlineNoteCard}>
                    <Text style={styles.inlineNoteText}>Com estoque ativo, item novo entra primeiro em PRE-CADASTRADOS antes de aparecer no saldo operacional.</Text>
                </View>

                <TouchableOpacity
                    style={[styles.submitButton, saving && styles.submitButtonDisabled]}
                    onPress={handleSubmit}
                    activeOpacity={0.88}
                    disabled={saving}
                >
                    {saving ? <ActivityIndicator size="small" color="#03111c" /> : null}
                    <Text style={styles.submitButtonText}>{saving ? 'Registrando documento...' : 'Registrar documento fiscal'}</Text>
                </TouchableOpacity>
            </DocumentSection>
        </HeroScreen>
    );
}

const styles = StyleSheet.create({
    heroStats: {
        flexDirection: 'row',
        gap: 12,
    },
    heroStatCard: {
        flex: 1,
        borderRadius: 18,
        paddingHorizontal: 14,
        paddingVertical: 14,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    heroStatLabel: {
        color: heroPalette.textMuted,
        fontSize: 11,
        fontWeight: '800',
        textTransform: 'uppercase',
        letterSpacing: 0.9,
    },
    heroStatValue: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
    },
    sectionCard: {
        backgroundColor: heroPalette.panel,
        borderRadius: 24,
        paddingHorizontal: 18,
        paddingVertical: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        marginBottom: 16,
        ...heroShadow,
    },
    sectionTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
    },
    sectionText: {
        marginTop: 6,
        marginBottom: 14,
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    choiceGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
    },
    choicePill: {
        borderRadius: 16,
        paddingHorizontal: 14,
        paddingVertical: 12,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    choicePillSelected: {
        backgroundColor: 'rgba(34, 211, 238, 0.18)',
        borderColor: heroPalette.primaryStrong,
    },
    choiceText: {
        color: heroPalette.textSoft,
        fontSize: 13,
        fontWeight: '700',
    },
    choiceTextSelected: {
        color: heroPalette.text,
    },
    fieldCard: {
        borderRadius: 18,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingHorizontal: 14,
        paddingVertical: 14,
        marginTop: 14,
    },
    fieldLabel: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '800',
        marginBottom: 6,
    },
    fieldHelper: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 17,
        marginBottom: 10,
    },
    input: {
        minHeight: 48,
        borderRadius: 14,
        paddingHorizontal: 14,
        paddingVertical: 12,
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        color: heroPalette.text,
        fontSize: 15,
    },
    multilineInput: {
        minHeight: 110,
    },
    selectedCard: {
        marginTop: 14,
        borderRadius: 18,
        padding: 14,
        backgroundColor: 'rgba(52, 211, 153, 0.12)',
        borderWidth: 1,
        borderColor: 'rgba(52, 211, 153, 0.24)',
    },
    selectedTitle: {
        color: heroPalette.text,
        fontSize: 15,
        fontWeight: '800',
    },
    selectedMeta: {
        marginTop: 4,
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 18,
    },
    linkButton: {
        marginTop: 10,
        alignSelf: 'flex-start',
    },
    linkButtonText: {
        color: heroPalette.primary,
        fontSize: 13,
        fontWeight: '800',
    },
    resultsStack: {
        marginTop: 14,
        gap: 10,
    },
    resultCard: {
        borderRadius: 16,
        paddingHorizontal: 14,
        paddingVertical: 13,
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    resultTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '800',
    },
    resultMeta: {
        marginTop: 4,
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 17,
    },
    emptyHintCard: {
        borderRadius: 16,
        padding: 14,
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    emptyHintTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '800',
    },
    emptyHintText: {
        marginTop: 4,
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 18,
    },
    inlineLoading: {
        marginTop: 14,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    inlineLoadingText: {
        color: heroPalette.textMuted,
        fontSize: 13,
    },
    inlineNoteCard: {
        marginTop: 14,
        borderRadius: 16,
        padding: 14,
        backgroundColor: 'rgba(251, 191, 36, 0.12)',
        borderWidth: 1,
        borderColor: 'rgba(251, 191, 36, 0.24)',
    },
    inlineNoteText: {
        color: heroPalette.textSoft,
        fontSize: 12,
        lineHeight: 18,
    },
    calcCard: {
        marginTop: 14,
        borderRadius: 18,
        padding: 14,
        backgroundColor: heroPalette.bgAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    calcLabel: {
        color: heroPalette.primary,
        fontSize: 11,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 0.9,
    },
    calcFormula: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
        lineHeight: 20,
    },
    submitButton: {
        marginTop: 18,
        minHeight: 54,
        borderRadius: 18,
        backgroundColor: heroPalette.primary,
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'row',
        gap: 10,
    },
    submitButtonDisabled: {
        opacity: 0.75,
    },
    submitButtonText: {
        color: '#03111c',
        fontSize: 15,
        fontWeight: '900',
    },
    loadingCard: {
        borderRadius: 22,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
        paddingHorizontal: 18,
        paddingVertical: 18,
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
    },
    loadingText: {
        color: heroPalette.textMuted,
        fontSize: 14,
        textAlign: 'center',
    },
    alertCard: {
        borderRadius: 22,
        backgroundColor: 'rgba(251, 113, 133, 0.12)',
        borderWidth: 1,
        borderColor: 'rgba(251, 113, 133, 0.28)',
        paddingHorizontal: 18,
        paddingVertical: 18,
    },
    alertTitle: {
        color: heroPalette.text,
        fontSize: 16,
        fontWeight: '800',
    },
    alertText: {
        marginTop: 8,
        color: heroPalette.textSoft,
        fontSize: 13,
        lineHeight: 19,
    },
});