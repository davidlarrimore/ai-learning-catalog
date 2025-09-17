'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { StatusMessage } from '../components/StatusMessage';
import { ToastStack, type ToastDescriptor, type ToastVariant } from '../components/ToastStack';

type CourseFormValues = {
  provider: string;
  link: string;
  course_name: string;
  summary: string;
  track: string;
  platform: string;
  hands_on: string;
  skill_level: string;
  difficulty: string;
  length: string;
  evidence_of_completion: string;
};

type Course = CourseFormValues & {
  [key: string]: unknown;
};

type AlertVariant = 'info' | 'success' | 'error' | 'neutral';

interface AlertState {
  message: string;
  variant: AlertVariant;
}

interface LoadOptions {
  showToastOnError?: boolean;
  silent?: boolean;
}

interface FieldConfig {
  name: keyof CourseFormValues;
  label: string;
  type?: 'text' | 'url';
  component?: 'textarea';
  required?: boolean;
  rows?: number;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim() ?? '/api';
const API_BASE = rawApiBase.endsWith('/') ? rawApiBase.slice(0, -1) : rawApiBase;

const courseFieldConfig: FieldConfig[] = [
  { name: 'provider', label: 'Provider' },
  { name: 'link', label: 'Link', type: 'url', required: true },
  { name: 'course_name', label: 'Course Name', required: true },
  { name: 'summary', label: 'Summary', component: 'textarea', rows: 2 },
  { name: 'track', label: 'Track' },
  { name: 'platform', label: 'Platform' },
  { name: 'hands_on', label: 'Hands On' },
  { name: 'skill_level', label: 'Skill Level' },
  { name: 'difficulty', label: 'Difficulty' },
  { name: 'length', label: 'Length' },
  { name: 'evidence_of_completion', label: 'Evidence of Completion' },
];

const defaultCourseValues: CourseFormValues = {
  provider: '',
  link: '',
  course_name: '',
  summary: '',
  track: '',
  platform: '',
  hands_on: 'Unknown',
  skill_level: 'Unknown',
  difficulty: 'Unknown',
  length: '0 Hours',
  evidence_of_completion: 'Unknown',
};

const defaultAlert: AlertState = { message: '', variant: 'neutral' };

const defaultEnrichValues = {
  link: '',
  provider: '',
  courseName: '',
};

type EnrichFormValues = typeof defaultEnrichValues;

const makeFormDefaults = () => ({ ...defaultCourseValues });

const makeEnrichDefaults = () => ({ ...defaultEnrichValues });

const createToastId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
};

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === 'string') {
      return payload.detail;
    }
  } catch (error) {
    console.debug('Failed to parse error payload', error);
  }
  return response.statusText || 'Request failed';
}

