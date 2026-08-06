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
    Popconfirm,
    Badge,
    Row,
    Col,
} from 'antd';
import {
    DeleteOutlined,
    SyncOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
} from '@ant-design/icons';
import { supabase } from '../lib/supabase';

const { Title, Text } = Typography;

interface PriceAlert {
    id: string;
    user_id: string;
    symbol: string;
    target_price: number;
    is_above: boolean;
    is_active: boolean;
    last_triggered_at: string | null;
    created_at: string;
}

export default function PriceAlertsManager() {
    const queryClient = useQueryClient();
    const { message: messageApi } = App.useApp();

    // 1. Fetch Alerts from Supabase
    const { data: alerts, isLoading } = useQuery<PriceAlert[]>({
        queryKey: ['system-alerts'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('price_alerts')
                .select('*')
                .order('created_at', { ascending: false });

            if (error) throw error;
            return data as PriceAlert[];
        }
    });

    // 2. Delete Alert Mutation
    const deleteMutation = useMutation({
        mutationFn: async (id: string) => {
            const { error } = await supabase
                .from('price_alerts')
                .delete()
                .eq('id', id);

            if (error) throw error;
        },
        onSuccess: () => {
            void messageApi.success('Alarm başarıyla silindi');
            void queryClient.invalidateQueries({ queryKey: ['system-alerts'] });
        }
    });

    const columns = [
        {
            title: 'Kullanıcı ID',
            dataIndex: 'user_id',
            key: 'user_id',
            render: (text: string) => <Text code copyable>{text}</Text>
        },
        {
            title: 'Varlık',
            dataIndex: 'symbol',
            key: 'symbol',
            render: (text: string) => <Tag color="blue">{text}</Tag>
        },
        {
            title: 'Hedef Fiyat',
            dataIndex: 'target_price',
            key: 'target_price',
            render: (price: number, record: PriceAlert) => (
                <Space>
                    <Text strong>${price.toLocaleString()}</Text>
                    <Tag color={record.is_above ? 'green' : 'orange'}>
                        {record.is_above ? 'Üstü' : 'Altı'}
                    </Tag>
                </Space>
            )
        },
        {
            title: 'Durum',
            dataIndex: 'is_active',
            key: 'status',
            render: (active: boolean) => (
                active
                    ? <Badge status="processing" text="Aktif İzleniyor" />
                    : <Badge status="default" text="Pasif / Tetiklendi" />
            )
        },
        {
            title: 'Oluşturulma',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (date: string) => <Text type="secondary" style={{ fontSize: '12px' }}>{new Date(date).toLocaleString()}</Text>
        },
        {
            title: 'İşlemler',
            key: 'actions',
            render: (record: PriceAlert) => (
                <Popconfirm
                    title="Alarmı silmek istediğinize emin misiniz?"
                    onConfirm={() => deleteMutation.mutate(record.id)}
                    okText="Evet"
                    cancelText="Hayır"
                >
                    <Button
                        danger
                        icon={<DeleteOutlined />}
                        size="small"
                        type="text"
                    />
                </Popconfirm>
            )
        }
    ];

    return (
        <div>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>
                    🔔 Fiyat Alarmları Yönetimi
                </Title>
                <Button
                    icon={<SyncOutlined />}
                    onClick={() => void queryClient.invalidateQueries({ queryKey: ['system-alerts'] })}
                >
                    Yenile
                </Button>
            </Flex>

            <Alert
                description={
                    <Flex vertical gap={4}>
                        <Text strong>Bulut Tabanlı (Supabase) Alarm Takibi</Text>
                        <Text type="secondary">Kullanıcıların mobil uygulama üzerinden oluşturduğu tüm alarmlar doğrudan Supabase üzerinde saklanır. Backend servisimiz hedefi kontrol eder, uygulama içi bildirim oluşturur ve iOS cihazına doğrudan Apple APNs üzerinden gönderir.</Text>
                    </Flex>
                }
                type="info"
                showIcon
                style={{ marginBottom: '24px', borderRadius: '12px' }}
            />

            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Card title={<Space><ClockCircleOutlined /> Bekleyen Alarmlar</Space>} styles={{ body: { padding: 0 } }}>
                        <Table
                            dataSource={alerts?.filter(a => a.is_active)}
                            columns={columns}
                            loading={isLoading}
                            rowKey="id"
                            pagination={{ pageSize: 10 }}
                        />
                    </Card>
                </Col>

                <Col span={24}>
                    <Card title={<Space><CheckCircleOutlined /> Geçmiş / Tetiklenen Alarmlar</Space>} styles={{ body: { padding: 0 } }}>
                        <Table
                            dataSource={alerts?.filter(a => !a.is_active)}
                            columns={columns}
                            loading={isLoading}
                            rowKey="id"
                            pagination={{ pageSize: 10 }}
                        />
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
