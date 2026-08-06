import { createClient } from '@supabase/supabase-js';
import { getSupabaseUrl, getSupabaseAnonKey } from '../config';

// Create Supabase client with runtime config
// Note: This will throw if config hasn't been loaded yet
export const supabase = createClient(
  getSupabaseUrl(),
  getSupabaseAnonKey()
);

// Types
export interface DashboardStats {
  total_users: number;
  active_users: number;
  guest_users: number;
  premium_users: number;
  banned_users: number;
  new_users_today: number;
  new_users_week: number;
  new_users_month: number;
  dau: number;
  wau: number;
  mau: number;
  avg_session_duration_minutes: number | null;
  total_sessions_today: number;
  total_events_today: number;
  premium_conversion_rate: number | null;
}

export interface UserGrowth {
  activity_date: string;
  new_users: number;
  total_users: number;
  premium_users: number;
  active_users: number;
}

export interface TopEvent {
  event_name: string;
  event_category: string;
  count: number;
  unique_users: number;
}

export interface AtRiskUser {
  user_id: string;
  email: string;
  display_name: string;
  engagement_score: number;
  days_inactive: number;
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
  recommended_action: string;
  is_premium: boolean;
}

export interface RFMSegment {
  segment_name: string;
  user_count: number;
  percentage: number;
  avg_engagement_score: number;
}
