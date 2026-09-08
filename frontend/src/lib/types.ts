// Shared API response types for the dashboard frontend.
// Field names match the FastAPI schemas (backend/app/schemas/schemas.py).

export interface CourseInfo {
  id: number;
  name: string;
  description?: string | null;
  student_count?: number;
  class_days?: string[];
  start_time?: string;
  end_time?: string;
  start_date?: string;
  end_date?: string;
  holidays?: string[];
  days_without_class?: string[];
  teaching_frequency?: string;
  teacher_timezone?: string;
  status?: string;
}

export interface DocumentInfo {
  id: number;
  course_id: number;
  document_type: 'textbook' | 'workbook';
  filename: string;
  total_pages: number;
  status: string;
}

export interface ScheduleItem {
  id: number;
  date: string;
  start_time: string;
  end_time: string;
  unit: string;
  lesson: string;
  textbook_pages?: string | null;
  workbook_pages?: string | null;
  status: string;
}

export interface TodayLesson {
  id: number;
  unit: string;
  lesson: string;
  time: string;
  date: string;
  textbook_pages?: string | null;
  workbook_pages?: string | null;
  objectives?: string | null;
  status: string;
}

export interface ProgressInfo {
  status: string;
  textbook_progress: string; // "42%"
  workbook_progress: string; // "38%"
  completed_lessons: number;
  total_lessons: number;
  average_quiz_score: string; // "85.0%"
  status_summary: string;
}

export interface AuthInfo {
  auth_url: string;
  has_client_id: boolean;
  connected: boolean;
}

export interface SyncResult {
  status: string;
  google_connected: boolean;
  total_synced: number;
  message: string;
}

export type ScheduleState = 'idle' | 'analyzing' | 'building' | 'done' | 'error';

export interface ScheduleStatus {
  state: ScheduleState;
  course_id: number;
  progress: number;
  message: string;
}