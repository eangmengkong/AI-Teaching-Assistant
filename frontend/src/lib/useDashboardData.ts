'use client';

import { useCallback, useEffect, useState } from 'react';

import { api, apiBlob, apiUploadJson, compressFileIfSupported, openBlobInNewTab, safeGet } from './api';
import { useToast } from './useToast';
import type { ToastData, ToastType } from './useToast';
import type {
  AuthInfo,
  CourseInfo,
  DocumentInfo,
  ProgressInfo,
  ScheduleItem,
  ScheduleStatus,
  SyncResult,
  TodayLesson,
} from './types';

export const DEFAULT_COURSE_ID = 1;

/** Fallbacks shown until the backend returns real course data. */
export const FALLBACK = {
  courseName: 'English 101',
  studentCount: '25',
  classDays: 'Monday, Wednesday, Friday',
  startTime: '08:00',
  endTime: '09:30',
  startDate: '2026-09-07',
  endDate: '2026-10-02',
  holidays: '2026-09-24',
} as const;

export const MILESTONES = [
  { title: 'Quizzes & Exercises', caption: 'Completed Content Only', tag: 'Periodic' },
  { title: 'Final Review', caption: 'Full Course Recap', tag: 'End of Term' },
  { title: 'Final Examination', caption: 'Comprehensive Exam', tag: 'Final Session' },
] as const;

export interface UploadedDoc {
  filename: string;
  total_pages: number;
}

export interface CourseDashboard {
  courseId: number;
  toast: ToastData | null;
  showToast: (type: ToastType, message: string) => void;
  loading: boolean;
  loadError: string | null;
  reload: () => void;
  courseName: string;
  setCourseName: (v: string) => void;
  studentCount: string;
  setStudentCount: (v: string) => void;
  classDays: string;
  setClassDays: (v: string) => void;
  startTime: string;
  setStartTime: (v: string) => void;
  endTime: string;
  setEndTime: (v: string) => void;
  startDate: string;
  setStartDate: (v: string) => void;
  endDate: string;
  setEndDate: (v: string) => void;
  holidays: string;
  setHolidays: (v: string) => void;
  saving: boolean;
  saveSettings: () => Promise<void>;
  schedules: ScheduleItem[];
  todayLesson: TodayLesson | null;
  progressData: ProgressInfo | null;
  googleConnected: boolean;
  syncedCount: number;
  syncCalendar: () => Promise<void>;
  textbookDoc: UploadedDoc | null;
  workbookDoc: UploadedDoc | null;
  uploadingTb: boolean;
  uploadingWb: boolean;
  tbSeconds: number;
  wbSeconds: number;
  tbProgress: number;
  wbProgress: number;
  tbSpeedMbS: number;
  wbSpeedMbS: number;
  uploadFile: (file: File, kind: 'textbook' | 'workbook') => Promise<void>;
  analyzingSchedule: boolean;
  scheduleProgress: number;
  scheduleSeconds: number;
  scheduleMessage: string;
  generateSchedule: () => Promise<void>;
  openingPages: string | null;
  sendingPagesFor: number | null;
  openStudyPages: (kind: 'textbook' | 'workbook', spec: string) => Promise<void>;
  sendLessonToTelegram: (lessonId: number) => Promise<void>;
  completeToday: () => Promise<void>;
  skipToday: () => Promise<void>;
}

/**
 * Central store for every dashboard action & fetched value. Each page of the
 * app (`/`, `/setup`, `/documents`, `/schedule`, `/progress`) consumes only
 * the slices it needs, so data stays consistent across navigation and a
 * reload after any mutation refreshes the whole app.
 */
