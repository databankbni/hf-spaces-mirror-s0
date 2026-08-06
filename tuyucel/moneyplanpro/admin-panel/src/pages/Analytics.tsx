import { useQuery } from '@tanstack/react-query';
import {
    Card,
    Row,
    Col,
    Table,
    Tag,
    Typography,
    Spin,
    Progress,
    Alert,
} from 'antd';
import {
    WarningOutlined,
    RiseOutlined,
    FallOutlined,
    TrophyOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    PieChart,
    Pie,
    Legend
} from 'recharts';
import { supabase } from '../lib/supabase';

const { Title, Text } = Typography;

const formatName = (name: string) => {
    return name
        .split(/[_/]/)
        .filter(Boolean)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
};

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const renderCustomizedLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }: any) => {
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * Math.PI / 180);
    const y = cy + radius * Math.sin(-midAngle * Math.PI / 180);

    if (percent < 0.05) return null; // Don't show label for small slices

    return (
        <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight="bold">
            {`${(percent * 100).toFixed(0)}%`}
        </text>
    );
};

interface AtRiskUser {
    user_id: string;
    email: string;
    display_name: string | null;
    engagement_score: number;
    days_inactive: number;
    risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
    recommended_action: string;
    is_premium: boolean;
}

interface FeatureAdoption {
    feature_name: string;
    total_users: number;
    adoption_rate: number;
    avg_uses_per_user: number;
    trend: 'up' | 'down' | 'stable' | 'new';
}

interface ChurnMetrics {
    period_days: number;
    active_at_start: number;
    churned: number;
    retained: number;
    churn_rate: number;
    retention_rate: number;
}

interface RetentionCohort {
    period_start: string;
    new_users: number;
    day_1_retention: number;
    day_7_retention: number;
    day_14_retention: number;
    day_30_retention: number;
}

interface PageEngagement {
    page_path: string;
    avg_duration_seconds: number;
    total_views: number;
    unique_visitors: number;
}

interface VisitFrequency {
    visits_per_day: number;
    user_count: number;
}

const getEngagementColor = (score: number) => {
    if (score >= 40) return '#52c41a';
    if (score >= 20) return '#faad14';
    return '#ff4d4f';
};

const getRiskLevelColor = (level: string) => {
    if (level === 'HIGH') return 'red';
    if (level === 'MEDIUM') return 'orange';
    return 'blue';
};

