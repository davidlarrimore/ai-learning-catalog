document.addEventListener('DOMContentLoaded', () => {
  // Configuration
  const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000'
    : '/api';

  // DOM elements
  const form = document.getElementById('course-form');
  const enrichForm = document.getElementById('enrich-form');
  const tableBody = document.getElementById('courses-body');
  const submitBtn = document.getElementById('submit-btn');
  const cancelBtn = document.getElementById('cancel-btn');
  const refreshBtn = document.getElementById('refresh-btn');
  const formTitle = document.getElementById('form-title');
  const alert = document.getElementById('alert');
  const enrichAlert = document.getElementById('enrich-alert');

  // State
  let editingLink = null;

  function resetForm() {
    editingLink = null;
    if (form) form.reset();
    if (formTitle) formTitle.textContent = 'Add Course';
    if (submitBtn) submitBtn.textContent = 'Save';
    if (cancelBtn) cancelBtn.classList.add('hidden');
    setAlert('');
  }

  function setAlert(message, type = 'info') {
    if (!alert) return;
    alert.textContent = message;
    alert.className = type;
  }

  function setEnrichAlert(message, type = 'info') {
    if (!enrichAlert) return;
    enrichAlert.textContent = message;
    enrichAlert.className = type;
  }

  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
      toast.classList.add('show');
    }, 100);
    
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3000);
  }

  function fillForm(course) {
    if (!form) return;
    const inputs = form.querySelectorAll('input, textarea');
    inputs.forEach(input => {
      const name = input.name;
      if (name && course[name] !== undefined) {
        input.value = course[name];
      } else {
        input.value = input.getAttribute('value') || '';
      }
    });
  }

  function startEditing(course) {
    // Store the raw link without any encoding
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
      <td><button type="button" class="secondary">Edit</button></td>
    `;
    // Add the click handler directly to avoid encoding issues
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
        
        console.debug('Submitting course request:', {
          method,
          url,
          editingLink,
          payload
        });
        
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
        console.error('Course save error:', error);
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