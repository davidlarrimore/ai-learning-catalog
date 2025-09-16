const API_BASE = '/api';
const form = document.getElementById('course-form');
const formTitle = document.getElementById('form-title');
const submitBtn = document.getElementById('submit-btn');
const cancelBtn = document.getElementById('cancel-btn');
const refreshBtn = document.getElementById('refresh-btn');
const alertBox = document.getElementById('alert');
const tableBody = document.getElementById('courses-body');
const enrichForm = document.getElementById('enrich-form');
const enrichAlert = document.getElementById('enrich-alert');

let editingLink = null;

const defaultValues = {
  hands_on: 'Unknown',
  skill_level: 'Unknown',
  difficulty: 'Unknown',
  length: '0 Hours',
  evidence_of_completion: 'Unknown',
};

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

function resetForm() {
  form.reset();
  Object.entries(defaultValues).forEach(([key, value]) => {
    if (form.elements[key]) {
      form.elements[key].value = value;
    }
  });
  editingLink = null;
  formTitle.textContent = 'Add Course';
  submitBtn.textContent = 'Save';
  cancelBtn.classList.add('hidden');
}

function fillForm(course) {
  Object.entries(course).forEach(([key, value]) => {
    if (form.elements[key]) {
      form.elements[key].value = value ?? '';
    }
  });
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
  row.querySelector('button').addEventListener('click', () => startEditing(course));
  return row;
}

function startEditing(course) {
  editingLink = course.link;
  fillForm(course);
  formTitle.textContent = 'Update Course';
  submitBtn.textContent = 'Update';
  cancelBtn.classList.remove('hidden');
  setAlert(`Editing ${course.course_name}`, 'success');
}

async function loadCourses() {
  setAlert('Loading courses...');
  try {
    const response = await fetch(`${API_BASE}/courses`);
    if (!response.ok) {
      throw new Error('Failed to load courses');
    }
    const data = await response.json();
    tableBody.replaceChildren(...data.map(createRow));
    if (data.length === 0) {
      const emptyRow = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 6;
      cell.textContent = 'No courses found yet.';
      emptyRow.appendChild(cell);
      tableBody.appendChild(emptyRow);
    }
    setAlert('Courses loaded', 'success');
  } catch (error) {
    console.error(error);
    setAlert(error.message, 'error');
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  const method = editingLink ? 'PUT' : 'POST';
  const url = editingLink
    ? `${API_BASE}/courses/${encodeURIComponent(editingLink)}`
    : `${API_BASE}/courses`;

  try {
    setAlert(editingLink ? 'Updating course...' : 'Creating course...');
    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let message = response.statusText;
      try {
        const errorPayload = await response.json();
        if (typeof errorPayload.detail === 'string') {
          message = errorPayload.detail;
        }
      } catch (parseError) {
        // ignore parse errors and fall back to status text
      }
      throw new Error(message || 'Request failed');
    }
    await loadCourses();
    resetForm();
    setAlert('Saved successfully', 'success');
  } catch (error) {
    console.error(error);
    setAlert(error.message, 'error');
  }
});

cancelBtn.addEventListener('click', () => {
  resetForm();
  setAlert('Edit cancelled');
});

refreshBtn.addEventListener('click', loadCourses);

resetForm();
loadCourses();

if (enrichForm) {
  enrichForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(enrichForm);
    const link = (formData.get('link') || '').toString().trim();
    const provider = (formData.get('provider') || '').toString().trim();
    const courseName = (formData.get('courseName') || '').toString().trim();

    if (!link) {
      setEnrichAlert('Course URL is required', 'error');
      return;
    }

    const payload = { link };
    if (provider) payload.provider = provider;
    if (courseName) payload.courseName = courseName;

    try {
      setEnrichAlert('Enriching course...');
      const response = await fetch(`${API_BASE}/courses/enrich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let message = response.statusText;
        try {
          const errorPayload = await response.json();
          if (typeof errorPayload.detail === 'string') {
            message = errorPayload.detail;
          }
        } catch (parseError) {
          // ignore
        }
        throw new Error(message || 'Enrichment failed');
      }
      await loadCourses();
      enrichForm.reset();
      setEnrichAlert('Course added from URL', 'success');
    } catch (error) {
      console.error(error);
      setEnrichAlert(error.message, 'error');
    }
  });
}
