import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Card,
    Table,
    Tag,
    Button,
    Space,
    Typography,
    Modal,
    message,
    Badge,
    Empty,
} from 'antd';
import {
    CheckCircleOutlined,
    CloseCircleOutlined,
    ExclamationCircleOutlined,
} from '@ant-design/icons';
import { supabase } from '../lib/supabase';
import type { ColumnsType } from 'antd/es/table';
import { maskEmail, maskName } from '../utils/mask';
import { useMaskStore } from '../store/maskStore';

const { Title, Text } = Typography;
const { confirm } = Modal;

interface DeletionRequest {
    id: string;
    user_id: string;
    reason: string;
    status: 'pending' | 'approved' | 'rejected';
    created_at: string;
    users: {
        email: string;
        display_name: string | null;
    };
}

const DeletionRequests: React.FC = () => {
    const queryClient = useQueryClient();
    const { isMasked } = useMaskStore();

    const { data: requests, isLoading } = useQuery({
        queryKey: ['deletion-requests'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('account_deletion_requests')
                .select(`
                    id,
                    user_id,
                    reason,
                    status,
                    created_at,
                    users (
                        email,
                        display_name
                    )
                `)
                .order('created_at', { ascending: false });

            if (error) throw error;
            return data as unknown as DeletionRequest[];
        },
    });

    const approveMutation = useMutation({
        mutationFn: async (id: string) => {
            const { data, error } = await supabase.rpc('approve_deletion_request', {
                p_request_id: id
            });
            if (error) throw error;
            return data;
        },
        onSuccess: () => {
            message.success('Hesap silme talebi onaylandı ve kullanıcı silindi.');
            queryClient.invalidateQueries({ queryKey: ['deletion-requests'] });
        },
        onError: (err: any) => {
            message.error(`Hata: ${err.message}`);
        }
    });

    const rejectMutation = useMutation({
        mutationFn: async (id: string) => {
            const { error } = await supabase
                .from('account_deletion_requests')
                .update({ status: 'rejected', processed_at: new Date().toISOString() })
                .eq('id', id);
            if (error) throw error;
        },
        onSuccess: () => {
            message.info('Hesap silme talebi reddedildi.');
            queryClient.invalidateQueries({ queryKey: ['deletion-requests'] });
        },
        onError: (err: any) => {
            message.error(`Hata: ${err.message}`);
        }
    });

    const handleApprove = (record: DeletionRequest) => {
        confirm({
            title: 'Hesap Silme Onayı',
            icon: <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />,
            content: `${isMasked ? maskEmail(record.users.email) : record.users.email} kullanıcısının hesabını silmek istediğinize emin misiniz? Bu işlem geri alınamaz.`,
            okText: 'Evet, Sil',
            okType: 'danger',
            cancelText: 'Vazgeç',
            onOk() {
                return approveMutation.mutateAsync(record.id);
            },
        });
    };

    const handleReject = (record: DeletionRequest) => {
        confirm({
            title: 'Talebi Reddet',
            content: 'Bu silme talebini reddetmek istediğinize emin misiniz?',
            onOk() {
                return rejectMutation.mutateAsync(record.id);
            },
        });
    };

    const columns: ColumnsType<DeletionRequest> = [
        {
            title: 'Kullanıcı',
            key: 'user',
            render: (record) => (
                <Space vertical size={0}>
                    <Text strong>{isMasked ? maskName(record.users?.display_name) : (record.users?.display_name || 'İsimsiz Kullanıcı')}</Text>
                    <Text type="secondary" style={{ fontSize: '12px' }}>{isMasked ? maskEmail(record.users?.email) : record.users?.email}</Text>
                </Space>
            ),
        },
        {
            title: 'Sebep',
            dataIndex: 'reason',
            key: 'reason',
            ellipsis: true,
        },
        {
            title: 'Tarih',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (date) => new Date(date).toLocaleString('tr-TR'),
        },
        {
            title: 'Durum',
            dataIndex: 'status',
            key: 'status',
            render: (status: 'pending' | 'approved' | 'rejected') => {
                const colors: Record<string, string> = {
                    pending: 'blue',
                    approved: 'green',
                    rejected: 'red',
                };
                const labels: Record<string, string> = {
                    pending: 'Bekliyor',
                    approved: 'Onaylandı',
                    rejected: 'Reddedildi',
                };
                return <Tag color={colors[status]}>{labels[status].toUpperCase()}</Tag>;
            },
        },
        {
            title: 'İşlemler',
            key: 'actions',
            render: (record: DeletionRequest) => (
                <Space size="middle">
                    {record.status === 'pending' ? (
                        <>
                            <Button
                                type="primary"
                                icon={<CheckCircleOutlined />}
                                onClick={() => handleApprove(record)}
                                size="small"
                                style={{ background: '#52c41a', borderColor: '#52c41a' }}
                            >
                                Onayla
                            </Button>
                            <Button
                                danger
                                icon={<CloseCircleOutlined />}
                                onClick={() => handleReject(record)}
                                size="small"
                            >
                                Reddet
                            </Button>
                        </>
                    ) : (
                        <Text type="secondary">İşlem Tamamlandı</Text>
                    )}
                </Space>
            ),
        },
    ];

    const pendingCount = requests?.filter(r => r.status === 'pending').length || 0;

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <Title level={2}>KVKK / GDPR Silme Talepleri</Title>
                    <Text type="secondary">Kullanıcılar tarafından iletilen hesap silme taleplerini yönetin.</Text>
                </div>
                {pendingCount > 0 && (
                    <Badge count={pendingCount} overflowCount={99}>
                        <Tag color="error" style={{ margin: 0, padding: '4px 12px', borderRadius: '12px' }}>
                            Bekleyen Talep
                        </Tag>
                    </Badge>
                )}
            </div>

            <Card style={{ borderRadius: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}>
                <Table
                    columns={columns}
                    dataSource={requests}
                    loading={isLoading}
                    rowKey="id"
                    pagination={{ pageSize: 10 }}
                    locale={{
                        emptyText: <Empty description="Henüz bir talep bulunmuyor." />
                    }}
                />
            </Card>
        </div>
    );
};

export default DeletionRequests;
