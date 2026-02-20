import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator, ScrollView } from 'react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import ApiService from '../services/api';

const scopes = [
    { key: 'materials', label: 'Materiais' },
    { key: 'tools', label: 'Ferramentas' },
    { key: 'all', label: 'Geral' },
];

const formats = [
    { key: 'pdf', label: 'PDF' },
    { key: 'xlsx', label: 'XLSX' },
    { key: 'jpeg', label: 'JPEG' },
];

const monthLabels = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

export default function ReportsMonthlyScreen() {
    const now = new Date();
    const [month, setMonth] = useState(now.getMonth() + 1);
    const [year, setYear] = useState(now.getFullYear());
    const [loading, setLoading] = useState(false);

    const years = useMemo(() => {
        const list = [];
        for (let i = 0; i < 4; i += 1) {
            list.push(now.getFullYear() - i);
        }
        return list;
    }, [now]);

    const handleShare = async (scope, format) => {
        setLoading(true);
        try {
            const token = await ApiService.getToken();
            const url = ApiService.getReportUrl('monthly', { scope, format, month, year });
            const filename = `relatorio_mensal_${year}_${String(month).padStart(2, '0')}_${scope}.${format}`;
            const fileUri = `${FileSystem.cacheDirectory}${filename}`;

            const download = await FileSystem.downloadAsync(url, fileUri, {
                headers: { Authorization: `Bearer ${token}` },
            });

            if (await Sharing.isAvailableAsync()) {
                const mimeType = format === 'pdf'
                    ? 'application/pdf'
                    : format === 'xlsx'
                        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        : 'image/jpeg';
                await Sharing.shareAsync(download.uri, {
                    mimeType,
                    dialogTitle: 'Compartilhar relatório',
                });
            } else {
                Alert.alert('Indisponível', 'Compartilhamento não disponível neste dispositivo.');
            }
        } catch (error) {
            Alert.alert('Erro', error?.message || 'Falha ao gerar relatório');
        } finally {
            setLoading(false);
        }
    };

    return (
        <ScrollView style={styles.container}>
            <Text style={styles.title}>Relatório Mensal</Text>

            <Text style={styles.sectionTitle}>Mês</Text>
            <View style={styles.chipsContainer}>
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
            </View>

            <Text style={styles.sectionTitle}>Ano</Text>
            <View style={styles.row}>
                {years.map((y) => {
                    const selected = y === year;
                    return (
                        <TouchableOpacity
                            key={y}
                            style={[styles.chip, selected && styles.chipActive]}
                            onPress={() => setYear(y)}
                        >
                            <Text style={[styles.chipText, selected && styles.chipTextActive]}>{y}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>

            {scopes.map((scope) => (
                <View key={scope.key} style={styles.section}>
                    <Text style={styles.sectionTitle}>{scope.label}</Text>
                    <View style={styles.row}>
                        {formats.map((format) => (
                            <TouchableOpacity
                                key={`${scope.key}-${format.key}`}
                                style={styles.button}
                                onPress={() => handleShare(scope.key, format.key)}
                                disabled={loading}
                            >
                                {loading ? (
                                    <ActivityIndicator color="#fff" />
                                ) : (
                                    <Text style={styles.buttonText}>{format.label}</Text>
                                )}
                            </TouchableOpacity>
                        ))}
                    </View>
                </View>
            ))}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        padding: 20,
        backgroundColor: '#f5f5f5',
    },
    title: {
        fontSize: 22,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 12,
    },
    section: {
        marginBottom: 16,
    },
    sectionTitle: {
        fontSize: 14,
        fontWeight: '600',
        color: '#111827',
        marginBottom: 8,
        marginTop: 8,
    },
    row: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 10,
    },
    chipsContainer: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
        marginBottom: 8,
    },
    chip: {
        backgroundColor: '#e5e7eb',
        paddingVertical: 6,
        paddingHorizontal: 10,
        borderRadius: 16,
    },
    chipActive: {
        backgroundColor: '#0d6efd',
    },
    chipText: {
        fontSize: 12,
        color: '#111827',
    },
    chipTextActive: {
        color: '#000',
        fontWeight: '600',
    },
    button: {
        backgroundColor: '#0d6efd',
        paddingVertical: 10,
        paddingHorizontal: 16,
        borderRadius: 8,
        alignItems: 'center',
    },
    buttonText: {
        color: '#000',
        fontWeight: '600',
    },
});
