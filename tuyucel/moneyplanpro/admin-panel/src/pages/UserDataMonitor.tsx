import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Card,
    Table,
    Tag,
    Space,
    Typography,
    Select,
    Spin,
    Flex,
    Row,
    Col,
    Statistic,
    Empty,
} from 'antd';
import {
    EyeOutlined,
    PieChartOutlined,
    SwapOutlined,
    WalletOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { supabase } from '../lib/supabase';

const { Title, Text } = Typography;

interface User {
    id: string;
    email: string;
    display_name: string | null;
}

interface WatchlistItem {
    symbol: string;
    asset_name: string;
    asset_type: string;
    added_at: string;
}

interface PortfolioAsset {
    symbol: string;
    name: string;
    quantity: number;
    average_cost: number;
    currency: string;
}

interface Transaction {
    id: string;
    amount: number;
    type: string;
    description: string;
    date: string;
    currency: string;
}

export default function UserDataMonitor() {
    const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

    // Fetch users for selection
    const { data: users, isLoading: usersLoading } = useQuery({
        queryKey: ['monitor-users'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('users')
                .select('id, email, display_name')
                .limit(100);
            if (error) throw error;
            return data as User[];
        },
    });

    // Fetch User Data (Watchlist, Portfolio, Transactions)
    const { data: userData, isLoading: dataLoading } = useQuery({
        queryKey: ['user-wealth-data', selectedUserId],
        queryFn: async () => {
            if (!selectedUserId) return null;

            const [watchlist, portfolio, transactions] = await Promise.all([
                supabase.from('user_watchlists').select('*').eq('user_id', selectedUserId),
                supabase.from('user_portfolio_assets').select('*').eq('user_id', selectedUserId),
                supabase.from('user_transactions').select('*').eq('user_id', selectedUserId).order('date', { ascending: false }),
            ]);

            return {
                watchlist: (watchlist.data || []) as WatchlistItem[],
                portfolio: (portfolio.data || []) as PortfolioAsset[],
                transactions: (transactions.data || []) as Transaction[],
            };
        },
        enabled: !!selectedUserId,
    });

    const watchlistColumns: ColumnsType<WatchlistItem> = [
        { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: (s) => <Tag color="blue">{s}</Tag> },
        { title: 'Name', dataIndex: 'asset_name', key: 'name' },
        { title: 'Type', dataIndex: 'asset_type', key: 'type', render: (t) => <Tag>{t?.toUpperCase()}</Tag> },
        { title: 'Added At', dataIndex: 'added_at', key: 'added_at', render: (d) => new Date(d).toLocaleDateString() },
    ];

    const portfolioColumns: ColumnsType<PortfolioAsset> = [
        { title: 'Asset', dataIndex: 'symbol', key: 'symbol', render: (s, r) => <Space><Tag color="orange">{s}</Tag><Text>{r.name}</Text></Space> },
        { title: 'Quantity', dataIndex: 'quantity', key: 'quantity', align: 'right', render: (v) => <Text strong>{v.toLocaleString()}</Text> },
        { title: 'Avg Cost', dataIndex: 'average_cost', key: 'avg_cost', align: 'right', render: (v, r) => <Text>{v.toLocaleString()} {r.currency}</Text> },
        { title: 'Total Cost', key: 'total', align: 'right', render: (_, r) => <Text strong style={{ color: '#1890ff' }}>{(r.quantity * r.average_cost).toLocaleString()} {r.currency}</Text> },
    ];

    const transactionColumns: ColumnsType<Transaction> = [
        { title: 'Date', dataIndex: 'date', key: 'date', render: (d) => new Date(d).toLocaleDateString() },
        { title: 'Type', dataIndex: 'type', key: 'type', render: (t) => <Tag color={t === 'income' ? 'green' : 'red'}>{t.toUpperCase()}</Tag> },
        { title: 'Description', dataIndex: 'description', key: 'desc' },
        { title: 'Amount', dataIndex: 'amount', key: 'amount', align: 'right', render: (v, r) => <Text strong>{v.toLocaleString()} {r.currency}</Text> },
    ];

    let content;

    if (dataLoading) {
        content = <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;
    } else if (selectedUserId && userData) {
        content = (
            <Flex vertical gap="large">
                {/* Summary Row */}
                <Row gutter={16}>
                    <Col span={8}>
                        <Card>
                            <Statistic
                                title="Watchlist Items"
                                value={userData.watchlist.length}
                                prefix={<EyeOutlined />}
                                styles={{ content: { color: '#1890ff' } }}
                            />
                        </Card>
                    </Col>
                    <Col span={8}>
                        <Card>
                            <Statistic
                                title="Portfolio Assets"
                                value={userData.portfolio.length}
                                prefix={<PieChartOutlined />}
                                styles={{ content: { color: '#faad14' } }}
                            />
                        </Card>
                    </Col>
                    <Col span={8}>
                        <Card>
                            <Statistic
                                title="Total Transactions"
                                value={userData.transactions.length}
                                prefix={<SwapOutlined />}
                                styles={{ content: { color: '#10b981' } }}
                            />
                        </Card>
                    </Col>
                </Row>

                {/* Detailed Tables */}
                <Row gutter={[16, 16]}>
                    <Col span={24}>
                        <Card title={<Space><PieChartOutlined />Portfolio & Assets</Space>}>
                            <Table
                                columns={portfolioColumns}
                                dataSource={userData.portfolio}
                                pagination={{ pageSize: 5 }}
                                rowKey="symbol"
                            />
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card title={<Space><EyeOutlined />Watchlist Items</Space>}>
                            <Table
                                columns={watchlistColumns}
                                dataSource={userData.watchlist}
                                pagination={{ pageSize: 5 }}
                                rowKey="symbol"
                            />
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card title={<Space><SwapOutlined />Recent Transactions</Space>}>
                            <Table
                                columns={transactionColumns}
                                dataSource={userData.transactions}
                                pagination={{ pageSize: 5 }}
                                rowKey="id"
                            />
                        </Card>
                    </Col>
                </Row>
            </Flex>
        );
    } else {
        content = (
            <Card style={{ textAlign: 'center', padding: '60px' }}>
                <Empty
                    image={<WalletOutlined style={{ fontSize: '64px', color: '#bfbfbf' }} />}
                    description="Please select a user from the dropdown above to start monitoring their wealth data."
                />
            </Card>
        );
    }

    return (
        <div style={{ padding: '0px' }}>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>💰 User Wealth Monitor</Title>
                <Select
                    showSearch
                    placeholder="Select a user to monitor"
                    style={{ width: 400 }}
                    onChange={setSelectedUserId}
                    loading={usersLoading}
                    options={users?.map(u => {
                        const email = u.email;
                        const suffix = u.display_name ? ' (' + u.display_name + ')' : '';
                        return {
                            label: email + suffix,
                            value: u.id,
                        };
                    })}
                />
            </Flex>

            {content}
        </div>
    );
}
