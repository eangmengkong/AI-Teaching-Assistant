'use client';

import { BookOpen } from 'lucide-react';
import { Pencil } from 'lucide-react';
import { UploadCloud } from 'lucide-react';
import { useRef, useState } from 'react';
import type { ChangeEvent, DragEvent } from 'react';
import ProgressBar from './ProgressBar';

export const MAX_UPLOAD_SIZE = 500 * 1024 * 1024; // match backend (500 MB)
export const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.txt'];

interface UploadCardProps {
  /** Unique id so the hidden file input + its label are connected. */
  uploadId: string;
  kind: 'textbook' | 'workbook';
  title: string;
  uploading: boolean;
  progress: number;
  seconds: number;
  fileName?: { filename: string; total_pages: number } | null;
  onFile: (file: File) => void;
  onInvalid?: (message: string) => void;
}

const KIND_CONFIG = {
  textbook: {
    icon: BookOpen,
    iconClasses: 'text-app-accent',
    barColor: 'indigo',
    gradient: 'from-indigo-500 to-violet-500',
    processingLabel: 'Parsing pages & building AI search index',
  },
  workbook: {
    icon: Pencil,
    iconClasses: 'text-app-success',
    barColor: 'emerald',
    gradient: 'from-emerald-500 to-teal-500',
    processingLabel: 'Parsing exercises & page references',
  },
} as const;

function validateFile(file: File): string | null {
  const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `Unsupported file type "${ext}". Allowed: PDF, DOCX, DOC, TXT.`;
  }
  if (file.size > MAX_UPLOAD_SIZE) {
    return 'File exceeds the 500 MB upload limit.';
  }
  return null;
}

export default function UploadCard({
  uploadId,
  kind,
  title,
  uploading,
  progress,
  seconds,
  fileName,
  onFile,
  onInvalid,
}: UploadCardProps) {
  const config = KIND_CONFIG[kind];
  const Icon = config.icon;
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const pickFile = (file: File | undefined) => {
    if (!file) return;
    const problem = validateFile(file);
    if (problem) {
      onInvalid?.(problem);
      return;
    }
    onFile(file);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    pickFile(e.target.files?.[0]);
    // Reset the value so the same file can be picked again.
    e.target.value = '';
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    pickFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      aria-disabled={uploading}
      className={`space-y-3 rounded-2xl border-2 border-dashed p-5 transition ${
        dragActive
          ? `border-indigo-500 bg-gradient-to-br ${config.gradient} bg-indigo-500/5 shadow-glow-accent`
          : uploading
            ? 'border-indigo-500/50 bg-app-surface-2/60'
            : 'border-app-border-strong bg-app-surface-2/40 hover:border-indigo-500/60'
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span aria-hidden className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-app-hover/80 ${config.iconClasses}`}>
              <Icon className="h-4.5 w-4.5" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-app-soft">
                {title}
                {!uploading && fileName && <span className="ml-1 font-normal text-app-faint">· {fileName.filename}</span>}
              </p>
              <p className="truncate text-xs text-app-muted">
                {uploading ? (
                  <span className={`font-semibold ${config.iconClasses}`}>
                    {config.processingLabel} ({seconds}s)
                  </span>
                ) : fileName ? (
                  <span className="font-semibold text-app-success">
                    ✓ {fileName.filename} — {fileName.total_pages} pages processed
                  </span>
                ) : (
                  'No file uploaded yet'
                )}
              </p>
            </div>
          </div>
        </div>

        <div className="shrink-0">
          <input
            ref={inputRef}
            type="file"
            id={uploadId}
            accept=".pdf,.docx,.doc,.txt"
            className="sr-only"
            disabled={uploading}
            onChange={handleChange}
          />
          <label
            htmlFor={uploadId}
            className={`inline-flex cursor-pointer select-none items-center rounded-xl border border-app-border bg-app-surface px-4 py-2 text-xs font-semibold shadow-sm transition hover:border-indigo-500/50 hover:bg-app-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70 ${config.iconClasses} ${uploading ? 'pointer-events-none opacity-50' : ''}`}
          >
            {uploading ? 'Uploading…' : fileName ? 'Change File' : 'Choose File'}
          </label>
        </div>
      </div>

      <p className="flex items-center justify-center gap-1.5 text-center text-[11px] text-app-faint">
        <UploadCloud className="h-3.5 w-3.5" aria-hidden />
        Drag &amp; drop a PDF / DOCX / TXT here (max 500 MB) or click to browse
      </p>

      {uploading && (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs font-mono text-app-muted">
            <span>Processing…</span>
            <span>
              {progress}% ({seconds}s)
            </span>
          </div>
          <ProgressBar value={progress} color={config.barColor} />
        </div>
      )}
    </div>
  );
}