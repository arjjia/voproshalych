export type Platform = "telegram" | "vk" | "max";
export type Period = "day" | "week" | "month" | "year";

export interface PlatformCount {
  platform: string;
  count: number;
}

export interface Overview {
  users_total: number;
  users_by_platform: PlatformCount[];
  questions_total: number;
  questions_today: number;
  questions_last_month: number;
  active_users_last_month: number;
}

export interface TimeseriesPoint {
  bucket: string;
  count: number;
}

export interface Timeseries {
  period: Period;
  platform: string | null;
  points: TimeseriesPoint[];
}

export interface Source {
  id: string | null;
  title: string | null;
  url: string | null;
}

export interface QAPair {
  question_id: number;
  answer_id: number | null;
  question: string;
  answer: string | null;
  platform: string | null;
  username: string | null;
  asked_at: string;
  model_used: string | null;
  sources: Source[];
}

export interface PageMeta {
  page: number;
  size: number;
  total: number;
}

export interface QAPageResponse {
  items: QAPair[];
  meta: PageMeta;
}

export interface UserRow {
  id: number;
  platform: string;
  platform_user_id: string;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_subscribed: boolean;
  questions_count: number;
  last_active_at: string | null;
  created_at: string | null;
}

export interface UsersPageResponse {
  items: UserRow[];
  meta: PageMeta;
}
