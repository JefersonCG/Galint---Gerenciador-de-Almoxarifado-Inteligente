import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import ScreenShell from '../components/ScreenShell';
import api from '../services/api';
import { palette } from '../theme';

function parseNumber(value) {
  const normalized = String(value || '').replace(',', '.').trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function ToolsScreen() {
  const [mode, setMode] = useState('converter');
  const [leftValue, setLeftValue] = useState('');
  const [rightValue, setRightValue] = useState('');
  const [operation, setOperation] = useState('+');

  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [quantity, setQuantity] = useState('1');
  const [fromUnit, setFromUnit] = useState('');
  const [converting, setConverting] = useState(false);
  const [conversionResult, setConversionResult] = useState(null);

  const calculatorResult = useMemo(() => {
    const left = parseNumber(leftValue);
    const right = parseNumber(rightValue);
    if (left == null || right == null) return null;
    if (operation === '+') return left + right;
    if (operation === '-') return left - right;
    if (operation === '×') return left * right;
    if (operation === '÷') return right === 0 ? null : left / right;
    return null;
  }, [leftValue, rightValue, operation]);

  async function searchItems() {
    if ((query || '').trim().length < 2) {
      Alert.alert('GalintNotify', 'Digite ao menos 2 caracteres para buscar.');
      return;
    }
    try {
      setSearching(true);
      const response = await api.searchToolItems(query.trim());
      setResults(response.items || []);
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao buscar itens.');
    } finally {
      setSearching(false);
    }
  }

  function selectItem(item) {
    setSelectedItem(item);
    const baseUnit = (item.product_units || []).find((entry) => entry.is_base) || (item.product_units || [])[0] || null;
    setFromUnit(baseUnit?.unit_code || item.unidade || '');
    setConversionResult(null);
  }

  async function convertUnits() {
    if (!selectedItem?.codigo_item) {
      Alert.alert('GalintNotify', 'Selecione um item primeiro.');
      return;
    }
    const quantityValue = parseNumber(quantity);
    if (quantityValue == null) {
      Alert.alert('GalintNotify', 'Informe uma quantidade válida.');
      return;
    }
    if (!fromUnit) {
      Alert.alert('GalintNotify', 'Selecione a unidade de origem.');
      return;
    }
    try {
      setConverting(true);
      const response = await api.convertToolUnits({
        codigoItem: selectedItem.codigo_item,
        quantity: quantityValue,
        fromUnit,
      });
      setConversionResult(response);
    } catch (error) {
      Alert.alert('GalintNotify', error.message || 'Falha ao converter unidades.');
    } finally {
      setConverting(false);
    }
  }

  const selectedPhotoUri = useMemo(() => api.resolveAssetUrl(selectedItem?.foto_url || selectedItem?.foto_path), [selectedItem]);

  return (
    <ScreenShell title="Ferramentas" subtitle="Calculadora rápida e conversor interno usando as regras reais de unidade do GALINT.">
      <View style={styles.modeRow}>
        {[
          { key: 'converter', label: 'Conversor' },
          { key: 'calculator', label: 'Calculadora' },
        ].map((entry) => (
          <Pressable key={entry.key} onPress={() => setMode(entry.key)} style={[styles.modeChip, mode === entry.key && styles.modeChipActive]}>
            <Text style={[styles.modeText, mode === entry.key && styles.modeTextActive]}>{entry.label}</Text>
          </Pressable>
        ))}
      </View>

      {mode === 'calculator' ? (
        <View style={styles.card}>
          <Text style={styles.label}>Calculadora rápida</Text>
          <View style={styles.row}>
            <TextInput style={styles.input} value={leftValue} onChangeText={setLeftValue} keyboardType="numeric" placeholder="Primeiro valor" placeholderTextColor={palette.muted} />
            <TextInput style={styles.input} value={rightValue} onChangeText={setRightValue} keyboardType="numeric" placeholder="Segundo valor" placeholderTextColor={palette.muted} />
          </View>
          <View style={styles.modeRow}>
            {['+', '-', '×', '÷'].map((entry) => (
              <Pressable key={entry} onPress={() => setOperation(entry)} style={[styles.operatorChip, operation === entry && styles.modeChipActive]}>
                <Text style={[styles.modeText, operation === entry && styles.modeTextActive]}>{entry}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.resultLabel}>Resultado</Text>
          <Text style={styles.resultValue}>{calculatorResult == null ? '-' : calculatorResult.toLocaleString('pt-BR')}</Text>
        </View>
      ) : (
        <>
          <View style={styles.card}>
            <Text style={styles.label}>Buscar item</Text>
            <View style={styles.searchRow}>
              <TextInput style={[styles.input, styles.searchInput]} value={query} onChangeText={setQuery} placeholder="Código, descrição ou categoria" placeholderTextColor={palette.muted} />
              <Pressable style={styles.button} onPress={searchItems}>
                {searching ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.buttonText}>Buscar</Text>}
              </Pressable>
            </View>

            {(results || []).map((item) => (
              <Pressable key={item.codigo_item} onPress={() => selectItem(item)} style={[styles.searchResult, selectedItem?.codigo_item === item.codigo_item && styles.searchResultActive]}>
                <Text style={styles.resultTitle}>{item.descricao}</Text>
                <Text style={styles.resultMeta}>{item.codigo_item} • {item.categoria || 'Sem categoria'}</Text>
                <Text style={styles.resultMeta}>{item.saldo_display || '-'}</Text>
              </Pressable>
            ))}
          </View>

          {selectedItem ? (
            <View style={styles.card}>
              <Text style={styles.label}>Item selecionado</Text>
              {selectedPhotoUri ? <Image source={{ uri: selectedPhotoUri }} style={styles.photo} resizeMode="cover" /> : null}
              <Text style={styles.itemTitle}>{selectedItem.descricao}</Text>
              <Text style={styles.resultMeta}>Código: {selectedItem.codigo_item}</Text>
              <Text style={styles.resultMeta}>Saldo: {selectedItem.saldo_display || '-'}</Text>

              <Text style={[styles.label, styles.spacingTop]}>Quantidade</Text>
              <TextInput style={styles.input} value={quantity} onChangeText={setQuantity} keyboardType="numeric" placeholder="1" placeholderTextColor={palette.muted} />

              <Text style={[styles.label, styles.spacingTop]}>Unidade de origem</Text>
              <View style={styles.modeRow}>
                {(selectedItem.product_units || []).map((unit) => (
                  <Pressable key={unit.unit_code} onPress={() => setFromUnit(unit.unit_code)} style={[styles.unitChip, fromUnit === unit.unit_code && styles.modeChipActive]}>
                    <Text style={[styles.modeText, fromUnit === unit.unit_code && styles.modeTextActive]}>{unit.unit_label || unit.unit_code}</Text>
                  </Pressable>
                ))}
              </View>

              <Pressable style={[styles.button, styles.spacingTop]} onPress={convertUnits}>
                {converting ? <ActivityIndicator color={palette.bg} /> : <Text style={styles.buttonText}>Converter</Text>}
              </Pressable>
            </View>
          ) : null}

          {conversionResult?.success ? (
            <View style={styles.card}>
              <Text style={styles.label}>Conversão</Text>
              <Text style={styles.resultValue}>{conversionResult.input?.display || '-'}</Text>
              <Text style={styles.resultMeta}>Base interna: {conversionResult.base?.display || '-'}</Text>
              <View style={styles.conversionList}>
                {(conversionResult.targets || []).map((target) => (
                  <View key={target.unit_code} style={styles.conversionCard}>
                    <Text style={styles.conversionTitle}>{target.unit_label || target.unit_code}</Text>
                    <Text style={styles.conversionValue}>{target.display}</Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
        </>
      )}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: palette.panel, borderRadius: 24, borderWidth: 1, borderColor: palette.border, padding: 18, marginBottom: 16 },
  modeRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 16 },
  modeChip: { borderRadius: 999, borderWidth: 1, borderColor: palette.border, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: palette.panel },
  modeChipActive: { backgroundColor: palette.primary, borderColor: palette.primary },
  modeText: { color: palette.text, fontWeight: '800' },
  modeTextActive: { color: palette.bg },
  operatorChip: { borderRadius: 999, borderWidth: 1, borderColor: palette.border, paddingHorizontal: 16, paddingVertical: 10, backgroundColor: palette.panelAlt },
  label: { color: palette.text, fontWeight: '800', marginBottom: 8 },
  resultLabel: { color: palette.muted, marginTop: 14, fontWeight: '700' },
  resultValue: { color: palette.primary, fontSize: 24, fontWeight: '900', marginTop: 8 },
  row: { flexDirection: 'row', gap: 12 },
  searchRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  input: { flex: 1, backgroundColor: palette.panelAlt, color: palette.text, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, borderWidth: 1, borderColor: palette.border },
  searchInput: { flex: 1 },
  button: { backgroundColor: palette.primary, borderRadius: 999, paddingVertical: 12, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center' },
  buttonText: { color: palette.bg, fontWeight: '900' },
  searchResult: { borderRadius: 18, borderWidth: 1, borderColor: palette.border, padding: 14, marginTop: 10, backgroundColor: palette.panelAlt },
  searchResultActive: { borderColor: palette.primary },
  resultTitle: { color: palette.text, fontWeight: '800' },
  resultMeta: { color: palette.muted, marginTop: 4 },
  itemTitle: { color: palette.text, fontWeight: '900', fontSize: 20, marginTop: 12 },
  spacingTop: { marginTop: 14 },
  unitChip: { borderRadius: 999, borderWidth: 1, borderColor: palette.border, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: palette.panelAlt },
  photo: { width: '100%', height: 180, borderRadius: 18, backgroundColor: palette.panelAlt },
  conversionList: { marginTop: 14, gap: 10 },
  conversionCard: { borderRadius: 18, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.panelAlt, padding: 14 },
  conversionTitle: { color: palette.text, fontWeight: '800' },
  conversionValue: { color: palette.primary, fontWeight: '900', fontSize: 18, marginTop: 6 },
});