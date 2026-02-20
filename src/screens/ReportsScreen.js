import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

export default function ReportsScreen({ navigation }) {
    return (
        <View style={styles.container}>
            <Text style={styles.title}>Relatórios</Text>

            <TouchableOpacity style={styles.card} onPress={() => navigation.navigate('ReportsDaily')}>
                <Text style={styles.cardTitle}>📅 Diário</Text>
                <Text style={styles.cardSubtitle}>Relatório do dia (PDF/XLSX)</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.card} onPress={() => navigation.navigate('ReportsMonthly')}>
                <Text style={styles.cardTitle}>🗓️ Mensal</Text>
                <Text style={styles.cardSubtitle}>Escolher mês e ano</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.card} onPress={() => navigation.navigate('ReportsHistory')}>
                <Text style={styles.cardTitle}>📚 Histórico de Relatórios</Text>
                <Text style={styles.cardSubtitle}>Acessar relatórios anteriores</Text>
            </TouchableOpacity>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        padding: 20,
        backgroundColor: '#f5f5f5',
    },
    title: {
        fontSize: 22,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 20,
    },
    card: {
        backgroundColor: '#ffffff',
        borderRadius: 12,
        padding: 16,
        marginBottom: 14,
        borderWidth: 1,
        borderColor: '#e5e7eb',
    },
    cardTitle: {
        fontSize: 16,
        fontWeight: '700',
        color: '#111827',
        marginBottom: 4,
    },
    cardSubtitle: {
        fontSize: 12,
        color: '#6b7280',
    },
});
