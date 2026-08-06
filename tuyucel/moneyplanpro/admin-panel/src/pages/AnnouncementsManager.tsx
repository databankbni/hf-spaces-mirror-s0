import React, { useState, useEffect } from 'react';
import {
    Card,
    Switch,
    Input,
    Select,
    Button,
    Row,
    Col,
    Typography,
    Space,
    Alert,
    Flex,
    message,
    Divider,
    DatePicker,
    Spin,
} from 'antd';
import {
    NotificationOutlined,
    ToolOutlined,
    SyncOutlined,
    ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;
const { TextArea } = Input;
const { Option } = Select;

interface NotificationConfig {
    announcement: {
        enabled: boolean;
        type: string;
        title: string | null;
        message: string;
        action_url: string | null;
        action_text: string | null;
        dismissible: boolean;
        icon: string | null;
        background_color: string | null;
    };
    maintenance: {
        enabled: boolean;
        message: string;
        estimated_end: string | null;
        show_countdown: boolean;
        allow_pro_users: boolean;
    };
    force_update: {
        enabled: boolean;
        min_version: string;
        message: string;
        blocking: boolean;
        store_url_ios: string | null;
        store_url_android: string | null;
    };
    updated_at: string;
}

const AnnouncementsManager: React.FC = () => {
    const [config, setConfig] = useState<NotificationConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState(false);

    const fetchConfig = async () => {
        setLoading(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/notifications/config`);
            const data = await response.json();
            setConfig(data);
        } catch (error) {
            message.error('Sistem ayarları yüklenemedi');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchConfig();
    }, []);

    const updateConfig = async (updates: Record<string, any>) => {
        setUpdating(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/notifications/config`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });

            if (!response.ok) throw new Error('Güncelleme başarısız');

            const data = await response.json();
            setConfig(data);
            message.success('Sistem ayarları güncellendi');
        } catch (error) {
            console.error(error);
            message.error('Güncelleme sırasında hata oluştu');
        } finally {
            setUpdating(false);
        }
    };

    if (loading || !config) {
        return (
            <div style={{ textAlign: 'center', padding: '50px' }}>
                <Spin size="large" />
            </div>
        );
    }

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={2} style={{ margin: 0 }}>Sistem Duyuruları ve Durumu</Title>
                    <Text type="secondary">Bakım modu, uygulama içi duyurular ve zorunlu güncellemeleri yönetin</Text>
                </div>
                <Button icon={<ReloadOutlined />} onClick={fetchConfig} disabled={updating}>Yenile</Button>
            </div>

            <Row gutter={[16, 16]}>
                {/* 1. ANNOUNCEMENTS */}
                <Col xs={24} lg={12}>
                    <Card
                        title={<Space><NotificationOutlined /> Uygulama İçi Duyuru</Space>}
                        extra={<Switch checked={config.announcement.enabled} onChange={(val) => updateConfig({ announcement_enabled: val })} />}
                    >
                        <Flex vertical style={{ width: '100%' }} gap="middle">
                            <Row gutter={8}>
                                <Col span={12}>
                                    <Text strong>Duyuru Tipi</Text>
                                    <Select
                                        style={{ width: '100%', marginTop: 8 }}
                                        value={config.announcement.type}
                                        onChange={(val) => updateConfig({ announcement_type: val })}
                                    >
                                        <Option value="info">Bilgi (Mavi)</Option>
                                        <Option value="warning">Uyarı (Turuncu)</Option>
                                        <Option value="success">Başarı (Yeşil)</Option>
                                        <Option value="error">Hata (Kırmızı)</Option>
                                    </Select>
                                </Col>
                                <Col span={12}>
                                    <Text strong>Kapatılabilir</Text>
                                    <div style={{ marginTop: 8 }}>
                                        <Switch checked={config.announcement.dismissible} onChange={(val) => updateConfig({ announcement_dismissible: val })} />
                                    </div>
                                </Col>
                            </Row>

                            <div>
                                <Text strong>Başlık (Opsiyonel)</Text>
                                <Input
                                    style={{ marginTop: 8 }}
                                    value={config.announcement.title || ''}
                                    onChange={(e) => updateConfig({ announcement_title: e.target.value })}
                                    placeholder="Duyuru başlığı..."
                                />
                            </div>

                            <div>
                                <Text strong>Mesaj</Text>
                                <TextArea
                                    style={{ marginTop: 8 }}
                                    rows={3}
                                    value={config.announcement.message}
                                    onChange={(e) => updateConfig({ announcement_message: e.target.value })}
                                    placeholder="Kullanıcılara gösterilecek mesaj..."
                                />
                            </div>

                            <Row gutter={8}>
                                <Col span={12}>
                                    <Text strong>Buton Metni</Text>
                                    <Input
                                        style={{ marginTop: 8 }}
                                        value={config.announcement.action_text || ''}
                                        onChange={(e) => updateConfig({ announcement_action_text: e.target.value })}
                                        placeholder="Dene, İncele vb."
                                    />
                                </Col>
                                <Col span={12}>
                                    <Text strong>Yönlendirme URL (Action)</Text>
                                    <Input
                                        style={{ marginTop: 8 }}
                                        value={config.announcement.action_url || ''}
                                        onChange={(e) => updateConfig({ announcement_action_url: e.target.value })}
                                        placeholder="/feature-path veya https://..."
                                    />
                                </Col>
                            </Row>

                            <Divider style={{ margin: '8px 0' }} />

                            <Text strong>Önizleme:</Text>
                            <Alert
                                description={
                                    <Flex vertical gap={4}>
                                        {config.announcement.title && <Text strong>{config.announcement.title}</Text>}
                                        <Text>{config.announcement.message}</Text>
                                    </Flex>
                                }
                                type={config.announcement.type as any}
                                showIcon
                                closable={config.announcement.dismissible}
                            />
                        </Flex>
                    </Card>
                </Col>

                {/* 2. MAINTENANCE MODE */}
                <Col xs={24} lg={12}>
                    <Card
                        title={<Space><ToolOutlined /> Bakım Modu</Space>}
                        extra={<Switch checked={config.maintenance.enabled} onChange={(val) => updateConfig({ maintenance_enabled: val })} />}
                    >
                        <Flex vertical style={{ width: '100%' }} gap="middle">
                            <Alert
                                description="DİKKAT: Bakım modu açıkken normal kullanıcılar uygulamaya erişemez."
                                type="warning"
                                showIcon
                            />

                            <div>
                                <Text strong>Bakım Mesajı</Text>
                                <TextArea
                                    style={{ marginTop: 8 }}
                                    rows={2}
                                    value={config.maintenance.message}
                                    onChange={(e) => updateConfig({ maintenance_message: e.target.value })}
                                />
                            </div>

                            <Row gutter={8}>
                                <Col span={12}>
                                    <Text strong>Tahmini Bitiş</Text>
                                    <DatePicker
                                        style={{ width: '100%', marginTop: 8 }}
                                        showTime
                                        value={config.maintenance.estimated_end ? dayjs(config.maintenance.estimated_end) : null}
                                        onChange={(date) => updateConfig({ maintenance_end: date?.toISOString() })}
                                    />
                                </Col>
                                <Col span={6}>
                                    <Text strong>Geri Sayım</Text>
                                    <div style={{ marginTop: 8 }}>
                                        <Switch checked={config.maintenance.show_countdown} onChange={(val) => updateConfig({ maintenance_show_countdown: val })} />
                                    </div>
                                </Col>
                                <Col span={6}>
                                    <Text strong>PRO İzinli</Text>
                                    <div style={{ marginTop: 8 }}>
                                        <Switch checked={config.maintenance.allow_pro_users} onChange={(val) => updateConfig({ maintenance_allow_pro: val })} />
                                    </div>
                                </Col>
                            </Row>
                        </Flex>
                    </Card>

                    <Card title={<Space><SyncOutlined /> Zorunlu Güncelleme</Space>} style={{ marginTop: 16 }}>
                        <Flex vertical style={{ width: '100%' }} gap="middle">
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Text strong>Min. Versiyon</Text>
                                    <Input
                                        style={{ marginTop: 8 }}
                                        value={config.force_update.min_version}
                                        onChange={(e) => updateConfig({ force_update_min_version: e.target.value })}
                                        placeholder="e.g. 1.2.0"
                                    />
                                </Col>
                                <Col span={6}>
                                    <Text strong>Aktif</Text>
                                    <div style={{ marginTop: 8 }}>
                                        <Switch checked={config.force_update.enabled} onChange={(val) => updateConfig({ force_update_enabled: val })} />
                                    </div>
                                </Col>
                                <Col span={6}>
                                    <Text strong>Blokla</Text>
                                    <div style={{ marginTop: 8 }}>
                                        <Switch checked={config.force_update.blocking} onChange={(val) => updateConfig({ force_update_blocking: val })} />
                                    </div>
                                </Col>
                            </Row>
                            <div>
                                <Text strong>Güncelleme Mesajı</Text>
                                <TextArea
                                    style={{ marginTop: 8 }}
                                    rows={2}
                                    value={config.force_update.message}
                                    onChange={(e) => updateConfig({ force_update_message: e.target.value })}
                                />
                            </div>
                        </Flex>
                    </Card>
                </Col>
            </Row>

            <div style={{ marginTop: 16 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                    Son Güncelleme: {new Date(config.updated_at).toLocaleString()}
                </Text>
            </div>
        </div>
    );
};

export default AnnouncementsManager;
