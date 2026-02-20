import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export default function ProfileScreen() {
    const [user, setUser] = useState(null);

    useEffect(() => {
        const loadUser = async () => {
            const stored = await AsyncStorage.getItem('user');
            if (stored) {
                setUser(JSON.parse(stored));
            }
        };
        loadUser();
    }, []);

    return (
        <View style={styles.container}>
            <Text style={styles.title}>Perfil do Usuário</Text>
            <View style={styles.card}>
                <Text style={styles.label}>Nome</Text>
                <Text style={styles.value}>{user?.nome || '-'}</Text>
                <Text style={styles.label}>Matrícula</Text>
                <Text style={styles.value}>{user?.matricula || '-'}</Text>
                <Text style={styles.label}>Setor</Text>
                <Text style={styles.value}>{user?.setor || '-'}</Text>
                <Text style={styles.label}>Cargo</Text>
                <Text style={styles.value}>{user?.cargo || '-'}</Text>
            </View>
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
        borderWidth: 1,
        borderColor: '#e5e7eb',
    },
    label: {
        fontSize: 12,
        color: '#6b7280',
        marginTop: 12,
    },
    value: {
        fontSize: 16,
        color: '#111827',
        fontWeight: '600',
    },
});
