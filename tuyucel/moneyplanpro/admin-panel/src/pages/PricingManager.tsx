import React, { useState, useEffect } from 'react';
import {
    Card,
    InputNumber,
    Button,
    Alert,
    Row,
    Col,
    Typography,
    Space,
    Switch,
    Input,
    DatePicker,
    Spin,
    Divider,
    App,
    Flex,
    Tag,
    Badge,
} from 'antd';
import {
    ReloadOutlined,
    DollarOutlined,
    GiftOutlined,
    ClockCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Title, Text } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;
const { TextArea } = Input;

interface PricingConfig {
    id: string;
    pricing: {
        monthly_price: number;
        yearly_price: number;
        currency: string;
        currency_symbol: string;
    };
    promotion: {
        enabled: boolean;
        discount_percentage: number;
        promo_code: string | null;
        start_date: string | null;
        end_date: string | null;
        message: string | null;
        banner_color: string;
    };
    trial: {
        enabled: boolean;
        duration_days: number;
        features_included: string[];
    };
    show_discount_banner: boolean;
    updated_at: string;
}

const PricingManager: React.FC = () => {
    const [config, setConfig] = useState<PricingConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const { message } = App.useApp();

    const fetchConfig = async () => {
        setLoading(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/pricing`);
            const data = await response.json();
            setConfig(data);
            message.success('Pricing configuration loaded');
        } catch (error) {
            message.error('Failed to load pricing configuration');
            console.error('Error:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchConfig();
    }, []);

    const updateConfig = async (updates: Record<string, any>) => {
        setSaving(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/pricing`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });

            if (!response.ok) throw new Error('Update failed');

            const result = await response.json();
            setConfig(result);
            message.success('Pricing updated successfully');
        } catch (error) {
            message.error('Failed to update pricing');
            console.error('Error:', error);
        } finally {
            setSaving(false);
        }
    };

    if (loading || !config) {
        return (
            <div style={{ textAlign: 'center', padding: '50px' }}>
                <Spin size="large" />
                <div style={{ marginTop: 16 }}>Loading pricing configuration...</div>
            </div>
        );
    }

    const yearlyDiscount = config.promotion.enabled
        ? config.pricing.yearly_price * (config.promotion.discount_percentage / 100)
        : 0;
    const monthlyDiscount = config.promotion.enabled
        ? config.pricing.monthly_price * (config.promotion.discount_percentage / 100)
        : 0;

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={2} style={{ margin: 0 }}>Pricing & Promotions</Title>
                    <Text type="secondary">Manage subscription pricing and promotional campaigns</Text>
                </div>
                <Button icon={<ReloadOutlined />} onClick={fetchConfig} loading={loading}>
                    Refresh
                </Button>
            </div>

            <Alert
                description={
                    <Flex gap="small" align="center">
                        <Text strong style={{ color: '#0369a1' }}>💡 Değişiklikler anında yayına alınır.</Text>
                        <Text type="secondary" style={{ fontSize: '13px' }}>Fiyat güncellemeleri önbellek süresi (yaklaşık 1 saat) sonrası mobil uygulamaya yansır.</Text>
                    </Flex>
                }
                type="info"
                showIcon
                style={{ marginBottom: 32, borderRadius: '12px', border: '1px solid #bae6fd', backgroundColor: '#f0f9ff' }}
            />

            <Row gutter={[16, 16]}>
                {/* Pricing Plans Preview */}
                <Col xs={24}>
                    <Flex gap="large" wrap="wrap" justify="center" style={{ marginBottom: 32 }}>
                        {/* Monthly Plan Card */}
                        <Card
                            style={{
                                width: 300,
                                borderRadius: '24px',
                                border: 'none',
                                textAlign: 'center',
                                background: '#fff',
                                boxShadow: '0 4px 15px rgba(0,0,0,0.05)'
                            }}
                            styles={{ body: { padding: '32px 24px' } }}
                            loading={saving}
                        >
                            <Text strong style={{ color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px', fontSize: '12px' }}>Aylık Plan</Text>
                            <div style={{ margin: '24px 0' }}>
                                <Text delete={config.promotion.enabled} style={{ fontSize: '18px', opacity: 0.5, marginRight: 8 }}>
                                    {config.pricing.currency_symbol}{config.pricing.monthly_price}
                                </Text>
                                <Title level={2} style={{ margin: 0, display: 'inline' }}>
                                    {config.pricing.currency_symbol}{(config.pricing.monthly_price - monthlyDiscount).toFixed(0)}
                                </Title>
                                <Text type="secondary"> /ay</Text>
                            </div>
                            <Button type="primary" block style={{ height: 45, borderRadius: '12px', background: '#6366f1', fontWeight: 600 }}>Düzenle</Button>
                            <Divider style={{ margin: '24px 0' }} />
                            <Flex vertical gap="small" align="start">
                                <Text style={{ fontSize: '13px' }}>✅ Temel Özellikler</Text>
                                <Text style={{ fontSize: '13px' }}>✅ Reklamsız Deneyim</Text>
                                <Text style={{ fontSize: '13px' }}>✅ Portföy Takibi</Text>
                            </Flex>
                        </Card>

                        {/* Yearly Plan Card (Most Popular) */}
                        <Badge.Ribbon text="POPÜLER" color="#f59e0b">
                            <Card
                                style={{
                                    width: 320,
                                    borderRadius: '24px',
                                    border: '2px solid #6366f1',
                                    textAlign: 'center',
                                    background: 'linear-gradient(145deg, #ffffff 0%, #f8faff 100%)',
                                    transform: 'scale(1.05)',
                                    boxShadow: '0 20px 25px -5px rgba(99, 102, 241, 0.1)'
                                }}
                                styles={{ body: { padding: '32px 24px' } }}
                                loading={saving}
                            >
                                <Text strong style={{ color: '#6366f1', textTransform: 'uppercase', letterSpacing: '1px', fontSize: '12px' }}>Yıllık Plan</Text>
                                <div style={{ margin: '24px 0' }}>
                                    <Text delete={config.promotion.enabled} style={{ fontSize: '18px', opacity: 0.5, marginRight: 8 }}>
                                        {config.pricing.currency_symbol}{config.pricing.yearly_price}
                                    </Text>
                                    <Title level={1} style={{ margin: 0, display: 'inline', color: '#1e293b' }}>
                                        {config.pricing.currency_symbol}{(config.pricing.yearly_price - yearlyDiscount).toFixed(0)}
                                    </Title>
                                    <Text type="secondary"> /yıl</Text>
                                    {config.promotion.enabled && (
                                        <div style={{ marginTop: 8 }}>
                                            <Tag color="success" style={{ border: 'none', borderRadius: '4px' }}>%{config.promotion.discount_percentage} İNDİRİM</Tag>
                                        </div>
                                    )}
                                </div>
                                <Button type="primary" block style={{ height: 45, borderRadius: '12px', background: '#4f46e5', fontWeight: 600 }}>Düzenle</Button>
                                <Divider style={{ margin: '24px 0' }} />
                                <Flex vertical gap="small" align="start">
                                    <Text style={{ fontSize: '13px' }}>✅ Tüm Pro Özellikler</Text>
                                    <Text style={{ fontSize: '13px' }}>✅ Öncelikli Destek</Text>
                                    <Text style={{ fontSize: '13px' }}>✅ Sınırsız Portföy</Text>
                                    <Text style={{ fontSize: '13px' }}>✅ Erken Erişim</Text>
                                </Flex>
                            </Card>
                        </Badge.Ribbon>
                    </Flex>
                </Col>

                {/* Configuration Cards */}
                <Col xs={24} lg={12}>
                    <Card
                        title={<Space><DollarOutlined style={{ color: '#6366f1' }} /> <Text strong>Fiyat Ayarları</Text></Space>}
                        style={{ border: 'none', borderRadius: '16px', boxShadow: '0 4px 15px rgba(0,0,0,0.05)' }}
                    >
                        <Flex vertical gap="large">
                            <div>
                                <Text strong style={{ display: 'block', marginBottom: 8 }}>Aylık Liste Fiyatı</Text>
                                <InputNumber
                                    value={config.pricing.monthly_price}
                                    onChange={(v) => updateConfig({ monthly_price: v })}
                                    prefix={config.pricing.currency_symbol}
                                    style={{ width: '100%', height: 40, borderRadius: '8px', display: 'flex', alignItems: 'center' }}
                                />
                            </div>
                            <div>
                                <Text strong style={{ display: 'block', marginBottom: 8 }}>Yıllık Liste Fiyatı</Text>
                                <InputNumber
                                    value={config.pricing.yearly_price}
                                    onChange={(v) => updateConfig({ yearly_price: v })}
                                    prefix={config.pricing.currency_symbol}
                                    style={{ width: '100%', height: 40, borderRadius: '8px', display: 'flex', alignItems: 'center' }}
                                />
                            </div>
                        </Flex>
                    </Card>
                </Col>

                <Col xs={24} lg={12}>
                    <Card
                        title={<Space><GiftOutlined style={{ color: '#f59e0b' }} /> <Text strong>Kampanya ve İndirimler</Text></Space>}
                        style={{ border: 'none', borderRadius: '16px', boxShadow: '0 4px 15px rgba(0,0,0,0.05)' }}
                    >
                        <Flex vertical gap="middle">
                            <Flex justify="space-between" align="center" style={{ padding: '8px 12px', background: '#f8fafc', borderRadius: '12px' }}>
                                <div>
                                    <Text strong style={{ display: 'block' }}>Kampanyayı Etkinleştir</Text>
                                    <Text type="secondary" style={{ fontSize: '11px' }}>Global indirim yüzdesi tüm planlara uygulanır</Text>
                                </div>
                                <Switch
                                    checked={config.promotion.enabled}
                                    onChange={(checked) => updateConfig({ promotion_enabled: checked })}
                                />
                            </Flex>

                            {config.promotion.enabled && (
                                <>
                                    <Row gutter={16}>
                                        <Col span={12}>
                                            <Text strong style={{ fontSize: '12px' }}>İndirim Yüzdesi</Text>
                                            <InputNumber
                                                value={config.promotion.discount_percentage}
                                                onChange={(v) => updateConfig({ discount_percentage: v })}
                                                style={{ width: '100%', marginTop: 4, borderRadius: '8px' }}
                                                formatter={(val) => `%${val}`}
                                                parser={(val) => val?.replace('%', '') as any}
                                            />
                                        </Col>
                                        <Col span={12}>
                                            <Text strong style={{ fontSize: '12px' }}>Bitiş Tarihi</Text>
                                            <DatePicker
                                                value={config.promotion.end_date ? dayjs(config.promotion.end_date) : null}
                                                onChange={(date) => updateConfig({ promotion_end_date: date?.toISOString() })}
                                                style={{ width: '100%', marginTop: 4, borderRadius: '8px' }}
                                                showTime
                                            />
                                        </Col>
                                    </Row>
                                    <div>
                                        <Text strong style={{ fontSize: '12px' }}>Kampanya Mesajı</Text>
                                        <TextArea
                                            value={config.promotion.message || ''}
                                            onChange={(e) => updateConfig({ promotion_message: e.target.value })}
                                            rows={2}
                                            style={{ marginTop: 4, borderRadius: '8px' }}
                                            placeholder="Örn: Sınırlı süre için %20 lansman indirimi!"
                                        />
                                    </div>
                                </>
                            )}
                        </Flex>
                    </Card>
                </Col>

                <Col xs={24} lg={12}>
                    <Card
                        title={<Space><ClockCircleOutlined style={{ color: '#ec4899' }} /> <Text strong>Ücretsiz Deneme (Trial)</Text></Space>}
                        style={{ border: 'none', borderRadius: '16px', boxShadow: '0 4px 15px rgba(0,0,0,0.05)' }}
                    >
                        <Flex vertical gap="middle">
                            <Flex justify="space-between" align="center" style={{ padding: '8px 12px', background: '#f8fafc', borderRadius: '12px' }}>
                                <div>
                                    <Text strong style={{ display: 'block' }}>Deneme Süresini Aktifleştir</Text>
                                    <Text type="secondary" style={{ fontSize: '11px' }}>Yeni kullanıcılara kısıtlı süreli Pro erişim verir</Text>
                                </div>
                                <Switch
                                    checked={config.trial.enabled}
                                    onChange={(checked) => updateConfig({ trial_enabled: checked })}
                                />
                            </Flex>

                            {config.trial.enabled && (
                                <>
                                    <div>
                                        <Text strong style={{ fontSize: '12px' }}>Deneme Süresi (Gün)</Text>
                                        <InputNumber
                                            value={config.trial.duration_days}
                                            onChange={(val) => updateConfig({ trial_days: val })}
                                            style={{ width: '100%', marginTop: 4, borderRadius: '8px' }}
                                            min={1}
                                        />
                                    </div>
                                    <div style={{ background: '#fdf2f8', padding: '12px', borderRadius: '8px' }}>
                                        <Text strong style={{ color: '#be185d', fontSize: '12px' }}>🎁 Dahil Olan Özellikler</Text>
                                        <div style={{ marginTop: 4, opacity: 0.8, fontSize: '12px' }}>
                                            {config.trial.features_included.join(', ')}
                                        </div>
                                    </div>
                                </>
                            )}
                        </Flex>
                    </Card>
                </Col>
            </Row>

            <div style={{ marginTop: 16 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                    Last updated: {new Date(config.updated_at).toLocaleString()}
                </Text>
            </div>
        </div>
    );
};

export default PricingManager;
