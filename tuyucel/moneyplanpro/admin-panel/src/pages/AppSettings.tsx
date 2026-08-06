import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Card,
    Input,
    Button,
    Typography,
    Space,
    App,
    Tag,
    Flex,
    Divider,
    Alert,
    Badge,
    Row,
    Col,
    Spin,
} from 'antd';
import {
    SaveOutlined,
    SettingOutlined,
    SafetyCertificateOutlined,
    GlobalOutlined,
    RocketOutlined
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;

interface AppSetting {
    key: string;
    value: string;
    description: string;
    category: string;
    updated_at: string;
    is_configured?: boolean;
}

export default function AppSettings() {
    const queryClient = useQueryClient();
    const { message: messageApi } = App.useApp();
    const [drafts, setDrafts] = useState<Record<string, string>>({});

    // 1. Fetch Settings
    const { data: settings, isLoading } = useQuery({
        queryKey: ['system-settings'],
        queryFn: async () => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/settings`);
            if (!resp.ok) throw new Error('Backend connection failed');
            return resp.json() as Promise<AppSetting[]>;
        }
    });

    // 2. Update Setting Mutation
    const updateMutation = useMutation({
        mutationFn: async ({ key, value }: { key: string, value: string }) => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/settings/${key}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value })
            });
            if (!resp.ok) {
                const body = await resp.json().catch(() => null);
                throw new Error(body?.detail || 'Update failed');
            }
            return resp.json();
        },
        onSuccess: (_, variables) => {
            setDrafts((current) => {
                const next = { ...current };
                delete next[variables.key];
                return next;
            });
            void messageApi.success('Setting updated successfully');
            void queryClient.invalidateQueries({ queryKey: ['system-settings'] });
        },
        onError: (error: Error) => {
            void messageApi.error(error.message);
        }
    });

    if (isLoading) return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" /></div>;

    const getCategoryIcon = (cat: string) => {
        switch (cat) {
            case 'api_keys': return <SafetyCertificateOutlined />;
            case 'content': return <GlobalOutlined />;
            case 'features': return <RocketOutlined />;
            default: return <SettingOutlined />;
        }
    };

    const groupedSettings = settings?.reduce((acc: any, curr) => {
        if (!acc[curr.category]) acc[curr.category] = [];
        acc[curr.category].push(curr);
        return acc;
    }, {}) || {};

    const categoryNames: Record<string, string> = {
        'api_keys': '🔑 API Anahtarları ve Güvenlik',
        'content': '🌍 İçerik ve Lokalizasyon',
        'features': '🚀 Özellik Yönetimi (Flags)',
        'system': '💻 Sistem ve Çekirdek Ayarlar'
    };

    return (
        <div style={{ maxWidth: '1200px', margin: '0 auto', paddingBottom: '40px' }}>
            <Flex justify="space-between" align="end" style={{ marginBottom: 32 }}>
                <div>
                    <Title level={2} style={{ margin: 0, letterSpacing: '-0.5px' }}>⚙️ Sistem Konfigürasyonu</Title>
                    <Text type="secondary">Uygulama çekirdek ayarlarını, API anahtarlarını ve global parametreleri yönetin</Text>
                </div>
                <Tag color="processing" icon={<RocketOutlined />}>Canlı Sistem</Tag>
            </Flex>

            <Alert
                description={
                    <Flex vertical gap={4}>
                        <Text strong>Bilgi</Text>
                        <Text type="secondary">Buradaki değişiklikler backend önbelleği yenilendiğinde (yaklaşık 1-5 dk) tüm kullanıcılara yansır. Boş alanlar için varsa Hugging Face üzerindeki <b>Environment Variables</b> (Sırlar) kullanılır.</Text>
                    </Flex>
                }
                type="info"
                showIcon
                style={{ marginBottom: 32, borderRadius: '12px' }}
            />

            <Flex vertical gap="xlarge">
                {Object.entries(groupedSettings).map(([category, items]) => (
                    <div key={category} style={{ marginBottom: 32 }}>
                        <Title level={4} style={{ marginBottom: 16 }}>{categoryNames[category] || category.toUpperCase()}</Title>
                        <Row gutter={[16, 16]}>
                            {(items as AppSetting[]).map((item) => (
                                <Col xs={24} md={12} key={item.key}>
                                    <Card
                                        size="small"
                                        style={{
                                            borderRadius: '12px',
                                            boxShadow: '0 4px 12px rgba(0,0,0,0.03)',
                                            border: '1px solid #f1f5f9'
                                        }}
                                        title={
                                            <Space>
                                                {getCategoryIcon(item.category)}
                                                <Text strong style={{ fontSize: '13px' }}>{item.key.replaceAll('_', ' ')}</Text>
                                                {item.is_configured !== undefined && (
                                                    <Tag color={item.is_configured ? 'success' : 'default'}>
                                                        {item.is_configured ? 'Configured' : 'Missing'}
                                                    </Tag>
                                                )}
                                            </Space>
                                        }
                                        extra={<Text type="secondary" style={{ fontSize: '11px' }}>{new Date(item.updated_at).toLocaleDateString()}</Text>}
                                    >
                                        <Paragraph type="secondary" style={{ fontSize: '12px', minHeight: '32px', marginBottom: 12 }}>
                                            {item.description}
                                        </Paragraph>
                                        <Flex gap="small">
                                            <Input
                                                value={drafts[item.key] ?? item.value}
                                                placeholder={item.is_configured ? '•••••••• (configured)' : 'Not configured'}
                                                type={item.is_configured !== undefined ? 'password' : 'text'}
                                                autoComplete="off"
                                                onChange={(e) => {
                                                    setDrafts((current) => ({
                                                        ...current,
                                                        [item.key]: e.target.value,
                                                    }));
                                                }}
                                                style={{ borderRadius: '6px' }}
                                                onPressEnter={() => {
                                                    const value = drafts[item.key];
                                                    if (value !== undefined && value.trim()) {
                                                        updateMutation.mutate({ key: item.key, value });
                                                    }
                                                }}
                                            />
                                            <Button
                                                icon={<SaveOutlined />}
                                                type="primary"
                                                disabled={
                                                    drafts[item.key] === undefined ||
                                                    (item.is_configured !== undefined && !drafts[item.key].trim())
                                                }
                                                loading={updateMutation.isPending && updateMutation.variables?.key === item.key}
                                                onClick={() => updateMutation.mutate({
                                                    key: item.key,
                                                    value: drafts[item.key] ?? '',
                                                })}
                                                style={{ borderRadius: '6px' }}
                                            />
                                        </Flex>
                                    </Card>
                                </Col>
                            ))}
                        </Row>
                    </div>
                ))}
            </Flex>

            <Divider style={{ margin: '40px 0' }} />

            <Row gutter={16}>
                <Col span={24}>
                    <Card
                        title="📊 Veritabanı ve Sistem Sağlığı"
                        size="small"
                        style={{ borderRadius: '12px', border: '1px solid #f1f5f9' }}
                    >
                        <Flex gap="large" wrap="wrap">
                            <Flex vertical>
                                <Text type="secondary" style={{ fontSize: '12px' }}>Ana Veritabanı</Text>
                                <Text strong><Badge status="success" /> SQLite (Core Engine)</Text>
                            </Flex>
                            <Divider style={{ height: '40px' }} />
                            <Flex vertical>
                                <Text type="secondary" style={{ fontSize: '12px' }}>Analitik Birimi</Text>
                                <Text strong><Badge status="success" /> Supabase (Realtime)</Text>
                            </Flex>
                            <Divider style={{ height: '40px' }} />
                            <Flex vertical>
                                <Text type="secondary" style={{ fontSize: '12px' }}>Backend Durumu</Text>
                                <Text strong><Badge status="processing" /> FastAPI / Python 3.12</Text>
                            </Flex>
                        </Flex>
                    </Card>
                </Col>
            </Row>
        </div>
    );
}
