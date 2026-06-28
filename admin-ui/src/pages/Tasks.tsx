import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Archive,
  CalendarDays,
  Download,
  ExternalLink,
  FileText,
  History,
  MinusCircle,
  MoreHorizontal,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import {
  createTaskReport,
  deleteTask,
  getTaskReport,
  getTaskReports,
  getTasks,
  restoreTaskReportItem,
  updateTaskStatus,
} from "@/api/endpoints";
import type {
  AdminTask,
  Source,
  TaskReportItem,
  TaskReportSummary,
  TaskStatus,
} from "@/api/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { PlatformBadge } from "@/components/ui/PlatformBadge";
import { cn, detectSourceKind } from "@/lib/utils";

const REPORTS_PAGE_SIZE = 20;

const TASK_COLUMNS: Array<{
  status: TaskStatus;
  title: string;
  className: string;
}> = [
  { status: "added", title: "Добавлен", className: "border-slate-200 bg-slate-50" },
  { status: "in_progress", title: "В работе", className: "border-blue-200 bg-blue-50" },
  { status: "done", title: "Выполнен", className: "border-emerald-200 bg-emerald-50" },
  { status: "on_hold", title: "На удержании", className: "border-amber-200 bg-amber-50" },
];

function getTaskStatusLabel(status: TaskStatus) {
  return TASK_COLUMNS.find((column) => column.status === status)?.title ?? status;
}

function TaskQuestionStatusBadge({ task }: { task: AdminTask }) {
  if (task.is_unanswered) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-red-100 px-2 py-1 text-xs font-semibold text-red-700">
        <XCircle className="h-3.5 w-3.5" />
        Не отвечен
      </span>
    );
  }

  if (task.is_not_confluence) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800">
        <AlertTriangle className="h-3.5 w-3.5" />
        Нет в Confluence
      </span>
    );
  }

  if (task.is_no_status) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
        <MinusCircle className="h-3.5 w-3.5" />
        Без статуса
      </span>
    );
  }

  return null;
}

function MetadataRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-utmn-muted">
        {label}
      </div>
      <div className="mt-1 text-xs text-slate-700">{children}</div>
    </div>
  );
}

function SourceLinks({ sources }: { sources: Source[] }) {
  if (!sources.length) {
    return <span className="text-utmn-muted">нет источников</span>;
  }

  return (
    <div className="space-y-2">
      {sources.map((source, index) => {
        const kind = detectSourceKind(source.url);
        const title = source.title ?? source.url ?? source.id ?? "Документ";
        const isUrl = source.url?.startsWith("http");
        const content = (
          <>
            <span
              className={cn(
                "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium",
                kind.color,
              )}
            >
              {kind.label}
            </span>
            <span className="min-w-0 flex-1 truncate">{title}</span>
            {isUrl ? (
              <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />
            ) : (
              <FileText className="h-3 w-3 shrink-0 opacity-60" />
            )}
          </>
        );

        return isUrl ? (
          <a
            key={source.id ?? index}
            href={source.url!}
            target="_blank"
            rel="noopener noreferrer"
            className="flex min-w-0 items-center gap-1.5 rounded-md border border-utmn-border bg-white px-2 py-1.5 text-xs transition-colors hover:border-utmn-primary/50 hover:bg-utmn-primary/5"
          >
            {content}
          </a>
        ) : (
          <span
            key={source.id ?? index}
            className="flex min-w-0 items-center gap-1.5 rounded-md border border-utmn-border bg-white px-2 py-1.5 text-xs"
            title={source.url ?? undefined}
          >
            {content}
          </span>
        );
      })}
    </div>
  );
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

function printTasksPdf(tasks: AdminTask[], statuses: TaskStatus[]) {
  const selectedColumns = TASK_COLUMNS.filter((column) => statuses.includes(column.status));
  const title = `Список вопросов - ${format(new Date(), "d MMM yyyy, HH:mm", {
    locale: ru,
  })}`;
  const sections = selectedColumns
    .map((column) => {
      const columnTasks = tasks.filter((task) => task.status === column.status);
      const items = columnTasks.length
        ? columnTasks
            .map((task) => `<li>${escapeHtml(task.question)}</li>`)
            .join("")
        : `<li class="empty">Нет вопросов</li>`;

      return `
        <section>
          <h2>${escapeHtml(column.title)} (${columnTasks.length})</h2>
          <ol>${items}</ol>
        </section>
      `;
    })
    .join("");

  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    window.alert("Браузер заблокировал окно печати. Разрешите всплывающие окна.");
    return;
  }

  printWindow.document.write(`
    <!doctype html>
    <html lang="ru">
      <head>
        <meta charset="utf-8" />
        <title>${escapeHtml(title)}</title>
        <style>
          @page { margin: 16mm; }
          body {
            margin: 0;
            color: #0f172a;
            font-family: Arial, sans-serif;
            font-size: 12px;
          }
          h1 {
            margin: 0 0 6px;
            font-size: 20px;
          }
          .meta {
            margin-bottom: 20px;
            color: #64748b;
          }
          h2 {
            margin: 22px 0 10px;
            font-size: 15px;
          }
          ol {
            margin: 0;
            padding-left: 22px;
          }
          li {
            margin: 0 0 8px;
            line-height: 1.45;
            page-break-inside: avoid;
          }
          li.empty {
            color: #64748b;
            font-style: italic;
            list-style: none;
          }
        </style>
      </head>
      <body>
        <h1>${escapeHtml(title)}</h1>
        <div class="meta">Колонки: ${escapeHtml(
          selectedColumns.map((column) => column.title).join(", "),
        )}</div>
        ${sections}
      </body>
    </html>
  `);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
}

