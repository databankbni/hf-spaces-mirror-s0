import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Table, Typography, Input, InputNumber, Button, Space, App, Tag } from 'antd';
import { SaveOutlined, EditOutlined, BankOutlined, GlobalOutlined, CreditCardOutlined } from '@ant-design/icons';
import { supabase } from '../lib/supabase';

const { Title, Text } = Typography;

export default function MarketRates() {
    const { message } = App.useApp();
    const queryClient = useQueryClient();
    const [editingKey, setEditingKey] = useState<string | null>(null);
    const [editForm, setEditForm] = useState<any>({});

    const { data: rates, isLoading } = useQuery({
        queryKey: ['market_rates'],
        queryFn: async () => {
            const { data, error } = await supabase
                .from('market_interest_rates')
                .select('*')
                .order('type');
            if (error) throw error;
            return data;
        },
    });

    const updateMutation = useMutation({
        mutationFn: async (values: any) => {
            const { error } = await supabase
                .from('market_interest_rates')
                .update({ rate: values.rate, description: values.description, last_updated: new Date() })
                .eq('id', values.id);
            if (error) throw error;
        },
        onSuccess: () => {
            message.success('Rate updated successfully');
            setEditingKey(null);
            queryClient.invalidateQueries({ queryKey: ['market_rates'] });
        },
        onError: (err) => {
            message.error('Failed to update rate: ' + err);
        }
    });

    const isEditing = (record: any) => record.id === editingKey;

    const edit = (record: any) => {
        setEditForm({ ...record });
        setEditingKey(record.id);
    };

    const cancel = () => {
        setEditingKey(null);
    };

    const save = async () => {
        updateMutation.mutate(editForm);
    };

    const getIcon = (type: string) => {
        if (type.includes('deposit')) return <BankOutlined style={{ color: 'green' }} />;
        if (type.includes('card') || type.includes('credit')) return <CreditCardOutlined style={{ color: 'orange' }} />;
        return <GlobalOutlined style={{ color: 'blue' }} />;
    };

    const columns = [
        {
            title: '',
            dataIndex: 'type',
            width: 50,
            render: (type: string) => getIcon(type),
        },
        {
            title: 'Rate Type',
            dataIndex: 'type',
            key: 'type',
            render: (t: string) => <Tag>{t.replace('_', ' ').toUpperCase()}</Tag>
        },
        {
            title: 'Current Rate (%)',
            dataIndex: 'rate',
            key: 'rate',
            render: (text: any, record: any) => {
                if (isEditing(record)) {
                    return (
                        <InputNumber
                            min={0}
                            max={200}
                            value={editForm.rate}
                            onChange={(val) => setEditForm({ ...editForm, rate: val })}
                            formatter={(value) => `${value}%`}
                            parser={(value) => value?.replace('%', '') as unknown as number}
                        />
                    );
                }
                return <Text strong style={{ fontSize: '16px', color: '#1890ff' }}>%{text}</Text>;
            }
        },
        {
            title: 'Description',
            dataIndex: 'description',
            key: 'description',
            width: '40%',
            render: (text: string, record: any) => {
                if (isEditing(record)) {
                    return (
                        <Input
                            value={editForm.description}
                            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        />
                    );
                }
                return text;
            }
        },
        {
            title: 'Last Updated',
            dataIndex: 'last_updated',
            key: 'last_updated',
            render: (d: string) => <Text type="secondary" style={{ fontSize: '12px' }}>{new Date(d).toLocaleString('tr-TR')}</Text>
        },
        {
            title: 'Action',
            key: 'action',
            render: (_: any, record: any) => {
                const editable = isEditing(record);
                return editable ? (
                    <Space>
                        <Button type="primary" size="small" icon={<SaveOutlined />} onClick={save} loading={updateMutation.isPending}>Save</Button>
                        <Button size="small" onClick={cancel}>Cancel</Button>
                    </Space>
                ) : (
                    <Button type="text" icon={<EditOutlined />} onClick={() => edit(record)}>Edit</Button>
                );
            },
        },
    ];

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <Title level={2} style={{ margin: 0 }}>Market Rates Manager</Title>
                    <Text type="secondary">Manage global financial indicators used by the AI Purchase Assistant.</Text>
                </div>
            </div>

            <Card>
                <Table
                    loading={isLoading}
                    dataSource={rates}
                    columns={columns}
                    rowKey="id"
                    pagination={false}
                />
            </Card>

            <div style={{ marginTop: '24px', padding: '16px', background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: '4px' }}>
                <Text strong>Note:</Text> These rates directly affect user's "Cash vs Installment" analysis results.
                The <b>deposit_monthly</b> rate is the primary "Opportunity Cost" metric.
            </div>
        </div>
    );
}
