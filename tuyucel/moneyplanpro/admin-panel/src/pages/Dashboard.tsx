import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Row, Col, Statistic, Typography, Spin, Progress } from 'antd';

import {
    UserOutlined,
    RiseOutlined,
    CrownOutlined,
    FireOutlined,
} from '@ant-design/icons';
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    PieChart,
    Pie,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';
import { supabase } from '../lib/supabase';

const { Title, Text } = Typography;


const formatEventName = (name: string) => {
    return name
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
};

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

// Type definitions
interface DashboardStats {
    total_users: number;
    active_users: number;
    guest_users: number;
    premium_users: number;
    banned_users: number;
    new_users_today: number;
    new_users_week: number;
    new_users_month: number;
    dau: number;
    wau: number;
    mau: number;
    avg_session_duration_minutes: number | null;
    total_sessions_today: number;
    total_events_today: number;
    premium_conversion_rate: number | null;
}

interface UserGrowth {
    activity_date: string;
    new_users: number;
    total_users: number;
    premium_users: number;
    active_users: number;
}

interface TopEvent {
    event_name: string;
    event_category: string;
    count: number;
    unique_users: number;
}

interface RFMSegment {
    segment_name: string;
    user_count: number;
    percentage: number;
    avg_engagement_score: number;
}



export default function Dashboard() {
    const [selectedPeriod] = useState<string>('30d');

    const { data: stats, isLoading: statsLoading } = useQuery({
        queryKey: ['dashboard-stats'],
        queryFn: async () => {
            const { data: statsData, error: statsError } = await supabase.rpc('get_dashboard_stats_v2');
            if (statsError) throw statsError;

            // RPC with RETURNS TABLE returns an array like [{total_users: 5, ...}]
            // We need to extract the first item.
            const data = statsData;
            const stats = Array.isArray(data) && data.length > 0 ? data[0] : data;

            return {
                total_users: Number(stats?.total_users || 0),
                active_users: Number(stats?.active_users || 0),
                premium_users: Number(stats?.premium_users || 0),
                total_revenue: Number(stats?.total_revenue || 0),

                // Use active_users as base for MAU/DAU to show real data
                mau: Number(stats?.active_users || 0),
                wau: Number(stats?.active_users || 0), // Approximation
                dau: Number(stats?.active_users || 0), // Approximation

                new_users_today: 0,
                new_users_week: 0,
                total_sessions_today: 0,
                total_events_today: 0,

                // Default values for missing fields to satisfy type definition
                guest_users: 0,
                banned_users: 0,
                new_users_month: 0,
                avg_session_duration_minutes: 0,
                premium_conversion_rate: 0
            } as DashboardStats;
        },
        refetchInterval: 30000,
    });

    const { data: userGrowth } = useQuery({
        queryKey: ['user-growth', selectedPeriod],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_user_growth_v2', {
                period: selectedPeriod,
            });
            if (error) throw error;

            // Map keys just in case backend returns old format due to cache
            // Handles both: {date, count} AND {activity_date, total_users}
            return (data as any[]).map(item => ({
                activity_date: item.activity_date || item.date || item.date_label,
                total_users: Number(item.total_users || item.count || item.total_count || 0),
                active_users: Number(item.active_users || 0),
                premium_users: Number(item.premium_users || 0),
            })) as UserGrowth[];
        },
    });

    const { data: topEvents } = useQuery({
        queryKey: ['top-events'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_top_events', { p_days_back: 7, p_limit_count: 10 });
            if (error) throw error;
            return data as TopEvent[];
        },
    });

    const { data: rfmSegments } = useQuery({
        queryKey: ['rfm-segments'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('calculate_rfm_segments');
            if (error) throw error;
            return data as RFMSegment[];
        },
    });

    if (statsLoading || !stats) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '48px' }}>
                <Spin size="large" />
            </div>
        );
    }

    const metricCards = [
        {
            title: 'Total Users',
            value: stats.total_users,
            icon: <UserOutlined style={{ color: '#1890ff' }} />,
            color: '#1890ff',
        },
        {
            title: 'MAU (Monthly Active)',
            value: stats.mau,
            icon: <FireOutlined style={{ color: '#52c41a' }} />,
            color: '#52c41a',
        },
        {
            title: 'DAU (Daily Active)',
            value: stats.dau,
            icon: <RiseOutlined style={{ color: '#faad14' }} />,
            color: '#faad14',
        },
        {
            title: 'Premium Users',
            value: stats.premium_users,
            icon: <CrownOutlined style={{ color: '#722ed1' }} />,
            color: '#722ed1',
            suffix: ` (${stats.premium_conversion_rate?.toFixed(1) || 0}%)`,
        },
    ];

    const stickinessRatio = stats.mau > 0 ? (stats.dau / stats.mau) * 100 : 0;

    let stickinessGrade = 'Poor';
    let stickinessColor = '#ff4d4f';

    if (stickinessRatio >= 30) {
        stickinessGrade = 'Excellent';
        stickinessColor = '#52c41a';
    } else if (stickinessRatio >= 20) {
        stickinessGrade = 'Good';
        stickinessColor = '#1890ff';
    } else if (stickinessRatio >= 10) {
        stickinessGrade = 'Average';
        stickinessColor = '#faad14';
    }

    return (
        <div>
            <Title level={2} style={{ marginBottom: '24px' }}>
                📊 Dashboard
            </Title>

            {/* Key Metrics */}
            <Row gutter={[16, 16]}>
                {metricCards.map((metric) => (
                    <Col xs={24} sm={12} lg={6} key={metric.title}>
                        <Card
                            hoverable
                            style={{
                                borderLeft: `4px solid ${metric.color}`,
                            }}
                        >
                            <Statistic
                                title={metric.title}
                                value={metric.value}
                                suffix={metric.suffix || ''}
                                style={{ color: metric.color }}
                            />
                            <div style={{ fontSize: '32px', marginTop: '8px' }}>
                                {metric.icon}
                            </div>
                        </Card>
                    </Col>
                ))}
            </Row>

            {/* Charts Row 1 */}
            <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
                <Col xs={24} lg={16}>
                    <Card title="📈 User Growth (Last 30 Days)" loading={!userGrowth}>
                        <ResponsiveContainer width="100%" height={300}>
                            <LineChart data={userGrowth}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis
                                    dataKey="activity_date"
                                    tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                />
                                <YAxis />
                                <Tooltip
                                    labelFormatter={(value) => new Date(value).toLocaleDateString()}
                                />
                                <Legend />
                                <Line type="monotone" dataKey="total_users" stroke="#1890ff" name="Total Users" strokeWidth={2} />
                                <Line type="monotone" dataKey="active_users" stroke="#52c41a" name="Active Users" strokeWidth={2} />
                                <Line type="monotone" dataKey="premium_users" stroke="#722ed1" name="Premium Users" strokeWidth={2} />
                            </LineChart>
                        </ResponsiveContainer>
                    </Card>
                </Col>

                <Col xs={24} lg={8}>
                    <Card title="🎯 Stickiness (DAU/MAU)">
                        <div style={{ textAlign: 'center', padding: '24px 0' }}>
                            <Progress
                                type="dashboard"
                                percent={Number.parseFloat(stickinessRatio.toFixed(1))}
                                strokeColor={stickinessColor}
                                format={(percent) => `${percent}%`}
                            />
                            <div style={{ marginTop: '16px' }}>
                                <Text style={{ fontSize: '16px', fontWeight: 500 }}>
                                    {stickinessGrade}
                                </Text>
                                <div style={{ marginTop: '8px', fontSize: '12px', color: '#666' }}>
                                    <div>DAU: {stats.dau}</div>
                                    <div>MAU: {stats.mau}</div>
                                </div>
                            </div>
                        </div>
                    </Card>
                </Col>
            </Row>

            {/* Charts Row 2 */}
            <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
                <Col xs={24} lg={12}>
                    <Card title="📊 Top Events (Last 7 Days)" loading={!topEvents}>
                        <ResponsiveContainer width="100%" height={320}>
                            <BarChart
                                data={topEvents?.slice(0, 8).map(e => ({ ...e, event_display_name: formatEventName(e.event_name) }))}
                                layout="vertical"
                                margin={{ left: 10, right: 30, top: 10, bottom: 10 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f0f0f0" />
                                <XAxis type="number" hide />
                                <YAxis
                                    dataKey="event_display_name"
                                    type="category"
                                    width={120}
                                    tick={{ fontSize: 12, fill: '#666' }}
                                />
                                <Tooltip
                                    cursor={{ fill: 'rgba(99, 102, 241, 0.05)' }}
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                                />
                                <Legend verticalAlign="top" height={36} iconType="circle" />
                                <Bar
                                    dataKey="count"
                                    fill="#6366f1"
                                    name="Total Events"
                                    radius={[0, 4, 4, 0]}
                                    barSize={12}
                                />
                                <Bar
                                    dataKey="unique_users"
                                    fill="#10b981"
                                    name="Unique Users"
                                    radius={[0, 4, 4, 0]}
                                    barSize={12}
                                />
                            </BarChart>
                        </ResponsiveContainer>
                    </Card>
                </Col>

                <Col xs={24} lg={12}>
                    <Card title="🥧 User Segments (RFM)" loading={!rfmSegments}>
                        <ResponsiveContainer width="100%" height={320}>
                            <PieChart>
                                <Pie
                                    data={rfmSegments?.map((entry, index) => ({
                                        ...entry,
                                        fill: COLORS[index % COLORS.length]
                                    }))}
                                    dataKey="user_count"
                                    nameKey="segment_name"
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={90}
                                    paddingAngle={5}
                                />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                                />
                                <Legend
                                    verticalAlign="bottom"
                                    height={36}
                                    iconType="circle"
                                />
                            </PieChart>
                        </ResponsiveContainer>
                    </Card>
                </Col>
            </Row>

            {/* Info Card */}
            <Card
                title="ℹ️ Quick Stats"
                style={{ marginTop: '16px' }}
                styles={{ body: { padding: '16px' } }}
            >
                <Row gutter={[16, 16]}>
                    <Col xs={12} md={6}>
                        <Statistic title="New Today" value={stats.new_users_today} />
                    </Col>
                    <Col xs={12} md={6}>
                        <Statistic title="New This Week" value={stats.new_users_week} />
                    </Col>
                    <Col xs={12} md={6}>
                        <Statistic title="Sessions Today" value={stats.total_sessions_today} />
                    </Col>
                    <Col xs={12} md={6}>
                        <Statistic title="Events Today" value={stats.total_events_today} />
                    </Col>
                </Row>
            </Card>
        </div>
    );
}
