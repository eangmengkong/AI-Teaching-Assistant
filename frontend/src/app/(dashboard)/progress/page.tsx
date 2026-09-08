'use client';

import { Check, FileText, Send, SkipForward, Target, TrendingUp } from 'lucide-react';

import Button from '../../../components/Button';
import Card from '../../../components/Card';
import PageHeader from '../../../components/PageHeader';
import PagesChip from '../../../components/PagesChip';
import ProgressBar from '../../../components/ProgressBar';
import Skeleton from '../../../components/Skeleton';
import StatusBadge from '../../../components/StatusBadge';
import Toast from '../../../components/Toast';
import { MILESTONES, useDashboardData } from '../../../lib/useDashboardData';

export default function ProgressPage() {
  const {
    toast,
    loading,
    schedules,
    todayLesson,
    progressData,
    openingPages,
    sendingPagesFor,
    openStudyPages,
    sendLessonToTelegram,
    completeToday,
    skipToday,
  } = useDashboardData();

  if (loading) {
    return (
      <div className="space-y-8" aria-busy="true">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const total = progressData?.total_lessons ?? schedules.length;
  const done = progressData?.completed_lessons ?? 0;

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
        icon={<TrendingUp className="h-6 w-6" />}
        title="Progress & Scores"
        subtitle="How the course is tracking — coverage, completion and assessment averages."
      />

      {/* Big stat row */}
      <section className="grid scroll-mt-20 grid-cols-1 gap-6 md:grid-cols-3">
        <Card className="flex flex-col justify-between">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-glow-accent">
              <Check className="h-5 w-5" />
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-app-accent">Lessons Completed</span>
          </div>
          <p className="mt-5">
            <span className="text-4xl font-extrabold tracking-tight text-app-text">{done}</span>
            <span className="text-xl font-semibold text-app-muted"> / {total}</span>
          </p>
          <ProgressBar value={total ? Math.round((done / total) * 100) : 0} color="indigo" />
        </Card>

        <Card className="flex flex-col justify-between">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-glow-accent">
              <Target className="h-5 w-5" />
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-app-success">Average Quiz Score</span>
          </div>
          <p className="mt-5 text-4xl font-extrabold tracking-tight text-app-text">
            {progressData?.average_quiz_score || '0%'}
          </p>
          <p className="text-xs text-app-muted">Across quizzes delivered by the AI agent</p>
        </Card>

        <Card className="flex flex-col justify-between">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-glow-accent">
              <FileText className="h-5 w-5" />
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">Coverage</span>
          </div>
          <p className="mt-5 text-4xl font-extrabold tracking-tight text-app-text">
            {progressData?.textbook_progress || '0%'}
          </p>
          <p className="text-xs text-app-muted">Textbook pages covered by the plan</p>
        </Card>
      </section>
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Material Coverage" icon={<FileText className="h-4.5 w-4.5" />} tint="indigo">
          <div className="space-y-4">
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
          <div className="mt-5 flex items-start gap-2 rounded-xl border border-app-border bg-app-surface-2 p-3 text-xs text-app-subtle">
            <span aria-hidden>ℹ️</span>
            <span>{progressData?.status_summary || 'On Track'}</span>
          </div>
        </Card>

        <Card title="Today's Lesson" icon={<Target className="h-4.5 w-4.5" />} tint="violet">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-base font-bold text-app-text">
              {todayLesson ? `${todayLesson.unit} — ${todayLesson.lesson}` : 'No Active Lesson Today'}
            </h3>
            <StatusBadge status={todayLesson?.status || 'planned'} />
          </div>
          <p className="mt-1 text-sm text-app-muted">
            {todayLesson ? `${todayLesson.time} • ${todayLesson.date}` : 'Generate a schedule to see today’s plan.'}
          </p>
          <div className="mt-4 space-y-2 text-sm text-app-subtle">
            <p className="flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-app-accent" aria-hidden />
              <strong className="text-app-text">Textbook:</strong>{' '}
              {todayLesson?.textbook_pages ? renderPagesChip('textbook', todayLesson.textbook_pages) : 'N/A'}
            </p>
            <p className="flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-app-success" aria-hidden />
              <strong className="text-app-text">Workbook:</strong>{' '}
              {todayLesson?.workbook_pages ? renderPagesChip('workbook', todayLesson.workbook_pages) : 'N/A'}
            </p>
          </div>
          <div className="mt-6 flex gap-2 border-t border-app-border/80 pt-4">
            <Button variant="success" size="sm" className="flex-1" onClick={() => void completeToday()} disabled={!todayLesson}>
              <Check className="h-4 w-4" aria-hidden />
              Complete
            </Button>
            <Button variant="warning" size="sm" className="flex-1" onClick={() => void skipToday()} disabled={!todayLesson}>
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
            >
              <Send className="h-4 w-4" aria-hidden />
              Send
            </Button>
          </div>
        </Card>

        <Card title="Milestones & Assessments" icon={<Target className="h-4.5 w-4.5" />} tint="amber">
          <div className="mt-1 space-y-3">
            {MILESTONES.map((m) => (
              <div
                key={m.title}
                className="flex items-center justify-between rounded-xl border border-app-border bg-app-surface-2 p-3"
              >
                <div>
                  <p className="text-sm font-semibold text-app-soft">{m.title}</p>
                  <p className="text-xs text-app-muted">{m.caption}</p>
                </div>
                <span className="shrink-0 text-xs font-bold text-app-subtle">{m.tag}</span>
              </div>
            ))}
          </div>
        </Card>
      </section>
      <Toast toast={toast} />
    </div>
  );
}