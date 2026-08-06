import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout as AntLayout, Menu, Typography, Switch, Space, Button, Avatar, Drawer, Empty, Alert, Flex } from 'antd';
import {
    DashboardOutlined,
    UserOutlined,
    BarChartOutlined,
    SyncOutlined,
    ToolOutlined,
    SettingOutlined,
    GlobalOutlined,
    NotificationOutlined,
    LineOutlined,
    LayoutOutlined,
    ThunderboltOutlined,
    InfoCircleOutlined,
    AuditOutlined,
    LogoutOutlined,
    SunOutlined,
    MoonOutlined,
    HeatMapOutlined,
    BankOutlined,
    CalendarOutlined,
    EyeOutlined,
    EyeInvisibleOutlined,
    AreaChartOutlined,
    DollarOutlined,
    WalletOutlined,
} from '@ant-design/icons';
import { Tooltip as AntTooltip } from 'antd';
import { useAuthStore } from '../store/authStore';
import { useThemeStore } from '../store/themeStore';
import { useMaskStore } from '../store/maskStore';
import { HELP_CONFIG } from '../constants/helpConfig';

const { Header, Sider, Content } = AntLayout;
const { Text, Paragraph } = Typography;

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
    const navigate = useNavigate();
    const { logout, user } = useAuthStore();
    const { isDark, toggleTheme } = useThemeStore();
    const { isMasked, toggleMasking } = useMaskStore();
    const [helpOpen, setHelpOpen] = useState(false);

    const currentPath = globalThis.location.pathname;
    // Map intelligence/profile/:id to /intelligence/profile
    const helpKey = currentPath.startsWith('/intelligence/profile') ? '/intelligence/profile' : currentPath;
    const pageHelp = HELP_CONFIG[helpKey];

    const menuItems = [
        {
            key: '/dashboard',
            icon: <DashboardOutlined />,
            label: 'Dashboard',
            onClick: () => { navigate('/'); },
        },
        {
            key: '/users',
            icon: <UserOutlined />,
            label: 'User Management',
            onClick: () => { navigate('/users'); },
        },
        {
            key: '/live',
            icon: <ThunderboltOutlined />,
            label: 'Live Intelligence',
            onClick: () => { navigate('/live'); },
        },
        {
            key: 'wealth_analysis',
            icon: <AreaChartOutlined />,
            label: 'Wealth Analysis',
            children: [
                {
                    key: '/wealth-monitor',
                    icon: <WalletOutlined />,
                    label: 'User Wealth Monitor',
                    onClick: () => { navigate('/wealth-monitor'); },
                },
                {
                    key: '/strategic',
                    icon: <HeatMapOutlined />,
                    label: 'Decision Panel',
                    onClick: () => { navigate('/strategic'); },
                },
                {
                    key: '/analytics',
                    icon: <BarChartOutlined />,
                    label: 'Analytics Insights',
                    onClick: () => { navigate('/analytics'); },
                },
            ]
        },
        {
            key: 'system',
            icon: <ToolOutlined />,
            label: 'System Engine',
            children: [
                {
                    key: '/system/tasks',
                    icon: <SyncOutlined />,
                    label: 'System Tasks',
                    onClick: () => { navigate('/system/tasks'); },
                },
                {
                    key: '/system/settings',
                    icon: <SettingOutlined />,
                    label: 'App Settings',
                    onClick: () => { navigate('/system/settings'); },
                },
                {
                    key: '/system/pricing',
                    icon: <DollarOutlined />,
                    label: 'Pricing & Promo',
                    onClick: () => { navigate('/system/pricing'); },
                },
                {
                    key: '/system/features',
                    icon: <LineOutlined />,
                    label: 'Feature Flags',
                    onClick: () => { navigate('/system/features'); },
                },
                {
                    key: '/system/announcements',
                    icon: <NotificationOutlined />,
                    label: 'App Announcements',
                    onClick: () => { navigate('/system/announcements'); },
                },
                {
                    key: '/system/ads',
                    icon: <GlobalOutlined />,
                    label: 'Ads Manager',
                    onClick: () => { navigate('/system/ads'); },
                },
                {
                    key: '/system/notifications',
                    icon: <NotificationOutlined />,
                    label: 'Push Notifications',
                    onClick: () => { navigate('/system/notifications'); },
                },
                {
                    key: '/system/limits',
                    icon: <LineOutlined />,
                    label: 'System Config',
                    onClick: () => { navigate('/system/limits'); },
                },
                {
                    key: '/system/ui',
                    icon: <LayoutOutlined />,
                    label: 'UI Components',
                    onClick: () => { navigate('/system/ui'); },
                },
                {
                    key: '/system/audit-logs',
                    icon: <AuditOutlined />,
                    label: 'Audit Logs',
                    onClick: () => { navigate('/system/audit-logs'); },
                },
                {
                    key: '/kvkk',
                    icon: <LogoutOutlined />,
                    label: 'KVKK Requests',
                    onClick: () => { navigate('/kvkk'); },
                },
                {
                    key: '/system/market-rates',
                    icon: <BankOutlined />,
                    label: 'Market Rates',
                    onClick: () => { navigate('/system/market-rates'); },
                },
                {
                    key: '/system/calendar',
                    icon: <CalendarOutlined />,
                    label: 'Economic Calendar',
                    onClick: () => { navigate('/system/calendar'); },
                },
            ]
        },
    ];

    return (
        <AntLayout style={{ minHeight: '100vh' }}>
            <Sider
                breakpoint="lg"
                collapsedWidth="0"
                theme={isDark ? 'dark' : 'light'}
                style={{
                    boxShadow: '2px 0 8px 0 rgba(29,35,41,.05)',
                    zIndex: 10
                }}
            >
                <div style={{
                    height: '64px',
                    display: 'flex',
                    alignItems: 'center',
                    padding: '0 24px',
                    background: isDark ? '#001529' : '#fff',
                    borderBottom: '1px solid ' + (isDark ? '#002140' : '#f0f0f0')
                }}>
                    <Text strong style={{ fontSize: '18px', color: '#1890ff' }}>MoneyPlan Pro</Text>
                </div>
                <Menu
                    mode="inline"
                    defaultSelectedKeys={[globalThis.location.pathname]}
                    items={menuItems}
                    theme={isDark ? 'dark' : 'light'}
                    style={{ borderRight: 0, marginTop: '8px' }}
                />
            </Sider>
            <AntLayout>
                <Header style={{
                    padding: '0 24px',
                    background: isDark ? '#001529' : '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    boxShadow: '0 1px 4px rgba(0,21,41,.08)',
                    zIndex: 9
                }}>
                    <Space size="large">
                        <Space>
                            {isDark ? <MoonOutlined style={{ color: '#fff' }} /> : <SunOutlined style={{ color: '#faad14' }} />}
                            <Switch
                                checked={isDark}
                                onChange={toggleTheme}
                                size="small"
                            />
                        </Space>
                        <AntTooltip title={isMasked ? "Unmask Sensitive Data" : "Mask Sensitive Data"}>
                            <Button
                                icon={isMasked ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                                onClick={toggleMasking}
                                type="text"
                                danger={!isMasked}
                                style={{ color: !isMasked ? '#ff4d4f' : (isDark ? '#fff' : '#1890ff') }}
                            >
                                {isMasked ? 'Masked' : 'Unmasked'}
                            </Button>
                        </AntTooltip>
                        <Button
                            icon={<InfoCircleOutlined />}
                            onClick={() => setHelpOpen(true)}
                            type="text"
                            style={{ color: isDark ? '#fff' : '#1890ff' }}
                        >
                            Info
                        </Button>
                        <div style={{
                            padding: '4px 12px',
                            background: isDark ? '#002140' : '#f5f5f5',
                            borderRadius: '16px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                        }}>
                            <Avatar size="small" icon={<UserOutlined />} />
                            <Text style={{ fontSize: '13px' }}>{user?.email}</Text>
                        </div>
                        <Button
                            type="text"
                            icon={<LogoutOutlined />}
                            onClick={logout}
                            danger
                        >
                            Logout
                        </Button>
                    </Space>
                </Header>
                <Content style={{ margin: '24px 24px 0', padding: '24px', background: isDark ? '#141414' : '#fff', borderRadius: '8px', minHeight: '280px' }}>
                    {children}
                </Content>
            </AntLayout>

            <Drawer
                title={<Space><InfoCircleOutlined style={{ color: '#1890ff' }} /> {pageHelp?.title || 'System Guide'}</Space>}
                placement="right"
                onClose={() => setHelpOpen(false)}
                open={helpOpen}
                styles={{ wrapper: { width: 400 } }}
            >
                {pageHelp ? (
                    <Flex vertical gap="large">
                        <div>
                            <Text strong style={{ display: 'block', marginBottom: '8px' }}>Nedir?</Text>
                            <Paragraph type="secondary">{pageHelp.description}</Paragraph>
                        </div>
                        <div>
                            <Text strong style={{ display: 'block', marginBottom: '8px' }}>Key Features</Text>
                            <ul style={{ paddingLeft: '20px', color: '#666' }}>
                                {pageHelp.features.map((f) => <li key={f} style={{ marginBottom: '4px' }}>{f}</li>)}
                            </ul>
                        </div>
                        <Alert
                            title="Dinamik Rehber"
                            description="Bu yardım içeriği bulunduğunuz sayfaya göre otomatik değişir."
                            type="info"
                            showIcon
                        />
                    </Flex>
                ) : (
                    <Empty description="Bu sayfa için henüz rehber içeriği eklenmedi." />
                )}
            </Drawer>
        </AntLayout>
    );
}
