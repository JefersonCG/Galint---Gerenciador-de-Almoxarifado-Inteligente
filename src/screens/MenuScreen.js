import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import ApiService from '../services/api';
import HeroScreen from '../components/HeroScreen';
import { subscribeNotifyInboxChanged } from '../services/notifyEvents';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

export default function MenuScreen({ navigation }) {
    const [overview, setOverview] = useState(null);
    const [loading, setLoading] = useState(true);

    const loadOverview = useCallback(async (silent = false) => {
        if (!silent) {
            setLoading(true);
        }

        const result = await ApiService.getErpOverview();
        if (result?.success) {
            setOverview(result.data || null);
        } else {
            setOverview(null);
        }

        if (!silent) {
            setLoading(false);
        }
    }, []);

    useFocusEffect(
        useCallback(() => {
            loadOverview();
            const intervalId = setInterval(() => loadOverview(true), 12000);
            const unsubscribeNotify = subscribeNotifyInboxChanged(() => {
                loadOverview(true);
            });

            return () => {
                clearInterval(intervalId);
                unsubscribeNotify();
            };
        }, [loadOverview])
    );

    const unreadCount = Number(overview?.notifications?.unread_count || 0);
    const movementStats = overview?.movement_stats?.today || {};
    const totalToday = Number(movementStats.entradas || 0) + Number(movementStats.saidas || 0) + Number(movementStats.inventario || 0);
    const totalItems = Number(overview?.stock?.total_itens || 0);
    const userName = String(overview?.user?.nome || '').trim();
    const firstName = userName ? userName.split(' ')[0] : '';
    const recentMovements = Array.isArray(overview?.recent_movements) ? overview.recent_movements.slice(0, 4) : [];
    const documentModes = Array.isArray(overview?.features?.document_modes) ? overview.features.document_modes : [];

    return (
        <HeroScreen
            eyebrow="Central mobile"
            title={firstName ? `Operacao rapida de ${firstName}` : 'Central mobile'}
            subtitle="O mobile agora vira a camada rapida do GALINT: acesso direto a notificacoes, entradas documentais, relatorios e leitura operacional do dia."
            heroContent={
                <View style={styles.heroStats}>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Notificacoes</Text>
                        <Text style={styles.heroStatValue}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
                    </View>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Hoje</Text>
                        <Text style={styles.heroStatValue}>{totalToday}</Text>
                    </View>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Estoque</Text>
                        <Text style={styles.heroStatValue}>{totalItems}</Text>
                    </View>
                </View>
            }
        >
            {loading ? (
                <View style={styles.loadingBox}>
                    <ActivityIndicator color={heroPalette.primaryStrong} />
                    <Text style={styles.loadingText}>Atualizando central mobile...</Text>
                </View>
            ) : null}

            <TouchableOpacity 
                style={[styles.modernCard, styles.profileCard]} 
                onPress={() => navigation.navigate('Profile')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>👤</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Perfil</Text>
                    <Text style={styles.cardSubtitle}>Dados do usuario e informacoes da conta</Text>
                </View>
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            <TouchableOpacity 
                style={[styles.modernCard, styles.notificationsCard]} 
                onPress={() => navigation.navigate('Notifications')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>🔔</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Notificações</Text>
                    <Text style={styles.cardSubtitle}>Mensagens operacionais e leitura de alertas</Text>
                </View>
                {unreadCount > 0 ? (
                    <View style={styles.notificationBadge}>
                        <Text style={styles.notificationBadgeText}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
                    </View>
                ) : null}
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            <TouchableOpacity
                style={[styles.modernCard, styles.documentsCard]}
                onPress={() => navigation.navigate('DocumentosFiscais')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>🧾</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Documentos Fiscais</Text>
                    <Text style={styles.cardSubtitle}>Cadastro mobile para NF, cupom, recibo e lancamento manual</Text>
                </View>
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            <TouchableOpacity
                style={[styles.modernCard, styles.consumptionCard]}
                onPress={() => navigation.navigate('ReportsConsumption')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>📊</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Consumo analitico</Text>
                    <Text style={styles.cardSubtitle}>Categoria, local e funcionario em leitura simplificada para o aparelho.</Text>
                </View>
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            <TouchableOpacity 
                style={[styles.modernCard, styles.updatesCard]} 
                onPress={() => navigation.navigate('Config')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>🔄</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Atualizações</Text>
                    <Text style={styles.cardSubtitle}>Servidor, OTA e configuracoes do dispositivo</Text>
                </View>
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            <TouchableOpacity 
                style={[styles.modernCard, styles.reportsCard]} 
                onPress={() => navigation.navigate('Reports')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>📄</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Relatórios</Text>
                    <Text style={styles.cardSubtitle}>Relatorios diarios, mensais e historicos</Text>
                </View>
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            {documentModes.length ? (
                <View style={styles.modeBox}>
                    <Text style={styles.modeTitle}>Entradas disponiveis no mobile</Text>
                    <View style={styles.modeRow}>
                        {documentModes.map((mode) => (
                            <View key={mode.value} style={styles.modeChip}>
                                <Text style={styles.modeChipText}>{mode.label}</Text>
                            </View>
                        ))}
                    </View>
                </View>
            ) : null}

            <View style={styles.footerInfo}>
                <Text style={styles.footerText}>Movimentacoes recentes</Text>
                {recentMovements.length ? recentMovements.map((movement, index) => (
                    <View key={`${movement.id || index}-${movement.tipo}`} style={styles.movementRow}>
                        <View style={styles.movementCopy}>
                            <Text style={styles.movementTitle}>{movement.tipo || 'Movimento'} • {movement.descricao || movement.codigo || 'Item'}</Text>
                            <Text style={styles.movementMeta}>{movement.responsavel || 'Sem responsavel'}{movement.local_servico ? ` • ${movement.local_servico}` : ''}</Text>
                        </View>
                        <Text style={styles.movementQty}>{movement.quantidade}</Text>
                    </View>
                )) : (
                    <Text style={styles.footerSubtext}>Sem movimentacoes recentes carregadas para este aparelho.</Text>
                )}
            </View>
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
        fontSize: 12,
        fontWeight: '700',
        textTransform: 'uppercase',
        letterSpacing: 0.8,
    },
    heroStatValue: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 22,
        fontWeight: '900',
    },
    modernCard: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: heroPalette.panel,
        borderRadius: 22,
        padding: 18,
        marginBottom: 14,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    profileCard: {
        borderColor: 'rgba(103, 232, 249, 0.24)',
    },
    updatesCard: {
        borderColor: 'rgba(251, 191, 36, 0.24)',
    },
    notificationsCard: {
        borderColor: 'rgba(52, 211, 153, 0.24)',
    },
    documentsCard: {
        borderColor: 'rgba(96, 165, 250, 0.26)',
    },
    reportsCard: {
        borderColor: 'rgba(244, 114, 182, 0.22)',
    },
    consumptionCard: {
        borderColor: 'rgba(251, 191, 36, 0.24)',
    },
    cardIconContainer: {
        width: 56,
        height: 56,
        borderRadius: 28,
        backgroundColor: heroPalette.panelAlt,
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: 16,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    cardIcon: {
        fontSize: 28,
    },
    cardContent: {
        flex: 1,
    },
    cardTitle: {
        fontSize: 17,
        fontWeight: '700',
        color: heroPalette.text,
        marginBottom: 4,
    },
    cardSubtitle: {
        fontSize: 13,
        color: heroPalette.textMuted,
        lineHeight: 18,
    },
    cardArrow: {
        fontSize: 32,
        color: heroPalette.textMuted,
        fontWeight: '300',
    },
    notificationBadge: {
        minWidth: 28,
        height: 28,
        borderRadius: 14,
        paddingHorizontal: 8,
        marginRight: 10,
        backgroundColor: heroPalette.danger,
        alignItems: 'center',
        justifyContent: 'center',
    },
    notificationBadgeText: {
        color: '#ffffff',
        fontSize: 12,
        fontWeight: '800',
    },
    loadingBox: {
        borderRadius: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        paddingHorizontal: 16,
        paddingVertical: 16,
        marginBottom: 14,
        alignItems: 'center',
    },
    loadingText: {
        marginTop: 8,
        color: heroPalette.textMuted,
        fontSize: 12,
    },
    modeBox: {
        borderRadius: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        paddingHorizontal: 16,
        paddingVertical: 16,
        marginTop: 2,
        marginBottom: 12,
    },
    modeTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 10,
    },
    modeRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    modeChip: {
        borderRadius: 999,
        paddingHorizontal: 10,
        paddingVertical: 6,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
    },
    modeChipText: {
        color: heroPalette.textSoft,
        fontSize: 11,
        fontWeight: '700',
    },
    footerInfo: {
        borderRadius: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        paddingHorizontal: 16,
        paddingVertical: 16,
        marginTop: 6,
    },
    footerText: {
        fontSize: 14,
        fontWeight: '600',
        color: heroPalette.text,
        marginBottom: 4,
    },
    footerSubtext: {
        fontSize: 12,
        color: heroPalette.textMuted,
    },
    movementRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 12,
        paddingTop: 10,
        borderTopWidth: 1,
        borderTopColor: heroPalette.border,
        marginTop: 10,
    },
    movementCopy: {
        flex: 1,
    },
    movementTitle: {
        color: heroPalette.text,
        fontSize: 13,
        fontWeight: '700',
        marginBottom: 3,
    },
    movementMeta: {
        color: heroPalette.textMuted,
        fontSize: 12,
    },
    movementQty: {
        color: heroPalette.primary,
        fontSize: 13,
        fontWeight: '800',
    },
});
