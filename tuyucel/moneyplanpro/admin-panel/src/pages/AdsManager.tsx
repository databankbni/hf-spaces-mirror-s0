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
    Switch,
    Input,
    Modal,
    Form,
    Select,
} from 'antd';
import {
    EditOutlined,
    SyncOutlined,
    GlobalOutlined,
    MobileOutlined,
    SafetyCertificateOutlined
} from '@ant-design/icons';
import { useState } from 'react';

const { Title, Text, Paragraph } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;

interface AdPlacement {
    id: number;
    name: string;
    placement_key: string;
    ad_unit_id: string;
    provider: string;
    is_enabled: number;
    updated_at: string;
}

export default function AdsManager() {
    const queryClient = useQueryClient();
    const { message: messageApi } = App.useApp();
    const [editingAd, setEditingAd] = useState<AdPlacement | null>(null);
    const [form] = Form.useForm();

    // 1. Fetch Ads
    const { data: ads, isLoading } = useQuery<AdPlacement[]>({
        queryKey: ['system-ads'],
        queryFn: async () => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/ads`);
            if (!resp.ok) throw new Error('Backend connection failed');
            return resp.json();
        }
    });

    // 2. Update Ad Mutation
    const updateMutation = useMutation({
        mutationFn: async ({ id, updates }: { id: number, updates: any }) => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/ads/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            if (!resp.ok) throw new Error('Failed to update ad placement');
            return resp.json();
        },
        onSuccess: () => {
            void messageApi.success('Placement updated successfully');
            setEditingAd(null);
            void queryClient.invalidateQueries({ queryKey: ['system-ads'] });
        },
        onError: (err: Error) => {
            void messageApi.error(err.message);
        }
    });

    const handleToggle = (id: number, checked: boolean) => {
        updateMutation.mutate({ id, updates: { is_enabled: checked ? 1 : 0 } });
    };

    const handleEdit = (ad: AdPlacement) => {
        setEditingAd(ad);
        form.setFieldsValue(ad);
    };

    const columns = [
        {
            title: 'Yerleşim Bilgisi',
            dataIndex: 'name',
            key: 'name',
            render: (text: string, record: AdPlacement) => (
                <Flex vertical gap={4}>
                    <Text strong style={{ fontSize: '15px' }}>{text}</Text>
                    <Text type="secondary" style={{ fontSize: '11px' }}>Anahtar: {record.placement_key}</Text>
                </Flex>
            )
        },
        {
            title: 'Sağlayıcı',
            dataIndex: 'provider',
            key: 'provider',
            width: 150,
            render: (text: string) => (
                <Tag color={text === 'admob' ? 'orange' : 'blue'} style={{ borderRadius: '4px', border: 'none', padding: '0 8px' }}>
                    {text.toUpperCase()}
                </Tag>
            )
        },
        {
            title: 'Ad Unit ID',
            dataIndex: 'ad_unit_id',
            key: 'ad_unit_id',
            render: (text: string) => (
                <div style={{ background: '#f8fafc', padding: '4px 8px', borderRadius: '4px', border: '1px solid #f1f5f9' }}>
                    <Text code style={{ fontSize: '12px', color: '#64748b' }}>{text}</Text>
                </div>
            )
        },
        {
            title: 'Durum',
            dataIndex: 'is_enabled',
            key: 'status',
            width: 100,
            render: (val: number, record: AdPlacement) => (
                <Switch
                    size="small"
                    checked={val === 1}
                    onChange={(checked) => handleToggle(record.id, checked)}
                    loading={updateMutation.isPending && editingAd?.id === record.id}
                />
            )
        },
        {
            title: 'İşlemler',
            key: 'actions',
            width: 120,
            render: (record: AdPlacement) => (
                <Button
                    icon={<EditOutlined />}
                    size="small"
                    onClick={() => handleEdit(record)}
                    style={{ borderRadius: '6px' }}
                >
                    Yapılandır
                </Button>
            )
        }
    ];

    return (
        <div>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>
                    📢 Advertisement Manager
                </Title>
                <Button icon={<SyncOutlined />} onClick={() => void queryClient.invalidateQueries({ queryKey: ['system-ads'] })}>
                    Refresh
                </Button>
            </Flex>

            <Alert
                description={
                    <Flex vertical gap={4}>
                        <Text strong>Reklam ve Monetizasyon Kontrolü</Text>
                        <Text type="secondary">Uygulama marketine güncelleme göndermeden AdMob unit ID'lerini ve görünürlük ayarlarını yönetin. Değişiklikler 5-10 dakika içinde uygulamaya yansır.</Text>
                    </Flex>
                }
                type="info"
                showIcon
                style={{ marginBottom: '32px', borderRadius: '12px' }}
            />

            <Flex gap="large" vertical>
                <Card title={<><MobileOutlined /> Active Placements</>} styles={{ body: { padding: 0 } }}>
                    <Table
                        dataSource={ads}
                        columns={columns}
                        loading={isLoading}
                        rowKey="id"
                        pagination={false}
                    />
                </Card>

                <Card title={<><SafetyCertificateOutlined /> Global Ad Settings</>} size="small">
                    <Paragraph type="secondary">
                        Current Strategy: <b>Hybrid bidding</b> (AdMob + Meta Audience Network)
                    </Paragraph>
                    <Space>
                        <Button icon={<GlobalOutlined />} disabled>Mediation Rules</Button>
                        <Button disabled>Revenue Analytics</Button>
                    </Space>
                </Card>
            </Flex>

            {/* Edit Modal */}
            <Modal
                title={`Configure Placement: ${editingAd?.name}`}
                open={!!editingAd}
                onCancel={() => setEditingAd(null)}
                onOk={() => form.submit()}
                confirmLoading={updateMutation.isPending}
            >
                <Form form={form} layout="vertical" onFinish={(values) => updateMutation.mutate({ id: editingAd!.id, updates: values })}>
                    <Form.Item name="name" label="Display Name" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="provider" label="Ad Provider">
                        <Select options={[
                            { label: 'Google AdMob', value: 'admob' },
                            { label: 'Unity Ads', value: 'unity' },
                            { label: 'Custom Asset', value: 'custom' }
                        ]} />
                    </Form.Item>
                    <Form.Item name="ad_unit_id" label="Ad Unit ID" rules={[{ required: true }]}>
                        <Input.TextArea autoSize placeholder="ca-app-pub-..." />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