export default function Home() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [formData, setFormData] = useState<CourseFormValues>(makeFormDefaults);
  const [enrichData, setEnrichData] = useState<EnrichFormValues>(makeEnrichDefaults);
  const [editingLink, setEditingLink] = useState<string | null>(null);
  const [alert, setAlert] = useState<AlertState>(defaultAlert);
  const [enrichAlert, setEnrichAlert] = useState<AlertState>(defaultAlert);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [toasts, setToasts] = useState<ToastDescriptor[]>([]);

  const pushToast = useCallback(
    (message: ToastDescriptor['message'], variant: ToastVariant = 'info') => {
      const id = createToastId();
      setToasts((prev) => [...prev, { id, message, variant }]);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((toast) => toast.id !== id));
      }, 3200);
    },
    []
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const resetForm = useCallback(() => {
    setFormData(makeFormDefaults());
    setEditingLink(null);
  }, []);

  const loadCourses = useCallback(
    async ({ showToastOnError = true, silent = false }: LoadOptions = {}) => {
      setIsLoading(true);
      if (!silent) {
        setAlert({ message: 'Loading courses…', variant: 'info' });
      }
      try {
        const response = await fetch(`${API_BASE}/courses`, {
          headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) {
          throw new Error('Failed to load courses');
        }
        const payload = (await response.json()) as Course[];
        const normalised = Array.isArray(payload)
          ? payload.map((course) => ({ ...makeFormDefaults(), ...course }))
          : [];
        setCourses(normalised);
        if (!silent) {
          setAlert({ message: 'Courses loaded', variant: 'success' });
        }
        return true;
      } catch (error) {
        console.error(error);
        const message = error instanceof Error ? error.message : 'Failed to load courses';
        setAlert({ message, variant: 'error' });
        if (showToastOnError) {
          pushToast(message, 'error');
        }
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [pushToast]
  );

  useEffect(() => {
    void loadCourses({ showToastOnError: false });
  }, [loadCourses]);

  useEffect(() => {
    const handleFocus = () => {
      void loadCourses({ showToastOnError: false, silent: true });
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [loadCourses]);

  const handleCourseChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const { name, value } = event.target;
      setFormData((prev) => ({ ...prev, [name as keyof CourseFormValues]: value }));
    },
    []
  );

  const handleEnrichChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setEnrichData((prev) => ({ ...prev, [name as keyof EnrichFormValues]: value }));
  }, []);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!formData.link || !formData.course_name) {
        setAlert({ message: 'Link and Course Name are required', variant: 'error' });
        pushToast('Link and Course Name are required', 'error');
        return;
      }
      const payload: CourseFormValues = { ...formData };
      const method = editingLink ? 'PUT' : 'POST';
      const endpoint = editingLink
        ? `${API_BASE}/courses/${encodeURIComponent(editingLink)}`
        : `${API_BASE}/courses`;

      const actionLabel = editingLink ? 'Updating course…' : 'Creating course…';
      setAlert({ message: actionLabel, variant: 'info' });
      pushToast(actionLabel, 'info');
      setIsSubmitting(true);
      try {
        const response = await fetch(endpoint, {
          method,
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const detail = await extractErrorMessage(response);
          throw new Error(detail || 'Request failed');
        }
        await loadCourses({ showToastOnError: false, silent: true });
        resetForm();
        setAlert({ message: 'Saved successfully', variant: 'success' });
        pushToast('Course saved', 'success');
      } catch (error) {
        console.error(error);
        const message = error instanceof Error ? error.message : 'Failed to save course';
        setAlert({ message, variant: 'error' });
        pushToast(message, 'error');
      } finally {
        setIsSubmitting(false);
      }
    },
    [editingLink, formData, loadCourses, pushToast, resetForm]
  );

  const handleCancelEdit = useCallback(() => {
    resetForm();
    setAlert({ message: 'Edit cancelled', variant: 'info' });
    pushToast('Edit cancelled', 'info');
  }, [pushToast, resetForm]);

  const startEditing = useCallback(
    (course: Course) => {
      setEditingLink(course.link);
      setFormData({ ...makeFormDefaults(), ...course });
      setAlert({ message: `Editing ${course.course_name}`, variant: 'success' });
      pushToast(`Editing ${course.course_name}`, 'success');
    },
    [pushToast]
  );

  const handleRefresh = useCallback(() => {
    void loadCourses();
  }, [loadCourses]);

  const handleEnrichSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!enrichData.link.trim()) {
        const message = 'Course URL is required';
        setEnrichAlert({ message, variant: 'error' });
        pushToast(message, 'error');
        return;
      }
      setIsEnriching(true);
      const payload: Record<string, string> = {
        link: enrichData.link.trim(),
      };
      if (enrichData.provider.trim()) {
        payload.provider = enrichData.provider.trim();
      }
      if (enrichData.courseName.trim()) {
        payload.courseName = enrichData.courseName.trim();
      }
      const actionLabel = 'Enriching course…';
      setEnrichAlert({ message: actionLabel, variant: 'info' });
      pushToast(actionLabel, 'info');
      try {
        const response = await fetch(`${API_BASE}/courses/enrich`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const detail = await extractErrorMessage(response);
          throw new Error(detail || 'Enrichment failed');
        }
        setEnrichAlert({ message: 'Course added from URL', variant: 'success' });
        pushToast('Course added from URL', 'success');
        setEnrichData(makeEnrichDefaults());
        await loadCourses({ showToastOnError: false, silent: true });
      } catch (error) {
        console.error('Enrichment error', error);
        const message = error instanceof Error ? error.message : 'Enrichment failed';
        setEnrichAlert({ message, variant: 'error' });
        pushToast(message, 'error');
      } finally {
        setIsEnriching(false);
      }
    },
    [enrichData, loadCourses, pushToast]
  );

  const activeFormTitle = editingLink ? 'Update Course' : 'Add Course';
  const submitLabel = editingLink ? 'Update' : 'Save';

  const tableRows = useMemo(() => {
    if (!courses.length) {
      return (
        <tr>
          <td colSpan={6} className="py-6 text-center text-sm text-slate-500">
            No courses found yet.
          </td>
        </tr>
      );
    }

    return courses.map((course) => (
      <tr key={course.link} className="border-b border-slate-200 last:border-none">
        <td className="py-3 text-sm font-medium text-slate-700">{course.provider || '—'}</td>
        <td className="py-3 text-sm">
          {course.link ? (
            <a href={course.link} target="_blank" rel="noopener noreferrer" className="font-semibold text-blue-600 hover:text-blue-500">
              {course.course_name || course.link}
            </a>
          ) : (
            <span>{course.course_name || 'Untitled course'}</span>
          )}
        </td>
        <td className="py-3 text-sm text-slate-600">{course.platform || '—'}</td>
        <td className="py-3 text-sm text-slate-600">{course.difficulty || '—'}</td>
        <td className="py-3 text-sm text-slate-600">{course.length || '—'}</td>
        <td className="py-3 text-right">
          <button
            type="button"
            onClick={() => startEditing(course)}
            className="btn-secondary text-xs"
          >
            Edit
          </button>
        </td>
      </tr>
    ));
  }, [courses, startEditing]);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-10 px-6 pb-16 pt-10">
      <header>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Training Courses</h1>
      </header>

      <main className="flex flex-col gap-12">
        <section className="card">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">Enrich From Course URL</h2>
              <p className="text-sm text-slate-500">Add a course by providing its public URL and optional metadata.</p>
            </div>
          </div>
          <form onSubmit={handleEnrichSubmit} className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <label className="field-label md:col-span-2 lg:col-span-1">
              Course URL
              <input
                type="url"
                name="link"
                required
                value={enrichData.link}
                onChange={handleEnrichChange}
                className="field-input"
                placeholder="https://example.com/course"
              />
            </label>
            <label className="field-label">
              Provider (optional)
              <input
                type="text"
                name="provider"
                value={enrichData.provider}
                onChange={handleEnrichChange}
                className="field-input"
                placeholder="e.g. Coursera"
              />
            </label>
            <label className="field-label">
              Course Name (optional)
              <input
                type="text"
                name="courseName"
                value={enrichData.courseName}
                onChange={handleEnrichChange}
                className="field-input"
                placeholder="e.g. Intro to AI"
              />
            </label>
            <div className="flex items-end">
              <button type="submit" className="btn-primary" disabled={isEnriching}>
                {isEnriching ? 'Enriching…' : 'Enrich & Add'}
              </button>
            </div>
          </form>
          <StatusMessage
            message={enrichAlert.message}
            variant={enrichAlert.variant}
            className="mt-4 text-sm"
          />
        </section>

        <section className="card">
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold text-slate-900" id="course-form-heading">
              {activeFormTitle}
            </h2>
            <p className="text-sm text-slate-500">
              Fill in course details or update an existing entry.
            </p>
          </div>
          <form onSubmit={handleSubmit} className="mt-6 space-y-6" aria-labelledby="course-form-heading">
            <div className="grid gap-4 md:grid-cols-2">
              {courseFieldConfig.map((field) => (
                <label key={field.name} className="field-label">
                  {field.label}
                  {field.component === 'textarea' ? (
                    <textarea
                      name={field.name}
                      value={formData[field.name] ?? ''}
                      onChange={handleCourseChange}
                      className="field-input min-h-[90px]"
                      rows={field.rows ?? 3}
                    />
                  ) : (
                    <input
                      type={field.type ?? 'text'}
                      name={field.name}
                      value={formData[field.name] ?? ''}
                      onChange={handleCourseChange}
                      className="field-input"
                      required={field.required}
                    />
                  )}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" className="btn-primary" disabled={isSubmitting}>
                {isSubmitting ? `${submitLabel}…` : submitLabel}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleCancelEdit}
                disabled={!editingLink || isSubmitting}
              >
                Cancel
              </button>
            </div>
          </form>
          <StatusMessage message={alert.message} variant={alert.variant} className="mt-4 text-sm" />
        </section>

        <section className="card">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-xl font-semibold text-slate-900">Existing Courses</h2>
            <button type="button" className="btn-secondary" onClick={handleRefresh} disabled={isLoading}>
              {isLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          <div className="mt-4 overflow-hidden rounded-xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-100">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Provider
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Course
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Platform
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Difficulty
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Length
                  </th>
                  <th scope="col" className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 px-4">{tableRows}</tbody>
            </table>
          </div>
        </section>
      </main>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
