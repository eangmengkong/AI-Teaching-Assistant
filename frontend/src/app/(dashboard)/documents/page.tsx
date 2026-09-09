'use client';

import { BookOpen, FileText, Pencil, Sparkles, TrendingUp } from 'lucide-react';
import { useRouter } from 'next/navigation';

import Button from '../../../components/Button';
import Card from '../../../components/Card';
import PageHeader from '../../../components/PageHeader';
import Skeleton from '../../../components/Skeleton';
import Toast from '../../../components/Toast';
import UploadCard from '../../../components/UploadCard';
import { useDashboardData } from '../../../lib/useDashboardData';

export default function DocumentsPage() {
  const router = useRouter();
  const {
    toast,
    showToast,
    loading,
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

  const totalPages = (textbookDoc?.total_pages ?? 0) + (workbookDoc?.total_pages ?? 0);
  const ready = Boolean(textbookDoc && workbookDoc);

  return (
    <div className="space-y-8">
      <PageHeader
        icon={<FileText className="h-6 w-6" />}
        title="Course Documents"
        subtitle="Upload the textbook &amp; workbook — the AI parses every page and keeps page references for study PDFs."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Upload Course Materials" icon={<BookOpen className="h-4.5 w-4.5" />} tint="indigo">
            <div className="space-y-4">
              <UploadCard
                kind="textbook"
                uploadId="tb-file"
                title="Upload Textbook"
                uploading={uploadingTb}
                progress={tbProgress}
                seconds={tbSeconds}
                speedMbPerSec={tbSpeedMbS}
                fileName={textbookDoc}
                onFile={(file) => void uploadFile(file, 'textbook')}
                onInvalid={(message) => showToast('error', message)}
              />
              <UploadCard
                kind="workbook"
                uploadId="wb-file"
                title="Upload Workbook"
                uploading={uploadingWb}
                progress={wbProgress}
                seconds={wbSeconds}
                speedMbPerSec={wbSpeedMbS}
                fileName={workbookDoc}
                onFile={(file) => void uploadFile(file, 'workbook')}
                onInvalid={(message) => showToast('error', message)}
              />
            </div>
          </Card>

          {ready && (
            <div className="flex items-start gap-2.5 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-app-subtle">
              <TrendingUp className="h-5 w-5 shrink-0 text-app-success" aria-hidden />
              <span>
                Both materials are indexed ({totalPages} pages total). You're ready to
                <button
                  type="button"
                  onClick={() => void router.push('/schedule')}
                  className="font-semibold text-app-accent underline-offset-2 hover:underline"
                >
                  generate the 1-month schedule →
                </button>
              </span>
            </div>
          )}
        </div>

        <Card
          title="Readiness"
          icon={<Sparkles className="h-4.5 w-4.5" />}
          tint="emerald"
          subtitle="What the AI still needs"
        >
          <ul className="space-y-3 text-sm">
            <li className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-app-subtle">
                <BookOpen className="h-4 w-4 text-app-accent" aria-hidden />
                Textbook
              </span>
              {textbookDoc ? (
                <span className="text-xs font-semibold text-app-success">{textbookDoc.total_pages} pages ✓</span>
              ) : (
                <span className="text-xs font-semibold text-app-muted">Missing</span>
              )}
            </li>
            <li className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-app-subtle">
                <Pencil className="h-4 w-4 text-app-success" aria-hidden />
                Workbook
              </span>
              {workbookDoc ? (
                <span className="text-xs font-semibold text-app-success">{workbookDoc.total_pages} pages ✓</span>
              ) : (
                <span className="text-xs font-semibold text-app-muted">Missing</span>
              )}
            </li>
          </ul>
          <div className="mt-5 rounded-xl border border-app-border bg-app-surface-2 p-3 text-xs text-app-muted">
            PDF, DOCX, DOC &amp; TXT are supported — up to 500 MB per file. Page numbers in the schedule stay clickable.
          </div>
          <Button
            variant="secondary"
            size="full"
            className="mt-4"
            onClick={() => void router.push('/schedule')}
            disabled={!ready}
          >
            {ready ? 'Continue to Schedule →' : 'Upload both files to continue'}
          </Button>
        </Card>
      </div>

      <Toast toast={toast} />
    </div>
  );
}