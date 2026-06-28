import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileText,
  MinusCircle,
  XCircle,
} from "lucide-react";
import {
  createTask,
  deleteTask,
  getQAPairs,
  markQAPairFalsePositive,
} from "@/api/endpoints";
import type { QAStatus, QAPair, Source, TaskStatus } from "@/api/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { PlatformBadge } from "@/components/ui/PlatformBadge";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { cn, detectSourceKind } from "@/lib/utils";

const PLATFORM_OPTIONS = [
  { value: "", label: "Все платформы" },
  { value: "telegram", label: "Telegram" },
  { value: "vk", label: "ВКонтакте" },
  { value: "max", label: "MAX" },
];

const STATUS_OPTIONS = [
  { value: "", label: "Все статусы" },
  { value: "answered", label: "Отвечен" },
  { value: "unanswered", label: "Не отвечен" },
  { value: "not_confluence", label: "Нет в Confluence" },
  { value: "document_added", label: "Документ добавлен" },
  { value: "no_status", label: "Без статуса" },
];

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  added: "Добавлен",
  in_progress: "В работе",
  done: "Выполнен",
  on_hold: "На удержании",
};

const QUESTION_ROW_HEIGHT = 96;
const RESERVED_VERTICAL_SPACE = 260;

function getViewportPageSize() {
  if (typeof window === "undefined") return 6;
  const availableHeight = window.innerHeight - RESERVED_VERTICAL_SPACE;
  return Math.max(4, Math.min(12, Math.floor(availableHeight / QUESTION_ROW_HEIGHT)));
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

function getPairStatus(pair: QAPair) {
  if (pair.is_document_added) {
    return {
      label: "Документ добавлен",
      description: "закрыто через канбан",
      icon: CheckCircle2,
      badgeClass: "bg-cyan-100 text-cyan-800",
      rowClass: "border-cyan-200 bg-cyan-50/70",
      accentClass: "text-cyan-800",
    };
  }

  if (pair.is_no_status) {
    return {
      label: "Без статуса",
      description: "поля классификации не заполнены",
      icon: MinusCircle,
      badgeClass: "bg-slate-100 text-slate-600",
      rowClass: "border-slate-200 bg-slate-50/70",
      accentClass: "text-slate-600",
    };
  }

  if (pair.is_unanswered) {
    return {
      label: "Не отвечен",
      description: "нет информации в БЗ",
      icon: XCircle,
      badgeClass: "bg-red-100 text-red-700",
      rowClass: "border-red-200 bg-red-50/70",
      accentClass: "text-red-700",
    };
  }

  if (pair.is_not_confluence) {
    return {
      label: "Нет в Confluence",
      description: "ответ из utmn/sveden",
      icon: AlertTriangle,
      badgeClass: "bg-amber-100 text-amber-800",
      rowClass: "border-amber-200 bg-amber-50/70",
      accentClass: "text-amber-800",
    };
  }

  return {
    label: "Отвечен",
    description: "источник Confluence",
    icon: CheckCircle2,
    badgeClass: "bg-emerald-100 text-emerald-700",
    rowClass: "border-transparent bg-white",
    accentClass: "text-emerald-700",
  };
}

function StatusBadge({ pair }: { pair: QAPair }) {
  const status = getPairStatus(pair);
  const Icon = status.icon;
  const showTaskStatus =
    pair.task_status && (pair.is_unanswered || pair.is_not_confluence);

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs font-semibold",
        status.badgeClass,
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {status.label}
      {showTaskStatus && <span className="opacity-70">· {TASK_STATUS_LABELS[pair.task_status!]}</span>}
    </span>
  );
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

function QuestionListItem({
  pair,
  selected,
  onSelect,
}: {
  pair: QAPair;
  selected: boolean;
  onSelect: () => void;
}) {
  const status = getPairStatus(pair);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "block h-24 w-full border-l-4 px-5 py-4 text-left transition-colors hover:bg-utmn-surface/70",
        status.rowClass,
        selected && "bg-utmn-primary/5 ring-1 ring-inset ring-utmn-primary/30",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="max-h-12 overflow-hidden text-sm font-medium leading-6 text-slate-900">
            {pair.question}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-utmn-muted">
            <PlatformBadge platform={pair.platform} />
            <span>{format(parseISO(pair.asked_at), "d MMM yyyy, HH:mm", { locale: ru })}</span>
          </div>
        </div>
        <StatusBadge pair={pair} />
      </div>
    </button>
  );
}

