import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

import ApiService from '../services/api';
import HeroScreen from '../components/HeroScreen';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

export default function MenuScreen({ navigation }) {
    const [unreadCount, setUnreadCount] = useState(0);

    useFocusEffect(
        useCallback(() => {
            let active = true;

            const loadSummary = async () => {
                const result = await ApiService.getNotifySummary();
                if (!active) return;
                if (result?.success) {
                    setUnreadCount(Number(result.unread_count || 0));
                } else {
                    setUnreadCount(0);
                }
            };

            loadSummary();
            return () => {
                active = false;
            };
        }, [])
    );

    return (
        <HeroScreen
            eyebrow="Painel mobile"
            title="Controle rapido do dispositivo"
            subtitle="Sem excesso de blocos. Aqui ficam os atalhos secundarios do app enquanto a operacao principal acontece no estoque, retirada e devolucao."
            heroContent={
                <View style={styles.heroStats}>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Notificacoes</Text>
                        <Text style={styles.heroStatValue}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
                    </View>
                    <View style={styles.heroStatCard}>
                        <Text style={styles.heroStatLabel}>Entrada rapida</Text>
                        <Text style={styles.heroStatValue}>NF mobile</Text>
                    </View>
                </View>
            }
        >
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

            <View style={styles.footerInfo}>
                <Text style={styles.footerText}>O fluxo operacional principal segue na pesquisa do estoque.</Text>
                <Text style={styles.footerSubtext}>Use este painel para funcoes auxiliares e governanca do aparelho.</Text>
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
});
