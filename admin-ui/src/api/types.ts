export type Platform = "telegram" | "vk" | "max";
export type Period = "day" | "week" | "month" | "year";
export type QAStatus =
  | "answered"
  | "unanswered"
  | "not_confluence"
  | "document_added"
  | "no_status";
export type TaskStatus = "added" | "in_progress" | "done" | "on_hold";

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
  unanswered_questions_total: number;
  not_confluence_questions_total: number;
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
  asked_at: string;
  model_used: string | null;
  is_unanswered: boolean;
  is_not_confluence: boolean;
  is_document_added: boolean;
  is_no_status: boolean;
  task_id: number | null;
  task_status: TaskStatus | null;
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

export interface AdminTask extends QAPair {
  id: number;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}

export interface TasksResponse {
  items: AdminTask[];
}

export interface TaskReportItem {
  id: number;
  task_id: number | null;
  question_id: number;
  answer_id: number | null;
  question: string;
  answer: string | null;
  platform: string | null;
  asked_at: string;
  model_used: string | null;
  sources: Source[];
  created_at: string;
  restored_at: string | null;
  restored_task_id: number | null;
}

export interface TaskReport {
  id: number;
  created_at: string;
  tasks_count: number;
  items: TaskReportItem[];
}

export interface TaskReportSummary {
  id: number;
  created_at: string;
  tasks_count: number;
}

export interface TaskReportsResponse {
  items: TaskReportSummary[];
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
