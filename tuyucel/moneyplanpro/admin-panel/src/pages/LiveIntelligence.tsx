import { useQuery } from '@tanstack/react-query';
import {
    Card,
    Row,
    Col,
    Statistic,
    Avatar,
    Typography,
    Tag,
    Empty,
    Flex,
    Timeline,
    Spin,
} from 'antd';
import {
    TeamOutlined,
    ThunderboltOutlined,
    SyncOutlined,
    UserOutlined,
    HistoryOutlined,
} from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { formatDistanceToNow } from 'date-fns';

const { Title, Text } = Typography;

interface IntelligenceEvent {
    id: string;
    user_email: string;
    activity_type: string;
    activity_name: string;
    metadata: any;
    created_at: string;
}

export default function LiveIntelligence() {
    const [events, setEvents] = useState<IntelligenceEvent[]>([]);

    // 1. Initial Load (Snapshot)
    const { isLoading } = useQuery({
        queryKey: ['live-snapshot'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_intelligence_live_feed', { p_limit: 50 });
            if (error) throw error;
            setEvents(data || []);
            return data;
        }
    });

    // 2. Realtime Subscription
    useEffect(() => {
        const channel = supabase
            .channel('intelligence-hub')
            .on(
                'postgres_changes',
                { event: 'INSERT', schema: 'public', table: 'audit_logs' },
                async (payload) => {
                    // Fetch user email for the new log
                    const { data: userData } = await supabase
                        .from('users')
                        .select('email')
                        .eq('id', payload.new.user_id)
                        .single();

                    const newEvent: IntelligenceEvent = {
                        id: payload.new.id,
                        user_email: userData?.email || 'System',
                        activity_type: 'AUDIT',
                        activity_name: payload.new.action + ' on ' + payload.new.table_name,
                        metadata: payload.new.new_data || {},
                        created_at: payload.new.created_at
                    };

                    setEvents(prev => [newEvent, ...prev.slice(0, 49)]);
                }
            )
            .subscribe();

        return () => {
            supabase.removeChannel(channel);
        };
    }, []);

    const onlineCount = events.filter(e =>
        new Date(e.created_at).getTime() > Date.now() - 5 * 60 * 1000
    ).length;

    return (
        <div style={{ padding: '0px' }}>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>⚡ Live Intelligence</Title>
                <Tag color="success" icon={<SyncOutlined spin />}>Realtime Connected</Tag>
            </Flex>

            <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
                <Col span={8}>
                    <Card style={{ borderRadius: '12px' }}>
                        <Statistic
                            title="Recent Active Users"
                            value={onlineCount}
                            prefix={<TeamOutlined style={{ color: '#6366f1' }} />}
                        />
                    </Card>
                </Col>
                <Col span={8}>
                    <Card style={{ borderRadius: '12px' }}>
                        <Statistic
                            title="Instant Traffic"
                            value={events.length}
                            prefix={<ThunderboltOutlined style={{ color: '#10b981' }} />}
                        />
                    </Card>
                </Col>
                <Col span={8}>
                    <Card style={{ borderRadius: '12px' }}>
                        <Statistic
                            title="Deep Log Stream"
                            value="ACTIVE"
                            prefix={<HistoryOutlined style={{ color: '#8b5cf6' }} />}
                            styles={{ content: { color: '#8b5cf6', fontWeight: 'bold' } }}
                        />
                    </Card>
                </Col>
            </Row>

            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Card title="Database Activity Stream" style={{ borderRadius: '12px' }}>
                        {isLoading && (
                            <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>
                        )}
                        {!isLoading && events.length > 0 && (
                            <div style={{ maxHeight: '600px', overflowY: 'auto', padding: '8px' }}>
                                <Timeline
                                    mode="left"
                                    items={events.map(event => ({
                                        color: event.activity_name.includes('DELETE') ? 'red' : 'blue',
                                        label: (
                                            <Text type="secondary" style={{ fontSize: '11px' }}>
                                                {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                                            </Text>
                                        ),
                                        children: renderEventContent(event)
                                    }))}
                                />
                            </div>
                        )}
                        {!isLoading && events.length === 0 && (
                            <Empty description="Waiting for signals..." />
                        )}
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
const renderEventContent = (event: IntelligenceEvent) => (
    <div style={{ marginBottom: '12px' }}>
        <Flex gap="small" align="center">
            <Avatar size="small" icon={<UserOutlined />} />
            <Text strong>{event.user_email}</Text>
            <Tag color={event.activity_name.includes('INSERT') ? 'green' : 'cyan'}>
                {event.activity_name}
            </Tag>
        </Flex>
        {event.metadata && Object.keys(event.metadata).length > 0 && (
            <div style={{ marginTop: '4px', padding: '8px', backgroundColor: '#f8fafc', borderRadius: '4px', fontSize: '11px' }}>
                <pre style={{ margin: 0, color: '#64748b' }}>
                    {JSON.stringify(event.metadata, null, 2).slice(0, 200)}...
                </pre>
            </div>
        )}
    </div>
);
