import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Table, Card, Typography, Tag, Input, Space, Button, Modal, Flex, Select, Descriptions } from 'antd';
import { SearchOutlined, ReloadOutlined, EyeOutlined } from '@ant-design/icons';
import { supabase } from '../lib/supabase';
import type { ColumnsType } from 'antd/es/table';
import { maskEmail, maskIp, maskId, maskJson } from '../utils/mask';
import { useMaskStore } from '../store/maskStore';

const { Title, Text } = Typography;

interface AuditLog {
    id: number;
    user_id: string;
    action: string;
    table_name: string;
    record_id: string;
    old_data: any;
    new_data: any;
    ip_address: string;
    created_at: string;
    users?: {
        email: string;
        display_name: string;
    };
}

export default function AuditLogs() {
    const { isMasked } = useMaskStore();
    const [searchText, setSearchText] = useState('');
    const [filterAction, setFilterAction] = useState<string | null>(null);
    const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

    const { data: logs, isLoading, refetch } = useQuery({
        queryKey: ['audit-logs'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('audit_logs')
                .select(`
                    *,
                    users: user_id(email, display_name)
                `)
                .order('created_at', { ascending: false })
                .limit(100);

            if (error) {
                console.error('Error fetching audit logs:', error);
                return [];
            }
            return data as AuditLog[];
        },
    });

    const getActionColor = (action: string) => {
        if (action.includes('LOGIN')) return 'green';
        if (action.includes('DELETE')) return 'red';
        if (action.includes('UPDATE')) return 'blue';
        if (action.includes('INSERT') || action.includes('CREATE')) return 'cyan';
        return 'default';
    };

    const columns: ColumnsType<AuditLog> = [
        {
            title: 'Time',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 160,
            render: (date: string) => new Date(date).toLocaleString('tr-TR'),
            sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
        },
        {
            title: 'User',
            key: 'user',
            render: (record: AuditLog) => (
                <Flex vertical gap={0}>
                    <Text strong>{isMasked ? maskEmail(record.users?.email) : record.users?.email}</Text>
                    <Text type="secondary" style={{ fontSize: '11px' }}>{isMasked ? maskId(record.user_id) : record.user_id}</Text>
                </Flex>
            ),
        },
        {
            title: 'Action',
            key: 'action',
            render: (record: AuditLog) => (
                <Flex vertical gap={0}>
                    <Tag color={getActionColor(record.action)}>{record.action}</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>{record.table_name}</Text>
                </Flex>
            ),
            filters: [
                { text: 'Login', value: 'LOGIN' },
                { text: 'Update', value: 'UPDATE' },
                { text: 'Insert', value: 'INSERT' },
                { text: 'Delete', value: 'DELETE' },
            ],
            onFilter: (value, record) => record.action.includes(value as string),
        },
        {
            title: 'Record ID',
            dataIndex: 'record_id',
            key: 'record_id',
            render: (id: string) => <Text code>{isMasked ? maskId(id) : id}</Text>
        },
        {
            title: 'IP Address',
            dataIndex: 'ip_address',
            key: 'ip_address',
            render: (ip: string) => isMasked ? maskIp(ip) : ip
        },
        {
            title: 'Action',
            key: 'view',
            render: (record: AuditLog) => (
                <Button type="link" icon={<EyeOutlined />} onClick={() => setSelectedLog(record)}>View</Button>
            ),
        },
    ];

    const filteredLogs = logs?.filter(log => {
        const matchesSearch =
            log.action.toLowerCase().includes(searchText.toLowerCase()) ||
            log.users?.email.toLowerCase().includes(searchText.toLowerCase()) ||
            log.table_name?.toLowerCase().includes(searchText.toLowerCase()) ||
            log.user_id.includes(searchText);

        const matchesAction = filterAction ? log.action === filterAction : true;

        return matchesSearch && matchesAction;
    });

    const formatValue = (value: any): string => {
        if (value === null) return 'null';
        if (value === undefined) return 'undefined';
        if (typeof value === 'boolean') return value ? 'true' : 'false';
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
    };

    const renderLogDetails = (log: AuditLog) => {
        if (!log) return null;

        const isUpdate = log.action === 'UPDATE';
        const isDelete = log.action === 'DELETE';
        const isInsert = log.action === 'INSERT' || log.action === 'CREATE';

        const renderDataList = (data: any, color: 'green' | 'red' | 'default' = 'default') => {
            const maskedData = isMasked ? maskJson(data) : data;
            if (!maskedData) return <Text type="secondary">N/A</Text>;

            const colors = {
                green: { bg: '#f6ffed', border: '#b7eb8f' },
                red: { bg: '#fff1f0', border: '#ffa39e' },
                default: { bg: '#fafafa', border: '#f0f0f0' }
            };
            const theme = colors[color];

            return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {Object.entries(maskedData).map(([key, value]) => (
                        <div key={key} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            background: theme.bg,
                            border: `1px solid ${theme.border}`,
                            borderRadius: '6px'
                        }}>
                            <Text strong style={{ minWidth: '120px' }}>{key}</Text>
                            <Text style={{ wordBreak: 'break-all', fontFamily: 'monospace' }}>{formatValue(value)}</Text>
                        </div>
                    ))}
                </div>
            );
        };

        const renderDiff = (oldVal: any, newVal: any) => {
            const o = isMasked ? maskJson(oldVal || {}) : (oldVal || {});
            const n = isMasked ? maskJson(newVal || {}) : (newVal || {});
            const allKeys = Array.from(new Set([...Object.keys(o), ...Object.keys(n)]));

            return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 2fr 2fr', padding: '8px', background: '#f5f5f5', borderRadius: '4px', fontWeight: 'bold' }}>
                        <div>Field</div>
                        <div style={{ color: '#cf1322' }}>Old Value</div>
                        <div style={{ color: '#389e0d' }}>New Value</div>
                    </div>
                    {allKeys.map(key => {
                        const isChanged = formatValue(o[key]) !== formatValue(n[key]);
                        return (
                            <div key={key} style={{
                                display: 'grid',
                                gridTemplateColumns: '1.5fr 2fr 2fr',
                                gap: '8px',
                                padding: '8px',
                                background: isChanged ? '#e6f7ff' : 'transparent',
                                borderBottom: '1px solid #f0f0f0'
                            }}>
                                <Text strong>{key}</Text>
                                <Text style={{ wordBreak: 'break-all', color: isChanged ? '#cf1322' : '#8c8c8c' }}>
                                    {o[key] === undefined ? '-' : formatValue(o[key])}
                                </Text>
                                <Text style={{ wordBreak: 'break-all', color: isChanged ? '#389e0d' : '#8c8c8c' }}>
                                    {n[key] === undefined ? '-' : formatValue(n[key])}
                                </Text>
                            </div>
                        );
                    })}
                </div>
            );
        };

        return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <Descriptions title="Log Metadata" bordered column={2}>
                    <Descriptions.Item label="Table"><Tag color="geekblue">{log.table_name}</Tag></Descriptions.Item>
                    <Descriptions.Item label="Action"><Tag color={getActionColor(log.action)}>{log.action}</Tag></Descriptions.Item>
                    <Descriptions.Item label="Record ID"><Text code>{isMasked ? maskId(log.record_id) : log.record_id}</Text></Descriptions.Item>
                    <Descriptions.Item label="IP Address">{isMasked ? maskIp(log.ip_address) : log.ip_address}</Descriptions.Item>
                    <Descriptions.Item label="User" span={2}>{isMasked ? maskEmail(log.users?.email) : log.users?.email} ({isMasked ? maskId(log.user_id) : log.user_id})</Descriptions.Item>
                </Descriptions>

                {isUpdate && (
                    <Card title="Data Changes" size="small">
                        {renderDiff(log.old_data, log.new_data)}
                    </Card>
                )}

                {isInsert && (
                    <Card title="Inserted Data" size="small">
                        {renderDataList(log.new_data, 'green')}
                    </Card>
                )}

                {isDelete && (
                    <Card title="Deleted Data" size="small">
                        {renderDataList(log.old_data, 'red')}
                    </Card>
                )}
            </div>
        );
    };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <Title level={2} style={{ margin: 0 }}>🛡️ Audit Logs</Title>
                <Space>
                    <Select
                        placeholder="Action Filter"
                        allowClear
                        style={{ width: 150 }}
                        onChange={value => setFilterAction(value)}
                        options={[
                            { value: 'LOGIN', label: 'Login' },
                            { value: 'INSERT', label: 'Insert' },
                            { value: 'UPDATE', label: 'Update' },
                            { value: 'DELETE', label: 'Delete' },
                        ]}
                    />
                    <Input
                        placeholder="Search logs..."
                        prefix={<SearchOutlined />}
                        onChange={e => setSearchText(e.target.value)}
                        style={{ width: 300 }}
                    />
                    <Button icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>
                </Space>
            </div>

            <Card>
                <Table
                    columns={columns}
                    dataSource={filteredLogs}
                    loading={isLoading}
                    rowKey="id"
                    pagination={{ pageSize: 15 }}
                />
            </Card>

            <Modal
                title={`Log Details #${selectedLog?.id}`}
                open={!!selectedLog}
                onCancel={() => setSelectedLog(null)}
                footer={[<Button key="close" onClick={() => setSelectedLog(null)}>Close</Button>]}
                width={800}
            >
                {selectedLog && renderLogDetails(selectedLog)}
            </Modal>
        </div>
    );
}
