import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    Card,
    Table,
    Tag,
    Space,
    Typography,
    Spin,
    Flex,
    Avatar,
    Row,
    Col,
    Statistic,
    Tabs,
    Button,
    Descriptions,
    Empty,
} from 'antd';
import {
    EyeOutlined,
    PieChartOutlined,
    WalletOutlined,
    HistoryOutlined,
    LeftOutlined,
    ArrowUpOutlined,
    ArrowDownOutlined,
    UserOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { supabase } from '../lib/supabase';
import { maskEmail, maskName, maskId } from '../utils/mask';
import { useMaskStore } from '../store/maskStore';

const { Title, Text } = Typography;

export default function UserProfileIntelligence() {
    const { id } = useParams<{ id: string }>();
    const { isMasked } = useMaskStore();
    const navigate = useNavigate();

    // 1. Fetch User Profile
    const { data: user, isLoading: userLoading } = useQuery({
        queryKey: ['user-intel', id],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('users')
                .select('*')
                .eq('id', id)
                .single();
            if (error) throw error;
            return data;
        },
        enabled: !!id,
    });

    // 2. Fetch User Wealth Data
    const { data: wealth, isLoading: wealthLoading } = useQuery({
        queryKey: ['user-wealth-intel', id],
        queryFn: async () => {
            if (!id) return null;
            const [watchlist, portfolio, transactions] = await Promise.all([
                supabase.from('user_watchlists').select('*').eq('user_id', id),
                supabase.from('user_portfolio_assets').select('*').eq('user_id', id),
                supabase.from('user_transactions').select('*').eq('user_id', id).order('date', { ascending: false }),
            ]);

            return {
                watchlist: watchlist.data || [],
                portfolio: portfolio.data || [],
                transactions: transactions.data || [],
            };
        },
        enabled: !!id,
    });

    // 3. Fetch User Logs (Audit Logs)
    const { data: logs, isLoading: logsLoading } = useQuery({
        queryKey: ['user-logs-intel', id],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('audit_logs')
                .select('*')
                .eq('user_id', id)
                .order('created_at', { ascending: false })
                .limit(50);
            if (error) throw error;
            return data;
        },
        enabled: !!id,
    });

    // 4. Fetch Financial Health Insights
    const { data: financialHealth, isLoading: healthLoading } = useQuery({
        queryKey: ['financial-health', id],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('analyze_user_financial_health', { p_user_id: id });
            if (error) {
                console.error('Financial health check failed:', error);
                return [];
            }
            return data;
        },
        enabled: !!id,
    });

    if (userLoading || wealthLoading) {
        return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
    }

    if (!user) {
        return <Empty description="User not found" />;
    }

    const getInsightBorderColor = (priority: string) => {
        switch (priority) {
            case 'critical': return '#cf1322';
            case 'high': return '#faad14';
            case 'medium': return '#faad14'; // Orange
            case 'low': return '#1890ff';
            default: return '#1890ff';
        }
    };

    const getAlertColor = (priority: string) => {
        switch (priority) {
            case 'critical': return 'error';
            case 'high': return 'warning';
            case 'medium': return 'warning';
            case 'low': return 'success';
            default: return 'info';
        }
    };

    const watchlistColumns: ColumnsType<any> = [
        { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: (s) => <Tag color="blue">{s}</Tag> },
        { title: 'Name', dataIndex: 'asset_name', key: 'name' },
        { title: 'Type', dataIndex: 'asset_type', key: 'type', render: (t) => <Tag>{t?.toUpperCase()}</Tag> },
        { title: 'Added At', dataIndex: 'added_at', key: 'added_at', render: (d) => new Date(d).toLocaleDateString() },
    ];

    const portfolioColumns: ColumnsType<any> = [
        { title: 'Asset', dataIndex: 'symbol', key: 'symbol', render: (s, r) => <Space><Tag color="orange">{s}</Tag><Text>{r.name}</Text></Space> },
        { title: 'Quantity', dataIndex: 'quantity', key: 'quantity', align: 'right', render: (v) => <Text strong>{v.toLocaleString()}</Text> },
        { title: 'Avg Cost', dataIndex: 'average_cost', key: 'avg_cost', align: 'right', render: (v, r) => <Text>{v.toLocaleString()} {r.currency}</Text> },
        { title: 'Total Cost', key: 'total', align: 'right', render: (_, r) => <Text strong style={{ color: '#1890ff' }}>{(r.quantity * r.average_cost).toLocaleString()} {r.currency}</Text> },
    ];

    const transactionColumns: ColumnsType<any> = [
        { title: 'Date', dataIndex: 'date', key: 'date', render: (d) => new Date(d).toLocaleDateString() },
        { title: 'Type', dataIndex: 'type', key: 'type', render: (t) => <Tag color={t === 'income' ? 'green' : 'red'}>{t.toUpperCase()}</Tag> },
        { title: 'Description', dataIndex: 'description', key: 'desc' },
        { title: 'Amount', dataIndex: 'amount', key: 'amount', align: 'right', render: (v, r) => <Text strong>{v.toLocaleString()} {r.currency}</Text> },
    ];

    const logColumns: ColumnsType<any> = [
        { title: 'Time', dataIndex: 'created_at', key: 'time', render: (d) => new Date(d).toLocaleString('tr-TR') },
        { title: 'Action', dataIndex: 'action', key: 'action', render: (a) => <Tag color={a === 'DELETE' ? 'red' : 'blue'}>{a}</Tag> },
        { title: 'Table', dataIndex: 'table_name', key: 'table' },
        { title: 'Record ID', dataIndex: 'record_id', key: 'rid', render: (rid) => <Text type="secondary" style={{ fontSize: '11px' }}>{isMasked ? maskId(rid) : rid}</Text> },
    ];

    return (
        <div style={{ padding: '0px' }}>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Space>
                    <Button icon={<LeftOutlined />} onClick={() => navigate('/intelligence/explorer')}>Back</Button>
                    <Title level={3} style={{ margin: 0 }}>👤 User Intelligence Profile</Title>
                </Space>
                <Tag color={user.is_premium ? 'gold' : 'blue'} style={{ fontSize: '14px', padding: '4px 12px' }}>
                    {user.is_premium ? 'PREMIUM USER' : 'FREE USER'}
                </Tag>
            </Flex>

            <Row gutter={[16, 16]}>
                {/* User Info Card */}
                <Col span={24}>
                    <Card>
                        <Row gutter={24} align="middle">
                            <Col>
                                <Avatar size={64} icon={<UserOutlined />} style={{ backgroundColor: '#1890ff' }} />
                            </Col>
                            <Col flex="auto">
                                <Descriptions column={3}>
                                    <Descriptions.Item label="Email">{isMasked ? maskEmail(user.email) : user.email}</Descriptions.Item>
                                    <Descriptions.Item label="Name">{isMasked ? maskName(user.display_name) : (user.display_name || 'Anonymous')}</Descriptions.Item>
                                    <Descriptions.Item label="Joined">{new Date(user.created_at).toLocaleDateString()}</Descriptions.Item>
                                    <Descriptions.Item label="Last Seen">{user.last_seen_at ? new Date(user.last_seen_at).toLocaleString() : 'Never'}</Descriptions.Item>
                                    <Descriptions.Item label="Auth Provider">{user.auth_provider?.toUpperCase()}</Descriptions.Item>
                                    <Descriptions.Item label="User ID"><Text copyable={!isMasked} style={{ fontSize: '12px' }}>{isMasked ? maskId(user.id) : user.id}</Text></Descriptions.Item>
                                </Descriptions>
                            </Col>
                        </Row>
                    </Card>
                </Col>

                {/* Financial Health Radar - AI Insights */}
                <Col span={24}>
                    <Card title={<Space><WalletOutlined style={{ color: '#722ed1' }} /> Financial Health Radar (AI Powered)</Space>}>
                        {healthLoading ? <Spin /> : (
                            <Row gutter={[16, 16]}>
                                {(!financialHealth || financialHealth.length === 0) && (
                                    <Col span={24}>
                                        <Empty description="No financial insights available yet." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                                    </Col>
                                )}
                                {financialHealth?.map((insight: any) => (
                                    <Col span={12} key={insight.title}>
                                        <Card
                                            type="inner"
                                            size="small"
                                            className={`insight-card ${insight.priority}`}
                                            styles={{
                                                body: {
                                                    borderLeft: `4px solid ${getInsightBorderColor(insight.priority)}`
                                                }
                                            }}
                                        >
                                            <Space align="start">
                                                <div style={{ fontSize: '24px' }}>{insight.icon}</div>
                                                <div>
                                                    <Text strong style={{ fontSize: '16px' }}>{insight.title}</Text>
                                                    <div style={{ marginTop: '4px', color: '#666' }}>{insight.message}</div>
                                                    <div style={{ marginTop: '8px' }}>
                                                        <Tag color={getAlertColor(insight.priority)}>{insight.priority.toUpperCase()}</Tag>
                                                    </div>
                                                </div>
                                            </Space>
                                        </Card>
                                    </Col>
                                ))}
                            </Row>
                        )}
                    </Card>
                </Col>

                {/* Stat Cards */}
                <Col span={6}>
                    <Card>
                        <Statistic title="Portfolio Assets" value={wealth?.portfolio.length || 0} prefix={<PieChartOutlined />} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic title="Watchlist Items" value={wealth?.watchlist.length || 0} prefix={<EyeOutlined />} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic title="Total Expenses" value={wealth?.transactions.filter((t: any) => t.type === 'expense').length || 0} prefix={<ArrowDownOutlined style={{ color: '#ef4444' }} />} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic title="Total Incomes" value={wealth?.transactions.filter((t: any) => t.type === 'income').length || 0} prefix={<ArrowUpOutlined style={{ color: '#10b981' }} />} />
                    </Card>
                </Col>

                {/* Detailed Intelligence Tabs */}
                <Col span={24}>
                    <Card>
                        <Tabs
                            defaultActiveKey="portfolio"
                            items={[
                                {
                                    key: 'portfolio',
                                    label: <Space><PieChartOutlined />Financial Assets</Space>,
                                    children: (
                                        <Row gutter={[16, 16]}>
                                            <Col span={24}>
                                                <Title level={5}>Current Portfolio</Title>
                                                <Table columns={portfolioColumns} dataSource={wealth?.portfolio} pagination={{ pageSize: 5 }} size="middle" rowKey="symbol" />
                                            </Col>
                                            <Col span={24}>
                                                <Title level={5}>Watchlist Items</Title>
                                                <Table columns={watchlistColumns} dataSource={wealth?.watchlist} pagination={{ pageSize: 5 }} size="middle" rowKey="symbol" />
                                            </Col>
                                        </Row>
                                    )
                                },
                                {
                                    key: 'wallet',
                                    label: <Space><WalletOutlined />Wallet History</Space>,
                                    children: (
                                        <Table columns={transactionColumns} dataSource={wealth?.transactions} pagination={{ pageSize: 10 }} size="middle" rowKey="id" />
                                    )
                                },
                                {
                                    key: 'logs',
                                    label: <Space><HistoryOutlined />Activity Logs</Space>,
                                    children: (
                                        <Table columns={logColumns} dataSource={logs} loading={logsLoading} pagination={{ pageSize: 10 }} size="middle" rowKey="id" />
                                    )
                                }
                            ]}
                        />
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