function PairDetails({
  pair,
  actionPending,
  onFalsePositive,
  onCreateTask,
  onRemoveTask,
}: {
  pair: QAPair | null;
  actionPending?: boolean;
  onFalsePositive: (pair: QAPair) => void;
  onCreateTask: (pair: QAPair) => void;
  onRemoveTask: (pair: QAPair) => void;
}) {
  if (!pair) {
    return (
      <div className="card flex min-h-80 items-center justify-center p-8 text-center text-sm text-utmn-muted">
        Выберите вопрос, чтобы посмотреть ответ, источники и метаданные
      </div>
    );
  }

  const status = getPairStatus(pair);
  const StatusIcon = status.icon;
  const needsAction = pair.is_unanswered || pair.is_not_confluence;

  return (
    <div className="card h-full overflow-hidden">
      <div className={cn("border-b border-utmn-border px-5 py-4", status.rowClass)}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-utmn-muted">
              Статус
            </div>
            <div className={cn("mt-1 flex items-center gap-2 text-sm font-semibold", status.accentClass)}>
              <StatusIcon className="h-4 w-4" />
              {status.label}
              {pair.task_status && (pair.is_unanswered || pair.is_not_confluence) && (
                <span className="rounded bg-white/80 px-2 py-0.5 text-xs font-medium text-slate-700">
                  {TASK_STATUS_LABELS[pair.task_status]}
                </span>
              )}
            </div>
          </div>
          <span className="text-xs text-utmn-muted">{status.description}</span>
        </div>
        {needsAction && (
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={actionPending}
              onClick={() => onFalsePositive(pair)}
              className="rounded-md border border-utmn-border bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-utmn-surface disabled:opacity-50"
            >
              Ложное срабатывание
            </button>
            <button
              type="button"
              disabled={actionPending}
              onClick={() => (pair.task_id ? onRemoveTask(pair) : onCreateTask(pair))}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50",
                pair.task_id
                  ? "border border-utmn-border bg-white text-slate-700 hover:bg-utmn-surface"
                  : "bg-utmn-primary text-white hover:bg-utmn-dark",
              )}
            >
              {pair.task_id ? "Убрать из работы" : "Добавить в работу"}
            </button>
          </div>
        )}
      </div>

      <div className="max-h-[calc(100vh-14rem)] space-y-6 overflow-auto p-5">
        <section>
          <div className="mb-2 text-xs font-semibold text-utmn-primary">Вопрос</div>
          <div className="whitespace-pre-wrap text-sm leading-6 text-slate-900">
            {pair.question}
          </div>
        </section>

        <section>
          <div className="mb-2 text-xs font-semibold text-utmn-accent">Ответ</div>
          {pair.answer ? (
            <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
              {pair.answer}
            </div>
          ) : (
            <span className="text-sm italic text-utmn-muted">нет ответа</span>
          )}
        </section>

        <section className="grid grid-cols-1 gap-4 rounded-lg border border-utmn-border bg-utmn-surface/60 p-4 sm:grid-cols-2">
          <MetadataRow label="Платформа">
            <PlatformBadge platform={pair.platform} />
          </MetadataRow>
          <MetadataRow label="Дата и время">
            {format(parseISO(pair.asked_at), "d MMM yyyy, HH:mm", { locale: ru })}
          </MetadataRow>
          <MetadataRow label="Модель">
            {pair.model_used ? (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                {pair.model_used}
              </span>
            ) : (
              "не указана"
            )}
          </MetadataRow>
        </section>

        <section>
          <div className="mb-2 text-xs font-semibold text-utmn-dark">Источники</div>
          <SourceLinks sources={pair.sources} />
        </section>
      </div>
    </div>
  );
}

