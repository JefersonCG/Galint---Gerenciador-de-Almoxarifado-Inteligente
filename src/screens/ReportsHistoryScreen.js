import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Alert,
  RefreshControl,
  ActivityIndicator,
  Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { MaterialIcons as Icon } from '@expo/vector-icons';

const API_BASE = 'http://10.0.0.245:5000';

export default function ReportsHistoryScreen({ navigation }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloading, setDownloading] = useState(null);

  const fetchReports = useCallback(async () => {
    try {
      const token = await AsyncStorage.getItem('jwt_token');
      if (!token) {
        Alert.alert('Erro', 'Token não encontrado. Faça login novamente.');
        navigation.navigate('Login');
        return;
      }

      const response = await fetch(`${API_BASE}/api/mobile/reports/history`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.status === 401) {
        Alert.alert('Sessão Expirada', 'Faça login novamente.');
        navigation.navigate('Login');
        return;
      }

      const data = await response.json();

      if (data.success) {
        setReports(data.reports);
      } else {
        Alert.alert('Erro', data.message || 'Erro ao carregar relatórios');
      }
    } catch (error) {
      console.error('Erro ao buscar relatórios:', error);
      Alert.alert('Erro', 'Não foi possível carregar os relatórios.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [navigation]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchReports();
  };

  const downloadReport = async (filename, format) => {
    setDownloading(filename);
    
    try {
      const token = await AsyncStorage.getItem('jwt_token');
      if (!token) {
        Alert.alert('Erro', 'Token não encontrado. Faça login novamente.');
        return;
      }

      const response = await fetch(
        `${API_BASE}/api/mobile/reports/download/${filename}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Erro ao baixar relatório');
      }

      const blob = await response.blob();
      
      // Escolher mimetype correto
      const mimeType = 
        format === 'JPEG' ? 'image/jpeg' : 
        format === 'PDF' ? 'application/pdf' : 
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      
      const fileUri = FileSystem.documentDirectory + filename;
      
      // Converter blob para base64
      const reader = new FileReader();
      reader.onloadend = async () => {
        const base64data = reader.result.split(',')[1];
        
        await FileSystem.writeAsStringAsync(fileUri, base64data, {
          encoding: FileSystem.EncodingType.Base64,
        });
        
        // Compartilhar arquivo
        const canShare = await Sharing.isAvailableAsync();
        if (canShare) {
          await Sharing.shareAsync(fileUri, {
            mimeType,
            dialogTitle: 'Compartilhar Relatório',
            UTI: format === 'JPEG' ? 'public.jpeg' : undefined,
          });
        } else {
          Alert.alert('Sucesso', `Relatório salvo em: ${fileUri}`);
        }
      };
      
      reader.readAsDataURL(blob);
      
    } catch (error) {
      console.error('Erro ao baixar:', error);
      Alert.alert('Erro', 'Não foi possível baixar o relatório.');
    } finally {
      setDownloading(null);
    }
  };

  const getFormatIcon = (format) => {
    switch (format) {
      case 'PDF':
        return 'picture-as-pdf';
      case 'XLSX':
        return 'table-chart';
      case 'JPEG':
      case 'JPG':
        return 'image';
      default:
        return 'description';
    }
  };

  const getFormatColor = (format) => {
    switch (format) {
      case 'PDF':
        return '#dc3545';
      case 'XLSX':
        return '#28a745';
      case 'JPEG':
      case 'JPG':
        return '#17a2b8';
      default:
        return '#6c757d';
    }
  };

  const getTypeLabel = (type) => {
    switch (type) {
      case 'saidas':
        return '📦 Saídas do Dia';
      case 'estoque':
        return '⚠️ Estoque Baixo';
      case 'mensal':
        return '📅 Relatório Mensal';
      default:
        return '📄 Relatório';
    }
  };

  const getScopeLabel = (scope) => {
    switch (scope) {
      case 'tools':
        return '🔧 Ferramentas';
      case 'materials':
        return '📦 Materiais';
      case 'all':
        return '🌐 Todos';
      default:
        return '';
    }
  };

  const renderReport = ({ item }) => (
    <View style={styles.reportCard}>
      <View style={styles.reportHeader}>
        <View style={styles.reportInfo}>
          <View style={styles.typeRow}>
            <Text style={styles.reportType}>{getTypeLabel(item.type)}</Text>
            {item.scope && item.scope !== 'all' && (
              <Text style={styles.scopeBadge}>{getScopeLabel(item.scope)}</Text>
            )}
          </View>
          <Text style={styles.reportDate}>📅 {item.date_formatted}</Text>
          {item.month && (
            <Text style={styles.reportMonth}>📊 Período: {item.month}</Text>
          )}
        </View>
        <View
          style={[
            styles.formatBadge,
            { backgroundColor: getFormatColor(item.format) },
          ]}
        >
          <Icon name={getFormatIcon(item.format)} size={20} color="#fff" />
          <Text style={styles.formatText}>{item.format}</Text>
        </View>
      </View>

      <View style={styles.reportFooter}>
        <Text style={styles.reportSize}>💾 {item.size_mb} MB</Text>
        <TouchableOpacity
          style={[
            styles.downloadButton,
            downloading === item.filename && styles.downloadButtonDisabled,
          ]}
          onPress={() => downloadReport(item.filename, item.format)}
          disabled={downloading === item.filename}
        >
          {downloading === item.filename ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <>
              <Icon name="download" size={20} color="#fff" />
              <Text style={styles.downloadButtonText}>Baixar</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Carregando relatórios...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backButton}
        >
          <Icon name="arrow-back" size={24} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Histórico de Relatórios</Text>
        <TouchableOpacity onPress={onRefresh} style={styles.refreshButton}>
          <Icon name="refresh" size={24} color="#fff" />
        </TouchableOpacity>
      </View>

      <View style={styles.statsContainer}>
        <View style={styles.statBox}>
          <Text style={styles.statNumber}>{reports.length}</Text>
          <Text style={styles.statLabel}>Relatórios</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNumber}>
            {reports.filter((r) => r.format === 'PDF').length}
          </Text>
          <Text style={styles.statLabel}>PDFs</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNumber}>
            {reports.filter((r) => r.format === 'XLSX').length}
          </Text>
          <Text style={styles.statLabel}>Planilhas</Text>
        </View>
        <View style={styles.statBox}>
          <Text style={styles.statNumber}>
            {reports.filter((r) => ['JPEG', 'JPG'].includes(r.format)).length}
          </Text>
          <Text style={styles.statLabel}>Imagens</Text>
        </View>
      </View>

      {reports.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Icon name="inbox" size={80} color="#ccc" />
          <Text style={styles.emptyText}>Nenhum relatório encontrado</Text>
          <Text style={styles.emptySubtext}>
            Os relatórios gerados aparecerão aqui
          </Text>
        </View>
      ) : (
        <FlatList
          data={reports}
          renderItem={renderReport}
          keyExtractor={(item) => item.filename}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
  },
  loadingText: {
    marginTop: 10,
    fontSize: 16,
    color: '#666',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#007bff',
    padding: 15,
    paddingTop: Platform.OS === 'ios' ? 50 : 15,
  },
  backButton: {
    padding: 5,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
    flex: 1,
    textAlign: 'center',
  },
  refreshButton: {
    padding: 5,
  },
  statsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    backgroundColor: '#fff',
    paddingVertical: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  statBox: {
    alignItems: 'center',
  },
  statNumber: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#007bff',
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  listContent: {
    padding: 10,
  },
  reportCard: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 15,
    marginBottom: 10,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  reportHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  reportInfo: {
    flex: 1,
  },
  typeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 5,
  },
  reportType: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
    marginRight: 8,
  },
  scopeBadge: {
    fontSize: 11,
    backgroundColor: '#e9ecef',
    color: '#495057',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  reportDate: {
    fontSize: 14,
    color: '#666',
    marginBottom: 2,
  },
  reportMonth: {
    fontSize: 13,
    color: '#007bff',
    fontStyle: 'italic',
  },
  formatBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
    gap: 5,
  },
  formatText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 12,
  },
  reportFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    paddingTop: 10,
  },
  reportSize: {
    fontSize: 13,
    color: '#666',
  },
  downloadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#28a745',
    paddingHorizontal: 15,
    paddingVertical: 8,
    borderRadius: 6,
    gap: 5,
  },
  downloadButtonDisabled: {
    backgroundColor: '#6c757d',
  },
  downloadButtonText: {
    color: '#000',
    fontWeight: 'bold',
    fontSize: 14,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#999',
    marginTop: 20,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#bbb',
    marginTop: 8,
    textAlign: 'center',
  },
});
