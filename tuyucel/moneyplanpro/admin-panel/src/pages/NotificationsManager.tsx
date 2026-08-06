import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Card,
    Table,
    Button,
    Tag,
    Typography,
    Space,
    App,
    Flex,
    Alert,
    Input,
    Form,
    Select,
    Divider,
    Badge,
    Row,
    Col
} from 'antd';
import {
    SendOutlined,
    HistoryOutlined,
    BellOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    ScheduleOutlined,
    PictureOutlined,
    LinkOutlined,
    SyncOutlined
} from '@ant-design/icons';

const { Title, Text } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';
import { supabase } from '../lib/supabase';

const BACKEND_URL = API_BASE_URL;

interface NotificationHistory {
    id: string;
    title: string;
    message: string;
    image_url: string | null;
    action_url: string | null;
    target_segment: string;
    status: 'queued' | 'sending' | 'sent' | 'partial' | 'failed';
    delivered_count: number;
    recipient_count: number;
    failed_count: number;
    created_at: string;
}

interface NotificationTargetUser {
    id: string;
    email: string;
    display_name: string | null;
}

export default function NotificationsManager() {
    const queryClient = useQueryClient();
    const { message: messageApi } = App.useApp();
    const [form] = Form.useForm();

    // 1. Fetch History
    const { data: history, isLoading } = useQuery<NotificationHistory[]>({
        queryKey: ['notification-history'],
        queryFn: async () => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/notifications`);
            if (!resp.ok) throw new Error('Backend connection failed');
            return resp.json();
        },
        refetchInterval: 10000 // Refresh history every 10s
    });

    // 2. Fetch active users so admins can safely send a test to one account.
    const { data: targetUsers = [], isLoading: areTargetsLoading } = useQuery<NotificationTargetUser[]>({
        queryKey: ['notification-target-users'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('users')
                .select('id,email,display_name')
                .eq('is_active', true)
                .eq('is_banned', false)
                .is('deleted_at', null)
                .order('email');
            if (error) throw error;
            return data ?? [];
        }
    });

    // 3. Send Mutation
    const sendMutation = useMutation({
        mutationFn: async (payload: any) => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/notifications/send`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Failed to send notification');
            }
            return resp.json();
        },
        onSuccess: () => {
            void messageApi.success('Bildirim kutuları oluşturuldu ve APNs teslimatı başlatıldı');
            form.resetFields();
            void queryClient.invalidateQueries({ queryKey: ['notification-history'] });
        },
        onError: (err: Error) => {
            void messageApi.error(err.message);
        }
    });

    const columns = [
        {
            title: 'Content',
            key: 'content',
            render: (record: NotificationHistory) => (
                <Flex vertical>
                    <Text strong>{record.title}</Text>
                    <Text type="secondary" style={{ fontSize: '12px' }}>{record.message}</Text>
                    <Space size="small" style={{ marginTop: '4px' }}>
                        {record.image_url && <Badge count={<PictureOutlined style={{ color: '#1890ff' }} />} />}
                        {record.action_url && <LinkOutlined style={{ color: '#52c41a' }} />}
                    </Space>
                </Flex>
            )
        },
        {
            title: 'Target',
            dataIndex: 'target_segment',
            key: 'target',
            render: (segment: string) => (
                <Tag color="cyan">{segment.toUpperCase()}</Tag>
            )
        },
        {
            title: 'Status',
            key: 'status',
            render: (record: NotificationHistory) => {
                if (record.status === 'sent') return <Tag color="success" icon={<CheckCircleOutlined />}>SENT ({record.delivered_count}/{record.recipient_count})</Tag>;
                if (record.status === 'failed') return <Tag color="error" icon={<CloseCircleOutlined />}>FAILED</Tag>;
                if (record.status === 'partial') return <Tag color="warning">PARTIAL ({record.delivered_count}/{record.recipient_count})</Tag>;
                return <Tag color="processing" icon={<SyncOutlined spin />}>IN-APP READY</Tag>;
            }
        },
        {
            title: 'Date',
            dataIndex: 'created_at',
            key: 'date',
            render: (val: string) => new Date(val).toLocaleString()
        }
    ];

    return (
        <div>
            <Title level={2} style={{ marginBottom: '24px' }}>
                🔔 Push Notifications
            </Title>

            <Alert
                title="Engagement Hub"
                description="Supabase bildirim kutusuna yayın yapar; iOS cihazlarına doğrudan Apple APNs üzerinden teslim eder. OneSignal kullanılmaz."
                type="info"
                showIcon
                style={{ marginBottom: '24px' }}
            />

            <Row gutter={24}>
                {/* Compose Form */}
                <Col xs={24} lg={10}>
                    <Card title={<><SendOutlined /> Compose New Broadcast</>} style={{ height: '100%' }}>
                        <Form
                            form={form}
                            layout="vertical"
                            onFinish={(values) => sendMutation.mutate(values)}
                            initialValues={{ segment: 'all' }}
                        >
                            <Form.Item name="title" label="Notification Title" rules={[{ required: true }]}>
                                <Input placeholder="e.g. Market Alert: Bitcoin on the rise!" />
                            </Form.Item>

                            <Form.Item name="message" label="Message Body" rules={[{ required: true }]}>
                                <Input.TextArea rows={3} placeholder="Compose your message here..." />
                            </Form.Item>

                            <Form.Item name="segment" label="Target Segment">
                                <Select
                                    loading={areTargetsLoading}
                                    options={[
                                        {
                                            label: 'Segments',
                                            options: [
                                                { label: 'All Users', value: 'all' },
                                                { label: 'Premium Only', value: 'premium' },
                                                { label: 'Free Users', value: 'free' }
                                            ]
                                        },
                                        {
                                            label: 'Individual Users',
                                            options: targetUsers.map((user) => ({
                                                label: user.display_name
                                                    ? `${user.email} (${user.display_name})`
                                                    : user.email,
                                                value: `user_${user.id}`
                                            }))
                                        }
                                    ]}
                                />
                            </Form.Item>

                            <Divider style={{ fontSize: '12px' }}>Rich Media (Optional)</Divider>

                            <Form.Item name="image_url" label="Big Picture URL">
                                <Input prefix={<PictureOutlined />} placeholder="https://example.com/image.jpg" />
                            </Form.Item>

                            <Form.Item name="action_url" label="In-App Action Link / URL">
                                <Input prefix={<LinkOutlined />} placeholder="moneyplan://market/btc" />
                            </Form.Item>

                            <Button
                                type="primary"
                                icon={<BellOutlined />}
                                block
                                size="large"
                                htmlType="submit"
                                loading={sendMutation.isPending}
                            >
                                Send Broadcast Now
                            </Button>
                        </Form>
                    </Card>
                </Col>

                {/* History Table */}
                <Col xs={24} lg={14}>
                    <Card title={<><HistoryOutlined /> Broadcast History</>} style={{ height: '100%' }} styles={{ body: { padding: 0 } }}>
                        <Table
                            dataSource={history}
                            columns={columns}
                            loading={isLoading}
                            rowKey="id"
                            pagination={{ pageSize: 8 }}
                        />
                    </Card>
                </Col>
            </Row>

            <Card style={{ marginTop: '24px' }} size="small">
                <Flex align="center" gap="middle">
                    <ScheduleOutlined style={{ fontSize: '24px', color: '#8c8c8c' }} />
                    <div>
                        <Text strong>Scheduled Notifications</Text><br />
                        <Text type="secondary" style={{ fontSize: '12px' }}>
                            Future updates will include the ability to schedule notifications for specific timezones.
                        </Text>
                    </div>
                    <Button disabled style={{ marginLeft: 'auto' }}>Manage Schedule</Button>
                </Flex>
            </Card>
        </div>
    );
}
