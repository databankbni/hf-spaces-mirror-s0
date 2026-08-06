import { useQuery } from '@tanstack/react-query';
import {
    Card,
    Row,
    Col,
    Typography,
    Table,
    Tag,
    Space,
    Flex,
    Spin,
    Empty,
    Alert,
    Statistic,
} from 'antd';
import {
    PieChart,
    Pie,
    Cell,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip as RechartTooltip,
    Legend,
    ResponsiveContainer,
    Treemap,
} from 'recharts';
import {
    RocketOutlined,
    HeatMapOutlined,
    UsergroupAddOutlined,
    WarningOutlined,
    RiseOutlined,
    FallOutlined,
} from '@ant-design/icons';
import { supabase } from '../lib/supabase';

const { Title, Paragraph } = Typography;

const COLORS = ['#8889DD', '#9597E4', '#8DC77B', '#A5D297', '#E2CF45', '#F8C12D'];

const CustomizedContent = (props: any) => {
    const { root, depth, x, y, width, height, index, colors, name } = props;

    // Safety check: Treemap might render before data is fully structured
    if (!root || !root.children) return null;

    return (
        <g>
            <rect
                x={x}
                y={y}
                width={width}
                height={height}
                style={{
                    fill: depth < 2 ? colors[Math.floor(index / (root.children.length || 1) * 6)] : 'none',
                    stroke: '#fff',
                    strokeWidth: 2 / (depth + 1e-10),
                    strokeOpacity: 1 / (depth + 1e-10),
                }}
            />
            {depth === 1 ? (
                <text x={x + width / 2} y={y + height / 2 + 7} textAnchor="middle" fill="#fff" fontSize={14}>
                    {name}
                </text>
            ) : null}
            {depth === 1 ? (
                <text x={x + 4} y={y + 18} fill="#fff" fontSize={14} fillOpacity={0.9}>
                    {index + 1}
                </text>
            ) : null}
        </g>
    );
};

