import React, { useCallback, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import HeroScreen from '../components/HeroScreen';
import ApiService from '../services/api';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

function formatCurrency(value) {
    const number = Number(value || 0);
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
        maximumFractionDigits: 2,
    }).format(number);
}

function formatCompactNumber(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) {
        return '0';
    }
    return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(number);
}

function formatDateLabel(value) {
    if (!value) {
        return 'Sem data';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value);
    }
    return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    }).format(date);
}

function Surface({ title, subtitle, children }) {
    return (
        <View style={styles.surface}>
            <View style={styles.surfaceHead}>
                <Text style={styles.surfaceTitle}>{title}</Text>
                {subtitle ? <Text style={styles.surfaceSubtitle}>{subtitle}</Text> : null}
            </View>
            <View style={styles.surfaceBody}>{children}</View>
        </View>
    );
}

function SummaryRow({ title, value, meta, onPress }) {
    const content = (
        <View style={styles.summaryRow}>
            <View style={styles.summaryCopy}>
                <Text style={styles.summaryTitle}>{title}</Text>
                {meta ? <Text style={styles.summaryMeta}>{meta}</Text> : null}
            </View>
            <Text style={styles.summaryValue}>{value}</Text>
        </View>
    );

    if (!onPress) {
        return content;
    }

    return (
        <TouchableOpacity onPress={onPress} activeOpacity={0.84}>
            {content}
        </TouchableOpacity>
    );
}