export function useDashboardData(): CourseDashboard {
  const { toast, showToast } = useToast();
  const [courseId, setCourseId] = useState(DEFAULT_COURSE_ID);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [courseName, setCourseName] = useState<string>(FALLBACK.courseName);
  const [studentCount, setStudentCount] = useState<string>(FALLBACK.studentCount);
  const [classDays, setClassDays] = useState<string>(FALLBACK.classDays);
  const [startTime, setStartTime] = useState<string>(FALLBACK.startTime);
  const [endTime, setEndTime] = useState<string>(FALLBACK.endTime);
  const [startDate, setStartDate] = useState<string>(FALLBACK.startDate);
  const [endDate, setEndDate] = useState<string>(FALLBACK.endDate);
  const [holidays, setHolidays] = useState<string>(FALLBACK.holidays);
  const [saving, setSaving] = useState(false);

  const [textbookDoc, setTextbookDoc] = useState<UploadedDoc | null>(null);
  const [workbookDoc, setWorkbookDoc] = useState<UploadedDoc | null>(null);
  const [uploadingTb, setUploadingTb] = useState(false);
  const [uploadingWb, setUploadingWb] = useState(false);
  const [tbSeconds, setTbSeconds] = useState(0);
  const [wbSeconds, setWbSeconds] = useState(0);
  const [tbProgress, setTbProgress] = useState(0);
  const [wbProgress, setWbProgress] = useState(0);
  const [tbSpeedMbS, setTbSpeedMbS] = useState(0);
  const [wbSpeedMbS, setWbSpeedMbS] = useState(0);

  const [analyzingSchedule, setAnalyzingSchedule] = useState(false);
  const [scheduleProgress, setScheduleProgress] = useState(0);
  const [scheduleSeconds, setScheduleSeconds] = useState(0);
  const [scheduleMessage, setScheduleMessage] = useState('');

  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [todayLesson, setTodayLesson] = useState<TodayLesson | null>(null);
  const [progressData, setProgressData] = useState<ProgressInfo | null>(null);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [syncedCount, setSyncedCount] = useState(0);

  const [openingPages, setOpeningPages] = useState<string | null>(null);
  const [sendingPagesFor, setSendingPagesFor] = useState<number | null>(null);
const loadAllData = useCallback(async () => {
    setLoadError(null);
    try {
      const [courseRes, schedRes, todayRes, progRes, docsRes, authRes] = await Promise.all([
        safeGet<CourseInfo>(`/api/v1/courses/${courseId}`),
        safeGet<ScheduleItem[]>(`/api/v1/schedule/${courseId}`),
        safeGet<{ status: string; lesson: TodayLesson | null }>(`/api/v1/lessons/today/${courseId}`),
        safeGet<ProgressInfo>(`/api/v1/progress/${courseId}`),
        safeGet<DocumentInfo[]>(`/api/v1/documents/${courseId}`),
        safeGet<AuthInfo>('/api/v1/calendar/auth-url'),
      ]);

      if (courseRes?.id) {
        setCourseId(courseRes.id);
        setCourseName(courseRes.name || FALLBACK.courseName);
        setStudentCount(String(courseRes.student_count ?? FALLBACK.studentCount));
        setClassDays(courseRes.class_days?.length ? courseRes.class_days.join(', ') : FALLBACK.classDays);
        setStartTime(courseRes.start_time || FALLBACK.startTime);
        setEndTime(courseRes.end_time || FALLBACK.endTime);
        setStartDate(courseRes.start_date || FALLBACK.startDate);
        setEndDate(courseRes.end_date || FALLBACK.endDate);
        setHolidays(courseRes.holidays?.length ? courseRes.holidays.join(', ') : FALLBACK.holidays);
      }

      setSchedules(Array.isArray(schedRes) ? schedRes : []);
      setTodayLesson(todayRes?.status === 'success' ? todayRes.lesson : null);
      setProgressData(progRes?.status === 'success' ? progRes : null);
      setGoogleConnected(!!authRes?.connected);

      if (Array.isArray(docsRes)) {
        setTextbookDoc(null);
        setWorkbookDoc(null);
        docsRes.forEach((doc) => {
          const info = { filename: doc.filename, total_pages: doc.total_pages || 0 };
          if (doc.document_type === 'textbook') setTextbookDoc(info);
          else if (doc.document_type === 'workbook') setWorkbookDoc(info);
        });
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    void loadAllData();
  }, [loadAllData]);

  const reload = useCallback(() => {
    setLoading(true);
    void loadAllData();
  }, [loadAllData]);

  const uploadFile = async (file: File, kind: 'textbook' | 'workbook') => {
    const isTextbook = kind === 'textbook';
    const setUploading = isTextbook ? setUploadingTb : setUploadingWb;
    const setSeconds = isTextbook ? setTbSeconds : setWbSeconds;
    const setProgress = isTextbook ? setTbProgress : setWbProgress;
    const setSpeed = isTextbook ? setTbSpeedMbS : setWbSpeedMbS;

    setUploading(true);
    setSeconds(0);
    setProgress(2);
    setSpeed(0);

    // Free client-side compression (browser built-in) — smaller payload, faster upload.
    const { blob: uploadBlob, compressed } = await compressFileIfSupported(file);
    const formData = new FormData();
    formData.append('course_id', String(courseId));
    formData.append('document_type', kind);
    formData.append('compressed', compressed ? '1' : '0');
    formData.append('file', uploadBlob, file.name);

    const startedAt = Date.now();
    let prevLoaded = 0;
    let prevAt = startedAt;
    let speed = 0;

    try {
      const data = (await apiUploadJson('/api/v1/documents/upload', formData, (e) => {
        if (!e.total) return;
        const now = Date.now();
        const dt = Math.max(0.2, (now - prevAt) / 1000);
        const instMbS = ((e.loaded - prevLoaded) / (1024 * 1024)) / dt;
        speed = speed === 0 ? instMbS : speed * 0.6 + instMbS * 0.4;
        prevLoaded = e.loaded;
        prevAt = now;
        setSpeed(Math.round(speed * 10) / 10);
        setProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)));
        setSeconds(Math.floor((now - startedAt) / 1000));
      })) as DocumentInfo;

      if (data.status === 'pending') {
        // The file was stored instantly; parsing runs in the background worker.
        // Poll until this document is processed (or fails) so the ready-check
        // and page counts stay accurate.
        const deadline = Date.now() + 10 * 60 * 1000;
        while (Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 2000));
          const docs = await safeGet<DocumentInfo[]>(`/api/v1/documents/${courseId}`);
          const match = (docs ?? []).find((d) => d.id === data.id);
          if (match?.status === 'processed') {
            const updated = { filename: match.filename, total_pages: match.total_pages || 0 };
            if (isTextbook) setTextbookDoc(updated);
            else setWorkbookDoc(updated);
            setProgress(100);
            setSpeed(0);
            setUploading(false);
            showToast('success', `${isTextbook ? 'Textbook' : 'Workbook'} uploaded & processed`);
            return;
          }
          if (match?.status === 'error') {
            throw new Error('The server could not process that file.');
          }
          setSeconds(Math.floor((Date.now() - startedAt) / 1000));
          setProgress(99);
        }
        setSpeed(0);
        setUploading(false);
        showToast('info', 'Upload complete — still processing in the background. It will be ready shortly.');
        return;
      }

      const updated = { filename: data.filename, total_pages: data.total_pages || 0 };
      if (isTextbook) setTextbookDoc(updated);
      else setWorkbookDoc(updated);
      setProgress(100);
      setSpeed(0);
      setUploading(false);
      showToast('success', `${isTextbook ? 'Textbook' : 'Workbook'} uploaded & processed`);
    } catch (err) {
      setUploading(false);
      setSpeed(0);
      const errorMsg = err instanceof Error ? err.message : 'unknown error';
      if (errorMsg.includes('abort') || errorMsg.includes('timeout')) {
        showToast('error', 'Upload timed out. Please try again with a stable connection.');
      } else {
        showToast('error', `Upload failed: ${errorMsg}`);
      }
    }
  };
