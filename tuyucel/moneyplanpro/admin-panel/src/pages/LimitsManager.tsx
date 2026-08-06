import React, { useState, useEffect } from 'react';
import {
    Card,
    InputNumber,
    Switch,
    Typography,
    Space,
    Row,
    Col,
    Button,
    Divider,
    Alert,
    Spin,
    Tag,
    Flex,
    App,
    Input,
    Tabs,
    Tooltip
} from 'antd';
import {
    CrownOutlined,
    RobotOutlined,
    SearchOutlined,
    InfoCircleOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    SettingOutlined,
    ExperimentOutlined
} from '@ant-design/icons';
import { supabase } from '../lib/supabase';
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const { Title, Text, Paragraph } = Typography;
const BACKEND_URL = API_BASE_URL;

// --- TYPES ---
interface FeatureFlag {
    id: string;
    name: string;
    description: string;
    is_pro: boolean;
    is_enabled: boolean;
    daily_free_limit: number | null;
    metadata: Record<string, any>;
    updated_at: string;
}

// --- SUB-COMPONENTS ---

const LimitsTab: React.FC = () => {
    const [loading, setLoading] = useState(true);
    const { message } = App.useApp();
    const [config, setConfig] = useState<Record<string, any>>({});

    // User Premium Management State
    const [searchEmail, setSearchEmail] = useState('');
    const [userResult, setUserResult] = useState<any>(null);
    const [searchingUser, setSearchingUser] = useState(false);

    const fetchConfig = async () => {
        setLoading(true);
        try {
            const { data, error } = await supabase
                .from('app_config')
                .select('key, value');

            if (error) throw error;

            const configMap: Record<string, any> = {};
            data?.forEach(item => {
                configMap[item.key] = item.value;
            });
            setConfig(configMap);
        } catch (error) {
            console.error(error);
            message.error('Limit ayarları yüklenemedi');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchConfig();
    }, []);

    const updateConfig = async (key: string, value: any) => {
        try {
            const { error } = await supabase
                .from('app_config')
                .upsert({ key, value });

            if (error) throw error;

            setConfig(prev => ({ ...prev, [key]: value }));
            message.success('Limit güncellendi');
        } catch (error) {
            console.error(error);
            message.error('Güncelleme hatası');
        }
    };

    const searchUser = async () => {
        if (!searchEmail) return;
        setSearchingUser(true);
        try {
            const { data, error } = await supabase
                .from('users')
                .select('id, email, is_premium, display_name')
                .eq('email', searchEmail)
                .maybeSingle();

            if (error) throw error;

            if (data) {
                setUserResult(data);
                message.success('Kullanıcı bulundu');
            } else {
                setUserResult(null);
                message.warning('Kullanıcı bulunamadı');
            }
        } catch (err) {
            console.error(err);
            message.error('Arama hatası');
        } finally {
            setSearchingUser(false);
        }
    };

    const togglePremium = async () => {
        if (!userResult) return;
        try {
            const newStatus = !userResult.is_premium;
            const { error } = await supabase
                .from('users')
                .update({ is_premium: newStatus })
                .eq('id', userResult.id);

            if (error) throw error;

            setUserResult({ ...userResult, is_premium: newStatus });
            message.success(`Kullanıcı ${newStatus ? 'Premium yapıldı' : 'Free üyeliğe döndürüldü'}`);
        } catch (err) {
            console.error(err);
            message.error('İşlem başarısız');
        }
    };

    const renderLimitItem = (label: string, valueName: string, defaultValue: number) => (
        <Row align="middle" style={{ marginBottom: 12 }}>
            <Col span={16}><Text>{label}</Text></Col>
            <Col span={8}>
                <InputNumber
                    style={{ width: '100%' }}
                    value={config[valueName] ? Number.parseInt(config[valueName]) : defaultValue}
                    onChange={(val) => updateConfig(valueName, val)}
                />
            </Col>
        </Row>
    );

    if (loading) return <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>;

    return (
        <Row gutter={[16, 16]}>
            {/* AI LIMITS */}
            <Col xs={24} md={12}>
                <Card title={<Space><RobotOutlined /> AI Asistan Limitleri (Aylık)</Space>}>
                    <Alert
                        title="Dinamik Limitler"
                        description="Bu değerler mobil uygulamaya anlık yansır. Kullanıcılar limitlerini doldurduğunda bu değerler baz alınır."
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                    />
                    {renderLimitItem('Free Kullanıcı Limiti', 'ai_limit_monthly_free', 3)}
                    {renderLimitItem('Premium Kullanıcı Limiti', 'ai_limit_monthly_premium', 10)}
                </Card>
            </Col>

            {/* USER PREMIUM MANAGER */}
            <Col xs={24} md={12}>
                <Card title={<Space><CrownOutlined style={{ color: '#faad14' }} /> Kullanıcı Premium Yönetimi</Space>}>
                    <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
                        <Input
                            placeholder="Kullanıcı E-posta Ara..."
                            value={searchEmail}
                            onChange={e => setSearchEmail(e.target.value)}
                            onPressEnter={searchUser}
                        />
                        <Button type="primary" icon={<SearchOutlined />} onClick={searchUser} loading={searchingUser}>Ara</Button>
                    </Space.Compact>

                    {userResult ? (
                        <div style={{ padding: 16, background: '#f5f5f5', borderRadius: 8 }}>
                            <Flex justify="space-between" align="center">
                                <div>
                                    <Text strong style={{ display: 'block' }}>{userResult.email}</Text>
                                    <Text type="secondary" style={{ fontSize: 12 }}>{userResult.id}</Text>
                                    <div style={{ marginTop: 8 }}>
                                        {userResult.is_premium ?
                                            <Tag color="gold" icon={<CrownOutlined />}>PREMIUM</Tag> :
                                            <Tag color="default">FREE</Tag>
                                        }
                                    </div>
                                </div>
                                <Button
                                    type={userResult.is_premium ? 'default' : 'primary'}
                                    danger={userResult.is_premium}
                                    onClick={togglePremium}
                                >
                                    {userResult.is_premium ? 'Free Yap' : 'Premium Yap'}
                                </Button>
                            </Flex>
                        </div>
                    ) : (
                        <div style={{ textAlign: 'center', padding: '20px', color: '#999' }}>
                            Kullanıcı aramak için e-posta girin
                        </div>
                    )}
                </Card>
            </Col>
        </Row>
    );
};

