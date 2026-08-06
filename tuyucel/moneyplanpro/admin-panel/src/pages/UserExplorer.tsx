import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Card,
    Table,
    Input,
    Tag,
    Space,
    Button,
    Typography,
    Select,
    Flex,
    Avatar,
    Statistic,
    Row,
    Col,
    Tooltip,
} from 'antd';
import {
    SearchOutlined,
    UserOutlined,
    CrownOutlined,
    FilterOutlined,
    ReloadOutlined,
    RocketOutlined,
    StopOutlined,
    GlobalOutlined,
    LineChartOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { maskEmail, maskName } from '../utils/mask';
import { useMaskStore } from '../store/maskStore';

const { Title, Text } = Typography;

interface UserIntelligence {
    id: string;
    email: string;
    display_name: string | null;
    is_premium: boolean;
    last_seen_at: string | null;
    created_at: string;
    total_assets_count: number;
    total_transactions_count: number;
    account_status: 'ONLINE' | 'OFFLINE' | 'BANNED' | 'DELETED';
}

export default function UserExplorer() {
    const navigate = useNavigate();
    const { isMasked } = useMaskStore();
    const [search, setSearch] = useState('');
    const [roleFilter, setRoleFilter] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState<string | null>(null);

    const { data: users, isLoading, refetch } = useQuery({
        queryKey: ['user-explorer', search, roleFilter, statusFilter],
        queryFn: async () => {
            const { data, error } = await supabase.rpc('search_users_intelligence', {
                p_search: search,
                p_role: roleFilter === 'all' ? null : roleFilter,
                p_status: statusFilter === 'all' ? null : statusFilter,
                p_limit: 100
            });
            if (error) throw error;
            return data as UserIntelligence[];
        }
    });

    const columns: ColumnsType<UserIntelligence> = [
        {
            title: 'User',
            key: 'user',
            render: (record: UserIntelligence) => (
                <Space size="middle">
                    <Avatar
                        icon={<UserOutlined />}
                        style={{ backgroundColor: record.account_status === 'ONLINE' ? '#10b981' : '#64748b' }}
                    />
                    <Flex vertical gap={0}>
                        <Text strong>{isMasked ? maskName(record.display_name) : (record.display_name || 'Anonymous')}</Text>
                        <Text type="secondary" style={{ fontSize: '12px' }}>{isMasked ? maskEmail(record.email) : record.email}</Text>
                    </Flex>
                </Space>
            ),
        },
        {
            title: 'Subscription',
            key: 'sub',
            render: (record: UserIntelligence) => (
                record.is_premium ?
                    <Tag color="gold" icon={<CrownOutlined />}>PREMIUM</Tag> :
                    <Tag color="default">FREE</Tag>
            ),
        },
        {
            title: 'Inventory',
            key: 'inventory',
            render: (record: UserIntelligence) => (
                <Space size="small">
                    <Tooltip title="Portfolio Assets">
                        <Tag color="blue" icon={<GlobalOutlined />}>{record.total_assets_count}</Tag>
                    </Tooltip>
                    <Tooltip title="Wallet Transactions">
                        <Tag color="cyan" icon={<LineChartOutlined />}>{record.total_transactions_count}</Tag>
                    </Tooltip>
                </Space>
            ),
        },
        {
            title: 'Status',
            dataIndex: 'account_status',
            key: 'status',
            render: (status) => {
                let color = 'default';
                if (status === 'ONLINE') color = 'success';
                if (status === 'BANNED') color = 'error';
                return <Tag color={color}>{status}</Tag>;
            }
        },
        {
            title: 'Last Activity',
            dataIndex: 'last_seen_at',
            key: 'last_seen',
            render: (date) => date ? new Date(date).toLocaleString('tr-TR') : 'Never',
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (record: UserIntelligence) => (
                <Button
                    type="primary"
                    ghost
                    icon={<RocketOutlined />}
                    onClick={() => navigate(`/intelligence/profile/${record.id}`)}
                >
                    Analyze
                </Button>
            )
        }
    ];

    return (
        <div style={{ padding: '0px' }}>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>👥 User Explorer</Title>
                <Space>
                    <Button icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>
                </Space>
            </Flex>

            {/* Quick Stats */}
            <Row gutter={16} style={{ marginBottom: '24px' }}>
                <Col span={6}>
                    <Card size="small">
                        <Statistic title="Total Screened" value={users?.length || 0} prefix={<UserOutlined />} />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card size="small">
                        <Statistic
                            title="Premium Ratio"
                            value={users ? (users.filter(u => u.is_premium).length / users.length * 100).toFixed(1) : 0}
                            suffix="%"
                            prefix={<CrownOutlined style={{ color: '#f59e0b' }} />}
                            styles={{ content: { color: '#f59e0b' } }}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card size="small">
                        <Statistic
                            title="Online Now"
                            value={users?.filter(u => u.account_status === 'ONLINE').length || 0}
                            styles={{ content: { color: '#10b981' } }}
                            prefix={<GlobalOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card size="small">
                        <Statistic
                            title="Banned"
                            value={users?.filter(u => u.account_status === 'BANNED').length || 0}
                            styles={{ content: { color: '#ef4444' } }}
                            prefix={<StopOutlined />}
                        />
                    </Card>
                </Col>
            </Row>

            <Card styles={{ body: { padding: '0px' } }}>
                <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0' }}>
                    <Flex justify="space-between" gap="middle">
                        <Input
                            placeholder="Search by name, email or ID..."
                            prefix={<SearchOutlined />}
                            style={{ maxWidth: 400 }}
                            onChange={(e) => setSearch(e.target.value)}
                            allowClear
                        />
                        <Space>
                            <FilterOutlined style={{ color: '#bfbfbf' }} />
                            <Select
                                defaultValue="all"
                                style={{ width: 150 }}
                                onChange={setRoleFilter}
                                options={[
                                    { value: 'all', label: 'All Roles' },
                                    { value: 'premium', label: 'Premium Only' },
                                    { value: 'free', label: 'Free Only' },
                                ]}
                            />
                            <Select
                                defaultValue="all"
                                style={{ width: 150 }}
                                onChange={setStatusFilter}
                                options={[
                                    { value: 'all', label: 'All Status' },
                                    { value: 'ONLINE', label: 'Online' },
                                    { value: 'OFFLINE', label: 'Offline' },
                                    { value: 'BANNED', label: 'Banned' },
                                ]}
                            />
                        </Space>
                    </Flex>
                </div>
                <Table
                    columns={columns}
                    dataSource={users}
                    loading={isLoading}
                    rowKey="id"
                    pagination={{ pageSize: 15 }}
                />
            </Card>
        </div>
    );
}
