import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import HeroScreen from '../components/HeroScreen';
import { heroPalette, heroShadow, heroSoftShadow } from '../theme/heroTheme';

const REPORT_CARDS = [
    {
        key: 'daily',
        route: 'ReportsDaily',
        eyebrow: 'PDF rapido',
        title: 'Relatorio diario',
        subtitle: 'Saidas do dia por materiais, ferramentas ou visao geral.',
        accent: 'rgba(103, 232, 249, 0.26)',
    },
    {
        key: 'monthly',
        route: 'ReportsMonthly',
        eyebrow: 'Fechamento',
        title: 'Relatorio mensal',
        subtitle: 'Periodo consolidado para auditoria e prestacao de contas.',
        accent: 'rgba(52, 211, 153, 0.24)',
    },
    {
        key: 'consumption',
        route: 'ReportsConsumption',
        eyebrow: 'Analitico',
        title: 'Consumo por categoria e funcionario',
        subtitle: 'Leitura simplificada do painel do web Flask, com local, categoria e colaborador.',
        accent: 'rgba(251, 191, 36, 0.26)',
    },
    {
        key: 'history',
        route: 'ReportsHistory',
        eyebrow: 'Arquivo',
        title: 'Historico de relatorios',
        subtitle: 'Recuperar PDFs ja gerados e compartilhar novamente pelo aparelho.',
        accent: 'rgba(244, 114, 182, 0.24)',
    },
];

export default function ReportsScreen({ navigation }) {
    return (
        <HeroScreen
            eyebrow="Relatorios"
            title="Central analitica mobile"
            subtitle="O mobile fica mais rapido: gera PDF operacional, abre o historico e consulta o consumo sem depender da tela web completa."
            heroContent={
                <View style={styles.heroGrid}>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Formatos reais</Text>
                        <Text style={styles.heroValue}>PDF</Text>
                    </View>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Analitico</Text>
                        <Text style={styles.heroValue}>Categoria</Text>
                    </View>
                    <View style={styles.heroCard}>
                        <Text style={styles.heroLabel}>Gestao</Text>
                        <Text style={styles.heroValue}>Funcionario</Text>
                    </View>
                </View>
            }
        >
            {REPORT_CARDS.map((card) => (
                <TouchableOpacity
                    key={card.key}
                    style={[styles.card, { borderColor: card.accent }]}
                    onPress={() => navigation.navigate(card.route)}
                    activeOpacity={0.86}
                >
                    <View style={styles.cardCopy}>
                        <Text style={styles.cardEyebrow}>{card.eyebrow}</Text>
                        <Text style={styles.cardTitle}>{card.title}</Text>
                        <Text style={styles.cardSubtitle}>{card.subtitle}</Text>
                    </View>
                    <View style={styles.cardBadge}>
                        <Text style={styles.cardBadgeText}>Abrir</Text>
                    </View>
                </TouchableOpacity>
            ))}

            <View style={styles.footerBox}>
                <Text style={styles.footerTitle}>Regra do app</Text>
                <Text style={styles.footerText}>
                    O mobile agora assume o que realmente entrega: PDF operacional, historico reutilizavel e leitura analitica simplificada.
                </Text>
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
        letterSpacing: 0.9,
    },
    heroValue: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '900',
    },
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderRadius: 22,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        padding: 18,
        marginBottom: 14,
        ...heroShadow,
    },
    cardCopy: {
        flex: 1,
        paddingRight: 14,
    },
    cardEyebrow: {
        color: heroPalette.primary,
        fontSize: 11,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 1,
        marginBottom: 6,
    },
    cardTitle: {
        color: heroPalette.text,
        fontSize: 18,
        fontWeight: '800',
        marginBottom: 6,
    },
    cardSubtitle: {
        color: heroPalette.textMuted,
        fontSize: 13,
        lineHeight: 19,
    },
    cardBadge: {
        minWidth: 78,
        borderRadius: 16,
        paddingHorizontal: 14,
        paddingVertical: 11,
        backgroundColor: heroPalette.panelAlt,
        borderWidth: 1,
        borderColor: heroPalette.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    cardBadgeText: {
        color: heroPalette.text,
        fontSize: 12,
        fontWeight: '800',
    },
    footerBox: {
        borderRadius: 18,
        borderWidth: 1,
        borderColor: heroPalette.border,
        backgroundColor: heroPalette.panelAlt,
        paddingHorizontal: 16,
        paddingVertical: 16,
        marginTop: 6,
    },
    footerTitle: {
        color: heroPalette.text,
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 4,
    },
    footerText: {
        color: heroPalette.textMuted,
        fontSize: 12,
        lineHeight: 18,
    },
});
