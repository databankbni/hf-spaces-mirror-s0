import React, { useState, useEffect } from 'react';
import {
    Card,
    Input,
    Switch,
    Row,
    Col,
    Typography,
    Space,
    Button,
    Select,
    Spin,
    Flex,
    App,
    Divider,
    Slider,
} from 'antd';
import {
    BgColorsOutlined,
    LayoutOutlined,
    ReloadOutlined,
    PictureOutlined,
    GlobalOutlined,
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;
const { Option } = Select;

interface UIConfig {
    theme: {
        primary_color: string;
        secondary_color: string;
        dark_mode_supported: boolean;
        default_dark_mode: boolean;
        border_radius: number;
        font_family: string;
    };
    layout: {
        home_style: string;
        show_onboarding: boolean;
        bottom_nav_enabled: boolean;
        sidebar_enabled: boolean;
        chart_style: string;
    };
    custom_assets: Record<string, string>;
    updated_at: string;
}

const UIManager: React.FC = () => {
    const [config, setConfig] = useState<UIConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState(false);
    const { message } = App.useApp();

    const fetchConfig = async () => {
        setLoading(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/ui/config`);
            const data = await response.json();
            setConfig(data);
        } catch (error) {
            console.error(error);
            message.error('UI ayarları yüklenemedi');
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
            const response = await adminFetch(`${BACKEND_URL}/api/v1/ui/config`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });

            if (!response.ok) throw new Error('Güncelleme başarısız');
            const data = await response.json();
            setConfig(data);
            message.success('UI ayarları güncellendi');
        } catch (error) {
            console.error(error);
            message.error('Hata oluştu');
        } finally {
            setUpdating(false);
        }
    };

    if (loading || !config) {
        return <div style={{ textAlign: 'center', padding: '50px' }}><Spin size="large" /></div>;
    }

    return (
        <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
            <Flex justify="space-between" align="center" style={{ marginBottom: 32 }}>
                <div>
                    <Title level={2} style={{ margin: 0, letterSpacing: '-0.5px' }}>🎨 UI/UX Deneyim Merkezi</Title>
                    <Text type="secondary" style={{ fontSize: '14px' }}>Uygulama kimliğini, renk paletini ve görsel dilini anlık olarak yönetin</Text>
                </div>
                <Button
                    type="primary"
                    icon={<ReloadOutlined />}
                    onClick={fetchConfig}
                    disabled={updating}
                    style={{ borderRadius: '8px' }}
                >
                    Ayarları Yenile
                </Button>
            </Flex>

            <Row gutter={[24, 24]}>
                {/* THEME SETTINGS */}
                <Col xs={24} lg={12}>
                    <Card
                        variant="borderless"
                        style={{ borderRadius: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}
                        title={<Space><BgColorsOutlined style={{ color: '#6366f1' }} /> <Text strong>Marka Renkleri ve Stil</Text></Space>}
                    >
                        <Flex vertical gap="large">
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Text strong style={{ fontSize: '13px' }}>Ana Renk (Primary)</Text>
                                    <Flex gap="small" align="center" style={{ marginTop: 8 }}>
                                        <div style={{ width: 40, height: 40, backgroundColor: config.theme.primary_color, borderRadius: '8px', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.1)' }} />
                                        <Input
                                            value={config.theme.primary_color}
                                            onChange={(e) => updateConfig({ theme: { ...config.theme, primary_color: e.target.value } })}
                                            style={{ borderRadius: '6px' }}
                                        />
                                    </Flex>
                                </Col>
                                <Col span={12}>
                                    <Text strong style={{ fontSize: '13px' }}>İkincil Renk (Secondary)</Text>
                                    <Flex gap="small" align="center" style={{ marginTop: 8 }}>
                                        <div style={{ width: 40, height: 40, backgroundColor: config.theme.secondary_color, borderRadius: '8px', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.1)' }} />
                                        <Input
                                            value={config.theme.secondary_color}
                                            onChange={(e) => updateConfig({ theme: { ...config.theme, secondary_color: e.target.value } })}
                                            style={{ borderRadius: '6px' }}
                                        />
                                    </Flex>
                                </Col>
                            </Row>

                            <Divider style={{ margin: '8px 0' }} />

                            <div>
                                <Flex justify="space-between" align="center">
                                    <Text strong style={{ fontSize: '13px' }}>Köşe Yuvarlaklığı (Radius: {config.theme.border_radius}px)</Text>
                                </Flex>
                                <Slider
                                    min={0}
                                    max={24}
                                    value={config.theme.border_radius}
                                    onChange={(v) => updateConfig({ theme: { ...config.theme, border_radius: v } })}
                                    style={{ marginTop: 12 }}
                                />
                            </div>

                            <Flex justify="space-between" align="center" style={{ padding: '12px', background: '#f8fafc', borderRadius: '12px' }}>
                                <div>
                                    <Text strong style={{ display: 'block' }}>Karanlık Mod Desteği</Text>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>Uygulamanın gece moduna geçiş yapmasını sağlar</Text>
                                </div>
                                <Switch
                                    checked={config.theme.dark_mode_supported}
                                    onChange={(v) => updateConfig({ theme: { ...config.theme, dark_mode_supported: v } })}
                                />
                            </Flex>
                        </Flex>
                    </Card>
                </Col>

                {/* LAYOUT SETTINGS */}
                <Col xs={24} lg={12}>
                    <Card
                        variant="borderless"
                        style={{ borderRadius: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}
                        title={<Space><LayoutOutlined style={{ color: '#10b981' }} /> <Text strong>Tasarım ve Düzen</Text></Space>}
                    >
                        <Flex vertical gap="large">
                            <div>
                                <Text strong style={{ fontSize: '13px' }}>Ana Sayfa Tasarım Stili</Text>
                                <Select
                                    style={{ width: '100%', marginTop: 8 }}
                                    value={config.layout.home_style}
                                    onChange={(v) => updateConfig({ layout: { ...config.layout, home_style: v } })}
                                >
                                    <Option value="cards">Geniş Kartlar (Modern)</Option>
                                    <Option value="list">Kompakt Liste (Verimli)</Option>
                                    <Option value="minimal">Minimalist (Sade)</Option>
                                </Select>
                            </div>

                            <div>
                                <Text strong style={{ fontSize: '13px' }}>Veri Görselleştirme Stili</Text>
                                <Select
                                    style={{ width: '100%', marginTop: 8 }}
                                    value={config.layout.chart_style}
                                    onChange={(v) => updateConfig({ layout: { ...config.layout, chart_style: v } })}
                                >
                                    <Option value="line">Yumuşak Çizgi</Option>
                                    <Option value="area">Gölgeli Alan</Option>
                                    <Option value="bar">Modern Çubuk</Option>
                                </Select>
                            </div>

                            <Flex justify="space-between" align="center" style={{ padding: '12px', background: '#f8fafc', borderRadius: '12px' }}>
                                <div>
                                    <Text strong style={{ display: 'block' }}>Onboarding Ekranı</Text>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>Yeni kullanıcılara tanıtım ekranlarını gösterir</Text>
                                </div>
                                <Switch
                                    checked={config.layout.show_onboarding}
                                    onChange={(v) => updateConfig({ layout: { ...config.layout, show_onboarding: v } })}
                                />
                            </Flex>
                        </Flex>
                    </Card>
                </Col>

                {/* ASSETS */}
                <Col xs={24}>
                    <Card
                        variant="borderless"
                        style={{ borderRadius: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}
                        title={<Space><PictureOutlined style={{ color: '#f59e0b' }} /> <Text strong>Görsel Varlıklar ve Uzaktan Yönetilen Linkler</Text></Space>}
                    >
                        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
                            Uygulama markete güncelleme gitmeden, logo ve banner gibi görsel materyalleri anlık olarak değiştirebilirsiniz.
                        </Paragraph>
                        <Row gutter={24}>
                            <Col xs={24} md={12}>
                                <Text strong style={{ fontSize: '13px' }}>Uygulama Logo URL</Text>
                                <Input
                                    style={{ marginTop: 8, borderRadius: '8px' }}
                                    value={config.custom_assets.logo_url || ''}
                                    placeholder="https://example.com/logo.png"
                                    prefix={<GlobalOutlined style={{ opacity: 0.5 }} />}
                                    onChange={(e) => updateConfig({ custom_assets: { ...config.custom_assets, logo_url: e.target.value } })}
                                />
                            </Col>
                            <Col xs={24} md={12}>
                                <Text strong style={{ fontSize: '13px' }}>Kampanya / Karşılama Banner URL</Text>
                                <Input
                                    style={{ marginTop: 8, borderRadius: '8px' }}
                                    value={config.custom_assets.welcome_banner || ''}
                                    placeholder="https://example.com/banner.jpg"
                                    prefix={<GlobalOutlined style={{ opacity: 0.5 }} />}
                                    onChange={(e) => updateConfig({ custom_assets: { ...config.custom_assets, welcome_banner: e.target.value } })}
                                />
                            </Col>
                        </Row>
                    </Card>
                </Col>
            </Row>

            <div style={{ marginTop: 40, textAlign: 'center', opacity: 0.5 }}>
                <Text style={{ fontSize: 12 }}>
                    💎 Bu paneldeki değişiklikler mobil uygulama tarafından otomatik olarak senkronize edilir.
                </Text><br />
                <Text style={{ fontSize: 11 }}>
                    Son Güncelleme: {new Date(config.updated_at).toLocaleString()}
                </Text>
            </div>
        </div>
    );
};

export default UIManager;
