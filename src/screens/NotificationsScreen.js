import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import {
    ActivityIndicator,
    FlatList,
    ImageBackground,
    RefreshControl,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';

import ApiService from '../services/api';
import { emitNotifyInboxChanged, subscribeNotifyInboxChanged } from '../services/notifyEvents';

function resolveVisualPayload(item) {
    const payload = item?.payload || {};
    if (payload && typeof payload === 'object' && payload.visual && typeof payload.visual === 'object') {
        return payload.visual;
    }
    return payload && typeof payload === 'object' ? payload : {};
}

function resolvePhotoUrl(item) {
    const visual = resolveVisualPayload(item);
    const visualItem = visual?.item || {};
    const media = item?.payload?.media || {};
    const rawPhotoUrl = media?.url || visualItem?.foto_url || visualItem?.foto_path || null;
    if (!rawPhotoUrl) return null;

    const configuredBaseURL = ApiService.baseURL || '';
    if (/^https?:\/\//i.test(rawPhotoUrl)) {
        try {
            const candidate = new URL(rawPhotoUrl);
            if (configuredBaseURL) {
                const base = new URL(configuredBaseURL);
                if (['127.0.0.1', 'localhost', '0.0.0.0'].includes(candidate.hostname)) {
                    candidate.protocol = base.protocol;
                    candidate.hostname = base.hostname;
                    candidate.port = base.port;
                    return candidate.toString();
                }
            }
        } catch (error) {
            return rawPhotoUrl;
        }
        return rawPhotoUrl;
    }

    if (!configuredBaseURL) return null;
    if (String(rawPhotoUrl).startsWith('/static/')) return `${configuredBaseURL}${rawPhotoUrl}`;
    if (String(rawPhotoUrl).startsWith('static/')) return `${configuredBaseURL}/${rawPhotoUrl}`;
    return `${configuredBaseURL}/static/${String(rawPhotoUrl).replace(/^\/+/, '')}`;
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
    const categoryLabel = String(item?.category || 'geral').replace(/_/g, ' ');
    const photoUrl = resolvePhotoUrl(item);
    const isUnread = item?.status === 'unread';
    const [photoFailed, setPhotoFailed] = useState(false);
    const showPhoto = Boolean(photoUrl) && !photoFailed;
    const hasVisualDetails = Boolean(
        visualItem?.descricao ||
        movement?.quantidade_display ||
        actor?.nome ||
        actor?.matricula ||
        context?.local_servico ||
        context?.observacao ||
        context?.retirado_por ||
        context?.devolvido_por
    );

    return (
        <TouchableOpacity
            activeOpacity={0.9}
            style={[styles.card, isUnread && styles.cardUnread]}
            onPress={() => isUnread && onMarkRead(item)}
        >
            <View style={styles.cardHeader}>
                <View style={styles.badgeWrap}>
                    <Text style={styles.badge}>{categoryLabel}</Text>
                    {isUnread ? <Text style={styles.unreadDot}>Novo</Text> : null}
                </View>
                <Text style={styles.dateText}>{formatDate(item?.created_at)}</Text>
            </View>

            <Text style={styles.title}>{item?.title || 'Notificação'}</Text>
            <Text style={styles.body}>{item?.body || ''}</Text>

            {showPhoto ? (
                <ImageBackground
                    source={{ uri: photoUrl }}
                    style={styles.photo}
                    imageStyle={styles.photoImage}
                    resizeMode="cover"
                    onError={() => setPhotoFailed(true)}
                >
                    <View style={styles.photoOverlay}>
                        <Text style={styles.photoBadge}>{visual?.kind_label || 'Operação'}</Text>
                        <Text style={styles.photoTitle} numberOfLines={2}>
                            {visualItem?.descricao || item?.title || 'Movimento operacional'}
                        </Text>
                        {movement?.quantidade_display ? (
                            <Text style={styles.photoMeta}>{movement.quantidade_display}</Text>
                        ) : null}
                    </View>
                </ImageBackground>
            ) : (
                <View style={styles.photoPlaceholder}>
                    <Text style={styles.photoPlaceholderIcon}>📸</Text>
                    <Text style={styles.photoPlaceholderTitle}>Visual da notificação</Text>
                    <Text style={styles.photoPlaceholderText}>
                        {photoUrl && photoFailed
                            ? 'A foto do item existe, mas não pôde ser carregada neste momento.'
                            : 'Quando o item tiver foto cadastrada, ela aparece aqui junto da retirada ou devolução.'}
                    </Text>
                </View>
            )}

            {hasVisualDetails ? (
                <View style={styles.visualPanel}>
                    <Text style={styles.visualTitle}>{visual?.kind_label || 'Operação'}</Text>
                    {visualItem?.descricao ? <Text style={styles.visualLine}>Item: {visualItem.descricao}</Text> : null}
                    {movement?.quantidade_display ? <Text style={styles.visualLine}>Quantidade: {movement.quantidade_display}</Text> : null}
                    {actor?.nome || actor?.matricula ? (
                        <Text style={styles.visualLine}>Colaborador: {actor.nome || actor.matricula}</Text>
                    ) : null}
                    {context?.retirado_por ? <Text style={styles.visualLine}>Retirado por: {context.retirado_por}</Text> : null}
                    {context?.devolvido_por ? <Text style={styles.visualLine}>Devolvido por: {context.devolvido_por}</Text> : null}
                    {context?.local_servico ? <Text style={styles.visualLine}>Local: {context.local_servico}</Text> : null}
                    {context?.observacao ? <Text style={styles.visualLine}>Obs.: {context.observacao}</Text> : null}
                </View>
            ) : null}
        </TouchableOpacity>
    );
}

export default function NotificationsScreen() {
    const [items, setItems] = useState([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState('');

    const loadInbox = useCallback(async ({ refresh = false, silent = false } = {}) => {
        if (refresh) setRefreshing(true);
        else if (!silent) setLoading(true);

        const result = await ApiService.getNotifyInbox();
        if (result?.success) {
            setItems(Array.isArray(result.items) ? result.items : []);
            setUnreadCount(Number(result.unread_count || 0));
            setError('');
        } else {
            setError(result?.message || 'Falha ao carregar notificações');
        }

        if (refresh) setRefreshing(false);
        if (!silent) setLoading(false);
    }, []);

    useFocusEffect(
        useCallback(() => {
            loadInbox();

            const intervalId = setInterval(() => {
                loadInbox({ silent: true });
            }, 12000);

            const unsubscribeNotify = subscribeNotifyInboxChanged((payload) => {
                if (payload?.reason === 'mark-read') {
                    return;
                }
                loadInbox({ silent: true });
            });

            return () => {
                clearInterval(intervalId);
                unsubscribeNotify();
            };
        }, [loadInbox])
    );

    const handleMarkRead = async (item) => {
        if (!item?.id) return;
        const result = await ApiService.markNotifyRead(item.id);
        if (result?.success) {
            setItems((current) => current.map((entry) => (entry.id === item.id ? { ...entry, status: 'read' } : entry)));
            setUnreadCount((current) => {
                const nextValue = Math.max(0, current - 1);
                emitNotifyInboxChanged({ reason: 'mark-read', messageId: item.id, unreadCount: nextValue });
                return nextValue;
            });
        }
    };

    if (loading && items.length === 0) {
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
            <View style={styles.summaryBar}>
                <Text style={styles.summaryLabel}>Inbox operacional</Text>
                <Text style={styles.summaryValue}>{unreadCount > 0 ? `${unreadCount} não lidas` : 'Tudo lido'}</Text>
            </View>
            <FlatList
                data={items}
                keyExtractor={(item) => String(item.id)}
                renderItem={({ item }) => <NotificationCard item={item} onMarkRead={handleMarkRead} />}
                contentContainerStyle={items.length === 0 ? styles.emptyList : styles.listContent}
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadInbox({ refresh: true })} />}
                ListEmptyComponent={
                    <View style={styles.stateContainer}>
                        <Text style={styles.emptyTitle}>Nenhuma notificação</Text>
                        <Text style={styles.stateText}>As mensagens operacionais do GALINT aparecem aqui.</Text>
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
    summaryBar: {
        paddingHorizontal: 16,
        paddingTop: 16,
        paddingBottom: 8,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    summaryLabel: {
        fontSize: 13,
        fontWeight: '700',
        color: '#1e3a8a',
        textTransform: 'uppercase',
    },
    summaryValue: {
        fontSize: 13,
        fontWeight: '700',
        color: '#0f172a',
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
        height: 190,
        borderRadius: 16,
        marginTop: 14,
        overflow: 'hidden',
        justifyContent: 'flex-end',
        backgroundColor: '#dbe4f3',
    },
    photoImage: {
        borderRadius: 16,
    },
    photoOverlay: {
        padding: 14,
        backgroundColor: 'rgba(15, 23, 42, 0.45)',
    },
    photoBadge: {
        alignSelf: 'flex-start',
        paddingHorizontal: 10,
        paddingVertical: 5,
        borderRadius: 999,
        backgroundColor: 'rgba(255,255,255,0.14)',
        color: '#ffffff',
        fontSize: 11,
        fontWeight: '800',
        textTransform: 'uppercase',
        marginBottom: 8,
    },
    photoTitle: {
        color: '#ffffff',
        fontSize: 17,
        fontWeight: '800',
        marginBottom: 4,
    },
    photoMeta: {
        color: 'rgba(255,255,255,0.88)',
        fontSize: 13,
        fontWeight: '600',
    },
    photoPlaceholder: {
        marginTop: 14,
        borderRadius: 16,
        minHeight: 160,
        borderWidth: 1,
        borderColor: '#dbe7ff',
        backgroundColor: '#eff5ff',
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 24,
        paddingVertical: 20,
    },
    photoPlaceholderIcon: {
        fontSize: 28,
        marginBottom: 10,
    },
    photoPlaceholderTitle: {
        fontSize: 15,
        fontWeight: '800',
        color: '#1e3a8a',
        marginBottom: 6,
        textAlign: 'center',
    },
    photoPlaceholderText: {
        fontSize: 13,
        color: '#475569',
        textAlign: 'center',
        lineHeight: 18,
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