const generateSchedule = async () => {
    setAnalyzingSchedule(true);
    setScheduleProgress(10);
    setScheduleSeconds(0);
    setScheduleMessage('Queued…');

    const startedAt = Date.now();
    const timer = setInterval(
      () => setScheduleSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );

    try {
      await api(`/api/v1/schedule/generate/${courseId}`, { method: 'POST' });

      let state = '';
      let backendMessage = '';
      for (let attempt = 0; attempt < 360 && state !== 'done' && state !== 'error'; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const job = await safeGet<ScheduleStatus>(`/api/v1/schedule/status/${courseId}`);
        if (!job) continue;
        state = job.state;
        backendMessage = job.message || backendMessage;
        setScheduleProgress(job.progress ?? 0);
        setScheduleMessage(job.message || 'Working…');
      }

      if (state === 'done') {
        setScheduleProgress(100);
        showToast('success', '1-month schedule generated');
      } else if (state === 'error') {
        throw new Error(
          `Schedule generation failed${backendMessage ? `: ${backendMessage}` : '. Check the backend logs.'}`,
        );
      } else {
        throw new Error('Schedule generation timed out.');
      }
      await reload();
    } catch (err) {
      showToast('error', `Schedule generation failed: ${err instanceof Error ? err.message : 'unknown error'}`);
    } finally {
      clearInterval(timer);
      setScheduleProgress(0);
      setAnalyzingSchedule(false);
    }
  };

  const openStudyPages = async (kind: 'textbook' | 'workbook', spec: string) => {
    setOpeningPages(`${kind}:${spec}`);
    try {
      const blob = await apiBlob(
        `/api/v1/documents/${courseId}/pages?document_type=${kind}&page_spec=${encodeURIComponent(spec)}`,
      );
      openBlobInNewTab(blob);
      showToast('success', `Opened ${kind} pages ${spec} in a new tab`);
    } catch (err) {
      showToast('error', `Could not build PDF: ${err instanceof Error ? err.message : 'unknown error'}`);
    } finally {
      setOpeningPages(null);
    }
  };

  const sendLessonToTelegram = async (lessonId: number) => {
    setSendingPagesFor(lessonId);
    try {
      const res = await api<{
        status: string;
        sent: { kind: string }[];
        skipped: { kind: string; reason: string }[];
      }>(`/api/v1/telegram/send-pages/${lessonId}`, { method: 'POST' });
      if (res.sent && res.sent.length > 0) {
        showToast('success', `Sent ${res.sent.length} study PDF${res.sent.length > 1 ? 's' : ''} to Telegram`);
      } else {
        showToast('info', res.skipped?.[0]?.reason || 'Nothing to send for this lesson');
      }
    } catch (err) {
      showToast('error', `Telegram send failed: ${err instanceof Error ? err.message : 'unknown error'}`);
    } finally {
      setSendingPagesFor(null);
    }
  };