function TaskCard({
  task,
  onDragStart,
  onOpenDetails,
  onDelete,
  onMove,
}: {
  task: AdminTask;
  onDragStart: (taskId: number) => void;
  onOpenDetails: (task: AdminTask) => void;
  onDelete: (task: AdminTask) => void;
  onMove: (task: AdminTask, status: TaskStatus) => void;
}) {
  const columnIndex = TASK_COLUMNS.findIndex((column) => column.status === task.status);
  const previousStatus = columnIndex > 0 ? TASK_COLUMNS[columnIndex - 1].status : null;
  const nextStatus =
    columnIndex >= 0 && columnIndex < TASK_COLUMNS.length - 1
      ? TASK_COLUMNS[columnIndex + 1].status
      : null;

  return (
    <article
      draggable
      onDragStart={() => onDragStart(task.id)}
      className="cursor-grab rounded-lg border border-utmn-border bg-white p-3 shadow-sm active:cursor-grabbing"
    >
      <div className="flex items-start gap-2">
        <div className="line-clamp-4 min-w-0 flex-1 whitespace-pre-wrap text-sm font-medium leading-5 text-slate-900">
          {task.question}
        </div>
        <button
          type="button"
          draggable={false}
          onClick={(event) => {
            event.stopPropagation();
            onOpenDetails(task);
          }}
          className="shrink-0 rounded-md p-1 text-slate-500 hover:bg-utmn-surface hover:text-slate-800"
          aria-label="Открыть детали задачи"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
        <button
          type="button"
          draggable={false}
          onClick={(event) => {
            event.stopPropagation();
            onDelete(task);
          }}
          className="shrink-0 rounded-md p-1 text-slate-500 hover:bg-red-50 hover:text-red-700"
          aria-label="Убрать вопрос из работы"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-utmn-muted">
        <TaskQuestionStatusBadge task={task} />
        <PlatformBadge platform={task.platform} />
      </div>
      <div className="mt-2 text-xs text-utmn-muted">
        {format(parseISO(task.asked_at), "d MMM yyyy, HH:mm", { locale: ru })}
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-utmn-border pt-2">
        <button
          type="button"
          disabled={!previousStatus}
          onClick={() => previousStatus && onMove(task, previousStatus)}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-utmn-surface disabled:opacity-30"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Назад
        </button>
        <button
          type="button"
          disabled={!nextStatus}
          onClick={() => nextStatus && onMove(task, nextStatus)}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-utmn-surface disabled:opacity-30"
        >
          Далее
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </article>
  );
}

