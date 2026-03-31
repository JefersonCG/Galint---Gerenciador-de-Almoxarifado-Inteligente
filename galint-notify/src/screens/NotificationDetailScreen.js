import React, { useMemo } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import api from '../services/api';
import { palette } from '../theme';

function formatDisplayValue(value) {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return numeric.toLocaleString('pt-BR', { maximumFractionDigits: 6 });
  }
  return String(value ?? '-');
}

export default function NotificationDetailScreen({ route }) {
  const item = route.params?.item;
  if (!item) {
    return <View style={styles.safe}><Text style={styles.empty}>Notificação não encontrada.</Text></View>;
  }

  const payload = item.payload || {};
  const visual = payload.visual || {};
  const visualItem = visual.item || {};
  const visualMovement = visual.movement || {};
  const visualActor = visual.actor || {};
  const visualContext = visual.context || {};
  const media = payload.media || {};

  const imageUri = useMemo(() => {
    const candidates = [
      media.url,
      visualItem.foto_url,
      visualItem.foto_path,
    ];
    for (const candidate of candidates) {
      const resolved = api.resolveAssetUrl(candidate);
      if (resolved) {
        return resolved;
      }
    }
    return null;
  }, [media.url, visualItem.foto_path, visualItem.foto_url]);

  return (
    <ScrollView style={styles.safe} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <Text style={styles.category}>{item.category}</Text>
        <Text style={styles.title}>{item.title}</Text>
        <Text style={styles.body}>{item.body}</Text>

        {imageUri ? <Image source={{ uri: imageUri }} style={styles.image} resizeMode="cover" /> : null}

        {(visualItem.codigo || visualItem.descricao) ? (
          <View style={styles.block}>
            <Text style={styles.blockTitle}>Item</Text>
            <Text style={styles.infoPrimary}>{visualItem.descricao || '-'}</Text>
            <Text style={styles.infoSecondary}>Código: {visualItem.codigo || '-'}</Text>
            <Text style={styles.infoSecondary}>Categoria: {visualItem.categoria || '-'}</Text>
            <Text style={styles.infoSecondary}>Unidade: {visualItem.unidade || '-'}</Text>
            {visualItem.saldo_display ? <Text style={styles.infoSecondary}>Saldo: {visualItem.saldo_display}</Text> : null}
          </View>
        ) : null}

        {(visualMovement.quantidade_display || visual.kind_label || visual.batch_label) ? (
          <View style={styles.block}>
            <Text style={styles.blockTitle}>Movimento</Text>
            {visual.kind_label ? <Text style={styles.infoPrimary}>{visual.kind_label}</Text> : null}
            {visualMovement.quantidade_display ? <Text style={styles.infoSecondary}>Quantidade: {visualMovement.quantidade_display}</Text> : null}
            {visualMovement.balance_before != null ? <Text style={styles.infoSecondary}>Saldo antes: {formatDisplayValue(visualMovement.balance_before)} {visualMovement.balance_unit || ''}</Text> : null}
            {visualMovement.balance_after != null ? <Text style={styles.infoSecondary}>Saldo depois: {formatDisplayValue(visualMovement.balance_after)} {visualMovement.balance_unit || ''}</Text> : null}
            {visual.batch_label ? <Text style={styles.infoSecondary}>Lote: {visual.batch_label}</Text> : null}
          </View>
        ) : null}

        {(visualActor.nome || visualActor.matricula || visualContext.local_servico || visualContext.observacao) ? (
          <View style={styles.block}>
            <Text style={styles.blockTitle}>Contexto</Text>
            {visualActor.nome ? <Text style={styles.infoSecondary}>Responsável: {visualActor.nome}</Text> : null}
            {visualActor.matricula ? <Text style={styles.infoSecondary}>Matrícula: {visualActor.matricula}</Text> : null}
            {visualContext.local_servico ? <Text style={styles.infoSecondary}>Local: {visualContext.local_servico}</Text> : null}
            {visualContext.observacao ? <Text style={styles.infoSecondary}>Obs.: {visualContext.observacao}</Text> : null}
          </View>
        ) : null}

        <Text style={styles.blockTitle}>Payload</Text>
        <Text style={styles.payload}>{JSON.stringify(item.payload || {}, null, 2)}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.bg },
  content: { padding: 20 },
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 18 },
  category: { color: palette.primary, textTransform: 'uppercase', fontSize: 11, fontWeight: '800' },
  title: { color: palette.text, fontWeight: '800', fontSize: 24, marginTop: 8 },
  body: { color: palette.muted, marginTop: 12, lineHeight: 22 },
  image: { width: '100%', height: 220, borderRadius: 18, marginTop: 18, backgroundColor: palette.panelAlt },
  block: { marginTop: 18, backgroundColor: palette.panelAlt, borderRadius: 18, padding: 14, borderWidth: 1, borderColor: palette.border },
  blockTitle: { color: palette.text, fontWeight: '800', marginTop: 18, marginBottom: 8 },
  infoPrimary: { color: palette.text, fontWeight: '800', fontSize: 17 },
  infoSecondary: { color: palette.muted, marginTop: 6, lineHeight: 20 },
  payload: { color: palette.text, fontFamily: 'monospace', backgroundColor: palette.panelAlt, padding: 12, borderRadius: 14 },
  empty: { color: palette.text, padding: 20 },
});