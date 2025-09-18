const API_BASE = '/api';

function ready(fn) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fn, { once: true });
  } else {
    fn();
  }
}

ready(() => {
  const form = document.getElementById('course-form');
  const formTitle = document.getElementById('form-title');
  const submitBtn = document.getElementById('submit-btn');
  const cancelBtn = document.getElementById('cancel-btn');
  const refreshBtn = document.getElementById('refresh-btn');
  const alertBox = document.getElementById('alert');
  const tableBody = document.getElementById('courses-body');
  const enrichForm = document.getElementById('enrich-form');
  const enrichAlert = document.getElementById('enrich-alert');
  const toastContainer = document.getElementById('toast-container');

  let editingLink = null;

  const defaultValues = new Map(
    Object.entries({
      hands_on: 'Unknown',
      skill_level: 'Unknown',
      difficulty: 'Unknown',
      length: '0 Hours',
      evidence_of_completion: 'Unknown',
    }),
  );

  const toastTimers = new WeakMap();

  function setStatus(element, message = '', type = '') {
    if (!element) return;
    element.textContent = message;
    element.className = type ? `alert-${type}` : '';
  }

  function setAlert(message = '', type = '') {
    setStatus(alertBox, message, type);
  }

  function setEnrichAlert(message = '', type = '') {
    setStatus(enrichAlert, message, type);
  }

  function showToast(message, type = '') {
    if (!toastContainer || !message) return;
    const toast = document.createElement('div');
    toast.className = `toast${type ? ` alert-${type}` : ''}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    const timer = setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-6px)';
      setTimeout(() => toast.remove(), 200);
    }, 3200);
    toastTimers.set(toast, timer);
  }

  function clearToast(toast) {
    const timer = toastTimers.get(toast);
    if (timer) {
      clearTimeout(timer);
      toastTimers.delete(toast);
    }
  }

  toastContainer?.addEventListener('click', (event) => {
    const toast = event.target.closest('.toast');
    if (!toast) return;
    clearToast(toast);
    toast.remove();
  });

  function resetForm() {
    if (!form) return;
    form.reset();
    defaultValues.forEach((value, key) => {
      const input = form.elements.namedItem(key);
      if (input && 'value' in input) {
        input.value = value;
      }
    });
    editingLink = null;
    if (formTitle) formTitle.textContent = 'Add Course';
    if (submitBtn) submitBtn.textContent = 'Save';
    if (cancelBtn) cancelBtn.classList.add('hidden');
  }

  function fillForm(course) {
    if (!form) return;
    Object.entries(course).forEach(([key, value]) => {
      if (form.elements[key]) {
        form.elements[key].value = value ?? '';
      }
    });
  }

  function startEditing(course) {
    editingLink = course.link;
    fillForm(course);
    if (formTitle) formTitle.textContent = 'Update Course';
    if (submitBtn) submitBtn.textContent = 'Update';
    if (cancelBtn) cancelBtn.classList.remove('hidden');
    setAlert(`Editing ${course.course_name}`, 'success');
    showToast(`Editing ${course.course_name}`, 'success');
  }

  function createRow(course) {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${course.provider || ''}</td>
      <td>
        <a href="${course.link}" target="_blank" rel="noopener">${course.course_name}</a>
      </td>
      <td>${course.platform || ''}</td>
      <td>${course.difficulty || ''}</td>
      <td>${course.length || ''}</td>
      <td><button type="button" data-link="${encodeURIComponent(course.link)}" class="secondary">Edit</button></td>
    `;
    row.querySelector('button')?.addEventListener('click', () => startEditing(course));
    return row;
  }

  async function loadCourses(options = { showToastOnError: true }) {
    setAlert('Loading courses...');
    try {
      const response = await fetch(`${API_BASE}/courses`);
      if (!response.ok) {
        throw new Error('Failed to load courses');
      }
      const data = await response.json();
      if (tableBody) {
        tableBody.replaceChildren(...data.map(createRow));
        if (data.length === 0) {
          const emptyRow = document.createElement('tr');
          const cell = document.createElement('td');
          cell.colSpan = 6;
          cell.textContent = 'No courses found yet.';
          emptyRow.appendChild(cell);
          tableBody.appendChild(emptyRow);
        }
      }
      setAlert('Courses loaded', 'success');
      return true;
    } catch (error) {
      console.error(error);
      setAlert(error.message, 'error');
      if (options.showToastOnError) {
        showToast(error.message || 'Failed to load courses', 'error');
      }
      return false;
    }
  }

  if (form) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());

      const method = editingLink ? 'PUT' : 'POST';
      const url = editingLink
        ? `${API_BASE}/courses/${encodeURIComponent(editingLink)}`
        : `${API_BASE}/courses`;

      try {
        const message = editingLink ? 'Updating course…' : 'Creating course…';
        setAlert(message);
        showToast(message);
        const response = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          let msg = response.statusText;
          try {
            const errorPayload = await response.json();
            if (typeof errorPayload.detail === 'string') {
              msg = errorPayload.detail;
            }
          } catch (_) {
            // ignore parse errors
          }
          throw new Error(msg || 'Request failed');
        }
        await loadCourses();
        resetForm();
        setAlert('Saved successfully', 'success');
        showToast('Course saved', 'success');
      } catch (error) {
        console.error(error);
        setAlert(error.message, 'error');
        showToast(error.message || 'Failed to save course', 'error');
      }
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      resetForm();
      setAlert('Edit cancelled');
      showToast('Edit cancelled');
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      loadCourses();
    });
  }

  if (enrichForm) {
    enrichForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const formData = new FormData(enrichForm);
      const link = (formData.get('link') || '').toString().trim();
      const provider = (formData.get('provider') || '').toString().trim();
      const courseName = (formData.get('courseName') || '').toString().trim();

      if (!link) {
        setEnrichAlert('Course URL is required', 'error');
        showToast('Course URL is required', 'error');
        return;
      }

      const payload = { link };
      if (provider) payload.provider = provider;
      if (courseName) payload.courseName = courseName;

      try {
        setEnrichAlert('Enriching course...');
        showToast('Enriching course…');
        console.debug('Submitting enrichment request', payload);
        const response = await fetch(`${API_BASE}/courses/enrich`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          let msg = response.statusText;
          try {
            const errorPayload = await response.json();
            if (typeof errorPayload.detail === 'string') {
              msg = errorPayload.detail;
            }
          } catch (_) {
            // ignore
          }
          throw new Error(msg || 'Enrichment failed');
        }
        await loadCourses();
        enrichForm.reset();
        setEnrichAlert('Course added from URL', 'success');
        showToast('Course added from URL', 'success');
      } catch (error) {
        console.error('Enrichment error', error);
        setEnrichAlert(error.message, 'error');
        showToast(error.message || 'Enrichment failed', 'error');
      }
    });
  }

  resetForm();
  console.debug('Initialising courses view');
  loadCourses({ showToastOnError: false }).then((success) => {
    if (!success) {
      setTimeout(() => loadCourses(), 2500);
    }
  });

  window.addEventListener('focus', () => {
    loadCourses({ showToastOnError: false });
  });
});