const FeaturesTab: React.FC = () => {
    const [flags, setFlags] = useState<Record<string, FeatureFlag>>({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState<string | null>(null);
    const { message: messageApi } = App.useApp();

    const fetchFlags = async () => {
        setLoading(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/features`);
            const data = await response.json();
            setFlags(data.features || {});
        } catch (error) {
            console.error(error);
            messageApi.error('Failed to load feature flags');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchFlags();
    }, []);

    const updateFlag = async (flagId: string, updates: Partial<FeatureFlag>) => {
        setSaving(flagId);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/features/${flagId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });

            if (!response.ok) throw new Error('Update failed');

            const result = await response.json();
            setFlags((prev) => ({
                ...prev,
                [flagId]: result.flag,
            }));
            messageApi.success(`${flags[flagId].name} updated`);
        } catch (error) {
            console.error(error);
            messageApi.error('Failed to update feature');
        } finally {
            setSaving(null);
        }
    };

    if (loading) return <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>;

    return (
        <Row gutter={[16, 16]}>
            {Object.entries(flags).map(([flagId, flag]) => (
                <Col xs={24} md={12} lg={8} key={flagId}>
                    <Card
                        title={
                            <Flex vertical style={{ width: '100%' }}>
                                <Text strong style={{ fontSize: 16 }}>{flag.name}</Text>
                                <Tag color="default" style={{ fontSize: 11 }}>{flag.id}</Tag>
                            </Flex>
                        }
                        extra={
                            <Tooltip title="Feature ID for app integration">
                                <InfoCircleOutlined />
                            </Tooltip>
                        }
                        loading={saving === flagId}
                        style={{ height: '100%' }}
                    >
                        <Flex vertical gap="middle" style={{ width: '100%' }}>
                            <Paragraph type="secondary" style={{ marginBottom: 0, minHeight: 40 }}>
                                {flag.description}
                            </Paragraph>

                            <Divider style={{ margin: '8px 0' }} />

                            <div>
                                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                                    <Flex vertical>
                                        <Text strong>Enabled</Text>
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                            {flag.is_enabled ? (
                                                <><CheckCircleOutlined style={{ color: '#52c41a' }} /> Active</>
                                            ) : (
                                                <><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> Disabled</>
                                            )}
                                        </Text>
                                    </Flex>
                                    <Switch
                                        size="small"
                                        checked={flag.is_enabled}
                                        onChange={(checked) => updateFlag(flagId, { is_enabled: checked })}
                                        disabled={saving === flagId}
                                    />
                                </Space>
                            </div>

                            <div>
                                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                                    <Flex vertical>
                                        <Text strong>PRO Only</Text>
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                            {flag.is_pro ? 'Premium Users' : 'All Users'}
                                        </Text>
                                    </Flex>
                                    <Switch
                                        size="small"
                                        checked={flag.is_pro}
                                        onChange={(checked) => updateFlag(flagId, { is_pro: checked })}
                                        disabled={saving === flagId}
                                        style={{ backgroundColor: flag.is_pro ? '#faad14' : undefined }}
                                    />
                                </Space>
                            </div>

                            <div>
                                <Text strong>Daily Limits</Text>
                                <Row gutter={12}>
                                    <Col span={12}>
                                        <Text type="secondary" style={{ fontSize: 12 }}>Free User Limit</Text>
                                        <InputNumber
                                            style={{ width: '100%', marginTop: 4 }}
                                            value={flag.daily_free_limit}
                                            onChange={(value) => updateFlag(flagId, { daily_free_limit: value })}
                                            disabled={saving === flagId}
                                            placeholder="Unlimited"
                                            min={0}
                                        />
                                    </Col>
                                    <Col span={12}>
                                        <Text type="secondary" style={{ fontSize: 12 }}>Pro User Limit</Text>
                                        <InputNumber
                                            style={{ width: '100%', marginTop: 4 }}
                                            value={flag.metadata?.daily_pro_limit ?? null}
                                            onChange={(value) => updateFlag(flagId, {
                                                metadata: { ...flag.metadata, daily_pro_limit: value }
                                            })}
                                            disabled={saving === flagId}
                                            placeholder="Unlimited"
                                            min={0}
                                        />
                                    </Col>
                                </Row>
                            </div>

                            <Text type="secondary" style={{ fontSize: 10, textAlign: 'right' }}>
                                Updated: {new Date(flag.updated_at).toLocaleDateString()}
                            </Text>
                        </Flex>
                    </Card>
                </Col>
            ))}
        </Row>
    );
};

// --- MAIN PAGE ---

const LimitsManager: React.FC = () => {
    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: 24 }}>
                <Title level={2} style={{ margin: 0 }}>System Configuration</Title>
                <Text type="secondary">Manage application limits, user tiers, and feature flags.</Text>
            </div>

            <Tabs
                defaultActiveKey="1"
                items={[
                    {
                        key: '1',
                        label: <Space><SettingOutlined /> Limits & Premium</Space>,
                        children: <LimitsTab />,
                    },
                    {
                        key: '2',
                        label: <Space><ExperimentOutlined /> Feature Flags</Space>,
                        children: <FeaturesTab />,
                    },
                ]}
            />
        </div>
    );
};

export default LimitsManager;