function TaskDetailsModal({
  item,
  onClose,
}: {
  item: AdminTask | TaskReportItem | null;
  onClose: () => void;
}) {
  if (!item) return null;
  const taskStatus = "status" in item ? item.status : null;
  const isArchivedItem = !("status" in item);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-6">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-xl border border-utmn-border bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-utmn-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-utmn-dark">Информация о вопросе</h2>
            <p className="mt-1 text-xs text-utmn-muted">
              {format(parseISO(item.asked_at), "d MMM yyyy, HH:mm", { locale: ru })}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-utmn-surface hover:text-slate-800"
            aria-label="Закрыть"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[calc(90vh-5rem)] space-y-6 overflow-auto p-5">
          <section>
            <div className="mb-2 text-xs font-semibold text-utmn-primary">Вопрос</div>
            <div className="whitespace-pre-wrap text-sm leading-6 text-slate-900">
              {item.question}
            </div>
          </section>

          <section>
            <div className="mb-2 text-xs font-semibold text-utmn-accent">Ответ</div>
            {item.answer ? (
              <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
                {item.answer}
              </div>
            ) : (
              <span className="text-sm italic text-utmn-muted">нет ответа</span>
            )}
          </section>

          <section className="grid grid-cols-1 gap-4 rounded-lg border border-utmn-border bg-utmn-surface/60 p-4 sm:grid-cols-2">
            <MetadataRow label="Платформа">
              <PlatformBadge platform={item.platform} />
            </MetadataRow>
            {!isArchivedItem && taskStatus && (
              <MetadataRow label="Статус задачи">
                {getTaskStatusLabel(taskStatus)}
              </MetadataRow>
            )}
            <MetadataRow label="Модель">
              {item.model_used ? (
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                  {item.model_used}
                </span>
              ) : (
                "не указана"
              )}
            </MetadataRow>
          </section>

          <section>
            <div className="mb-2 text-xs font-semibold text-utmn-dark">Источники</div>
            <SourceLinks sources={item.sources} />
          </section>
        </div>
      </div>
    </div>
  );
}