export default function Analytics() {
    const { data: atRiskUsers, isLoading: atRiskLoading } = useQuery({
        queryKey: ['at-risk-users'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_at_risk_users_v2');
            if (error) {
                console.warn('At-risk users error:', error);
                return [];
            }

            // Map V2 response to Interface
            return (data as any[]).map(item => ({
                user_id: item.user_id,
                email: item.email_addr,
                display_name: item.display_name,
                engagement_score: item.engagement_score,
                days_inactive: item.days_inactive,
                risk_level: item.risk_status,
                recommended_action: item.recommended_action,
                is_premium: item.is_premium
            })) as AtRiskUser[];
        },
        retry: false,
    });

    const { data: featureAdoption, isLoading: featuresLoading } = useQuery({
        queryKey: ['feature-adoption'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_feature_adoption', { p_days_back: 30 });
            if (error) {
                console.warn('Feature adoption not available:', error);
                return [];
            }
            return data as FeatureAdoption[];
        },
        retry: false,
    });

    const { data: churnMetrics } = useQuery({
        queryKey: ['churn-metrics'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('calculate_churn_rate', { p_period_days: 30 });
            if (error) {
                console.warn('Churn metrics not available:', error);
                return null;
            }
            return (Array.isArray(data) ? data[0] : data) as ChurnMetrics | null;
        },
        retry: false,
    });

    const { data: cohorts, isLoading: cohortsLoading } = useQuery({
        queryKey: ['retention-cohorts'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_retention_cohorts');
            if (error) {
                console.warn('Retention cohorts not available:', error);
                return [];
            }
            return data as RetentionCohort[];
        },
        retry: false,
    });

    const { data: pageStats } = useQuery({
        queryKey: ['page-engagement'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_page_engagement_stats', { p_days_back: 30 });
            if (error) return [];
            return data as PageEngagement[];
        }
    });

    const { data: visitFreq } = useQuery({
        queryKey: ['visit-frequency'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_daily_visit_frequency', { p_days_back: 30 });
            if (error) return [];
            return data as VisitFrequency[];
        }
    });

    const { data: demographics } = useQuery({
        queryKey: ['user-demographics'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('users')
                .select('birth_year, gender, occupation, financial_goal, risk_tolerance');

            if (error) {
                console.warn('Demographics load failed:', error);
                return [];
            }
            return data;
        }
    });

    // Process Demographics
    const genderStats = demographics?.reduce((acc: any, curr) => {
        const key = curr.gender || 'Not Specified';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
    }, {});

    const genderData = Object.keys(genderStats || {}).map((key, index) => ({
        name: key,
        value: genderStats[key],
        fill: ['Not Specified', 'Unknown'].includes(key) ? '#d9d9d9' : COLORS[index % COLORS.length]
    }));

    const riskStats = demographics?.reduce((acc: any, curr) => {
        const key = curr.risk_tolerance || 'Unknown';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
    }, {});

    const riskData = Object.keys(riskStats || {}).map((key, index) => ({
        name: key,
        value: riskStats[key],
        fill: ['Unknown', 'Not Set'].includes(key) ? '#d9d9d9' : COLORS[(index + 2) % COLORS.length]
    }));

    const goalStats = demographics?.reduce((acc: any, curr) => {
        const key = curr.financial_goal || 'Unknown';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
    }, {});

    const goalData = Object.keys(goalStats || {}).map((key, index) => ({
        name: key,
        value: goalStats[key],
        fill: ['Unknown', 'Not Set'].includes(key) ? '#d9d9d9' : COLORS[(index + 4) % COLORS.length]
    }));

    const atRiskColumns: ColumnsType<AtRiskUser> = [
        {
            title: 'User',
            key: 'user',
            render: (record: AtRiskUser) => (
                <div>
                    <div>{record.email}</div>
                    {record.display_name && (
                        <Text type="secondary" style={{ fontSize: '12px' }}>
                            {record.display_name}
                        </Text>
                    )}
                </div>
            ),
        },
        {
            title: 'Engagement Score',
            dataIndex: 'engagement_score',
            key: 'engagement_score',
            width: 180,
            render: (score: number) => (
                <Progress
                    percent={score}
                    size="small"
                    strokeColor={getEngagementColor(score)}
                />
            ),
            sorter: (a, b) => a.engagement_score - b.engagement_score,
        },
        {
            title: 'Risk Level',
            dataIndex: 'risk_level',
            key: 'risk_level',
            width: 120,
            render: (level: string) => (
                <Tag
                    icon={<WarningOutlined />}
                    color={getRiskLevelColor(level)}
                >
                    {level}
                </Tag>
            ),
            filters: [
                { text: 'High', value: 'HIGH' },
                { text: 'Medium', value: 'MEDIUM' },
                { text: 'Low', value: 'LOW' },
            ],
            onFilter: (value, record) => record.risk_level === value,
        },
        {
            title: 'Premium',
            dataIndex: 'is_premium',
            key: 'is_premium',
            width: 100,
            render: (isPremium: boolean) =>
                isPremium ? <Tag color="gold">Yes</Tag> : <Tag>No</Tag>,
        },
        {
            title: 'Days Inactive',
            dataIndex: 'days_inactive',
            key: 'days_inactive',
            width: 120,
            sorter: (a, b) => a.days_inactive - b.days_inactive,
        },
        {
            title: 'Recommended Action',
            dataIndex: 'recommended_action',
            key: 'recommended_action',
            ellipsis: true,
        },
    ];

    const featureColumns: ColumnsType<FeatureAdoption> = [
        {
            title: 'Feature',
            dataIndex: 'feature_name',
            key: 'feature_name',
            render: (text: string) => <Text strong>{formatName(text)}</Text>
        },
        {
            title: 'Users',
            dataIndex: 'total_users',
            key: 'total_users',
            width: 100,
            sorter: (a, b) => a.total_users - b.total_users,
        },
        {
            title: 'Adoption Rate',
            dataIndex: 'adoption_rate',
            key: 'adoption_rate',
            width: 150,
            render: (rate: number) => `${rate.toFixed(1)}%`,
            sorter: (a, b) => a.adoption_rate - b.adoption_rate,
        },
        {
            title: 'Avg Uses/User',
            dataIndex: 'avg_uses_per_user',
            key: 'avg_uses_per_user',
            width: 130,
            render: (avg: number) => avg.toFixed(1),
            sorter: (a, b) => a.avg_uses_per_user - b.avg_uses_per_user,
        },
        {
            title: 'Trend',
            dataIndex: 'trend',
            key: 'trend',
            width: 100,
            render: (trend: string) => {
                if (trend === 'up') return <Tag icon={<RiseOutlined />} color="green">Growing</Tag>;
                if (trend === 'down') return <Tag icon={<FallOutlined />} color="red">Declining</Tag>;
                if (trend === 'new') return <Tag icon={<TrophyOutlined />} color="blue">New</Tag>;
                return <Tag>Stable</Tag>;
            },
            filters: [
                { text: 'Growing', value: 'up' },
                { text: 'Declining', value: 'down' },
                { text: 'New', value: 'new' },
                { text: 'Stable', value: 'stable' },
            ],
            onFilter: (value, record) => record.trend === value,
        },
    ];

    const cohortColumns: ColumnsType<RetentionCohort> = [
        {
            title: 'Cohort (Week/Month)',
            dataIndex: 'period_start',
            key: 'period_start',
            render: (date: string) => new Date(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        },
        {
            title: 'New Users',
            dataIndex: 'new_users',
            key: 'new_users',
            align: 'center',
        },
        {
            title: 'Day 1',
            dataIndex: 'day_1_retention',
            key: 'day_1',
            align: 'center',
            render: (val: number = 0) => {
                return (
                    <div style={{ background: `rgba(82, 196, 26, ${val / 100})`, padding: '4px', borderRadius: '4px', color: val > 50 ? '#fff' : 'inherit' }}>
                        {val.toFixed(1)}%
                    </div>
                );
            }
        },
        {
            title: 'Day 7',
            dataIndex: 'day_7_retention',
            key: 'day_7',
            align: 'center',
            render: (val: number = 0) => {
                return (
                    <div style={{ background: `rgba(82, 196, 26, ${val / 100})`, padding: '4px', borderRadius: '4px', color: val > 50 ? '#fff' : 'inherit' }}>
                        {val.toFixed(1)}%
                    </div>
                );
            }
        },
        {
            title: 'Day 14',
            dataIndex: 'day_14_retention',
            key: 'day_14',
            align: 'center',
            render: (val: number = 0) => {
                return (
                    <div style={{ background: `rgba(82, 196, 26, ${val / 100})`, padding: '4px', borderRadius: '4px', color: val > 50 ? '#fff' : 'inherit' }}>
                        {val.toFixed(1)}%
                    </div>
                );
            }
        },
        {
            title: 'Day 30',
            dataIndex: 'day_30_retention',
            key: 'day_30',
            align: 'center',
            render: (val: number = 0) => {
                return (
                    <div style={{ background: `rgba(82, 196, 26, ${val / 100})`, padding: '4px', borderRadius: '4px', color: val > 50 ? '#fff' : 'inherit' }}>
                        {val.toFixed(1)}%
                    </div>
                );
            }
        },
    ];

    return (
        <div>
            <Title level={2} style={{ marginBottom: '24px' }}>
                📈 Analytics
            </Title>

            {/* Churn Metrics */}
            {typeof churnMetrics?.churn_rate === 'number' && (
                <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
                    <Col xs={24} sm={12} lg={6}>
                        <Card>
                            <div style={{ textAlign: 'center' }}>
                                <Text type="secondary">Churn Rate (30d)</Text>
                                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#ff4d4f', marginTop: '8px' }}>
                                    {churnMetrics.churn_rate?.toFixed(1) || 0}%
                                </div>
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    {churnMetrics.churned || 0} / {churnMetrics.active_at_start || 0} users
                                </Text>
                            </div>
                        </Card>
                    </Col>
                    <Col xs={24} sm={12} lg={6}>
                        <Card>
                            <div style={{ textAlign: 'center' }}>
                                <Text type="secondary">Retention Rate</Text>
                                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#52c41a', marginTop: '8px' }}>
                                    {churnMetrics.retention_rate?.toFixed(1) || 0}%
                                </div>
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    {churnMetrics.retained || 0} users retained
                                </Text>
                            </div>
                        </Card>
                    </Col>
                    <Col xs={24} sm={12} lg={6}>
                        <Card>
                            <div style={{ textAlign: 'center' }}>
                                <Text type="secondary">Active at Start</Text>
                                <div style={{ fontSize: '32px', fontWeight: 'bold', marginTop: '8px' }}>
                                    {churnMetrics.active_at_start || 0}
                                </div>
                            </div>
                        </Card>
                    </Col>
                    <Col xs={24} sm={12} lg={6}>
                        <Card>
                            <div style={{ textAlign: 'center' }}>
                                <Text type="secondary">Churned Users</Text>
                                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#ff4d4f', marginTop: '8px' }}>
                                    {churnMetrics.churned || 0}
                                </div>
                            </div>
                        </Card>
                    </Col>
                </Row>
            )}

            {/* Demographics */}
            <Title level={4}>👥 User Demographics</Title>
            <Row gutter={[16, 16]} style={{ marginBottom: '32px' }}>
                <Col xs={24} md={8}>
                    <Card title="Gender Distribution" size="small">
                        <div style={{ height: 250 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={genderData}
                                        cx="50%"
                                        cy="50%"
                                        labelLine={false}
                                        label={renderCustomizedLabel}
                                        innerRadius={50}
                                        outerRadius={90}
                                        paddingAngle={2}
                                        dataKey="value"
                                    />
                                    <Tooltip contentStyle={{ borderRadius: '8px', border: 'none' }} />
                                    <Legend verticalAlign="bottom" height={36} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </Card>
                </Col>
                <Col xs={24} md={8}>
                    <Card title="Risk Tolerance" size="small">
                        <div style={{ height: 250 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={riskData}
                                        cx="50%"
                                        cy="50%"
                                        labelLine={false}
                                        label={renderCustomizedLabel}
                                        innerRadius={50}
                                        outerRadius={90}
                                        paddingAngle={2}
                                        dataKey="value"
                                    />
                                    <Tooltip contentStyle={{ borderRadius: '8px', border: 'none' }} />
                                    <Legend verticalAlign="bottom" height={36} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </Card>
                </Col>
                <Col xs={24} md={8}>
                    <Card title="Financial Goals" size="small">
                        <div style={{ height: 250 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={goalData}
                                        cx="50%"
                                        cy="50%"
                                        labelLine={false}
                                        label={renderCustomizedLabel}
                                        innerRadius={50}
                                        outerRadius={90}
                                        paddingAngle={2}
                                        dataKey="value"
                                    />
                                    <Tooltip contentStyle={{ borderRadius: '8px', border: 'none' }} />
                                    <Legend verticalAlign="bottom" height={36} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </Card>
                </Col>
            </Row>

            {/* Engagement Charts Section */}
            <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
                <Col xs={24} lg={16}>
                    <Card title="⏱️ Average Time Spent per Page (Seconds)">
                        <div style={{ height: 320 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={pageStats?.map(p => ({ ...p, display_path: formatName(p.page_path) }))}
                                    layout="vertical"
                                    margin={{ left: 10, right: 40, top: 10, bottom: 10 }}
                                >
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f0f0f0" />
                                    <XAxis type="number" hide />
                                    <YAxis
                                        dataKey="display_path"
                                        type="category"
                                        width={140}
                                        tick={{ fontSize: 12, fill: '#666' }}
                                    />
                                    <Tooltip
                                        cursor={{ fill: 'rgba(99, 102, 241, 0.05)' }}
                                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                                        formatter={(value: number | undefined) => {
                                            if (value === undefined) return ['0s', 'Avg Duration'];
                                            return [`${value.toFixed(1)}s`, 'Avg Duration'];
                                        }}
                                    />
                                    <Bar
                                        dataKey="avg_duration_seconds"
                                        fill="#6366f1"
                                        radius={[0, 4, 4, 0]}
                                        barSize={15}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </Card>
                </Col>
                <Col xs={24} lg={8}>
                    <Card title="🔄 Daily Session Frequency">
                        <div style={{ height: 320 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={visitFreq?.slice(0, 5).map((f, index) => ({
                                            name: `${f.visits_per_day} visits`,
                                            value: Number(f.user_count),
                                            id: f.visits_per_day,
                                            fill: COLORS[index % COLORS.length]
                                        }))}
                                        innerRadius={60}
                                        outerRadius={90}
                                        paddingAngle={5}
                                        dataKey="value"
                                    />
                                    <Tooltip
                                        contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                                    />
                                    <Legend iconType="circle" verticalAlign="bottom" height={36} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </Card>
                </Col>
            </Row>

            {/* At-Risk Users */}
            <Card
                title={
                    <span>
                        ⚠️ At-Risk Users{' '}
                        <Tag color="red">{atRiskUsers?.length || 0}</Tag>
                    </span>
                }
                style={{ marginBottom: '24px' }}
            >
                {atRiskUsers && atRiskUsers.length > 0 ? (
                    <>
                        <Alert
                            description={
                                <div>
                                    <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Users with low engagement scores who may churn soon</div>
                                    <div>Take immediate action for HIGH risk users, especially premium ones.</div>
                                </div>
                            }
                            type="warning"
                            showIcon
                            style={{ marginBottom: '16px' }}
                        />
                        <Table
                            columns={atRiskColumns}
                            dataSource={atRiskUsers}
                            loading={atRiskLoading}
                            rowKey="user_id"
                            pagination={{
                                pageSize: 10,
                                showSizeChanger: true,
                            }}
                        />
                    </>
                ) : (
                    <Alert
                        description={
                            <div>
                                <div style={{ fontWeight: 'bold' }}>No at-risk users found</div>
                                <div>All users have healthy engagement scores!</div>
                            </div>
                        }
                        type="success"
                        showIcon
                    />
                )}
            </Card>

            {/* Feature Adoption */}
            <Card title="🎯 Feature Adoption (Last 30 Days)" style={{ marginBottom: '24px' }}>
                {featureAdoption && featureAdoption.length > 0 ? (
                    <Table
                        columns={featureColumns}
                        dataSource={featureAdoption}
                        loading={featuresLoading}
                        rowKey={(record) => record.feature_name || Math.random().toString()}
                        pagination={{
                            pageSize: 15,
                            showSizeChanger: true,
                        }}
                    />
                ) : (
                    <Spin />
                )}
            </Card>

            {/* Retention Cohorts */}
            <Card title="📊 Retention Cohorts (Registration Time vs Return Rate)">
                <Table
                    columns={cohortColumns}
                    dataSource={cohorts || []}
                    loading={cohortsLoading}
                    rowKey={(record) => record.period_start || Math.random().toString()}
                    pagination={false}
                    bordered
                />
            </Card>
        </div>
    );
}