const completeToday = async () => {
    if (!todayLesson) return;
    try {
      await api('/api/v1/lessons/complete', {
        method: 'POST',
        body: JSON.stringify({ lesson_id: todayLesson.id, completion_status: 'fully' }),
      });
      showToast('success', `"${todayLesson.lesson}" marked as complete`);
      await reload();
    } catch (err) {
      showToast('error', `Could not complete lesson: ${err instanceof Error ? err.message : 'unknown error'}`);
    }
  };

  const skipToday = async () => {
    if (!todayLesson) return;
    try {
      await api('/api/v1/schedule/skip', {
        method: 'POST',
        body: JSON.stringify({ lesson_id: todayLesson.id, reason: 'Skipped from web dashboard' }),
      });
      showToast('info', `"${todayLesson.lesson}" skipped`);
      await reload();
    } catch (err) {
      showToast('error', `Could not skip lesson: ${err instanceof Error ? err.message : 'unknown error'}`);
    }
  };

  const syncCalendar = async () => {
    try {
      const data = await api<SyncResult>(`/api/v1/calendar/sync/${courseId}`, { method: 'POST' });
      setGoogleConnected(data.google_connected);
      setSyncedCount(data.total_synced || 0);
      showToast(data.google_connected ? 'success' : 'info', data.message || 'Calendar sync finished');
    } catch (err) {
      setGoogleConnected(false);
      showToast('error', `Calendar sync failed: ${err instanceof Error ? err.message : 'unknown error'}`);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const payload = {
        name: courseName.trim(),
        student_count: parseInt(studentCount, 10) || 0,
        class_days: classDays
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        start_time: startTime,
        end_time: endTime,
        start_date: startDate,
        end_date: endDate,
        holidays: holidays
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      };

      try {
        await api(`/api/v1/courses/${courseId}`, { method: 'PUT', body: JSON.stringify(payload) });
      } catch {
        const created = await api<CourseInfo>('/api/v1/courses/', { method: 'POST', body: JSON.stringify(payload) });
        setCourseId(created.id);
      }
      showToast('success', 'Course settings saved');
    } catch (err) {
      showToast('error', `Could not save settings: ${err instanceof Error ? err.message : 'unknown error'}`);
    } finally {
      setSaving(false);
    }
  };
return {
    courseId,
    toast,
    showToast,
    loading,
    loadError,
    reload,
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
    schedules,
    todayLesson,
    progressData,
    googleConnected,
    syncedCount,
    syncCalendar,
    textbookDoc,
    workbookDoc,
    uploadingTb,
    uploadingWb,
    tbSeconds,
    wbSeconds,
    tbProgress,
    wbProgress,
    tbSpeedMbS,
    wbSpeedMbS,
    uploadFile,
    analyzingSchedule,
    scheduleProgress,
    scheduleSeconds,
    scheduleMessage,
    generateSchedule,
    openingPages,
    sendingPagesFor,
    openStudyPages,
    sendLessonToTelegram,
    completeToday,
    skipToday,
  };
}