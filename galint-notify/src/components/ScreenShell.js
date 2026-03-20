import React from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { palette } from '../theme';

export default function ScreenShell({ title, subtitle, children, scroll = true }) {
  const content = (
    <View style={styles.inner}>
      <Text style={styles.title}>{title}</Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
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
  scroll: { padding: 20 },
  inner: { padding: 20 },
  title: { color: palette.text, fontSize: 28, fontWeight: '800' },
  subtitle: { color: palette.muted, fontSize: 14, marginTop: 6, marginBottom: 20, lineHeight: 20 },
});