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
    Timeline
} from 'antd';
import {
    TeamOutlined,
    ThunderboltOutlined,
    SyncOutlined,
    UserOutlined,
    ClockCircleOutlined
} from '@ant-design/icons';
import { supabase } from '../lib/supabase';
import { formatDistanceToNow } from 'date-fns';

import { PieChart, Pie, ResponsiveContainer, Legend, Tooltip as RechartsTooltip } from 'recharts';

const { Title, Text } = Typography;

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const formatName = (name: string) => {
    return name
        .split(/[_/]/)
        .filter(Boolean)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
};
const getEventStatus = (eventName: string) => {
    const isError = eventName === 'error';
    const isNavigation = eventName.includes('view') || eventName.includes('screen');

    let tagColor = 'success';
    let dotColor = '#10b981';

    if (isError) {
        tagColor = 'error';
        dotColor = '#ef4444';
    } else if (isNavigation) {
        tagColor = 'processing';
        dotColor = '#6366f1';
    }

    return { tagColor, dotColor };
};

interface LiveStats {
    active_count: number;
    premium_count: number;
    latest_event_time: string | null;
}

interface LiveEvent {
    id: string;
    user_id: string;
    email: string;
    event_name: string;
    screen_name: string | null;
    properties: any;
    event_timestamp: string;
}

export default function LiveMonitor() {
    // 1. Live Stats (Polling every 10 seconds)
    const { data: stats } = useQuery({
        queryKey: ['live-stats'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_live_active_users');
            if (error) throw error;
            return (data?.[0] || { active_count: 0, premium_count: 0, latest_event_time: null }) as LiveStats;
        },
        refetchInterval: 10000,
    });

    // 2. Live Event Feed (Polling every 5 seconds)
    const { data: feed, isLoading: feedLoading } = useQuery({
        queryKey: ['live-feed'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_live_event_feed');
            if (error) throw error;
            return data as LiveEvent[];
        },
        refetchInterval: 5000,
    });

    return (
        <div>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>
                    ⚡ Live Monitor
                </Title>
                <Tag color="processing" icon={<SyncOutlined spin />}>
                    Auto-updating every 5s
                </Tag>
            </Flex>

            <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
                <Col xs={24} sm={8}>
                    <Card style={{ border: 'none', boxShadow: '0 4px 12px rgba(99, 102, 241, 0.08)', borderRadius: '12px' }}>
                        <Statistic
                            title={<Text type="secondary" style={{ fontSize: '13px' }}>Users Online (Last 5m)</Text>}
                            value={stats?.active_count || 0}
                            prefix={<TeamOutlined style={{ color: '#6366f1' }} />}
                            style={{ color: '#6366f1' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={8}>
                    <Card style={{ border: 'none', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.08)', borderRadius: '12px' }}>
                        <Statistic
                            title={<Text type="secondary" style={{ fontSize: '13px' }}>Premium Online</Text>}
                            value={stats?.premium_count || 0}
                            prefix={<ThunderboltOutlined style={{ color: '#10b981' }} />}
                            style={{ color: '#10b981' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={8}>
                    <Card style={{ border: 'none', boxShadow: '0 4px 12px rgba(245, 158, 11, 0.08)', borderRadius: '12px' }}>
                        <Statistic
                            title={<Text type="secondary" style={{ fontSize: '13px' }}>Last Activity</Text>}
                            value={stats?.latest_event_time ? formatDistanceToNow(new Date(stats.latest_event_time), { addSuffix: true }) : 'N/A'}
                            prefix={<ClockCircleOutlined style={{ color: '#f59e0b' }} />}
                        />
                    </Card>
                </Col>
            </Row>

            <Row gutter={[16, 16]}>
                <Col xs={24} lg={16}>
                    <Card title="Live Activity Feed" loading={feedLoading} style={{ borderRadius: '12px' }}>
                        <div style={{ maxHeight: '640px', overflowY: 'auto', padding: '8px' }}>
                            {feed && feed.length > 0 ? (
                                <Timeline
                                    mode="start"
                                    items={feed.map(event => {
                                        const { tagColor, dotColor } = getEventStatus(event.event_name);

                                        return {
                                            title: (
                                                <Text type="secondary" style={{ fontSize: '11px', fontVariantNumeric: 'tabular-nums' }}>
                                                    {new Date(event.event_timestamp).toLocaleTimeString()}
                                                </Text>
                                            ),
                                            content: (
                                                <div style={{ marginBottom: '20px' }}>
                                                    <Flex gap="small" align="center" wrap="wrap">
                                                        <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#6366f1' }} />
                                                        <Text strong style={{ fontSize: '14px' }}>{event.email}</Text>
                                                        <Tag
                                                            color={tagColor}
                                                            style={{ borderRadius: '4px', border: 'none', fontWeight: 500 }}
                                                        >
                                                            {formatName(event.event_name)}
                                                        </Tag>
                                                        {event.screen_name && (
                                                            <Tag color="default" style={{ borderRadius: '4px', opacity: 0.8 }}>
                                                                {formatName(event.screen_name)}
                                                            </Tag>
                                                        )}
                                                    </Flex>
                                                    {event.properties && Object.keys(event.properties).length > 0 && (
                                                        <div style={{ marginTop: '8px', padding: '8px 12px', backgroundColor: '#f8fafc', borderRadius: '8px', borderLeft: '3px solid #e2e8f0' }}>
                                                            <pre style={{ margin: 0, fontSize: '11px', whiteSpace: 'pre-wrap', color: '#64748b' }}>
                                                                {JSON.stringify(event.properties, null, 2)}
                                                            </pre>
                                                        </div>
                                                    )}
                                                </div>
                                            ),
                                            color: dotColor
                                        };
                                    })}
                                />
                            ) : (
                                <Empty description="Waiting for live events..." style={{ padding: '40px' }} />
                            )}
                        </div>
                    </Card>
                </Col>
                <Col xs={24} lg={8}>
                    <Card title="📍 Active Screens" style={{ borderRadius: '12px' }}>
                        <div style={{ height: 320 }}>
                            {feed && feed.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={Object.entries(
                                                feed.reduce((acc: any, curr) => {
                                                    const screen = curr.screen_name || 'Background';
                                                    acc[screen] = (acc[screen] || 0) + 1;
                                                    return acc;
                                                }, {})
                                            ).map(([name, value], index) => ({
                                                name: formatName(name),
                                                value,
                                                fill: COLORS[index % COLORS.length]
                                            }))}
                                            innerRadius={65}
                                            outerRadius={90}
                                            paddingAngle={5}
                                            dataKey="value"
                                        />
                                        <RechartsTooltip
                                            contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                                        />
                                        <Legend iconType="circle" />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <Empty description="Calculating screen distribution..." style={{ paddingTop: '80px' }} />
                            )}
                        </div>
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
