import React, { useEffect, useState } from 'react';
import {
    ActivityIndicator,
    FlatList,
    Image,
    RefreshControl,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';

import ApiService from '../services/api';

function resolveVisualPayload(item) {
    const payload = item?.payload || {};
    if (payload && typeof payload === 'object' && payload.visual && typeof payload.visual === 'object') {
        return payload.visual;
    }
    return payload && typeof payload === 'object' ? payload : {};
}

function formatDate(value) {
    if (!value) return '-';
    try {
        return new Date(value).toLocaleString('pt-BR');
    } catch (error) {
        return value;
    }
}

function NotificationCard({ item, onMarkRead }) {
    const visual = resolveVisualPayload(item);
    const visualItem = visual?.item || {};
    const movement = visual?.movement || {};
    const actor = visual?.actor || {};
    const context = visual?.context || {};
    const photoUrl = visualItem?.foto_url || null;
    const isUnread = item?.status === 'unread';

    return (
        <TouchableOpacity
            activeOpacity={0.9}
            style={[styles.card, isUnread && styles.cardUnread]}
            onPress={() => isUnread && onMarkRead(item)}
        >
            <View style={styles.cardHeader}>
                <View style={styles.badgeWrap}>
                    <Text style={styles.badge}>{item?.category || 'geral'}</Text>
                    {isUnread ? <Text style={styles.unreadDot}>Novo</Text> : null}
                </View>
                <Text style={styles.dateText}>{formatDate(item?.created_at)}</Text>
            </View>

            <Text style={styles.title}>{item?.title || 'Notificação'}</Text>
            <Text style={styles.body}>{item?.body || ''}</Text>

            {photoUrl ? (
                <Image source={{ uri: photoUrl }} style={styles.photo} resizeMode="cover" />
            ) : null}

            {(visualItem?.descricao || movement?.quantidade_display || actor?.nome || context?.local_servico) ? (
                <View style={styles.visualPanel}>
                    <Text style={styles.visualTitle}>{visual?.kind_label || 'Operação'}</Text>
                    {visualItem?.descricao ? <Text style={styles.visualLine}>Item: {visualItem.descricao}</Text> : null}
                    {movement?.quantidade_display ? <Text style={styles.visualLine}>Quantidade: {movement.quantidade_display}</Text> : null}
                    {actor?.nome || actor?.matricula ? (
                        <Text style={styles.visualLine}>Colaborador: {actor.nome || actor.matricula}</Text>
                    ) : null}
                    {context?.local_servico ? <Text style={styles.visualLine}>Local: {context.local_servico}</Text> : null}
                    {context?.observacao ? <Text style={styles.visualLine}>Obs.: {context.observacao}</Text> : null}
                </View>
            ) : null}
        </TouchableOpacity>
    );
}

export default function NotificationsScreen() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState('');

    const loadInbox = async (refresh = false) => {
        if (refresh) setRefreshing(true);
        else setLoading(true);

        const result = await ApiService.getNotifyInbox();
        if (result?.success) {
            setItems(Array.isArray(result.items) ? result.items : []);
            setError('');
        } else {
            setError(result?.message || 'Falha ao carregar notificações');
        }

        setLoading(false);
        setRefreshing(false);
    };

    useEffect(() => {
        loadInbox();
    }, []);

    const handleMarkRead = async (item) => {
        if (!item?.id) return;
        const result = await ApiService.markNotifyRead(item.id);
        if (result?.success) {
            setItems((current) => current.map((entry) => (entry.id === item.id ? { ...entry, status: 'read' } : entry)));
        }
    };

    if (loading) {
        return (
            <View style={styles.stateContainer}>
                <ActivityIndicator size="large" color="#2563eb" />
                <Text style={styles.stateText}>Carregando notificações...</Text>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            {error ? <Text style={styles.errorText}>{error}</Text> : null}
            <FlatList
                data={items}
                keyExtractor={(item) => String(item.id)}
                renderItem={({ item }) => <NotificationCard item={item} onMarkRead={handleMarkRead} />}
                contentContainerStyle={items.length === 0 ? styles.emptyList : styles.listContent}
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadInbox(true)} />}
                ListEmptyComponent={
                    <View style={styles.stateContainer}>
                        <Text style={styles.emptyTitle}>Nenhuma notificação</Text>
                        <Text style={styles.stateText}>As mensagens do GalintNotify aparecerão aqui.</Text>
                    </View>
                }
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#eef4ff',
    },
    listContent: {
        padding: 16,
        gap: 12,
    },
    emptyList: {
        flexGrow: 1,
        justifyContent: 'center',
        padding: 24,
    },
    stateContainer: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
    },
    stateText: {
        marginTop: 12,
        fontSize: 14,
        color: '#64748b',
        textAlign: 'center',
    },
    emptyTitle: {
        fontSize: 20,
        fontWeight: '700',
        color: '#0f172a',
    },
    errorText: {
        margin: 16,
        padding: 12,
        borderRadius: 12,
        backgroundColor: '#fee2e2',
        color: '#991b1b',
        fontWeight: '600',
    },
    card: {
        backgroundColor: '#ffffff',
        borderRadius: 18,
        padding: 16,
        borderWidth: 1,
        borderColor: '#dbe7ff',
        shadowColor: '#0f172a',
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.06,
        shadowRadius: 18,
        elevation: 4,
    },
    cardUnread: {
        borderColor: '#2563eb',
        backgroundColor: '#f8fbff',
    },
    cardHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 10,
        gap: 8,
    },
    badgeWrap: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
    },
    badge: {
        paddingHorizontal: 10,
        paddingVertical: 5,
        borderRadius: 999,
        backgroundColor: '#dbeafe',
        color: '#1d4ed8',
        fontSize: 12,
        fontWeight: '700',
        textTransform: 'uppercase',
    },
    unreadDot: {
        color: '#2563eb',
        fontWeight: '800',
        fontSize: 12,
    },
    dateText: {
        color: '#64748b',
        fontSize: 12,
    },
    title: {
        fontSize: 18,
        fontWeight: '800',
        color: '#0f172a',
        marginBottom: 6,
    },
    body: {
        fontSize: 14,
        color: '#334155',
        lineHeight: 20,
    },
    photo: {
        width: '100%',
        height: 180,
        borderRadius: 14,
        marginTop: 14,
        backgroundColor: '#e2e8f0',
    },
    visualPanel: {
        marginTop: 14,
        borderRadius: 14,
        padding: 12,
        backgroundColor: '#f8fafc',
        borderWidth: 1,
        borderColor: '#e2e8f0',
    },
    visualTitle: {
        fontSize: 13,
        fontWeight: '800',
        color: '#1d4ed8',
        marginBottom: 8,
        textTransform: 'uppercase',
    },
    visualLine: {
        fontSize: 13,
        color: '#334155',
        marginBottom: 4,
    },
});