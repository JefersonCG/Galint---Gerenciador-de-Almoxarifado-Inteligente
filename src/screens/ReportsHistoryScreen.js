import React, { useCallback, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
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

function getTypeLabel(type) {
    switch (type) {
        case 'saidas':
            return 'Saidas do dia';
        case 'estoque':
            return 'Estoque baixo';
        case 'mensal':
            return 'Relatorio mensal';
        case 'consumo':
            return 'Consumo analitico';
        default:
            return 'Relatorio';
    }
}

function getScopeLabel(scope, scopeValue) {
    const base = {
        tools: 'Ferramentas',
        materials: 'Materiais',
        all: 'Geral',
        local: 'Local',
        categoria: 'Categoria',
        funcionario: 'Funcionario',
    }[scope] || null;

    if (!base && !scopeValue) {
        return null;
    }

    if (scopeValue) {
        const readableValue = String(scopeValue).replace(/_/g, ' ');
        return base ? `${base}: ${readableValue}` : readableValue;
    }

    return base;
}

function resolveMimeType(filename) {
    const lower = String(filename || '').toLowerCase();
    if (lower.endsWith('.xlsx')) {
        return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    }
    if (lower.endsWith('.jpeg') || lower.endsWith('.jpg')) {
        return 'image/jpeg';
    }
    return 'application/pdf';
}

export default function ReportsHistoryScreen() {
    const [reports, setReports] = useState([]);
    const [loading, setLoading] = useState(true);
    const [downloading, setDownloading] = useState(null);

    const loadReports = useCallback(async () => {
        setLoading(true);
        try {
            const result = await ApiService.getReportsHistory();
            if (!result?.success) {
                Alert.alert('Historico', result?.message || 'Nao foi possivel carregar os relatorios.');
                setReports([]);
                return;
            }
            setReports(Array.isArray(result.reports) ? result.reports : []);
        } catch (error) {
            Alert.alert('Historico', error?.message || 'Nao foi possivel carregar os relatorios.');
            setReports([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useFocusEffect(
        useCallback(() => {
            loadReports();
        }, [loadReports])
    );

    const downloadReport = async (report) => {
        setDownloading(report.filename);
        try {
            const token = await ApiService.getToken();
            const url = ApiService.getReportUrl('download', { filename: report.filename });
            const fileUri = `${FileSystem.cacheDirectory}${report.filename}`;
            const download = await FileSystem.downloadAsync(url, fileUri, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (await Sharing.isAvailableAsync()) {
                await Sharing.shareAsync(download.uri, {
                    mimeType: resolveMimeType(report.filename),
                    dialogTitle: 'Compartilhar relatorio',
                });
            } else {
                Alert.alert('Relatorio salvo', download.uri);
            }
        } catch (error) {
            Alert.alert('Download', error?.message || 'Nao foi possivel baixar o relatorio.');
        } finally {
            setDownloading(null);
        }
    };

    const pdfCount = reports.filter((report) => String(report.format || '').toUpperCase() === 'PDF').length;
    const monthlyCount = reports.filter((report) => report.type === 'mensal').length;
    const consumptionCount = reports.filter((report) => report.type === 'consumo').length;

    return (
        <HeroScreen
            eyebrow="Arquivo"
            title="Historico de relatorios"
            subtitle="Tudo que ja foi gerado no servidor fica disponivel aqui para reuso rapido no aparelho."
            heroContent={
                <View style={styles.heroGrid}>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>Arquivos</Text>
                        <Text style={styles.heroValue}>{reports.length}</Text>
                    </View>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>PDFs</Text>
                        <Text style={styles.heroValue}>{pdfCount}</Text>
                    </View>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>Mensais</Text>
                        <Text style={styles.heroValue}>{monthlyCount}</Text>
                    </View>
                    <View style={styles.heroStat}>
                        <Text style={styles.heroLabel}>Consumo</Text>
                        <Text style={styles.heroValue}>{consumptionCount}</Text>
                    </View>
                </View>
            }
        >
            <TouchableOpacity style={styles.refreshButton} onPress={loadReports} activeOpacity={0.86}>
                <Text style={styles.refreshButtonText}>{loading ? 'Atualizando...' : 'Recarregar historico'}</Text>
            </TouchableOpacity>

            {loading ? (
                <View style={styles.loadingBox}>
                    <ActivityIndicator color={heroPalette.primaryStrong} />
                    <Text style={styles.loadingText}>Carregando relatorios...</Text>
                </View>
            ) : null}

            {!loading && reports.length === 0 ? (
                <View style={styles.emptyBox}>
                    <Text style={styles.emptyTitle}>Nenhum relatorio encontrado</Text>
                    <Text style={styles.emptyText}>Os PDFs gerados pelo servidor vao aparecer aqui para download e compartilhamento.</Text>
                </View>
            ) : null}

            {!loading && reports.map((report) => {
                const scopeLabel = getScopeLabel(report.scope, report.scope_value);
                return (
                    <View key={report.filename} style={styles.reportCard}>
                        <View style={styles.reportHeader}>
                            <View style={styles.reportCopy}>
                                <Text style={styles.reportTitle}>{getTypeLabel(report.type)}</Text>
                                <Text style={styles.reportMeta}>{report.date_formatted || 'Sem data'}</Text>
                                {report.month ? <Text style={styles.reportMeta}>Periodo: {report.month}</Text> : null}
                                {scopeLabel ? <Text style={styles.scopeBadge}>{scopeLabel}</Text> : null}
                            </View>
                            <View style={styles.formatBadge}>
                                <Text style={styles.formatBadgeText}>{report.format || 'PDF'}</Text>
                            </View>
                        </View>

                        <View style={styles.reportFooter}>
                            <Text style={styles.reportSize}>{report.size_mb} MB</Text>
                            <TouchableOpacity
                                style={styles.downloadButton}
                                onPress={() => downloadReport(report)}
                                disabled={downloading === report.filename}
                            >
                                {downloading === report.filename ? (
                                    <ActivityIndicator color={heroPalette.bg} />
                                ) : (
                                    <Text style={styles.downloadButtonText}>Baixar arquivo</Text>
                                )}
                            </TouchableOpacity>
                        </View>
                    </View>
                );
            })}
        </HeroScreen>
    );
}

const styles = StyleSheet.create({
    heroGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 12,
    },
    heroStat: {
        minWidth: '47%',
        flexGrow: 1,
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
    refreshButton: {
        borderRadius: 18,
        paddingVertical: 12,
        paddingHorizontal: 16,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        marginBottom: 14,
        alignItems: 'center',
    },
    refreshButtonText: {
        color: heroPalette.text,
        fontSize: 13,
        fontWeight: '800',
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
    emptyBox: {
        borderRadius: 22,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
        padding: 20,
        ...heroShadow,
    },
    emptyTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 6,
    },
    emptyText: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    reportCard: {
        backgroundColor: heroPalette.panel,
        borderRadius: 22,
        padding: 18,
        marginBottom: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    reportHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 10,
    },
    reportCopy: {
        flex: 1,
    },
    reportTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 6,
    },
    reportMeta: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 18,
    },
    scopeBadge: {
        marginTop: 8,
        alignSelf: 'flex-start',
        borderRadius: 999,
        paddingHorizontal: 10,
        paddingVertical: 5,
        backgroundColor: heroPalette.panelAlt,
        color: heroPalette.textSoft,
        fontSize: 11,
        fontWeight: '700',
    },
    formatBadge: {
        borderRadius: 14,
        paddingHorizontal: 12,
        paddingVertical: 10,
        backgroundColor: 'rgba(103, 232, 249, 0.14)',
        borderWidth: 1,
        borderColor: heroPalette.borderStrong,
        alignSelf: 'flex-start',
    },
    formatBadgeText: {
        color: heroPalette.text,
        fontSize: 12,
        fontWeight: '800',
    },
    reportFooter: {
        marginTop: 14,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
    },
    reportSize: {
        color: heroPalette.textMuted,
        fontSize: 12,
        fontWeight: '700',
    },
    downloadButton: {
        minWidth: 136,
        borderRadius: 14,
        paddingVertical: 10,
        paddingHorizontal: 16,
        backgroundColor: heroPalette.primaryStrong,
        alignItems: 'center',
        justifyContent: 'center',
    },
    downloadButtonText: {
        color: heroPalette.bg,
        fontSize: 13,
        fontWeight: '800',
    },
});