function ReportsHistoryModal({
  reports,
  page,
  total,
  isLoading,
  onOpenItem,
  onRestoreItem,
  onPageChange,
  restoringItemId,
  onClose,
}: {
  reports: TaskReportSummary[];
  page: number;
  total: number;
  isLoading: boolean;
  onOpenItem: (item: TaskReportItem) => void;
  onRestoreItem: (item: TaskReportItem) => void;
  onPageChange: (page: number) => void;
  restoringItemId: number | null;
  onClose: () => void;
}) {
  const [selectedReportId, setSelectedReportId] = useState<number | null>(
    reports[0]?.id ?? null,
  );
  const selectedReport =
    reports.find((report) => report.id === selectedReportId) ?? reports[0] ?? null;
  const totalPages = Math.max(1, Math.ceil(total / REPORTS_PAGE_SIZE));
  const selectedReportQuery = useQuery({
    queryKey: ["task-report", selectedReport?.id],
    queryFn: () => getTaskReport(selectedReport!.id),
    enabled: Boolean(selectedReport),
  });
  const selectedReportDetails = selectedReportQuery.data ?? null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/35 p-6">
      <div className="grid max-h-[90vh] w-full max-w-6xl grid-cols-[18rem_1fr] overflow-hidden rounded-xl border border-utmn-border bg-white shadow-xl">
        <aside className="min-h-0 border-r border-utmn-border bg-utmn-surface/60">
          <div className="flex items-center justify-between border-b border-utmn-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold text-utmn-dark">История</h2>
              <p className="mt-1 text-xs text-utmn-muted">Сохраненные результаты</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-slate-500 hover:bg-white hover:text-slate-800"
              aria-label="Закрыть историю"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="max-h-[calc(90vh-4.25rem)] space-y-2 overflow-auto p-3">
            {isLoading ? (
              <div className="rounded-lg border border-dashed border-utmn-border bg-white p-4 text-center text-xs text-utmn-muted">
                Загрузка…
              </div>
            ) : reports.length === 0 ? (
              <div className="rounded-lg border border-dashed border-utmn-border bg-white p-4 text-center text-xs text-utmn-muted">
                История пока пустая
              </div>
            ) : (
              reports.map((report) => (
                <button
                  key={report.id}
                  type="button"
                  onClick={() => setSelectedReportId(report.id)}
                  className={cn(
                    "w-full rounded-lg border p-3 text-left transition-colors",
                    selectedReport?.id === report.id
                      ? "border-utmn-primary bg-white shadow-sm"
                      : "border-transparent bg-white/70 hover:border-utmn-border hover:bg-white",
                  )}
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <Archive className="h-4 w-4 text-utmn-primary" />
                    Отчет #{report.id}
                  </div>
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-utmn-muted">
                    <CalendarDays className="h-3.5 w-3.5" />
                    {format(parseISO(report.created_at), "d MMM yyyy, HH:mm", {
                      locale: ru,
                    })}
                  </div>
                  <div className="mt-2 text-xs font-medium text-slate-600">
                    Закрыто: {report.tasks_count}
                  </div>
                </button>
              ))
            )}
          </div>
          <div className="flex items-center justify-between border-t border-utmn-border px-3 py-2 text-xs text-utmn-muted">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="rounded px-2 py-1 hover:bg-white disabled:opacity-40"
            >
              Назад
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="rounded px-2 py-1 hover:bg-white disabled:opacity-40"
            >
              Далее
            </button>
          </div>
        </aside>

        <section className="min-h-0">
          <div className="border-b border-utmn-border px-5 py-4">
            <h3 className="text-base font-semibold text-utmn-dark">
              {selectedReport ? `Отчет #${selectedReport.id}` : "Выберите отчет"}
            </h3>
            {selectedReport && (
              <p className="mt-1 text-xs text-utmn-muted">
                {format(parseISO(selectedReport.created_at), "d MMM yyyy, HH:mm", {
                  locale: ru,
                })}
              </p>
            )}
          </div>
          <div className="max-h-[calc(90vh-5rem)] space-y-3 overflow-auto p-5">
            {!selectedReport ? (
              <div className="rounded-lg border border-dashed border-utmn-border p-6 text-center text-sm text-utmn-muted">
                Нет сохраненных отчетов
              </div>
            ) : selectedReportQuery.isLoading ? (
              <div className="rounded-lg border border-dashed border-utmn-border p-6 text-center text-sm text-utmn-muted">
                Загрузка вопросов отчета…
              </div>
            ) : (
              (selectedReportDetails?.items ?? []).map((item) => (
                <article
                  key={item.id}
                  className="rounded-lg border border-utmn-border bg-white p-4 shadow-sm"
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="line-clamp-2 whitespace-pre-wrap text-sm font-medium text-slate-900">
                        {item.question}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-utmn-muted">
                        <PlatformBadge platform={item.platform} />
                        <span>
                          {format(parseISO(item.asked_at), "d MMM yyyy, HH:mm", {
                            locale: ru,
                          })}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onOpenItem(item)}
                      className="shrink-0 rounded-md p-1.5 text-slate-500 hover:bg-utmn-surface hover:text-slate-800"
                      aria-label="Открыть детали архивной задачи"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-3 flex justify-end">
                    <button
                      type="button"
                      disabled={Boolean(item.restored_at) || restoringItemId === item.id}
                      onClick={() => onRestoreItem(item)}
                      className="rounded-md border border-utmn-border px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-utmn-surface disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {item.restored_at
                        ? "Уже возвращен"
                        : restoringItemId === item.id
                          ? "Возврат…"
                          : "Вернуть в канбан"}
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function PdfOptionsModal({
  selectedStatuses,
  onSelectedStatusesChange,
  onSave,
  onClose,
}: {
  selectedStatuses: TaskStatus[];
  onSelectedStatusesChange: (statuses: TaskStatus[]) => void;
  onSave: () => void;
  onClose: () => void;
}) {
  const toggleStatus = (status: TaskStatus) => {
    if (selectedStatuses.includes(status)) {
      onSelectedStatusesChange(selectedStatuses.filter((item) => item !== status));
    } else {
      onSelectedStatusesChange([...selectedStatuses, status]);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/35 p-6">
      <div className="w-full max-w-lg rounded-xl border border-utmn-border bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-utmn-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-utmn-dark">Сохранить в PDF</h2>
            <p className="mt-1 text-xs text-utmn-muted">
              Выберите колонки канбана, которые попадут в список вопросов
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-utmn-surface hover:text-slate-800"
            aria-label="Закрыть"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-2 p-5">
          {TASK_COLUMNS.map((column) => (
            <label
              key={column.status}
              className="flex cursor-pointer items-center justify-between rounded-lg border border-utmn-border px-3 py-2 text-sm text-slate-700 hover:bg-utmn-surface"
            >
              <span>{column.title}</span>
              <input
                type="checkbox"
                checked={selectedStatuses.includes(column.status)}
                onChange={() => toggleStatus(column.status)}
                className="h-4 w-4 accent-utmn-primary"
              />
            </label>
          ))}
        </div>

        <div className="flex justify-end gap-2 border-t border-utmn-border px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-utmn-border px-4 py-2 text-sm font-medium text-slate-700 hover:bg-utmn-surface"
          >
            Отмена
          </button>
          <button
            type="button"
            disabled={selectedStatuses.length === 0}
            onClick={onSave}
            className="inline-flex items-center gap-2 rounded-lg bg-utmn-primary px-4 py-2 text-sm font-medium text-white hover:bg-utmn-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

export function TasksPage() {
  const queryClient = useQueryClient();
  const [draggedTaskId, setDraggedTaskId] = useState<number | null>(null);
  const [selectedItem, setSelectedItem] = useState<AdminTask | TaskReportItem | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isPdfOptionsOpen, setIsPdfOptionsOpen] = useState(false);
  const [pdfStatuses, setPdfStatuses] = useState<TaskStatus[]>(["added"]);
  const [reportsPage, setReportsPage] = useState(1);

  const tasksQuery = useQuery({
    queryKey: ["tasks"],
    queryFn: getTasks,
  });

  const reportsQuery = useQuery({
    queryKey: ["task-reports", reportsPage],
    queryFn: () => getTaskReports({ page: reportsPage, size: REPORTS_PAGE_SIZE }),
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ taskId, status }: { taskId: number; status: TaskStatus }) =>
      updateTaskStatus(taskId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const deleteTaskMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
    },
  });

  const createReportMutation = useMutation({
    mutationFn: createTaskReport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["task-reports"] });
      queryClient.invalidateQueries({ queryKey: ["task-report"] });
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const restoreReportItemMutation = useMutation({
    mutationFn: restoreTaskReportItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["task-reports"] });
      queryClient.invalidateQueries({ queryKey: ["task-report"] });
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const tasks = tasksQuery.data?.items ?? [];
  const reports = reportsQuery.data?.items ?? [];
  const reportsTotal = reportsQuery.data?.meta.total ?? 0;
  const doneTasksCount = tasks.filter((task) => task.status === "done").length;
  const mutationError =
    updateStatusMutation.error ??
    deleteTaskMutation.error ??
    createReportMutation.error ??
    restoreReportItemMutation.error;

  const handleDrop = (status: TaskStatus) => {
    if (draggedTaskId === null) return;
    const task = tasks.find((item) => item.id === draggedTaskId);
    setDraggedTaskId(null);
    if (!task || task.status === status) return;
    updateStatusMutation.mutate({ taskId: task.id, status });
  };

  const handleDelete = (task: AdminTask) => {
    const confirmed = window.confirm("Убрать этот вопрос из работы?");
    if (confirmed) {
      deleteTaskMutation.mutate(task.id);
    }
  };

  const handleMove = (task: AdminTask, status: TaskStatus) => {
    if (task.status !== status) {
      updateStatusMutation.mutate({ taskId: task.id, status });
    }
  };

  const handleCreateReport = () => {
    if (doneTasksCount === 0) return;
    const confirmed = window.confirm(
      `Сохранить ${doneTasksCount} выполненных задач в историю и очистить колонку "Выполнен"?`,
    );
    if (confirmed) {
      createReportMutation.mutate(undefined, {
        onSuccess: () => {
          setReportsPage(1);
          setIsHistoryOpen(true);
        },
      });
    }
  };

  const handleRestoreReportItem = (item: TaskReportItem) => {
    const confirmed = window.confirm("Вернуть этот вопрос из истории в колонку \"Добавлен\"?");
    if (confirmed) {
      restoreReportItemMutation.mutate(item.id);
    }
  };

  const handleSavePdf = () => {
    printTasksPdf(tasks, pdfStatuses);
    setIsPdfOptionsOpen(false);
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden p-8">
      <PageHeader
        title="Задачи"
        description="Вопросы, которые нужно разобрать и довести до результата"
      />
      {mutationError && (
        <div className="mb-3 shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {getErrorMessage(mutationError)}
        </div>
      )}

      {tasksQuery.isLoading ? (
        <div className="card p-8 text-center text-utmn-muted">Загрузка…</div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
          {TASK_COLUMNS.map((column) => {
            const columnTasks = tasks.filter((task) => task.status === column.status);
            return (
              <section
                key={column.status}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => handleDrop(column.status)}
                className={cn(
                  "flex min-h-0 flex-col rounded-xl border",
                  column.className,
                )}
              >
                <div className="flex shrink-0 items-center justify-between border-b border-black/5 px-4 py-3">
                  <h2 className="text-sm font-semibold text-slate-900">{column.title}</h2>
                  <span className="rounded bg-white/80 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {columnTasks.length}
                  </span>
                </div>
                <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
                  {columnTasks.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-utmn-muted">
                      Нет задач
                    </div>
                  ) : (
                    columnTasks.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        onDragStart={setDraggedTaskId}
                        onOpenDetails={setSelectedItem}
                        onDelete={handleDelete}
                        onMove={handleMove}
                      />
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
      <div className="mt-4 flex shrink-0 items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsHistoryOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-utmn-border bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-utmn-surface"
          >
            <History className="h-4 w-4" />
            История
            {reportsTotal > 0 && (
              <span className="rounded bg-utmn-surface px-1.5 py-0.5 text-xs text-utmn-muted">
                {reportsTotal}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setIsPdfOptionsOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-utmn-border bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-utmn-surface"
          >
            <Download className="h-4 w-4" />
            Сохранить в PDF
          </button>
        </div>
        <button
          type="button"
          disabled={doneTasksCount === 0 || createReportMutation.isPending}
          onClick={handleCreateReport}
          className="inline-flex items-center gap-2 rounded-lg bg-utmn-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-utmn-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Archive className="h-4 w-4" />
          {createReportMutation.isPending
            ? "Сохранение…"
            : `Сохранить результат${doneTasksCount > 0 ? ` (${doneTasksCount})` : ""}`}
        </button>
      </div>
      {isHistoryOpen && (
        <ReportsHistoryModal
          reports={reports}
          page={reportsPage}
          total={reportsTotal}
          isLoading={reportsQuery.isLoading}
          onOpenItem={setSelectedItem}
          onRestoreItem={handleRestoreReportItem}
          onPageChange={setReportsPage}
          restoringItemId={restoreReportItemMutation.variables ?? null}
          onClose={() => setIsHistoryOpen(false)}
        />
      )}
      {isPdfOptionsOpen && (
        <PdfOptionsModal
          selectedStatuses={pdfStatuses}
          onSelectedStatusesChange={setPdfStatuses}
          onSave={handleSavePdf}
          onClose={() => setIsPdfOptionsOpen(false)}
        />
      )}
      <TaskDetailsModal item={selectedItem} onClose={() => setSelectedItem(null)} />
    </div>
  );
}
