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
  id: string;
  version: number;
  date_created: string;
  last_updated: string;
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

const filterKeys = ['provider', 'difficulty', 'skillLevel', 'track'] as const;
type FilterKey = (typeof filterKeys)[number];

type AvailableFilters = Record<FilterKey, string[]>;
type FilterState = Record<FilterKey, string>;

type CourseListResponse = {
  items: Course[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  availableFilters: Partial<AvailableFilters>;
};

type PaginationState = {
  page: number;
  pageSize: number;
  totalPages: number;
  total: number;
};

const filterLabels: Record<FilterKey, string> = {
  provider: 'Provider',
  difficulty: 'Difficulty',
  skillLevel: 'Skill Level',
  track: 'Track',
};

const filterParamMap: Record<FilterKey, string> = {
  provider: 'provider',
  difficulty: 'difficulty',
  skillLevel: 'skill_level',
  track: 'track',
};

const makeEmptyFilterState = (): FilterState => ({
  provider: '',
  difficulty: '',
  skillLevel: '',
  track: '',
});

const makeEmptyAvailableFilters = (): AvailableFilters => ({
  provider: [],
  difficulty: [],
  skillLevel: [],
  track: [],
});

const makeDefaultPagination = (): PaginationState => ({
  page: 1,
  pageSize: 25,
  totalPages: 0,
  total: 0,
});

const pageSizeOptions = [10, 25, 50, 100];

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
  const [enrichData, setEnrichData] = useState<EnrichFormValues>(makeEnrichDefaults);
  const [editingCourseId, setEditingCourseId] = useState<string | null>(null);
  const [editingCourseVersion, setEditingCourseVersion] = useState<number | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [modalFormData, setModalFormData] = useState<CourseFormValues>(makeFormDefaults);
  const [modalAlert, setModalAlert] = useState<AlertState>(defaultAlert);
  const [enrichAlert, setEnrichAlert] = useState<AlertState>(defaultAlert);
  const [isLoading, setIsLoading] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isModalSubmitting, setIsModalSubmitting] = useState(false);
  const [toasts, setToasts] = useState<ToastDescriptor[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchDraft, setSearchDraft] = useState('');
  const [filtersState, setFiltersState] = useState<FilterState>(makeEmptyFilterState);
  const [availableFilters, setAvailableFilters] = useState<AvailableFilters>(makeEmptyAvailableFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [pagination, setPagination] = useState<PaginationState>(makeDefaultPagination);

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

  const loadCourses = useCallback(
    async ({ showToastOnError = true, silent = false }: LoadOptions = {}) => {
      setIsLoading(true);
      try {
        const params = new URLSearchParams();
        params.set('page', String(page));
        params.set('page_size', String(pageSize));
        const trimmedSearch = searchTerm.trim();
        if (trimmedSearch) {
          params.set('search', trimmedSearch);
        }
        filterKeys.forEach((key) => {
          const value = filtersState[key].trim();
          if (value) {
            params.append(filterParamMap[key], value);
          }
        });

        const queryString = params.toString();
        const response = await fetch(`${API_BASE}/courses${queryString ? `?${queryString}` : ''}`, {
          headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) {
          throw new Error('Failed to load courses');
        }
        const payload = (await response.json()) as CourseListResponse;
        const normalised = Array.isArray(payload.items)
          ? payload.items
              .map((course) => {
                const id = typeof course.id === 'string' ? course.id : '';
                const versionValue =
                  typeof course.version === 'number'
                    ? course.version
                    : Number((course as Record<string, unknown>).version ?? 1) || 1;
                const dateCreatedRaw = (course as Record<string, unknown>).date_created;
                const lastUpdatedRaw = (course as Record<string, unknown>).last_updated;
                const dateCreated = typeof dateCreatedRaw === 'string' && dateCreatedRaw ? dateCreatedRaw : new Date().toISOString();
                const lastUpdated = typeof lastUpdatedRaw === 'string' && lastUpdatedRaw ? lastUpdatedRaw : dateCreated;
                if (!id) {
                  return null;
                }
                return {
                  ...makeFormDefaults(),
                  ...course,
                  id,
                  version: versionValue,
                  date_created: dateCreated,
                  last_updated: lastUpdated,
                } as Course;
              })
              .filter((item): item is Course => item !== null)
          : [];
        setCourses(normalised);
        const nextAvailableFilters = makeEmptyAvailableFilters();
        filterKeys.forEach((key) => {
          const values = payload.availableFilters?.[key];
          nextAvailableFilters[key] = Array.isArray(values) ? values : [];
        });
        setAvailableFilters(nextAvailableFilters);
        setPagination({
          page: payload.page,
          pageSize: payload.pageSize,
          totalPages: payload.totalPages,
          total: payload.total,
        });
        if (payload.page !== page) {
          setPage(payload.page);
        }
        if (payload.pageSize !== pageSize) {
          setPageSize(payload.pageSize);
        }
        return true;
      } catch (error) {
        console.error(error);
        const message = error instanceof Error ? error.message : 'Failed to load courses';
        if (showToastOnError) {
          pushToast(message, 'error');
        }
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [filtersState, page, pageSize, pushToast, searchTerm]
  );

  useEffect(() => {
    void loadCourses({ showToastOnError: false, silent: true });
  }, [loadCourses]);

  useEffect(() => {
    const handleFocus = () => {
      void loadCourses({ showToastOnError: false, silent: true });
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [loadCourses]);

  const handleEnrichChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setEnrichData((prev) => ({ ...prev, [name as keyof EnrichFormValues]: value }));
  }, []);

  const startEditing = useCallback(
    (course: Course) => {
      setModalMode('edit');
      setEditingCourseId(course.id);
      const nextVersion = typeof course.version === 'number' ? course.version : Number(course.version || 1) || 1;
      setEditingCourseVersion(nextVersion);
      setModalFormData({ ...makeFormDefaults(), ...course });
      setModalAlert({ message: '', variant: 'neutral' });
      setIsModalOpen(true);
      pushToast(`Editing ${course.course_name}`, 'info');
    },
    [pushToast]
  );

  const handleRefresh = useCallback(() => {
    void loadCourses();
  }, [loadCourses]);

  const handleSearchInput = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchDraft(event.target.value);
  }, []);

  const handleSearchSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const nextValue = searchDraft.trim();
      setPage(1);
      setSearchTerm(nextValue);
    },
    [searchDraft]
  );

  const handleClearSearch = useCallback(() => {
    if (!searchDraft && !searchTerm) {
      return;
    }
    setSearchDraft('');
    setSearchTerm('');
    setPage(1);
  }, [searchDraft, searchTerm]);

  const handleFilterChange = useCallback((key: FilterKey, value: string) => {
    let didChange = false;
    setFiltersState((prev) => {
      if (prev[key] === value) {
        return prev;
      }
      didChange = true;
      return { ...prev, [key]: value };
    });
    if (didChange) {
      setPage(1);
    }
  }, []);

  const handleResetFilters = useCallback(() => {
    setFiltersState(makeEmptyFilterState());
    setPage(1);
  }, []);

  const handlePreviousPage = useCallback(() => {
    if (pagination.page <= 1) {
      return;
    }
    setPage(pagination.page - 1);
  }, [pagination.page]);

  const handleNextPage = useCallback(() => {
    if (!pagination.totalPages || pagination.page >= pagination.totalPages) {
      return;
    }
    setPage(pagination.page + 1);
  }, [pagination.page, pagination.totalPages]);

  const handlePageSizeChange = useCallback(
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const nextSize = Number(event.target.value) || pageSizeOptions[0];
      if (nextSize === pageSize) {
        return;
      }
      setPageSize(nextSize);
      setPage(1);
    },
    [pageSize]
  );

  const handleModalChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const { name, value } = event.target;
      setModalFormData((prev) => ({ ...prev, [name as keyof CourseFormValues]: value }));
    },
    []
  );

  const handleCloseModal = useCallback(() => {
    setIsModalOpen(false);
    setIsModalSubmitting(false);
    setEditingCourseId(null);
    setEditingCourseVersion(null);
    setModalFormData(makeFormDefaults());
    setModalAlert({ message: '', variant: 'neutral' });
    setModalMode('create');
  }, []);

  const handleModalSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const payload: CourseFormValues = { ...modalFormData };

      if (modalMode === 'create') {
        if (!payload.link || !payload.course_name) {
          const message = 'Link and Course Name are required';
          setModalAlert({ message, variant: 'error' });
          pushToast(message, 'error');
          return;
        }
      } else {
        if (!editingCourseId || typeof editingCourseVersion !== 'number') {
          const message = 'Missing course metadata for update';
          setModalAlert({ message, variant: 'error' });
          pushToast(message, 'error');
          return;
        }
      }

      const isCreate = modalMode === 'create';
      const endpoint = isCreate
        ? `${API_BASE}/courses`
        : `${API_BASE}/courses/${editingCourseId}`;
      const method = isCreate ? 'POST' : 'PUT';
      const actionLabel = isCreate ? 'Creating course…' : 'Updating course…';
      setModalAlert({ message: actionLabel, variant: 'info' });
      pushToast(actionLabel, 'info');
      setIsModalSubmitting(true);
      try {
        const bodyPayload = isCreate ? payload : { ...payload, version: editingCourseVersion };
        const response = await fetch(endpoint, {
          method,
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(bodyPayload),
        });
        if (!response.ok) {
          const detail = await extractErrorMessage(response);
          if (response.status === 409) {
            throw new Error(detail || 'Course was updated elsewhere. Please refresh and try again.');
          }
          throw new Error(detail || 'Request failed');
        }
        await loadCourses({ showToastOnError: false, silent: true });
        pushToast(isCreate ? 'Course added' : 'Course updated', 'success');
        handleCloseModal();
      } catch (error) {
        console.error(error);
        const message = error instanceof Error ? error.message : isCreate ? 'Failed to create course' : 'Failed to update course';
        setModalAlert({ message, variant: 'error' });
        pushToast(message, 'error');
      } finally {
        setIsModalSubmitting(false);
      }
    },
    [editingCourseId, editingCourseVersion, handleCloseModal, loadCourses, modalFormData, modalMode, pushToast]
  );

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

  const hasActiveFilters = useMemo(() => {
    return filterKeys.some((key) => filtersState[key].trim());
  }, [filtersState]);

  const tableRows = useMemo(() => {
    if (isLoading) {
      return (
        <tr>
          <td colSpan={6} className="py-6 text-center text-sm text-slate-500">
            <span className="inline-flex items-center justify-center gap-2" role="status">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" aria-hidden="true" />
              Loading courses…
            </span>
          </td>
        </tr>
      );
    }

    if (!courses.length) {
      return (
        <tr>
          <td colSpan={6} className="py-6 text-center text-sm text-slate-500">
            {searchTerm || hasActiveFilters ? 'No courses match your search or filters.' : 'No courses found yet.'}
          </td>
        </tr>
      );
    }

    return courses.map((course) => (
      <tr key={course.id} className="border-b border-slate-200 last:border-none">
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
  }, [courses, hasActiveFilters, isLoading, searchTerm, startEditing]);

  const hasResults = pagination.total > 0;
  const startIndex = hasResults ? (pagination.page - 1) * pagination.pageSize + 1 : 0;
  const endIndex = hasResults ? Math.min(pagination.total, startIndex + courses.length - 1) : 0;
  const totalPagesDisplay = hasResults ? Math.max(pagination.totalPages, 1) : 0;
  const currentPageDisplay = hasResults ? pagination.page : 0;
  const disablePrevious = !hasResults || pagination.page <= 1 || isLoading;
  const disableNext =
    !hasResults || !pagination.totalPages || pagination.page >= pagination.totalPages || isLoading;

  const modalTitle = modalMode === 'create' ? 'Add Course' : 'Update Course';
  const modalDescription =
    modalMode === 'create'
      ? 'Create a course manually by completing the fields below.'
      : 'Modify the selected course and save your changes.';

  return (
    <div className="flex min-h-screen flex-col text-slate-100">
      <nav className="border-b border-slate-800 bg-slate-900/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xl font-semibold tracking-tight sm:text-2xl">AI Learning Courses Admin Tool</span>
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-300 sm:justify-end">
            <a href="#add-course" className="transition hover:text-white">
              Add Course
            </a>
            <a href="#courses" className="transition hover:text-white">
              Courses
            </a>
          </div>
        </div>
      </nav>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 pb-16 pt-10">
        <main className="flex flex-1 flex-col gap-12">
          <section id="add-course" className="card">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">Add New Course</h2>
                <p className="text-sm text-slate-500">Provide a public course URL and optional details to enrich the record.</p>
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

          <section id="courses" className="card">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <h2 className="text-xl font-semibold text-slate-900">Existing Courses</h2>
              <button type="button" className="btn-secondary" onClick={handleRefresh} disabled={isLoading}>
                {isLoading ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
            <form
              onSubmit={handleSearchSubmit}
              className="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:gap-4"
            >
              <input
                type="search"
                name="course-search"
                value={searchDraft}
                onChange={handleSearchInput}
                className="field-input w-full md:flex-1"
                placeholder="Search by course name, provider, or platform"
                aria-label="Search courses"
              />
              <div className="flex items-center gap-2">
                <button type="submit" className="btn-secondary" disabled={isLoading}>
                  Search
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleClearSearch}
                  disabled={!searchDraft && !searchTerm}
                >
                  Clear
                </button>
              </div>
            </form>
            <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {filterKeys.map((key) => (
                <label key={key} className="field-label">
                  {filterLabels[key]}
                  <select
                    className="field-input"
                    value={filtersState[key]}
                    onChange={(event) => handleFilterChange(key, event.target.value)}
                  >
                    <option value="">All {filterLabels[key]}</option>
                    {availableFilters[key].map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="btn-secondary"
                onClick={handleResetFilters}
                disabled={!hasActiveFilters}
              >
                Reset Filters
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
            <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="text-sm text-slate-600">
                {hasResults
                ? `Showing ${startIndex}–${endIndex} of ${pagination.total} courses`
                : 'No courses to display'}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="btn-secondary"
                onClick={handlePreviousPage}
                disabled={disablePrevious}
              >
                Previous
              </button>
              <span className="text-sm text-slate-600">
                {hasResults ? `Page ${currentPageDisplay} of ${totalPagesDisplay}` : 'Page 0 of 0'}
              </span>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleNextPage}
                disabled={disableNext}
              >
                Next
              </button>
              <label className="field-label w-32">
                Per page
                <select
                  className="field-input"
                  value={pageSize}
                  onChange={handlePageSizeChange}
                  disabled={isLoading}
                >
                  {pageSizeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </section>
      </main>
    </div>

      {isModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="course-modal-title"
        >
          <div className="w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-900" id="course-modal-title">
                  {modalTitle}
                </h2>
                <p className="mt-1 text-sm text-slate-500">{modalDescription}</p>
              </div>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleCloseModal}
                disabled={isModalSubmitting}
              >
                Close
              </button>
            </div>
            <form onSubmit={handleModalSubmit} className="mt-6 space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                {courseFieldConfig.map((field) => (
                  <label key={field.name} className="field-label">
                    {field.label}
                    {field.component === 'textarea' ? (
                      <textarea
                        name={field.name}
                        value={modalFormData[field.name] ?? ''}
                        onChange={handleModalChange}
                        className="field-input min-h-[90px]"
                        rows={field.rows ?? 3}
                      />
                    ) : (
                      <input
                        type={field.type ?? 'text'}
                        name={field.name}
                        value={modalFormData[field.name] ?? ''}
                        onChange={handleModalChange}
                        className="field-input"
                        required={field.required}
                      />
                    )}
                  </label>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button type="submit" className="btn-primary" disabled={isModalSubmitting}>
                  {isModalSubmitting ? 'Saving…' : modalMode === 'create' ? 'Add Course' : 'Save changes'}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleCloseModal}
                  disabled={isModalSubmitting}
                >
                  Cancel
                </button>
              </div>
            </form>
            <StatusMessage message={modalAlert.message} variant={modalAlert.variant} className="mt-4 text-sm" />
          </div>
        </div>
      )}

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
