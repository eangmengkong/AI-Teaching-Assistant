'use client';

import { CalendarDays, RefreshCw, Send, Sparkles } from 'lucide-react';

import Button from '../../../components/Button';
import Card from '../../../components/Card';
import PageHeader from '../../../components/PageHeader';
import PagesChip from '../../../components/PagesChip';
import ProgressBar from '../../../components/ProgressBar';
import Skeleton from '../../../components/Skeleton';
import StatusBadge from '../../../components/StatusBadge';
import Toast from '../../../components/Toast';
import { useDashboardData } from '../../../lib/useDashboardData';

export default function SchedulePage() {
  const {
    toast,
    loading,
    schedules,
    analyzingSchedule,
    scheduleProgress,
    scheduleSeconds,
    scheduleMessage,
    generateSchedule,
    openingPages,
    sendingPagesFor,
    openStudyPages,
    sendLessonToTelegram,
  } = useDashboardData();

  if (loading) {
    return (
      <div className="space-y-8" aria-busy="true">
        <Skeleton className="h-24" />
        <Skeleton className="h-72" />
      </div>
    );
  }

  const renderPagesChip = (kind: 'textbook' | 'workbook', spec: string) => (
    <PagesChip
      kind={kind}
      spec={spec}
      busy={openingPages !== null}
      onOpen={() => void openStudyPages(kind, spec)}
    />
  );

  return (
    <div className="space-y-8">
      <PageHeader
        icon={<CalendarDays className="h-6 w-6" />}
        title="1-Month Schedule"
        subtitle="The AI agent plans every session, page range and assessment into a single calendar."
        actions={
          <Button variant="primary" onClick={() => void generateSchedule()} disabled={analyzingSchedule} loading={analyzingSchedule}>
            <RefreshCw className="h-4 w-4" aria-hidden />
            {analyzingSchedule ? 'Generating…' : 'Generate 1-Month Schedule'}
          </Button>
        }
        meta={
          <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-app-accent">
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            {schedules.length} sessions planned
          </span>
        }
      />

      {analyzingSchedule && (
        <Card
          title="Central AI Agent at work"
          icon={<Sparkles className="h-4.5 w-4.5" />}
          tint="violet"
          subtitle="The server-side scheduler is building your plan…"
        >
          <div className="space-y-2">
            <div className="flex justify-between gap-2 text-xs font-mono text-app-accent">
              <span className="truncate">{scheduleMessage || '✨ Analyzing course materials…'}</span>
              <span className="shrink-0">
                {scheduleProgress}% ({scheduleSeconds}s)
              </span>
            </div>
            <ProgressBar value={scheduleProgress} color="gradient" />
          </div>
        </Card>
      )}

      {!analyzingSchedule && schedules.length === 0 && (
        <Card
          title="No schedule yet"
          icon={<CalendarDays className="h-4.5 w-4.5" />}
          tint="indigo"
          actions={
            <Button variant="primary" size="sm" onClick={() => void generateSchedule()}>
              <RefreshCw className="h-4 w-4" aria-hidden />
              Generate
            </Button>
          }
        >
          <p className="text-sm text-app-muted">
            Configure the course and upload your materials first, then generate the 1-month schedule.
            The plan will also be pushed to Google Calendar and Telegram.
          </p>
        </Card>
      )}
      {!analyzingSchedule && schedules.length > 0 && (
        <Card
          title="Planned Sessions"
          icon={<CalendarDays className="h-4.5 w-4.5" />}
          tint="indigo"
          actions={
            <span className="inline-flex items-center rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-app-accent">
              {schedules.length} Sessions
            </span>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm text-app-subtle">
              <thead className="border-b border-app-border bg-app-surface-2 text-xs uppercase tracking-wider text-app-muted">
                <tr>
                  <th className="px-4 py-3 font-semibold">Date</th>
                  <th className="px-4 py-3 font-semibold">Unit / Lesson</th>
                  <th className="px-4 py-3 font-semibold">Textbook</th>
                  <th className="px-4 py-3 font-semibold">Workbook</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Study</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-app-border/60">
                {schedules.map((item) => (
                  <tr key={item.id} className="transition-colors hover:bg-app-surface-2/40">
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-app-soft">
                      {item.date} <span className="text-app-faint">({item.start_time}–{item.end_time})</span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-app-accent">
                      {item.unit} – {item.lesson}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-app-accent">
                      {item.textbook_pages
                        ? renderPagesChip('textbook', item.textbook_pages)
                        : <span className="text-app-faint">N/A</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-app-success">
                      {item.workbook_pages
                        ? renderPagesChip('workbook', item.workbook_pages)
                        : <span className="text-app-faint">N/A</span>}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void sendLessonToTelegram(item.id)}
                        disabled={sendingPagesFor !== null}
                        loading={sendingPagesFor === item.id}
                        title="Send this lesson's study pages to Telegram"
                      >
                        <Send className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <Toast toast={toast} />
    </div>
  );
}