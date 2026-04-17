import React, { useEffect, useState } from 'react';
import {
    ActivityIndicator,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';

import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

function formatDays(value) {
    const total = Number(value || 0);
    return `${total} dia${total === 1 ? '' : 's'}`;
}

function formatDateLabel(value) {
    if (!value) {
        return 'Data indisponivel';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return String(value);
    }
    return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    }).format(parsed);
}

function formatLocations(values) {
    const uniqueValues = [...new Set((values || []).filter(Boolean))];
    if (!uniqueValues.length) {
        return 'Sem local informado';
    }
    if (uniqueValues.length <= 2) {
        return uniqueValues.join(' • ');
    }
    return `${uniqueValues.slice(0, 2).join(' • ')} +${uniqueValues.length - 2}`;
}

export default function DailyCustodyPanel({
    groups,
    summary,
    loading,
    message,
    returningKey,
    onReload,
    onReturnPress,
}) {
    const [selectedByGroup, setSelectedByGroup] = useState({});

    useEffect(() => {
        setSelectedByGroup((previousState) => {
            const nextState = {};
            (groups || []).forEach((group) => {
                const items = Array.isArray(group?.items) ? group.items : [];
                const previousKey = previousState[group.key];
                const stillExists = items.some((item) => item.tool_key === previousKey);
                nextState[group.key] = stillExists ? previousKey : (items[0]?.tool_key || null);
            });
            return nextState;
        });
    }, [groups]);

    const handleSelect = (groupKey, toolKey) => {
        setSelectedByGroup((previousState) => ({
            ...previousState,
            [groupKey]: toolKey,
        }));
    };

    return (
        <View style={styles.section}>
            <View style={styles.headerRow}>
                <View style={styles.headerCopy}>
                    <Text style={styles.title}>Custodia diaria</Text>
                    <Text style={styles.subtitle}>Mesmo fluxo do painel web, adaptado para baixa direta no telefone por colaborador.</Text>
                </View>
                <TouchableOpacity style={styles.reloadButton} onPress={() => onReload(false)} activeOpacity={0.84}>
                    <Text style={styles.reloadButtonText}>{loading ? 'Atualizando' : 'Atualizar'}</Text>
                </TouchableOpacity>
            </View>

            <View style={styles.statsRow}>
                <View style={styles.statCard}>
                    <Text style={styles.statLabel}>Colaboradores</Text>
                    <Text style={styles.statValue}>{summary?.employees || 0}</Text>
                </View>
                <View style={styles.statCard}>
                    <Text style={styles.statLabel}>Ferramentas</Text>
                    <Text style={styles.statValue}>{summary?.tools || 0}</Text>
                </View>
                <View style={[styles.statCard, (summary?.overdue || 0) > 0 && styles.statCardAlert]}>
                    <Text style={styles.statLabel}>Pendencias</Text>
                    <Text style={styles.statValue}>{summary?.overdue || 0}</Text>
                </View>
            </View>

            {loading ? (
                <View style={styles.loadingBox}>
                    <ActivityIndicator color={heroPalette.primaryStrong} />
                    <Text style={styles.loadingText}>Carregando custodia diaria...</Text>
                </View>
            ) : null}

            {!loading && (!groups || groups.length === 0) ? (
                <View style={styles.emptyBox}>
                    <Text style={styles.emptyTitle}>Sem ferramentas em custodia diaria</Text>
                    <Text style={styles.emptyText}>{message || 'Nenhuma ferramenta temporaria ativa precisa de baixa neste momento.'}</Text>
                </View>
            ) : null}

            {!loading && (groups || []).map((group) => {
                const items = Array.isArray(group?.items) ? group.items : [];
                const selectedKey = selectedByGroup[group.key] || items[0]?.tool_key;
                const selectedItem = items.find((item) => item.tool_key === selectedKey) || items[0] || null;
                const isLate = Number(group?.overdue_count || 0) > 0;
                const needsAttention = !isLate && Number(group?.max_days || 0) >= 15;

                return (
                    <View
                        key={group.key}
                        style={[
                            styles.employeeCard,
                            isLate ? styles.employeeCardLate : null,
                            needsAttention ? styles.employeeCardAttention : null,
                        ]}
                    >
                        <View style={styles.employeeHeader}>
                            <View style={styles.employeeCopy}>
                                <Text style={styles.employeeName}>{group.usuario}</Text>
                                <Text style={styles.employeeMeta}>
                                    {group.matricula_full || group.matricula || 'Sem matricula'} • {group.total_tools || 0} ferramenta(s)
                                </Text>
                            </View>
                            <View style={[styles.employeeBadge, isLate ? styles.employeeBadgeLate : needsAttention ? styles.employeeBadgeAttention : null]}>
                                <Text style={styles.employeeBadgeText}>
                                    {isLate ? `${group.overdue_count} em atraso` : formatDays(group.max_days || 0)}
                                </Text>
                            </View>
                        </View>

                        <View style={styles.locationPill}>
                            <Text style={styles.locationPillText}>{formatLocations(group.locations)}</Text>
                        </View>

                        <View style={styles.toolsList}>
                            {items.map((item) => {
                                const selected = selectedKey === item.tool_key;
                                return (
                                    <TouchableOpacity
                                        key={item.tool_key}
                                        style={[styles.toolCard, selected && styles.toolCardSelected]}
                                        onPress={() => handleSelect(group.key, item.tool_key)}
                                        activeOpacity={0.84}
                                    >
                                        <View style={styles.toolHeader}>
                                            <Text style={styles.toolTitle}>{item.descricao}</Text>
                                            <View style={[styles.daysBadge, item.atrasada && styles.daysBadgeLate]}>
                                                <Text style={styles.daysBadgeText}>{formatDays(item.dias_em_uso)}</Text>
                                            </View>
                                        </View>
                                        <Text style={styles.toolMeta}>
                                            {item.local_servico || 'Sem local'} • Qtd {item.quantidade || 1} • {formatDateLabel(item.data_retirada_iso)}
                                        </Text>
                                        {item.observacao ? <Text style={styles.toolNote}>{item.observacao}</Text> : null}
                                    </TouchableOpacity>
                                );
                            })}
                        </View>

                        <View style={styles.selectedBox}>
                            <Text style={styles.selectedText}>
                                {selectedItem
                                    ? `Pronta para baixa: ${selectedItem.descricao} • ${selectedItem.local_servico || 'Sem local'}`
                                    : 'Selecione uma ferramenta para liberar a baixa.'}
                            </Text>
                        </View>

                        <TouchableOpacity
                            style={[styles.returnButton, !selectedItem && styles.returnButtonDisabled]}
                            onPress={() => onReturnPress(group, selectedItem)}
                            disabled={!selectedItem || returningKey === selectedItem?.tool_key}
                            activeOpacity={0.86}
                        >
                            {returningKey === selectedItem?.tool_key ? (
                                <ActivityIndicator color={heroPalette.bg} />
                            ) : (
                                <Text style={styles.returnButtonText}>Dar baixa da selecionada</Text>
                            )}
                        </TouchableOpacity>
                    </View>
                );
            })}
        </View>
    );
}

