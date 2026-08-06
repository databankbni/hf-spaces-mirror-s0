import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Table, Typography, Button, Space, Modal, Input, App, Tag, Tooltip, Empty } from 'antd';
import {
    DeleteOutlined,
    ImportOutlined,
    SyncOutlined
} from '@ant-design/icons';
import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const { Title, Text } = Typography;
const { TextArea } = Input;

const BACKEND_URL = `${API_BASE_URL}/api/v1`;

export default function CalendarManager() {
    const { message, modal } = App.useApp();
    const queryClient = useQueryClient();
    const [importModalOpen, setImportModalOpen] = useState(false);
    const [jsonInput, setJsonInput] = useState('');

    const { data: events, isLoading, refetch } = useQuery({
        queryKey: ['admin_calendar'],
        queryFn: async () => {
            const resp = await adminFetch(`${BACKEND_URL}/system/calendar?limit=200`);
            if (!resp.ok) throw new Error('Failed to fetch calendar');
            return resp.json();
        },
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: number) => {
            const resp = await adminFetch(`${BACKEND_URL}/system/calendar/${id}`, {
                method: 'DELETE'
            });
            if (!resp.ok) throw new Error('Delete failed');
        },
        onSuccess: () => {
            message.success('Event deleted');
            queryClient.invalidateQueries({ queryKey: ['admin_calendar'] });
        },
    });

    const importMutation = useMutation({
        mutationFn: async (payload: { events: any[], clear: boolean }) => {
            const resp = await adminFetch(`${BACKEND_URL}/market/calendar?clear=${payload.clear}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ events: payload.events })
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || 'Import failed');
            }
        },
        onSuccess: () => {
            message.success('Data imported successfully');
            setImportModalOpen(false);
            setJsonInput('');
            queryClient.invalidateQueries({ queryKey: ['admin_calendar'] });
        },
        onError: (err: any) => {
            message.error('Import failed: ' + (err.response?.data?.detail || err.message));
        }
    });

    const handleDelete = (record: any) => {
        modal.confirm({
            title: 'Are you sure?',
            content: `Deleting: ${record.title}`,
            okText: 'Delete',
            okType: 'danger',
            onOk: () => deleteMutation.mutate(record.id),
        });
    };

    const handleImport = () => {
        try {
            const parsed = JSON.parse(jsonInput);
            const eventsArray = Array.isArray(parsed) ? parsed : (parsed.events || []);

            if (eventsArray.length === 0) {
                message.warning('No events found in JSON');
                return;
            }

            modal.confirm({
                title: 'Import Mode',
                content: 'Do you want to clear existing data before importing?',
                okText: 'Clear & Import',
                cancelText: 'Just Append',
                onOk: () => importMutation.mutate({ events: eventsArray, clear: true }),
                onCancel: () => importMutation.mutate({ events: eventsArray, clear: false }),
            });
        } catch (e) {
            message.error('Invalid JSON format');
        }
    };

    const columns = [
        {
            title: 'Date & Time',
            dataIndex: 'date_time',
            key: 'date_time',
            width: 180,
            render: (dt: string) => (
                <Space direction="vertical" size={0}>
                    <Text strong>{new Date(dt).toLocaleDateString('tr-TR')}</Text>
                    <Text type="secondary" style={{ fontSize: '12px' }}>{new Date(dt).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</Text>
                </Space>
            )
        },
        {
            title: 'Country',
            dataIndex: 'currency',
            key: 'currency',
            width: 100,
            render: (curr: string, record: any) => (
                <Space>
                    <Tag color="blue">{curr || 'Global'}</Tag>
                    <Text type="secondary">(ID: {record.country_id})</Text>
                </Space>
            )
        },
        {
            title: 'Event Title',
            dataIndex: 'title',
            key: 'title',
            render: (text: string) => <Text strong>{text}</Text>
        },
        {
            title: 'Impact',
            dataIndex: 'impact',
            key: 'impact',
            width: 100,
            render: (impact: string) => {
                let color = 'blue';
                if (impact === 'High') color = 'red';
                else if (impact === 'Medium') color = 'orange';
                return <Tag color={color}>{impact.toUpperCase()}</Tag>;
            }
        },
        {
            title: 'Values',
            key: 'values',
            render: (_: any, record: any) => (
                <Space size="middle">
                    <Tooltip title="Actual">
                        <Tag color="cyan">A: {record.actual || '-'}</Tag>
                    </Tooltip>
                    <Tooltip title="Forecast">
                        <Tag color="purple">F: {record.forecast || '-'}</Tag>
                    </Tooltip>
                    <Tooltip title="Previous">
                        <Tag color="default">P: {record.previous || '-'}</Tag>
                    </Tooltip>
                </Space>
            )
        },
        {
            title: 'Action',
            key: 'action',
            width: 80,
            render: (_: any, record: any) => (
                <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => handleDelete(record)}
                />
            ),
        },
    ];

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <Title level={2} style={{ margin: 0 }}>Economic Calendar Manager</Title>
                    <Text type="secondary">Manage "Static" calendar events. FXStreet API remains the primary live source.</Text>
                </div>
                <Space>
                    <Button icon={<SyncOutlined />} onClick={() => refetch()}>Refresh</Button>
                    <Button type="primary" icon={<ImportOutlined />} onClick={() => setImportModalOpen(true)}>
                        Import JSON
                    </Button>
                </Space>
            </div>

            <Card styles={{ body: { padding: 0 } }}>
                <Table
                    loading={isLoading}
                    dataSource={events}
                    columns={columns}
                    rowKey="id"
                    pagination={{ pageSize: 15 }}
                    locale={{ emptyText: <Empty description="No manual events in database" /> }}
                />
            </Card>

            <Modal
                title="Import Calendar Data"
                open={importModalOpen}
                onOk={handleImport}
                onCancel={() => setImportModalOpen(false)}
                okText="Process JSON"
                width={700}
                confirmLoading={importMutation.isPending}
            >
                <div style={{ marginBottom: '16px' }}>
                    <Text type="secondary">Paste your calendar JSON here. Expected format: <code>Array&lt;Event&gt;</code> or <code>{"{ events: [] }"}</code></Text>
                </div>
                <TextArea
                    rows={15}
                    placeholder='[ { "title": "...", "date_time": "2026-01-26 10:00:00", "impact": "High", ... } ]'
                    value={jsonInput}
                    onChange={(e) => setJsonInput(e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '12px' }}
                />
            </Modal>
        </div>
    );
}
