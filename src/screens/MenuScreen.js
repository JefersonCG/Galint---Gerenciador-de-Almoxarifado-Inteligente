import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';

import ApiService from '../services/api';

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
        <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
            {/* Header Moderno */}
            <View style={styles.modernHeader}>
                <Text style={styles.headerTitle}>⚙️ Menu</Text>
                <Text style={styles.headerSubtitle}>Configurações e Opções</Text>
            </View>

            {/* Cards Modernos */}
            <TouchableOpacity 
                style={[styles.modernCard, styles.profileCard]} 
                onPress={() => navigation.navigate('Profile')}
                activeOpacity={0.85}
            >
                <View style={styles.cardIconContainer}>
                    <Text style={styles.cardIcon}>👤</Text>
                </View>
                <View style={styles.cardContent}>
                    <Text style={styles.cardTitle}>Perfil do Usuário</Text>
                    <Text style={styles.cardSubtitle}>Visualizar dados pessoais e informações da conta</Text>
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
                    <Text style={styles.cardSubtitle}>Ver mensagens operacionais com foto e contexto visual</Text>
                </View>
                {unreadCount > 0 ? (
                    <View style={styles.notificationBadge}>
                        <Text style={styles.notificationBadgeText}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
                    </View>
                ) : null}
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
                    <Text style={styles.cardSubtitle}>Verificar e instalar atualizações OTA</Text>
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
                    <Text style={styles.cardSubtitle}>Visualizar relatórios diários e mensais</Text>
                </View>
                <Text style={styles.cardArrow}>›</Text>
            </TouchableOpacity>

            {/* Footer Info */}
            <View style={styles.footerInfo}>
                <Text style={styles.footerText}>GALINT v1.2.0</Text>
                <Text style={styles.footerSubtext}>© 2026 Sublime Max Condominium</Text>
            </View>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#f8fafc',
    },
    contentContainer: {
        paddingBottom: 30,
    },
    modernHeader: {
        backgroundColor: '#22c55e',
        paddingTop: 60,
        paddingBottom: 30,
        paddingHorizontal: 24,
        marginBottom: 20,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 6,
        elevation: 8,
    },
    headerTitle: {
        fontSize: 28,
        fontWeight: '800',
        color: '#ffffff',
        marginBottom: 6,
    },
    headerSubtitle: {
        fontSize: 15,
        fontWeight: '500',
        color: '#e0ffe6',
    },
    modernCard: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#ffffff',
        borderRadius: 16,
        padding: 18,
        marginHorizontal: 16,
        marginBottom: 14,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.08,
        shadowRadius: 8,
        elevation: 4,
        borderLeftWidth: 4,
    },
    profileCard: {
        borderLeftColor: '#3b82f6',
    },
    updatesCard: {
        borderLeftColor: '#8b5cf6',
    },
    notificationsCard: {
        borderLeftColor: '#0ea5e9',
    },
    reportsCard: {
        borderLeftColor: '#f59e0b',
    },
    cardIconContainer: {
        width: 56,
        height: 56,
        borderRadius: 28,
        backgroundColor: '#f0f9ff',
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: 16,
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
        color: '#111827',
        marginBottom: 4,
    },
    cardSubtitle: {
        fontSize: 13,
        color: '#6b7280',
        lineHeight: 18,
    },
    cardArrow: {
        fontSize: 32,
        color: '#d1d5db',
        fontWeight: '300',
    },
    notificationBadge: {
        minWidth: 28,
        height: 28,
        borderRadius: 14,
        paddingHorizontal: 8,
        marginRight: 10,
        backgroundColor: '#dc2626',
        alignItems: 'center',
        justifyContent: 'center',
    },
    notificationBadgeText: {
        color: '#ffffff',
        fontSize: 12,
        fontWeight: '800',
    },
    footerInfo: {
        alignItems: 'center',
        marginTop: 30,
        paddingHorizontal: 20,
    },
    footerText: {
        fontSize: 14,
        fontWeight: '600',
        color: '#6b7280',
        marginBottom: 4,
    },
    footerSubtext: {
        fontSize: 12,
        color: '#9ca3af',
    },
});