export default function ReportsConsumptionScreen() {
    const [panel, setPanel] = useState(null);
    const [filters, setFilters] = useState({});
    const [loading, setLoading] = useState(true);
    const [sharing, setSharing] = useState(false);

    const loadPanel = useCallback(async (nextFilters = {}, silent = false) => {
        if (!silent) {
            setLoading(true);
        }
        try {
            const result = await ApiService.getConsumptionPanel(nextFilters);
            if (!result?.success) {
                Alert.alert('Consumo', result?.message || 'Não foi possível carregar o painel analítico.');
                setPanel(null);
                return;
            }
            setPanel(result.data || null);
        } catch (error) {
            Alert.alert('Consumo', error?.message || 'Não foi possível carregar o painel analítico.');
            setPanel(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useFocusEffect(
        useCallback(() => {
            loadPanel(filters);
        }, [filters, loadPanel])
    );

    const applyScopedFilter = (scopeKey, scopeValue) => {
        const nextFilters = {};
        if (filters.exercicio) {
            nextFilters.exercicio = filters.exercicio;
        }
        if (scopeKey && scopeValue) {
            nextFilters[scopeKey] = scopeValue;
        }
        setFilters(nextFilters);
        loadPanel(nextFilters, true);
    };

    const applyExercise = (exerciseLabel) => {
        const nextFilters = { ...filters };
        if (exerciseLabel) {
            nextFilters.exercicio = exerciseLabel;
        } else {
            delete nextFilters.exercicio;
        }
        setFilters(nextFilters);
        loadPanel(nextFilters, true);
    };

    const resetScope = () => {
        const nextFilters = {};
        if (filters.exercicio) {
            nextFilters.exercicio = filters.exercicio;
        }
        setFilters(nextFilters);
        loadPanel(nextFilters, true);
    };

    const sharePdf = async () => {
        setSharing(true);
        try {
            const token = await ApiService.getToken();
            const url = ApiService.getReportUrl('consumption', filters);
            const suffix = panel?.scope_type || 'geral';
            const fileUri = `${FileSystem.cacheDirectory}relatorio_consumo_${suffix}.pdf`;
            const download = await FileSystem.downloadAsync(url, fileUri, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (await Sharing.isAvailableAsync()) {
                await Sharing.shareAsync(download.uri, {
                    mimeType: 'application/pdf',
                    dialogTitle: 'Compartilhar relatório de consumo',
                });
            } else {
                Alert.alert('Relatório salvo', download.uri);
            }
        } catch (error) {
            Alert.alert('Consumo', error?.message || 'Não foi possível exportar o relatório.');
        } finally {
            setSharing(false);
        }
    };

    const overview = panel?.overview || {};
    const currentExercise = panel?.exercise?.label;
    const exerciseOptions = Array.isArray(panel?.exercise_options) ? panel.exercise_options : [];
    const categories = Array.isArray(panel?.global_categories) && panel.global_categories.length
        ? panel.global_categories
        : (panel?.categories || []);
    const employees = Array.isArray(panel?.global_employees) && panel.global_employees.length
        ? panel.global_employees
        : (panel?.employees || []);
    const locations = Array.isArray(panel?.global_locations) && panel.global_locations.length
        ? panel.global_locations
        : (panel?.locations || []);
    const recentEntries = Array.isArray(panel?.recent_entries) ? panel.recent_entries.slice(0, 8) : [];
    const isScoped = Boolean(filters.categoria || filters.matricula || filters.local);

    return (
        <HeroScreen
            eyebrow="Consumo"
            title={panel?.scope_title || 'Painel de consumo'}
            subtitle={panel?.scope_subtitle || 'Visão simplificada do consumo por categoria, colaborador e local.'}
            heroContent={
                <View style={styles.heroGrid}>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>Valor</Text>
                        <Text style={styles.heroValue}>{formatCurrency(overview.total_valor)}</Text>
                    </View>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>Saídas</Text>
                        <Text style={styles.heroValue}>{formatCompactNumber(overview.saidas)}</Text>
                    </View>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>Pessoas</Text>
                        <Text style={styles.heroValue}>{formatCompactNumber(overview.colaboradores)}</Text>
                    </View>
                </View>
            }
        >
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.exerciseRow}>
                {exerciseOptions.map((exercise) => {
                    const label = exercise?.label || String(exercise || '');
                    const selected = currentExercise === label;
                    return (
                        <TouchableOpacity
                            key={label}
                            style={[styles.chip, selected && styles.chipActive]}
                            onPress={() => applyExercise(label)}
                        >
                            <Text style={[styles.chipText, selected && styles.chipTextActive]}>{label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </ScrollView>

            <View style={styles.actionRow}>
                <TouchableOpacity style={styles.primaryButton} onPress={sharePdf} disabled={sharing || loading}>
                    {sharing ? <ActivityIndicator color={heroPalette.bg} /> : <Text style={styles.primaryButtonText}>Compartilhar PDF</Text>}
                </TouchableOpacity>
                {isScoped ? (
                    <TouchableOpacity style={styles.secondaryButton} onPress={resetScope}>
                        <Text style={styles.secondaryButtonText}>Voltar ao geral</Text>
                    </TouchableOpacity>
                ) : null}
            </View>

            {loading ? (
                <View style={styles.loadingBox}>
                    <ActivityIndicator color={heroPalette.primaryStrong} />
                    <Text style={styles.loadingText}>Carregando analítico...</Text>
                </View>
            ) : null}

            {!loading && panel?.current_employee ? (
                <View style={styles.highlightCard}>
                    <Text style={styles.highlightTitle}>{panel.current_employee.nome || panel.current_employee.matricula}</Text>
                    <Text style={styles.highlightText}>
                        {(panel.current_employee.cargo || 'Sem cargo')}
                        {' - '}
                        {panel.current_employee.saidas || 0} saída(s)
                        {' - '}
                        {panel.current_employee.locais || 0} local(is)
                    </Text>
                    <Text style={styles.highlightText}>
                        Material destaque: {panel.current_employee.material_destaque || 'Sem dado'}
                        {' - '}
                        Local destaque: {panel.current_employee.local_destaque || 'Sem dado'}
                    </Text>
                </View>
            ) : null}

            {!loading && panel?.current_category ? (
                <View style={styles.highlightCard}>
                    <Text style={styles.highlightTitle}>{panel.current_category.categoria || 'Categoria'}</Text>
                    <Text style={styles.highlightText}>
                        {panel.current_category.saidas || 0} saída(s)
                        {' - '}
                        {panel.current_category.colaboradores || 0} colaborador(es)
                        {' - '}
                        {panel.current_category.locais || 0} local(is)
                    </Text>
                </View>
            ) : null}

            {!loading && panel?.current_local ? (
                <View style={styles.highlightCard}>
                    <Text style={styles.highlightTitle}>{panel.current_local.local || 'Local'}</Text>
                    <Text style={styles.highlightText}>
                        {panel.current_local.saidas || 0} saída(s)
                        {' - '}
                        {panel.current_local.colaboradores || 0} colaborador(es)
                        {' - '}
                        {panel.current_local.categorias || 0} categoria(s)
                    </Text>
                </View>
            ) : null}

            {!loading ? (
                <>
                    <Surface title="Categorias" subtitle="Toque para abrir o recorte da categoria.">
                        {categories.slice(0, 6).map((row) => (
                            <SummaryRow
                                key={`categoria-${row.categoria}`}
                                title={row.categoria || 'Sem categoria'}
                                value={formatCurrency(row.total_valor)}
                                meta={`${row.saidas || 0} saída(s) - ${row.colaboradores || 0} colaborador(es)`}
                                onPress={() => applyScopedFilter('categoria', row.categoria)}
                            />
                        ))}
                    </Surface>

                    <Surface title="Colaboradores" subtitle="Visão individual do consumo por funcionário.">
                        {employees.slice(0, 6).map((row) => (
                            <SummaryRow
                                key={`funcionario-${row.matricula}`}
                                title={row.nome || row.matricula || 'Funcionário'}
                                value={formatCurrency(row.total_valor)}
                                meta={`${row.saidas || 0} saída(s) - ${row.locais || 0} local(is)`}
                                onPress={() => applyScopedFilter('matricula', row.matricula)}
                            />
                        ))}
                    </Surface>

                    <Surface title="Locais" subtitle="Recorte operacional por ponto de consumo.">
                        {locations.slice(0, 6).map((row) => (
                            <SummaryRow
                                key={`local-${row.local}`}
                                title={row.local || 'Sem local'}
                                value={formatCurrency(row.total_valor)}
                                meta={`${row.saidas || 0} saída(s) - ${row.categorias || 0} categoria(s)`}
                                onPress={() => applyScopedFilter('local', row.local)}
                            />
                        ))}
                    </Surface>

                    <Surface title="Movimentos recentes" subtitle={`${panel?.entries_count || 0} registro(s) no recorte atual.`}>
                        {recentEntries.map((entry, index) => (
                            <View key={`entry-${index}`} style={styles.entryRow}>
                                <View style={styles.entryCopy}>
                                    <Text style={styles.entryTitle}>{entry.descricao || entry.codigo_item || 'Movimento'}</Text>
                                    <Text style={styles.entryMeta}>
                                        {[entry.categoria, entry.nome || entry.matricula, entry.local].filter(Boolean).join(' - ') || 'Sem detalhes'}
                                    </Text>
                                </View>
                                <View style={styles.entryAside}>
                                    <Text style={styles.entryValue}>{formatCurrency(entry.valor_total)}</Text>
                                    <Text style={styles.entryDate}>{formatDateLabel(entry.data)}</Text>
                                </View>
                            </View>
                        ))}
                        {!recentEntries.length ? <Text style={styles.emptyInlineText}>Nenhum movimento recente neste recorte.</Text> : null}
                    </Surface>
                </>
            ) : null}
        </HeroScreen>
    );
}

const styles = StyleSheet.create({
    heroGrid: {
        flexDirection: 'row',
        gap: 12,
    },
    heroStat: {
        flex: 1,
        borderRadius: 18,
        paddingHorizontal: 14,
        paddingVertical: 14,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    heroLabel: {
        color: heroPalette.textMuted,
        fontSize: 11,
        fontWeight: '800',
        textTransform: 'uppercase',
        letterSpacing: 1,
    },
    heroValue: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '900',
    },
    exerciseRow: {
        gap: 8,
        paddingBottom: 4,
        marginBottom: 12,
    },
    chip: {
        borderRadius: 16,
        paddingHorizontal: 12,
        paddingVertical: 8,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    chipActive: {
        backgroundColor: heroPalette.primaryStrong,
        borderColor: heroPalette.primaryStrong,
    },
    chipText: {
        color: heroPalette.text,
        fontSize: 12,
        fontWeight: '700',
    },
    chipTextActive: {
        color: heroPalette.bg,
    },
    actionRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
        marginBottom: 14,
    },
    primaryButton: {
        minWidth: 150,
        borderRadius: 16,
        paddingVertical: 12,
        paddingHorizontal: 16,
        backgroundColor: heroPalette.primaryStrong,
        alignItems: 'center',
        justifyContent: 'center',
    },
    primaryButtonText: {
        color: heroPalette.bg,
        fontSize: 13,
        fontWeight: '800',
    },
    secondaryButton: {
        borderRadius: 16,
        paddingVertical: 12,
        paddingHorizontal: 16,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    secondaryButtonText: {
        color: heroPalette.text,
        fontSize: 13,
        fontWeight: '700',
    },
    loadingBox: {
        borderRadius: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        paddingHorizontal: 16,
        paddingVertical: 18,
        alignItems: 'center',
        marginBottom: 14,
    },
    loadingText: {
        marginTop: 10,
        color: heroPalette.textMuted,
        fontSize: 13,
    },
    highlightCard: {
        borderRadius: 22,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
        padding: 18,
        marginBottom: 14,
        ...heroShadow,
    },
    highlightTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 6,
    },
    highlightText: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    surface: {
        borderRadius: 22,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
        marginBottom: 14,
        overflow: 'hidden',
        ...heroShadow,
    },
    surfaceHead: {
        paddingHorizontal: 18,
        paddingTop: 18,
        paddingBottom: 10,
    },
    surfaceTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 4,
    },
    surfaceSubtitle: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 18,
    },
    surfaceBody: {
        paddingHorizontal: 18,
        paddingBottom: 18,
    },
    summaryRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: heroPalette.border,
    },
    summaryCopy: {
        flex: 1,
    },
    summaryTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 4,
    },
    summaryMeta: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 17,
    },
    summaryValue: {
        color: heroPalette.primary,
        fontSize: 13,
        fontWeight: '800',
        textAlign: 'right',
    },
    entryRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 12,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: heroPalette.border,
    },
    entryCopy: {
        flex: 1,
    },
    entryTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 4,
    },
    entryMeta: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 17,
    },
    entryAside: {
        alignItems: 'flex-end',
        justifyContent: 'center',
    },
    entryValue: {
        color: heroPalette.primary,
        fontSize: 13,
        fontWeight: '800',
        marginBottom: 4,
    },
    entryDate: {
        color: heroPalette.textMuted,
        fontSize: 11,
    },
    emptyInlineText: {
        color: heroPalette.textMuted,
        fontSize: 12,
        paddingTop: 6,
    },
});