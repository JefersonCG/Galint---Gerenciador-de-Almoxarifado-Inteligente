import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { palette } from '../theme';

export default function ScreenShell({ title, subtitle, children, scroll = true }) {
  const content = (
    <View style={styles.inner}>
      <View style={styles.heroCard}>
        <View style={styles.heroGlowPrimary} />
        <View style={styles.heroGlowAccent} />
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {children}
    </View>
  );

  return (
    <SafeAreaView style={styles.safe}>
      {scroll ? <ScrollView contentContainerStyle={styles.scroll}>{content}</ScrollView> : content}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.bg },
  scroll: { padding: 18, paddingBottom: 30 },
  inner: { padding: 18 },
  heroCard: {
    position: 'relative',
    overflow: 'hidden',
    marginBottom: 18,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.panel,
    paddingHorizontal: 20,
    paddingVertical: 20,
  },
  heroGlowPrimary: {
    position: 'absolute',
    width: 180,
    height: 180,
    borderRadius: 999,
    backgroundColor: 'rgba(56, 189, 248, 0.14)',
    top: -64,
    right: -32,
  },
  heroGlowAccent: {
    position: 'absolute',
    width: 112,
    height: 112,
    borderRadius: 999,
    backgroundColor: 'rgba(34, 197, 94, 0.12)',
    bottom: -36,
    left: -18,
  },
  title: { color: palette.text, fontSize: 28, fontWeight: '800' },
  subtitle: { color: palette.muted, fontSize: 14, marginTop: 6, lineHeight: 20 },
});