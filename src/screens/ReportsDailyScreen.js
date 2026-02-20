import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
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

export default function ReportsDailyScreen() {
    const [loading, setLoading] = useState(false);

    const handleShare = async (scope, format) => {
        setLoading(true);
        try {
            const token = await ApiService.getToken();
            const url = ApiService.getReportUrl('daily', { scope, format });
            const filename = `relatorio_diario_${scope}.${format}`;
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
        <View style={styles.container}>
            <Text style={styles.title}>Relatório Diário</Text>
            <Text style={styles.subtitle}>Escolha o tipo e o formato</Text>

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
        </View>
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
        marginBottom: 6,
    },
    subtitle: {
        fontSize: 12,
        color: '#6b7280',
        marginBottom: 20,
    },
    section: {
        marginBottom: 16,
    },
    sectionTitle: {
        fontSize: 14,
        fontWeight: '600',
        color: '#111827',
        marginBottom: 8,
    },
    row: {
        flexDirection: 'row',
        gap: 10,
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
