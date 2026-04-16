import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { heroPalette, heroShadow } from '../theme/heroTheme';

export default function HeroScreen({
    eyebrow,
    title,
    subtitle,
    heroContent,
    children,
    scroll = true,
    contentContainerStyle,
}) {
    const content = (
        <View style={[styles.scroll, contentContainerStyle]}>
            <View style={styles.heroCard}>
                <View style={styles.orbPrimary} />
                <View style={styles.orbAccent} />
                {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
                <Text style={styles.title}>{title}</Text>
                {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
                {heroContent ? <View style={styles.heroContent}>{heroContent}</View> : null}
            </View>
            {children}
        </View>
    );

    return (
        <SafeAreaView style={styles.safe}>
            {scroll ? <ScrollView contentContainerStyle={styles.content}>{content}</ScrollView> : content}
        </SafeAreaView>
    );
}

const styles = StyleSheet.create({
    safe: {
        flex: 1,
        backgroundColor: heroPalette.bg,
    },
    content: {
        paddingBottom: 28,
    },
    scroll: {
        paddingHorizontal: 18,
        paddingTop: 16,
    },
    heroCard: {
        position: 'relative',
        overflow: 'hidden',
        borderRadius: 28,
        paddingHorizontal: 20,
        paddingVertical: 22,
        marginBottom: 18,
        backgroundColor: heroPalette.panel,
        borderWidth: 1,
        borderColor: heroPalette.border,
        ...heroShadow,
    },
    orbPrimary: {
        position: 'absolute',
        width: 180,
        height: 180,
        borderRadius: 999,
        top: -60,
        right: -40,
        backgroundColor: 'rgba(34, 211, 238, 0.16)',
    },
    orbAccent: {
        position: 'absolute',
        width: 120,
        height: 120,
        borderRadius: 999,
        bottom: -35,
        left: -18,
        backgroundColor: 'rgba(52, 211, 153, 0.14)',
    },
    eyebrow: {
        color: heroPalette.primary,
        fontSize: 11,
        fontWeight: '900',
        textTransform: 'uppercase',
        letterSpacing: 1.3,
    },
    title: {
        marginTop: 8,
        color: heroPalette.text,
        fontSize: 28,
        fontWeight: '900',
        letterSpacing: -0.8,
    },
    subtitle: {
        marginTop: 8,
        color: heroPalette.textMuted,
        fontSize: 14,
        lineHeight: 21,
        maxWidth: 520,
    },
    heroContent: {
        marginTop: 16,
    },
});