export function QAPairsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(getViewportPageSize);
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["qa-pairs", page, pageSize, platform, status, search],
    queryFn: () =>
      getQAPairs({
        page,
        size: pageSize,
        platform: platform || undefined,
        status: (status || undefined) as QAStatus | undefined,
        search: search || undefined,
      }),
  });

  useEffect(() => {
    const handleResize = () => {
      const nextPageSize = getViewportPageSize();
      setPageSize((current) => {
        if (current === nextPageSize) return current;
        setPage(1);
        setSelectedQuestionId(null);
        return nextPageSize;
      });
    };

    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (!data?.items.length) {
      setSelectedQuestionId(null);
      return;
    }

    const selectedIsVisible = data.items.some(
      (pair) => pair.question_id === selectedQuestionId,
    );
    if (!selectedIsVisible) {
      setSelectedQuestionId(data.items[0].question_id);
    }
  }, [data?.items, selectedQuestionId]);

  const selectedPair =
    data?.items.find((pair) => pair.question_id === selectedQuestionId) ?? null;

  const falsePositiveMutation = useMutation({
    mutationFn: markQAPairFalsePositive,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const createTaskMutation = useMutation({
    mutationFn: createTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const deleteTaskMutation = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["qa-pairs"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const handleFalsePositive = (pair: QAPair) => {
    const confirmed = window.confirm(
      "Снять проблемный статус с этого вопроса и считать его отвеченным?",
    );
    if (confirmed) {
      falsePositiveMutation.mutate(pair.question_id);
    }
  };

  const handleCreateTask = (pair: QAPair) => {
    createTaskMutation.mutate(pair.question_id);
  };

  const handleRemoveTask = (pair: QAPair) => {
    if (pair.task_id) {
      deleteTaskMutation.mutate(pair.task_id);
    }
  };

  const actionPending =
    falsePositiveMutation.isPending ||
    createTaskMutation.isPending ||
    deleteTaskMutation.isPending;
  const mutationError =
    falsePositiveMutation.error ?? createTaskMutation.error ?? deleteTaskMutation.error;

  return (
    <div className="flex h-screen flex-col overflow-hidden p-8">
      <PageHeader
        title="Вопросы и ответы"
        description="История диалогов пользователей с ботом"
      />
      {mutationError && (
        <div className="mb-3 shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {getErrorMessage(mutationError)}
        </div>
      )}

      <div className="mb-4 flex shrink-0 items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(searchInput);
            setPage(1);
            setSelectedQuestionId(null);
          }}
          className="flex items-center gap-2"
        >
          <Input
            placeholder="Поиск по тексту…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-80"
          />
        </form>
        <Select
          value={platform}
          onChange={(e) => {
            setPlatform(e.target.value);
            setPage(1);
            setSelectedQuestionId(null);
          }}
          options={PLATFORM_OPTIONS}
        />
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
            setSelectedQuestionId(null);
          }}
          options={STATUS_OPTIONS}
        />
      </div>

      {isLoading ? (
        <div className="card p-8 text-center text-utmn-muted">Загрузка…</div>
      ) : !data?.items.length ? (
        <div className="card p-8 text-center text-utmn-muted">Ничего не найдено</div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
          <div className="card flex min-h-0 flex-col overflow-hidden">
            <div className="shrink-0 border-b border-utmn-border px-5 py-3 text-xs font-semibold uppercase tracking-wide text-utmn-muted">
              Вопросы
            </div>
            <div className="min-h-0 divide-y divide-utmn-border overflow-hidden">
              {data.items.map((pair) => (
                <QuestionListItem
                  key={pair.question_id}
                  pair={pair}
                  selected={pair.question_id === selectedQuestionId}
                  onSelect={() => setSelectedQuestionId(pair.question_id)}
                />
              ))}
            </div>
          </div>

          <div className="min-h-0">
            <PairDetails
              pair={selectedPair}
              actionPending={actionPending}
              onFalsePositive={handleFalsePositive}
              onCreateTask={handleCreateTask}
              onRemoveTask={handleRemoveTask}
            />
          </div>
        </div>
      )}

      {data && (
        <Pagination
          page={page}
          size={pageSize}
          total={data.meta.total}
          onChange={(nextPage) => {
            setPage(nextPage);
            setSelectedQuestionId(null);
          }}
        />
      )}
    </div>
  );
}