export default function StrategicDecisions() {
    // 1. Data Fetching
    const { data: cohortData, isLoading: cohortLoading } = useQuery({
        queryKey: ['cohort-retention'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_cohort_retention');
            if (error) throw error;
            return data;
        }
    });


    const { data: segmentData, isLoading: segmentLoading } = useQuery({
        queryKey: ['user-segmentation'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_user_segmentation');
            if (error) throw error;
            return data;
        }
    });

    const { data: anomalyData, isLoading: anomalyLoading } = useQuery({
        queryKey: ['anomaly-detection'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_anomaly_detection');
            if (error) throw error;
            return data;
        }
    });

    const { data: funnelData, isLoading: funnelLoading } = useQuery({
        queryKey: ['funnel-analysis'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_funnel_analysis');
            if (error) throw error;
            return data;
        }
    });

    const { data: pageStats, isLoading: pageLoading } = useQuery({
        queryKey: ['page-engagement-stats'],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('get_page_engagement_stats', { p_days_back: 30 });
            if (error) throw error;
            return data;
        }
    });

    if (cohortLoading || segmentLoading || anomalyLoading || funnelLoading || pageLoading) {
        return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
    }

    return (
        <div style={{ padding: '0px' }}>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>🧠 Strategic Decision Panel</Title>
                <Tag color="purple" icon={<RocketOutlined />}>AI Supported Insights</Tag>
            </Flex>

            <Alert
                message="Decision Maker Mode"
                description="Bu sayfa sadece veri göstermez; düşük tutunma (retention) veya şüpheli işlemlerde aksiyon almanız için sinyaller üretir."
                type="info"
                showIcon
                style={{ marginBottom: '24px' }}
            />

            <Row gutter={[16, 16]}>
                {/* 1. Cohort Analysis Matrix */}
                <Col span={24}>
                    <Card title={<Space><HeatMapOutlined /> Cohort Retention Analysis (Weekly)</Space>} style={{ borderRadius: '12px' }}>
                        <Paragraph type="secondary">Yeni kullanıcıların haftalık bazda uygulamada kalma oranları. %30 ve altı riskli kabul edilir.</Paragraph>
                        <Table
                            dataSource={cohortData || []}
                            pagination={false}
                            size="small"
                            rowKey={(record: any, index: any) => `${record.cohort_week}-${index}`}
                            columns={[
                                { title: 'Cohort (Week)', dataIndex: 'cohort_week', key: 'cohort', render: (val: string) => new Date(val).toLocaleDateString() },
                                { title: 'Size', dataIndex: 'cohort_size', key: 'size' },
                                { title: 'W0', render: (_, r: any) => r.week_number === 0 ? <Tag color="blue">{r.retention_rate}%</Tag> : null },
                                {
                                    title: 'W1-W12 Retention',
                                    key: 'retention',
                                    render: (_, r: any) => (
                                        <Tag color={r.retention_rate < 30 ? 'volcano' : 'green'}>
                                            {r.week_number > 0 ? `W${r.week_number}: ${r.retention_rate}%` : '-'}
                                        </Tag>
                                    )
                                }
                            ]}
                        />
                    </Card>
                </Col>

                {/* 2.1 Page Engagement Heatmap (Treemap) */}
                <Col span={24} md={12}>
                    <Card title={<Space><HeatMapOutlined /> Page Heatmap (Category Breakdown)</Space>} style={{ height: '400px', borderRadius: '12px' }}>
                        <Paragraph type="secondary" style={{ fontSize: '12px', marginBottom: '8px' }}>
                            Kategori bazlı kullanıcı yoğunluk haritası. Kutu büyüklüğü = Ziyaret Sayısı, Renk = Kategori.
                        </Paragraph>
                        <ResponsiveContainer width="100%" height={280}>
                            <Treemap
                                data={pageStats || []}
                                dataKey="views"
                                nameKey="page_path"
                                stroke="#fff"
                                fill="#8884d8"
                                content={<CustomizedContent colors={COLORS} />}
                            >
                                <RechartTooltip
                                    content={({ active, payload }) => {
                                        if (active && payload && payload.length) {
                                            const data = payload[0].payload;
                                            return (
                                                <div style={{ background: '#fff', padding: '10px', border: '1px solid #ccc' }}>
                                                    <p style={{ fontWeight: 'bold' }}>{data.category}</p>
                                                    <p>{data.page_path}</p>
                                                    <p>Views: {data.views}</p>
                                                    <p>Avg Duration: {data.avg_duration_seconds}s</p>
                                                </div>
                                            );
                                        }
                                        return null;
                                    }}
                                />
                            </Treemap>
                        </ResponsiveContainer>
                    </Card>
                </Col>

                {/* 2.5 Drop-off Funnel (New) */}
                <Col span={24}>
                    <Card title={<Space><WarningOutlined style={{ color: '#faad14' }} /> Conversion Funnel (Drop-off Analysis)</Space>} style={{ borderRadius: '12px' }}>
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={funnelData} layout="vertical" margin={{ left: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
                                <XAxis type="number" />
                                <YAxis type="category" dataKey="stage" width={120} />
                                <RechartTooltip
                                    formatter={(val: any, name: any) => {
                                        if (name === 'Users') return [val, 'Users'];
                                        return [val, name];
                                    }}
                                    content={({ active, payload, label }) => {
                                        if (active && payload && payload.length) {
                                            const data = payload[0].payload;
                                            return (
                                                <div style={{ background: '#fff', padding: '10px', border: '1px solid #ccc' }}>
                                                    <p style={{ fontWeight: 'bold' }}>{label}</p>
                                                    <p>Users: {data.count}</p>
                                                    {data.conversion_rate && <p style={{ color: data.conversion_rate > 50 ? 'green' : 'red' }}>Conversion: {data.conversion_rate}%</p>}
                                                </div>
                                            );
                                        }
                                        return null;
                                    }}
                                />
                                <Bar dataKey="count" fill="#8884d8" barSize={30}>
                                    {
                                        (funnelData || []).map((_: any, index: number) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))
                                    }
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                        <div style={{ display: 'flex', justifyContent: 'space-around', marginTop: '10px' }}>
                            {funnelData?.map((step: any, index: number) => (
                                index > 0 && (
                                    <Statistic
                                        key={step.step}
                                        title={`${step.stage} Rate`}
                                        value={step.conversion_rate}
                                        suffix="%"
                                        prefix={step.conversion_rate < 40 ? <FallOutlined /> : <RiseOutlined />}
                                        styles={{ content: { color: step.conversion_rate < 40 ? '#cf1322' : '#3f8600' } }}
                                    />
                                )
                            ))}
                        </div>
                    </Card>
                </Col>

                {/* 3. User Segmentation */}
                <Col span={12}>
                    <Card title={<Space><UsergroupAddOutlined /> User Segmentation (30 Days)</Space>} style={{ height: '400px', borderRadius: '12px' }}>
                        <ResponsiveContainer width="100%" height={300}>
                            <PieChart>
                                <Pie
                                    data={segmentData || []}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="user_count"
                                    nameKey="segment"
                                >
                                    {(segmentData || []).map((_entry: any) => (
                                        <Cell key={_entry.segment} fill={COLORS[(segmentData || []).indexOf(_entry) % COLORS.length]} />
                                    ))}
                                </Pie>
                                <RechartTooltip />
                                <Legend />
                            </PieChart>
                        </ResponsiveContainer>
                    </Card>
                </Col>

                {/* 4. Anomaly & Fraud Signals */}
                <Col span={24}>
                    <Card title={<Space><WarningOutlined style={{ color: '#ef4444' }} /> Anomaly & Fraud Signals</Space>} style={{ borderRadius: '12px' }}>
                        {!anomalyData || anomalyData.length === 0 ? (
                            <Empty description="No suspicious activity detected." />
                        ) : (
                            <Table
                                dataSource={anomalyData}
                                pagination={false}
                                columns={[
                                    { title: 'Type', dataIndex: 'anomaly_type', key: 'type', render: (t) => <Tag color="error">{t}</Tag> },
                                    { title: 'User', dataIndex: 'user_email', key: 'user' },
                                    { title: 'Details', dataIndex: 'ip_count', key: 'details', render: (v, r: any) => v ? `${v} distinct IPs` : `${r.action_count} actions/min` },
                                    { title: 'Severity', dataIndex: 'severity', key: 'severity', render: (s) => <Tag color={s === 'Critical' ? 'magenta' : 'orange'}>{s}</Tag> },
                                    { title: 'Latest', dataIndex: 'latest_event', key: 'latest', render: (d) => new Date(d).toLocaleString() },
                                ]}
                            />
                        )}
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
