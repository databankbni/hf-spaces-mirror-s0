import { create } from 'zustand';
import { supabase } from '../lib/supabase';
import type { User } from '@supabase/supabase-js';

interface AuthState {
    user: User | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    login: (email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
    user: null,
    isLoading: true,
    isAuthenticated: false,

    login: async (email: string, password: string) => {
        const { data, error } = await supabase.auth.signInWithPassword({
            email,
            password,
        });

        if (error) throw error;

        const { data: profile, error: profileError } = await supabase
            .from('users')
            .select('role, is_active, is_banned, deleted_at')
            .eq('id', data.user.id)
            .single();

        const isAdmin = profile?.role === 'admin' || profile?.role === 'super_admin';
        if (profileError || !isAdmin || !profile.is_active || profile.is_banned || profile.deleted_at) {
            await supabase.auth.signOut();
            throw new Error('Bu hesap admin paneline erişim yetkisine sahip değil.');
        }

        set({ user: data.user, isAuthenticated: true });
    },

    logout: async () => {
        await supabase.auth.signOut();
        set({ user: null, isAuthenticated: false });
    },

    checkAuth: async () => {
        try {
            const { data } = await supabase.auth.getSession();
            const sessionUser = data.session?.user;
            let isAdmin = false;

            if (sessionUser) {
                const { data: profile } = await supabase
                    .from('users')
                    .select('role, is_active, is_banned, deleted_at')
                    .eq('id', sessionUser.id)
                    .maybeSingle();
                isAdmin = Boolean(
                    profile &&
                    (profile.role === 'admin' || profile.role === 'super_admin') &&
                    profile.is_active &&
                    !profile.is_banned &&
                    !profile.deleted_at
                );
                if (!isAdmin) await supabase.auth.signOut();
            }

            set({
                user: isAdmin ? sessionUser || null : null,
                isAuthenticated: isAdmin,
                isLoading: false,
            });
        } catch (error) {
            console.error('Auth check failed:', error);
            set({ user: null, isAuthenticated: false, isLoading: false });
        }
    },
}));
