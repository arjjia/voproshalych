import { apiGet } from "./client";
import type {
  Overview,
  Period,
  QAPageResponse,
  Timeseries,
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
  date_from?: string;
  date_to?: string;
}) => apiGet<QAPageResponse>("/qa/pairs", params);

export const getUsers = (params: {
  page: number;
  size: number;
  platform?: string;
  search?: string;
}) => apiGet<UsersPageResponse>("/users", params);
