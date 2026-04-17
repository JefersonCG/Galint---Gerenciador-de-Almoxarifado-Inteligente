import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import HeroScreen from '../components/HeroScreen';
import ApiService from '../services/api';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

const scopes = [
    { key: 'materials', label: 'Materiais' },
    { key: 'tools', label: 'Ferramentas' },
    { key: 'all', label: 'Geral' },
];

const monthLabels = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

export default function ReportsMonthlyScreen() {
    const now = new Date();
    const [month, setMonth] = useState(now.getMonth() + 1);
    const [year, setYear] = useState(now.getFullYear());
    const [loadingScope, setLoadingScope] = useState(null);

    const years = useMemo(() => {
        const list = [];
        for (let i = 0; i < 4; i += 1) {
            list.push(now.getFullYear() - i);
        }
        return list;
    }, [now]);

    const handleShare = async (scope) => {
        setLoadingScope(scope);
        try {
            const token = await ApiService.getToken();
            const url = ApiService.getReportUrl('monthly', { scope, format: 'pdf', month, year });
            const filename = `relatorio_mensal_${year}_${String(month).padStart(2, '0')}_${scope}.pdf`;
            const fileUri = `${FileSystem.cacheDirectory}${filename}`;

            const download = await FileSystem.downloadAsync(url, fileUri, {
                headers: { Authorization: `Bearer ${token}` },
            });

            if (await Sharing.isAvailableAsync()) {
                await Sharing.shareAsync(download.uri, {
                    mimeType: 'application/pdf',
                    dialogTitle: 'Compartilhar relatório',
                });
            } else {
                Alert.alert('Indisponível', 'Compartilhamento não disponível neste dispositivo.');
            }
        } catch (error) {
            Alert.alert('Erro', error?.message || 'Falha ao gerar relatório');
        } finally {
            setLoadingScope(null);
        }
    };

    return (
        <HeroScreen
            eyebrow="Relatorio mensal"
            title="Fechamento em PDF"
            subtitle="Selecione mes, ano e escopo. O mobile usa a mesma trilha de PDF do servidor para manter consistencia operacional."
            heroContent={
                <View style={styles.heroGrid}>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Periodo</Text>
                        <Text style={styles.heroValue}>{monthLabels[month - 1]}</Text>
                    </View>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Ano</Text>
                        <Text style={styles.heroValue}>{year}</Text>
                    </View>
                </View>
            }
        >
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsContainer}>
                {monthLabels.map((label, index) => {
                    const value = index + 1;
                    const selected = value === month;
                    return (
                        <TouchableOpacity
                            key={label}
                            style={[styles.chip, selected && styles.chipActive]}
                            onPress={() => setMonth(value)}
                        >
                            <Text style={[styles.chipText, selected && styles.chipTextActive]}>{label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </ScrollView>

            <View style={styles.yearRow}>
                {years.map((y) => {
                    const selected = y === year;
                    return (
                        <TouchableOpacity
                            key={y}
                            style={[styles.yearChip, selected && styles.chipActive]}
                            onPress={() => setYear(y)}
                        >
                            <Text style={[styles.chipText, selected && styles.chipTextActive]}>{y}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>

            {scopes.map((scope) => (
                <View key={scope.key} style={styles.sectionCard}>
                    <View style={styles.sectionCopy}>
                        <Text style={styles.sectionTitle}>{scope.label}</Text>
                        <Text style={styles.sectionSubtitle}>Gera o fechamento do periodo em PDF pronto para envio.</Text>
                    </View>
                    <TouchableOpacity
                        style={styles.button}
                        onPress={() => handleShare(scope.key)}
                        disabled={loadingScope === scope.key}
                    >
                        {loadingScope === scope.key ? (
                            <ActivityIndicator color={heroPalette.bg} />
                        ) : (
                            <Text style={styles.buttonText}>Gerar PDF</Text>
                        )}
                    </TouchableOpacity>
                </View>
            ))}

            <View style={styles.infoBox}>
                <Text style={styles.infoTitle}>Uso recomendado</Text>
                <Text style={styles.infoText}>Use o mensal para fechamento, auditoria e prestacao de contas. O analitico por categoria e colaborador fica na tela separada de consumo.</Text>
            </View>
        </HeroScreen>
    );
}

const styles = StyleSheet.create({
    heroGrid: {
        flexDirection: 'row',
        gap: 12,
    },
    heroCard: {
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
    chipsContainer: {
        paddingBottom: 4,
        gap: 8,
        marginBottom: 10,
    },
    chip: {
        backgroundColor: heroPalette.panelAlt,
        paddingVertical: 6,
        paddingHorizontal: 10,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    chipActive: {
        backgroundColor: heroPalette.primaryStrong,
        borderColor: heroPalette.primaryStrong,
    },
    chipText: {
        fontSize: 12,
        color: heroPalette.text,
    },
    chipTextActive: {
        color: heroPalette.bg,
        fontWeight: '800',
    },
    yearRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
        marginBottom: 14,
    },
    yearChip: {
        backgroundColor: heroPalette.panelAlt,
        paddingVertical: 8,
        paddingHorizontal: 12,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    sectionCard: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: heroPalette.panel,
        borderRadius: 22,
        padding: 18,
        marginBottom: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    sectionCopy: {
        flex: 1,
        paddingRight: 12,
    },
    sectionTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 6,
    },
    sectionSubtitle: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    button: {
        minWidth: 116,
        backgroundColor: heroPalette.primaryStrong,
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
    },
    buttonText: {
        color: heroPalette.bg,
        fontWeight: '800',
        fontSize: 13,
    },
    infoBox: {
        borderRadius: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        paddingHorizontal: 16,
        paddingVertical: 16,
        marginTop: 6,
    },
    infoTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 4,
    },
    infoText: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 18,
    },
});
