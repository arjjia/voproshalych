import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type {
  AdminTask,
  Overview,
  Period,
  QAStatus,
  QAPageResponse,
  TaskReport,
  TaskReportsResponse,
  TaskStatus,
  Timeseries,
  TasksResponse,
  UsersPageResponse,
} from "./types";

export const getOverview = () => apiGet<Overview>("/stats/overview");

export const getTimeseries = (params: {
  period: Period;
  platform?: string;
  days_back?: number;
}) => apiGet<Timeseries>("/stats/questions-timeseries", params);

export const getQAPairs = (params: {
  page: number;
  size: number;
  platform?: string;
  search?: string;
  status?: QAStatus;
  date_from?: string;
  date_to?: string;
}) => apiGet<QAPageResponse>("/qa/pairs", params);

export const markQAPairFalsePositive = (questionId: number) =>
  apiPost<{ ok: boolean }>(`/qa/pairs/${questionId}/false-positive`);

export const getTasks = () => apiGet<TasksResponse>("/tasks");

export const getTaskReports = (params: { page: number; size: number }) =>
  apiGet<TaskReportsResponse>("/tasks/reports", params);

export const getTaskReport = (reportId: number) =>
  apiGet<TaskReport>(`/tasks/reports/${reportId}`);

export const createTask = (questionId: number) =>
  apiPost<AdminTask>("/tasks", { question_id: questionId });

export const createTaskReport = () => apiPost<TaskReport>("/tasks/reports");

export const restoreTaskReportItem = (itemId: number) =>
  apiPost<AdminTask>(`/tasks/reports/items/${itemId}/restore`);

export const deleteTask = (taskId: number) =>
  apiDelete<{ ok: boolean }>(`/tasks/${taskId}`);

export const updateTaskStatus = (taskId: number, status: TaskStatus) =>
  apiPatch<AdminTask>(`/tasks/${taskId}/status`, { status });

export const getUsers = (params: {
  page: number;
  size: number;
  platform?: string;
  search?: string;
}) => apiGet<UsersPageResponse>("/users", params);
