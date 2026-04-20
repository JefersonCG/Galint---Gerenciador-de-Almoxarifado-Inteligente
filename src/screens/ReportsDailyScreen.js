import React, { useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
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

export default function ReportsDailyScreen() {
    const [loadingScope, setLoadingScope] = useState(null);

    const handleShare = async (scope) => {
        setLoadingScope(scope);
        try {
            const token = await ApiService.getToken();
            const url = ApiService.getReportUrl('daily', { scope, format: 'pdf' });
            const filename = `relatorio_diario_${scope}.pdf`;
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
            eyebrow="Relatório diário"
            title="PDF operacional do dia"
            subtitle="O mobile gera o PDF real do fluxo diário e compartilha direto do aparelho. Escolha o escopo e dispare."
            heroContent={
                <View style={styles.heroGrid}>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Formato</Text>
                        <Text style={styles.heroValue}>PDF</Text>
                    </View>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Escopos</Text>
                        <Text style={styles.heroValue}>3 modos</Text>
                    </View>
                </View>
            }
        >
            {scopes.map((scope) => (
                <View key={scope.key} style={styles.sectionCard}>
                    <View style={styles.sectionCopy}>
                        <Text style={styles.sectionTitle}>{scope.label}</Text>
                        <Text style={styles.sectionSubtitle}>Gera o relatório diário em PDF pronto para compartilhar.</Text>
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
                <Text style={styles.infoTitle}>Escopos disponíveis</Text>
                <Text style={styles.infoText}>Materiais, ferramentas e visão geral. O app não oferece formato falso: aqui o compartilhamento segue exatamente o arquivo que o servidor entrega.</Text>
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
        fontSize: 20,
        fontWeight: '900',
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