const styles = StyleSheet.create({
    section: {
        paddingHorizontal: 14,
        paddingBottom: 16,
        backgroundColor: heroPalette.panel,
        marginBottom: 12,
        marginHorizontal: 14,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    headerRow: {
        paddingTop: 16,
        paddingBottom: 10,
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 12,
    },
    headerCopy: {
        flex: 1,
    },
    title: {
        fontSize: 18,
        fontWeight: '800',
        color: heroPalette.text,
    },
    subtitle: {
        marginTop: 4,
        fontSize: 12,
        color: heroPalette.textMuted,
        lineHeight: 18,
    },
    reloadButton: {
        alignSelf: 'flex-start',
        borderRadius: 16,
        paddingVertical: 10,
        paddingHorizontal: 12,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    reloadButtonText: {
        color: heroPalette.text,
        fontSize: 12,
        fontWeight: '700',
    },
    statsRow: {
        flexDirection: 'row',
        gap: 10,
        marginBottom: 14,
    },
    statCard: {
        flex: 1,
        minHeight: 88,
        borderRadius: 18,
        paddingHorizontal: 12,
        paddingVertical: 14,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroSoftShadow,
    },
    statCardAlert: {
        borderColor: 'rgba(248, 113, 113, 0.5)',
        backgroundColor: 'rgba(248, 113, 113, 0.12)',
    },
    statLabel: {
        color: heroPalette.textMuted,
        fontSize: 11,
        fontWeight: '800',
        textTransform: 'uppercase',
        letterSpacing: 0.8,
    },
    statValue: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 20,
        fontWeight: '900',
    },
    loadingBox: {
        borderRadius: 18,
        paddingVertical: 20,
        alignItems: 'center',
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        marginBottom: 14,
    },
    loadingText: {
        marginTop: 10,
        color: heroPalette.textMuted,
        fontSize: 13,
    },
    emptyBox: {
        borderRadius: 20,
        padding: 18,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    emptyTitle: {
        color: heroPalette.text,
        fontSize: 16,
        fontWeight: '800',
        marginBottom: 6,
    },
    emptyText: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    employeeCard: {
        borderRadius: 22,
        padding: 16,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        marginBottom: 12,
        ...heroShadow,
    },
    employeeCardLate: {
        borderColor: 'rgba(248, 113, 113, 0.5)',
        backgroundColor: 'rgba(127, 29, 29, 0.24)',
    },
    employeeCardAttention: {
        borderColor: 'rgba(251, 191, 36, 0.45)',
        backgroundColor: 'rgba(120, 53, 15, 0.22)',
    },
    employeeHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 10,
    },
    employeeCopy: {
        flex: 1,
    },
    employeeName: {
        color: heroPalette.text,
        fontSize: 17,
        fontWeight: '800',
    },
    employeeMeta: {
        marginTop: 4,
        color: heroPalette.textMuted,
        fontSize: 12,
    },
    employeeBadge: {
        borderRadius: 999,
        paddingHorizontal: 10,
        paddingVertical: 6,
        backgroundColor: 'rgba(103, 232, 249, 0.14)',
        borderWidth: 1,
        borderColor: 'rgba(103, 232, 249, 0.28)',
    },
    employeeBadgeLate: {
        backgroundColor: 'rgba(248, 113, 113, 0.18)',
        borderColor: 'rgba(248, 113, 113, 0.32)',
    },
    employeeBadgeAttention: {
        backgroundColor: 'rgba(251, 191, 36, 0.18)',
        borderColor: 'rgba(251, 191, 36, 0.32)',
    },
    employeeBadgeText: {
        color: heroPalette.text,
        fontSize: 11,
        fontWeight: '800',
    },
    locationPill: {
        marginTop: 12,
        marginBottom: 12,
        borderRadius: 14,
        paddingHorizontal: 12,
        paddingVertical: 10,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    locationPillText: {
        color: heroPalette.textSoft,
        fontSize: 12,
        fontWeight: '600',
    },
    toolsList: {
        gap: 10,
    },
    toolCard: {
        borderRadius: 18,
        padding: 14,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    toolCardSelected: {
        borderColor: heroPalette.primaryStrong,
        backgroundColor: 'rgba(34, 197, 94, 0.12)',
    },
    toolHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 10,
    },
    toolTitle: {
        flex: 1,
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
    },
    daysBadge: {
        borderRadius: 999,
        paddingHorizontal: 8,
        paddingVertical: 5,
        backgroundColor: 'rgba(96, 165, 250, 0.16)',
    },
    daysBadgeLate: {
        backgroundColor: 'rgba(248, 113, 113, 0.18)',
    },
    daysBadgeText: {
        color: heroPalette.text,
        fontSize: 11,
        fontWeight: '800',
    },
    toolMeta: {
        marginTop: 8,
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 17,
    },
    toolNote: {
        marginTop: 8,
        color: heroPalette.textSoft,
        fontSize: 12,
        lineHeight: 17,
    },
    selectedBox: {
        marginTop: 12,
        borderRadius: 14,
        paddingHorizontal: 12,
        paddingVertical: 10,
        backgroundColor: 'rgba(34, 197, 94, 0.12)',
        borderWidth: 1,
        borderColor: 'rgba(34, 197, 94, 0.24)',
    },
    selectedText: {
        color: heroPalette.text,
        fontSize: 12,
        fontWeight: '700',
        lineHeight: 18,
    },
    returnButton: {
        marginTop: 12,
        borderRadius: 16,
        paddingVertical: 13,
        paddingHorizontal: 16,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: heroPalette.primaryStrong,
    },
    returnButtonDisabled: {
        opacity: 0.45,
    },
    returnButtonText: {
        color: heroPalette.bg,
        fontSize: 13,
        fontWeight: '800',
    },
});