'use client';

import {
  Bot,
  CalendarCheck,
  Check,
  FileText,
  GraduationCap,
  Send,
  SkipForward,
  Sparkles,
  TrendingUp,
} from 'lucide-react';

import Button from '../../components/Button';
import Card from '../../components/Card';
import PageHeader from '../../components/PageHeader';
import PagesChip from '../../components/PagesChip';
import ProgressBar from '../../components/ProgressBar';
import Skeleton from '../../components/Skeleton';
import StatusBadge from '../../components/StatusBadge';
import Toast from '../../components/Toast';
import { MILESTONES, useDashboardData } from '../../lib/useDashboardData';

export default function DashboardPage() {
  const {
    toast,
    loading,
    loadError,
    reload,
    schedules,
    todayLesson,
    progressData,
    googleConnected,
    syncedCount,
    syncCalendar,
    openingPages,
    sendingPagesFor,
    openStudyPages,
    sendLessonToTelegram,
    completeToday,
    skipToday,
  } = useDashboardData();

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
      {loadError && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-600 dark:text-rose-200 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-center gap-2">
            <span aria-hidden>⚠️</span>
            <span>Could not reach the API — {loadError}</span>
          </div>
          <Button variant="danger" size="sm" onClick={reload}>
            Retry
          </Button>
        </div>
      )}

      <PageHeader
        icon={<GraduationCap className="h-6 w-6" />}
        title="Course Overview"
        subtitle="Your 1-month study plan at a glance — kept in sync automatically with Google Calendar & Telegram."
        actions={
          <>
            <Button variant={googleConnected ? 'success' : 'primary'} onClick={() => void syncCalendar()}>
              <CalendarCheck className="h-4 w-4" aria-hidden />
              {googleConnected
                ? `Calendar Synced${syncedCount > 0 ? ` · ${syncedCount} events` : ''}`
                : 'Sync Google Calendar'}
            </Button>
            <a
              href="https://t.me/Assistant_Teaching_bot"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-app-border-strong bg-app-hover px-4 py-2 text-sm font-semibold text-app-soft transition hover:border-app-border hover:bg-app-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
            >
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden />
              Telegram Bot
            </a>
          </>
        }
      />

      {loading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3" aria-busy="true" aria-label="Loading dashboard">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : (
        <>
          {/* Overview cards */}
          <section className="grid scroll-mt-20 grid-cols-1 gap-6 md:grid-cols-3">
            <Card className="flex flex-col justify-between">
              <div>
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-app-accent">
                    Today's Scheduled Lesson
                  </span>
                  <StatusBadge status={todayLesson?.status || 'planned'} />
                </div>
                <h3 className="text-lg font-bold text-app-text">
                  {todayLesson ? `${todayLesson.unit} — ${todayLesson.lesson}` : 'No Active Lesson Today'}
                </h3>
                <p className="mt-1 text-sm text-app-muted">
                  {todayLesson
                    ? `${todayLesson.time} • ${todayLesson.date}`
                    : 'Generate a schedule to see today’s plan.'}
                </p>
                <div className="mt-4 space-y-2 text-sm text-app-subtle">
                  <p className="flex items-center gap-1.5">
                    <FileText className="h-4 w-4 text-app-accent" aria-hidden />
                    <strong className="text-app-text">Textbook:</strong>{' '}
                    {todayLesson?.textbook_pages ? renderPagesChip('textbook', todayLesson.textbook_pages) : 'N/A'}
                  </p>
                  <p className="flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4 text-app-success" aria-hidden />
                    <strong className="text-app-text">Workbook:</strong>{' '}
                    {todayLesson?.workbook_pages ? renderPagesChip('workbook', todayLesson.workbook_pages) : 'N/A'}
                  </p>
                  <p className="flex items-center gap-1.5">
                    <Sparkles className="h-4 w-4 text-amber-500" aria-hidden />
                    <strong className="text-app-text">Objectives:</strong>{' '}
                    {todayLesson?.objectives || 'General lesson study'}
                  </p>
                </div>
              </div>
              <div className="mt-6 flex gap-2 border-t border-app-border/80 pt-4">
                <Button
                  variant="success"
                  size="sm"
                  className="flex-1"
                  onClick={() => void completeToday()}
                  disabled={!todayLesson}
                >
                  <Check className="h-4 w-4" aria-hidden />
                  Complete
                </Button>
                <Button
                  variant="warning"
                  size="sm"
                  className="flex-1"
                  onClick={() => void skipToday()}
                  disabled={!todayLesson}
                >
                  <SkipForward className="h-4 w-4" aria-hidden />
                  Skip
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  onClick={() => todayLesson && void sendLessonToTelegram(todayLesson.id)}
                  disabled={!todayLesson || sendingPagesFor !== null}
                  loading={sendingPagesFor === todayLesson?.id}
                  title="Send this lesson's textbook & workbook pages to Telegram"
                >
                  <Send className="h-4 w-4" aria-hidden />
                  Send
                </Button>
              </div>
            </Card>

            <Card className="flex flex-col justify-between">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-app-accent">Course Progress</span>
                <div className="mt-4 space-y-4">
                  <div>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="text-app-subtle">Textbook Coverage</span>
                      <span className="font-bold text-app-accent">{progressData?.textbook_progress || '0%'}</span>
                    </div>
                    <ProgressBar value={progressData?.textbook_progress || '0%'} color="indigo" />
                  </div>
                  <div>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="text-app-subtle">Workbook Exercises</span>
                      <span className="font-bold text-app-success">{progressData?.workbook_progress || '0%'}</span>
                    </div>
                    <ProgressBar value={progressData?.workbook_progress || '0%'} color="emerald" />
                  </div>
                </div>
                <div className="mt-6 space-y-2 border-t border-app-border/80 pt-4 text-sm">
                  <div className="flex justify-between text-app-subtle">
                    <span>Completed Lessons</span>
                    <span className="font-semibold text-app-text">
                      {progressData?.completed_lessons ?? 0} / {progressData?.total_lessons ?? schedules.length}
                    </span>
                  </div>
                  <div className="flex justify-between text-app-subtle">
                    <span>Average Quiz Score</span>
                    <span className="font-semibold text-app-success">{progressData?.average_quiz_score || '0%'}</span>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-start gap-2 rounded-xl border border-app-border bg-app-surface-2 p-2.5 text-xs text-app-subtle">
                <span aria-hidden>ℹ️</span>
                <span>{progressData?.status_summary || 'On Track'}</span>
              </div>
            </Card>

            <Card className="flex flex-col justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-app-accent">
                Milestones &amp; Assessments
              </span>
              <div className="mt-4 space-y-3">
                {MILESTONES.map((m) => (
                  <div
                    key={m.title}
                    className="flex items-center justify-between rounded-xl border border-app-border bg-app-surface-2 p-3"
                  >
                    <div>
                      <p className="text-sm font-semibold text-app-soft">{m.title}</p>
                      <p className="text-xs text-app-muted">{m.caption}</p>
                    </div>
                    <span className="text-sm font-bold text-app-subtle">{m.tag}</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-app-faint">
                <Sparkles className="h-3.5 w-3.5" aria-hidden />
                Strict Anti-Hallucination active.
              </p>
            </Card>
          </section>
          {!loading && schedules.length === 0 && (
            <div className="rounded-2xl border border-dashed border-app-border bg-app-surface/60 p-6 text-center text-sm text-app-muted">
              No schedule generated yet — configure the course, upload your materials, then
              <span className="mx-1 font-semibold text-app-success">generate the 1-month schedule</span>.
            </div>
          )}

          {/* Integrations strip */}
          <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card
              title="Google Calendar"
              subtitle="Push every session to your Google Calendar"
              icon={<CalendarCheck className="h-4.5 w-4.5" />}
              tint="indigo"
              hover
            >
              <div className="flex items-center justify-between gap-3">
                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${
                  googleConnected
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-app-success'
                    : 'border-app-border bg-app-surface-2 text-app-muted'
                }`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${googleConnected ? 'bg-emerald-400 animate-pulse-soft' : 'bg-app-muted'}`} aria-hidden />
                  {googleConnected ? 'Connected' : 'Not connected'}
                </span>
                <Button variant="secondary" size="sm" onClick={() => void syncCalendar()}>
                  {googleConnected ? 'Resync' : 'Connect'}
                </Button>
              </div>
            </Card>
            <Card
              title="Telegram Delivery"
              subtitle="Receive today's study pages as PDFs in chat"
              icon={<Bot className="h-4.5 w-4.5" />}
              tint="emerald"
              hover
            >
              <div className="flex items-center justify-between gap-3">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-app-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse-soft" aria-hidden />
                  Bot agent live
                </span>
                <a
                  href="https://t.me/Assistant_Teaching_bot"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl border border-app-border-strong bg-app-hover px-4 py-2 text-xs font-semibold text-app-soft transition hover:bg-app-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
                >
                  Open @Assistant_Teaching_bot
                </a>
              </div>
            </Card>
          </section>
        </>
      )}

      <Toast toast={toast} />
    </div>
  );
}