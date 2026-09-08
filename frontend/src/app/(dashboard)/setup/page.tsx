'use client';

import { Info, Settings, Sparkles } from 'lucide-react';

import Button from '../../../components/Button';
import Card from '../../../components/Card';
import Field from '../../../components/Field';
import PageHeader from '../../../components/PageHeader';
import Skeleton from '../../../components/Skeleton';
import Toast from '../../../components/Toast';
import { useDashboardData } from '../../../lib/useDashboardData';

export default function CourseSetupPage() {
  const {
    toast,
    loading,
    courseName,
    setCourseName,
    studentCount,
    setStudentCount,
    classDays,
    setClassDays,
    startTime,
    setStartTime,
    endTime,
    setEndTime,
    startDate,
    setStartDate,
    endDate,
    setEndDate,
    holidays,
    setHolidays,
    saving,
    saveSettings,
  } = useDashboardData();

  if (loading) {
    return (
      <div className="space-y-8" aria-busy="true">
        <Skeleton className="h-24" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader
        icon={<Settings className="h-6 w-6" />}
        title="Course Setup"
        subtitle="Describe the class so the AI agent can build an accurate monthly plan."
        meta={
          <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-app-accent">
            <Info className="h-3.5 w-3.5" aria-hidden />
            Changes are saved to the course profile
          </span>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Course Information & Availability"
          icon={<Settings className="h-4.5 w-4.5" />}
          tint="indigo"
          subtitle="Used by the AI agent to build the monthly plan"
        >
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Course Name"
                value={courseName}
                onChange={(e) => setCourseName(e.target.value)}
                placeholder="e.g. English 101"
              />
              <Field
                label="Number of Students"
                type="number"
                min={1}
                value={studentCount}
                onChange={(e) => setStudentCount(e.target.value)}
              />
            </div>
            <Field
              label="Class Days"
              value={classDays}
              onChange={(e) => setClassDays(e.target.value)}
              placeholder="e.g. Monday, Wednesday, Friday"
              hint="Comma-separated weekdays"
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Start Time"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
              <Field
                label="End Time"
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Start Date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
              <Field
                label="End Date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            <Field
              label="Holidays / Excluded Dates"
              value={holidays}
              onChange={(e) => setHolidays(e.target.value)}
              placeholder="e.g. 2026-09-24"
              hint="Comma-separated dates (YYYY-MM-DD)"
            />
            <Button variant="primary" size="full" onClick={() => void saveSettings()} loading={saving}>
              Save Settings
            </Button>
          </div>
        </Card>

        <Card
          title="What the AI uses"
          icon={<Sparkles className="h-4.5 w-4.5" />}
          tint="violet"
          subtitle="How these details shape your plan"
        >
          <ul className="space-y-2.5 text-sm text-app-subtle">
            <li className="flex items-start gap-2">
              <span aria-hidden className="text-app-accent">✦</span>
              <span><strong className="text-app-text">Class days &amp; times</strong> become the recurring session skeleton.</span>
            </li>
            <li className="flex items-start gap-2">
              <span aria-hidden className="text-app-accent">✦</span>
              <span><strong className="text-app-text">Holidays</strong> are skipped automatically when the schedule is generated.</span>
            </li>
            <li className="flex items-start gap-2">
              <span aria-hidden className="text-app-accent">✦</span>
              <span><strong className="text-app-text">Start / end dates</strong> bound the 1-month horizon.</span>
            </li>
            <li className="flex items-start gap-2">
              <span aria-hidden className="text-app-accent">✦</span>
              <span><strong className="text-app-text">Student count</strong> is passed to exercises &amp; pacing suggestions.</span>
            </li>
          </ul>
          <p className="mt-5 rounded-xl border border-app-border bg-app-surface-2 p-3 text-xs text-app-muted">
            You can edit this any time and re-generate the schedule to apply changes.
          </p>
        </Card>
      </div>

      <Toast toast={toast} />
    </div>
  );
}