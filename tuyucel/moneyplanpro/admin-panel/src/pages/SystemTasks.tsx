import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Card,
    Table,
    Button,
    Tag,
    Typography,
    Space,
    App,
    Drawer,
    Flex,
    Alert,
    Modal,
    Input,
    Tooltip,
    Form,
} from 'antd';
import {
    PlayCircleOutlined,
    SyncOutlined,
    CodeOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    ClockCircleOutlined,
    EditOutlined
} from '@ant-design/icons';
import { useState } from 'react';

const { Title, Text } = Typography;

import { API_BASE_URL } from '../config';
import { adminFetch } from '../lib/adminFetch';

const BACKEND_URL = API_BASE_URL;

interface Job {
    id: string;
    name: string;
    description: string;
    type: 'script' | 'internal';
    status: 'idle' | 'running' | 'success' | 'failed' | 'error';
    last_run: string | null;
    output: string;
    path?: string;
    args?: string[] | string;
    service?: string;
    method?: string;
}

export default function SystemTasks() {
    const queryClient = useQueryClient();
    const { message: messageApi } = App.useApp();
    const [selectedJob, setSelectedJob] = useState<Job | null>(null);
    const [editingJob, setEditingJob] = useState<Job | null>(null);
    const [form] = Form.useForm();

    // 1. Fetch Jobs
    const { data: jobs, isLoading } = useQuery<Job[]>({
        queryKey: ['system-jobs'],
        queryFn: async () => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/jobs`);
            if (!resp.ok) throw new Error('Backend connection failed');
            return resp.json();
        },
        refetchInterval: (query) => {
            return query.state.data?.some((j: Job) => j.status === 'running') ? 2000 : 10000;
        },
    });

    // 2. Run Job Mutation
    const runMutation = useMutation({
        mutationFn: async (job_id: string) => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/jobs/${job_id}/run`, {
                method: 'POST'
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Job failed to start');
            }
            return resp.json();
        },
        onSuccess: () => {
            void messageApi.success('Job started successfully');
            void queryClient.invalidateQueries({ queryKey: ['system-jobs'] });
        },
        onError: (err: Error) => {
            void messageApi.error(err.message);
        }
    });

    // 3. Update Job Mutation
    const updateMutation = useMutation({
        mutationFn: async ({ id, updates }: { id: string, updates: any }) => {
            const resp = await adminFetch(`${BACKEND_URL}/api/v1/system/jobs/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            if (!resp.ok) throw new Error('Failed to update job');
            return resp.json();
        },
        onSuccess: () => {
            void messageApi.success('Job updated successfully');
            setEditingJob(null);
            void queryClient.invalidateQueries({ queryKey: ['system-jobs'] });
        },
        onError: (err: Error) => {
            void messageApi.error(err.message);
        }
    });

    const getStatusTag = (status: Job['status']) => {
        switch (status) {
            case 'running': return <Tag icon={<SyncOutlined spin />} color="processing">RUNNING</Tag>;
            case 'success': return <Tag icon={<CheckCircleOutlined />} color="success">SUCCESS</Tag>;
            case 'failed':
            case 'error': return <Tag icon={<CloseCircleOutlined />} color="error">FAILED</Tag>;
            default: return <Tag color="default">IDLE</Tag>;
        }
    };

    const handleEdit = (job: Job) => {
        setEditingJob(job);
        form.setFieldsValue({
            ...job,
            args: Array.isArray(job.args) ? JSON.stringify(job.args) : (job.args || '[]')
        });
    };

    const onEditFinish = (values: any) => {
        if (!editingJob) return;

        const updates = { ...values };
        if (updates.args) {
            try {
                updates.args = JSON.parse(updates.args);
            } catch (err) {
                console.error('Failed to parse JSON arguments:', err);
                void messageApi.error('Invalid JSON in arguments');
                return;
            }
        }

        updateMutation.mutate({ id: editingJob.id, updates });
    };

    const columns = [
        {
            title: 'Sistem Görevi / Script',
            dataIndex: 'name',
            key: 'name',
            render: (text: string, record: Job) => (
                <Flex vertical gap={4}>
                    <Space size={4}>
                        <CodeOutlined style={{ color: '#6366f1' }} />
                        <Text strong style={{ fontSize: '15px' }}>{text}</Text>
                    </Space>
                    <Text type="secondary" style={{ fontSize: '12px' }}>{record.description}</Text>
                    {record.type === 'script' && (
                        <div style={{ background: '#f8fafc', padding: '4px 8px', borderRadius: '4px', border: '1px solid #f1f5f9' }}>
                            <Text code style={{ fontSize: '11px', color: '#64748b' }}>
                                📂 {record.path} {Array.isArray(record.args) ? record.args.join(' ') : ''}
                            </Text>
                        </div>
                    )}
                </Flex>
            )
        },
        {
            title: 'Durum',
            dataIndex: 'status',
            key: 'status',
            width: 150,
            render: (status: Job['status']) => getStatusTag(status)
        },
        {
            title: 'Son Çalıştırma',
            dataIndex: 'last_run',
            key: 'last_run',
            width: 180,
            render: (val: string | null) => val ? (
                <Flex vertical gap={2}>
                    <Text style={{ fontSize: '13px' }}>{new Date(val).toLocaleDateString()}</Text>
                    <Text type="secondary" style={{ fontSize: '11px' }}>{new Date(val).toLocaleTimeString()}</Text>
                </Flex>
            ) : <Text type="secondary" italic>Hiç çalışmadı</Text>
        },
        {
            title: 'İşlemler',
            key: 'actions',
            width: 220,
            render: (record: Job) => (
                <Space size="middle">
                    <Button
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        loading={record.status === 'running' || runMutation.isPending}
                        onClick={() => runMutation.mutate(record.id)}
                        style={{ borderRadius: '8px', background: '#6366f1' }}
                    >
                        Başlat
                    </Button>
                    <Tooltip title="Logları Gör">
                        <Button
                            icon={<CodeOutlined />}
                            onClick={() => setSelectedJob(record)}
                            style={{ borderRadius: '8px' }}
                        />
                    </Tooltip>
                    <Tooltip title="Düzenle">
                        <Button
                            icon={<EditOutlined />}
                            onClick={() => handleEdit(record)}
                            style={{ borderRadius: '8px' }}
                        />
                    </Tooltip>
                </Space>
            )
        }
    ];

    return (
        <div>
            <Flex justify="space-between" align="center" style={{ marginBottom: '24px' }}>
                <Title level={2} style={{ margin: 0 }}>
                    🛠️ System Tasks & Scripts
                </Title>
                <Button icon={<ClockCircleOutlined />} onClick={() => void queryClient.invalidateQueries({ queryKey: ['system-jobs'] })}>
                    Refresh Status
                </Button>
            </Flex>

            <Alert
                description={
                    <Flex vertical gap={4}>
                        <Text strong>Dinamik Görev Yönetimi</Text>
                        <Text type="secondary">Otomasyon scriptlerini ve dahili servisleri tetikleyin. Script yollarını ve argümanları anlık olarak güncelleyebilirsiniz.</Text>
                    </Flex>
                }
                type="info"
                showIcon
                style={{ marginBottom: '32px', borderRadius: '12px' }}
            />

            <Card styles={{ body: { padding: 0 } }}>
                <Table
                    dataSource={jobs}
                    columns={columns}
                    loading={isLoading}
                    rowKey="id"
                    pagination={false}
                />
            </Card>

            {/* Execution Logs Drawer */}
            <Drawer
                title={
                    <Space>
                        <CodeOutlined />
                        <Text strong>Çalıştırma Logları: {selectedJob?.name}</Text>
                    </Space>
                }
                placement="right"
                style={{ width: '800px' }}
                onClose={() => setSelectedJob(null)}
                open={!!selectedJob}
                styles={{
                    body: { background: '#0f172a', padding: 0 },
                    header: { borderBottom: '1px solid #1e293b' }
                }}
                extra={
                    <Space>
                        <Button
                            icon={<SyncOutlined />}
                            onClick={() => void queryClient.invalidateQueries({ queryKey: ['system-jobs'] })}
                            style={{ borderRadius: '8px' }}
                        >
                            Tazele
                        </Button>
                        <Button
                            type="primary"
                            icon={<PlayCircleOutlined />}
                            onClick={() => runMutation.mutate(selectedJob!.id)}
                            style={{ borderRadius: '8px', background: '#6366f1' }}
                        >
                            Yeniden Çalıştır
                        </Button>
                    </Space>
                }
            >
                {selectedJob && (
                    <div style={{
                        color: '#94a3b8',
                        padding: '24px',
                        fontFamily: '"Fira Code", "Source Code Pro", monospace',
                        fontSize: '13px',
                        lineHeight: '1.6',
                        minHeight: '100%',
                        whiteSpace: 'pre-wrap',
                    }}>
                        <div style={{ color: '#10b981', marginBottom: 16 }}>
                            $ execution_start --task={selectedJob.id} --time={new Date().toISOString()}
                        </div>
                        {selectedJob.output || 'Log verisi bekleniyor...'}
                        {selectedJob.status === 'running' && (
                            <div style={{ color: '#6366f1', marginTop: 16 }}>
                                <SyncOutlined spin /> İşlem devam ediyor...
                            </div>
                        )}
                        <div style={{ color: '#10b981', marginTop: 16 }}>
                            $ _
                        </div>
                    </div>
                )}
            </Drawer>

            {/* Edit Job Modal */}
            <Modal
                title={`Edit Task: ${editingJob?.name}`}
                open={!!editingJob}
                onCancel={() => setEditingJob(null)}
                onOk={() => form.submit()}
                confirmLoading={updateMutation.isPending}
                width={600}
            >
                <Form
                    form={form}
                    onFinish={onEditFinish}
                    layout="vertical"
                >
                    <Form.Item name="name" label="Display Name" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                        <Input.TextArea rows={2} />
                    </Form.Item>

                    {editingJob?.type === 'script' ? (
                        <>
                            <Form.Item name="path" label="Script Path" rules={[{ required: true }]}>
                                <Input placeholder="e.g. scripts/myscript.py" />
                            </Form.Item>
                            <Form.Item name="args" label="Arguments (JSON Array)">
                                <Input placeholder='e.g. ["arg1", "arg2"]' />
                            </Form.Item>
                        </>
                    ) : (
                        <>
                            <Form.Item name="service" label="Service Name" rules={[{ required: true }]}>
                                <Input disabled />
                            </Form.Item>
                            <Form.Item name="method" label="Method" rules={[{ required: true }]}>
                                <Input disabled />
                            </Form.Item>
                        </>
                    )}
                </Form>
            </Modal>
        </div>
    );
}
