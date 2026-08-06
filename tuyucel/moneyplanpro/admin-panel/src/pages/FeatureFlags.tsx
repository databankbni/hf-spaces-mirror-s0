import React, { useState, useEffect } from 'react';
import {
    Card,
    Switch,
    InputNumber,
    Button,
    Alert,
    Row,
    Col,
    Typography,
    Tag,
    Space,
    Divider,
    Tooltip,
    Spin,
    Flex,
    App,
} from 'antd';
import {
    ReloadOutlined,
    InfoCircleOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;

interface FeatureFlag {
    id: string;
    name: string;
    description: string;
    is_pro: boolean;
    is_enabled: boolean;
    daily_free_limit: number | null;
    metadata: Record<string, any>;
    created_at: string;
    updated_at: string;
}

interface FeatureFlagsResponse {
    features: Record<string, FeatureFlag>;
    version: number;
    cached_until: string;
}

const FeatureFlags: React.FC = () => {
    const [flags, setFlags] = useState<Record<string, FeatureFlag>>({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState<string | null>(null);
    const [version, setVersion] = useState<number>(0);
    const { message } = App.useApp();

    const fetchFlags = async () => {
        setLoading(true);
        try {
            const response = await adminFetch(`${BACKEND_URL}/api/v1/features`);
            const data: FeatureFlagsResponse = await response.json();
            setFlags(data.features);
            setVersion(data.version);
            message.success('Feature flags loaded successfully');
        } catch (error) {
            message.error('Failed to load feature flags');
            console.error('Error fetching flags:', error);
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
            message.success(`${flags[flagId].name} updated successfully`);
        } catch (error) {
            message.error('Failed to update feature flag');
            console.error('Error updating flag:', error);
        } finally {
            setSaving(null);
        }
    };

    const handleTogglePro = (flagId: string, checked: boolean) => {
        updateFlag(flagId, { is_pro: checked });
    };

    const handleToggleEnabled = (flagId: string, checked: boolean) => {
        updateFlag(flagId, { is_enabled: checked });
    };

    const handleUpdateLimit = (flagId: string, value: number | null) => {
        updateFlag(flagId, { daily_free_limit: value });
    };

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: '50px' }}>
                <Spin size="large" />
                <div style={{ marginTop: 16 }}>Loading feature flags...</div>
            </div>
        );
    }

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={2} style={{ margin: 0 }}>Feature Flags</Title>
                    <Text type="secondary">Control app features remotely without deploying to stores</Text>
                </div>
                <Space>
                    <Tag color="blue">Version: {version}</Tag>
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={fetchFlags}
                        loading={loading}
                    >
                        Refresh
                    </Button>
                </Space>
            </div>

            <Alert
                description={
                    <>
                        <Text strong style={{ display: 'block', marginBottom: 8 }}>💡 How it works</Text>
                        <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
                            <li>Changes take effect immediately without app store deployment</li>
                            <li>App caches flags for up to 5 minutes to reduce API calls</li>
                            <li>PRO features require active subscription</li>
                            <li>Daily limits reset at midnight (user's local time)</li>
                            <li>Disabled features are hidden from the app</li>
                            <li>Release-blocker flags fail closed if remote configuration cannot be loaded</li>
                        </ul>
                    </>
                }
                type="info"
                showIcon
                style={{ marginBottom: 24 }}
            />

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
                                <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                                    {flag.description}
                                </Paragraph>

                                <Divider style={{ margin: '8px 0' }} />

                                <div>
                                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                                        <Flex vertical>
                                            <Text strong>Enabled</Text>
                                            <Text type="secondary" style={{ fontSize: 12 }}>
                                                {flag.is_enabled ? (
                                                    <><CheckCircleOutlined style={{ color: '#52c41a' }} /> Feature is active</>
                                                ) : (
                                                    <><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> Feature is disabled</>
                                                )}
                                            </Text>
                                        </Flex>
                                        <Switch
                                            checked={flag.is_enabled}
                                            onChange={(checked) => handleToggleEnabled(flagId, checked)}
                                            disabled={saving === flagId}
                                        />
                                    </Space>
                                </div>

                                <div>
                                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                                        <Flex vertical>
                                            <Text strong>PRO Feature</Text>
                                            <Text type="secondary" style={{ fontSize: 12 }}>
                                                {flag.is_pro ? 'Requires PRO subscription' : 'Available to all users'}
                                            </Text>
                                        </Flex>
                                        <Switch
                                            checked={flag.is_pro}
                                            onChange={(checked) => handleTogglePro(flagId, checked)}
                                            disabled={saving === flagId}
                                            style={{ backgroundColor: flag.is_pro ? '#faad14' : undefined }}
                                        />
                                    </Space>
                                </div>

                                <div>
                                    <Text strong>Daily Free Limit</Text>
                                    <InputNumber
                                        style={{ width: '100%', marginTop: 8 }}
                                        value={flag.daily_free_limit}
                                        onChange={(value) => handleUpdateLimit(flagId, value)}
                                        disabled={saving === flagId}
                                        placeholder="Unlimited"
                                        min={0}
                                    />
                                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                                        {(() => {
                                            if (flag.daily_free_limit === null) return 'Unlimited usage';
                                            if (flag.daily_free_limit === 0) return 'No free usage';
                                            return `${flag.daily_free_limit} use(s) per day`;
                                        })()}
                                    </Text>
                                </div>

                                {flag.metadata && Object.keys(flag.metadata).length > 0 && (
                                    <div>
                                        <Text strong>Metadata</Text>
                                        <pre style={{
                                            background: '#f5f5f5',
                                            padding: 8,
                                            borderRadius: 4,
                                            fontSize: 11,
                                            marginTop: 8,
                                            marginBottom: 0,
                                            overflow: 'auto'
                                        }}>
                                            {JSON.stringify(flag.metadata, null, 2)}
                                        </pre>
                                    </div>
                                )}

                                <Text type="secondary" style={{ fontSize: 11 }}>
                                    Last updated: {new Date(flag.updated_at).toLocaleString()}
                                </Text>
                            </Flex>
                        </Card>
                    </Col>
                ))}
            </Row>
        </div>
    );
};

export default FeatureFlags;
