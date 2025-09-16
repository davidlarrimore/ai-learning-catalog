// Global variables
let allCourses = [];
let filteredCourses = [];

// Fetch courses data
async function loadCourses() {
    try {
        const response = await fetch('data/courses.json');
        allCourses = await response.json();
        filteredCourses = [...allCourses];
        
        // Update stats
        updateStats();
        
        // Populate filters
        populateFilters();
        
        // Display courses
        displayCourses();
        
        // Hide loading
        document.getElementById('loading').style.display = 'none';
    } catch (error) {
        console.error('Error loading courses:', error);
        document.getElementById('loading').innerHTML = '<p>Error loading courses. Please try again later.</p>';
    }
}

// Update statistics
function updateStats() {
    const providers = new Set(allCourses.map(c => c.Provider).filter(p => p));
    document.getElementById('total-courses').textContent = `${allCourses.length}+`;
    document.getElementById('total-providers').textContent = `${providers.size}+`;
}

// Populate filter dropdowns
function populateFilters() {
    const providers = new Set(allCourses.map(c => c.Provider).filter(p => p));
    const providerFilter = document.getElementById('provider-filter');
    
    [...providers].sort().forEach(provider => {
        const option = document.createElement('option');
        option.value = provider;
        option.textContent = provider;
        providerFilter.appendChild(option);
    });
}

// Display courses
function displayCourses() {
    const grid = document.getElementById('courses-grid');
    const noResults = document.getElementById('no-results');
    const resultsCount = document.getElementById('results-count');
    
    grid.innerHTML = '';
    
    if (filteredCourses.length === 0) {
        grid.style.display = 'none';
        noResults.style.display = 'block';
        resultsCount.textContent = '0 courses found';
        return;
    }
    
    grid.style.display = 'grid';
    noResults.style.display = 'none';
    resultsCount.textContent = `${filteredCourses.length} course${filteredCourses.length !== 1 ? 's' : ''} found`;
    
    filteredCourses.forEach(course => {
        const card = createCourseCard(course);
        grid.appendChild(card);
    });
}

// Create course card
function createCourseCard(course) {
    const card = document.createElement('div');
    card.className = 'course-card';
    
    const difficultyClass = getDifficultyClass(course.Difficulty);
    const skillClass = getSkillClass(course['Skill Level']);
    
    card.innerHTML = `
        <div class="course-header">
            <div class="course-provider">${course.Provider || 'Unknown Provider'}</div>
            <h3 class="course-title">
                <a href="${course.Link}" target="_blank" rel="noopener noreferrer">
                    ${course['Course Name']}
                </a>
            </h3>
        </div>
        <div class="course-body">
            <p class="course-summary">${truncateText(course.Summary, 120)}</p>
            <div class="course-tags">
                ${course['Skill Level'] ? `<span class="tag skill-level">${course['Skill Level']}</span>` : ''}
                ${course.Difficulty ? `<span class="tag difficulty">${course.Difficulty}</span>` : ''}
                ${course['Hands On'] && course['Hands On'].toLowerCase().includes('yes') ? '<span class="tag hands-on">Hands-on</span>' : ''}
            </div>
            <div class="course-meta">
                <div class="meta-item">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                    ${course.Length || 'N/A'}
                </div>
                <div class="meta-item">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                        <polyline points="10 9 9 9 8 9"/>
                    </svg>
                    ${course['Evidence of Completion'] || 'None'}
                </div>
            </div>
        </div>
    `;
    
    return card;
}

// Helper functions
function truncateText(text, maxLength) {
    if (!text || text === 'Unknown') return 'No description available';
    if (text.length <= maxLength) return text;
    return text.substr(0, maxLength) + '...';
}

function getDifficultyClass(difficulty) {
    const map = {
        'Low': 'easy',
        'Easy': 'easy',
        'Medium': 'medium',
        'Moderate': 'medium',
        'High': 'hard',
        'Intense': 'hard'
    };
    return map[difficulty] || 'medium';
}

function getSkillClass(skill) {
    const map = {
        'Novice': 'beginner',
        'Beginner': 'beginner',
        'Intermediate': 'intermediate',
        'Advanced': 'advanced',
        'Expert': 'expert'
    };
    return map[skill] || 'beginner';
}

// Filter courses
function filterCourses() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const provider = document.getElementById('provider-filter').value;
    const skillLevel = document.getElementById('skill-filter').value;
    const difficulty = document.getElementById('difficulty-filter').value;
    const track = document.getElementById('track-filter').value;
    
    filteredCourses = allCourses.filter(course => {
        // Search filter
        const searchMatch = !searchTerm || 
            course['Course Name'].toLowerCase().includes(searchTerm) ||
            (course.Provider && course.Provider.toLowerCase().includes(searchTerm)) ||
            (course.Summary && course.Summary.toLowerCase().includes(searchTerm)) ||
            (course.Track && course.Track.toLowerCase().includes(searchTerm));
        
        // Provider filter
        const providerMatch = !provider || course.Provider === provider;
        
        // Skill level filter
        const skillMatch = !skillLevel || course['Skill Level'] === skillLevel;
        
        // Difficulty filter
        const difficultyMatch = !difficulty || course.Difficulty === difficulty;
        
        // Track filter
        const trackMatch = !track || (course.Track && course.Track.includes(track));
        
        return searchMatch && providerMatch && skillMatch && difficultyMatch && trackMatch;
    });
    
    displayCourses();
}

// Clear filters
function clearFilters() {
    document.getElementById('search-input').value = '';
    document.getElementById('provider-filter').value = '';
    document.getElementById('skill-filter').value = '';
    document.getElementById('difficulty-filter').value = '';
    document.getElementById('track-filter').value = '';
    filterCourses();
}

// Download functions
function downloadCSV() {
    const headers = [
        'Provider', 'Link', 'Course Name', 'Summary', 'Track', 'Platform',
        'Hands On', 'Skill Level', 'Difficulty', 'Length', 'Evidence of Completion'
    ];
    
    let csv = headers.join(',') + '\n';
    
    filteredCourses.forEach(course => {
        const row = headers.map(header => {
            const value = course[header] || '';
            // Escape quotes and wrap in quotes if contains comma
            const escaped = value.toString().replace(/"/g, '""');
            return `"${escaped}"`;
        });
        csv += row.join(',') + '\n';
    });
    
    downloadFile(csv, 'ai-courses.csv', 'text/csv');
}

function downloadExcel() {
    // Convert to Excel format using a simple XLSX structure
    const headers = [
        'Provider', 'Link', 'Course Name', 'Summary', 'Track', 'Platform',
        'Hands On', 'Skill Level', 'Difficulty', 'Length', 'Evidence of Completion'
    ];
    
    // Create HTML table that can be opened in Excel
    let html = '<table><thead><tr>';
    headers.forEach(header => {
        html += `<th>${header}</th>`;
    });
    html += '</tr></thead><tbody>';
    
    filteredCourses.forEach(course => {
        html += '<tr>';
        headers.forEach(header => {
            const value = course[header] || '';
            html += `<td>${value.toString().replace(/</g, '&lt;').replace(/>/g, '&gt;')}</td>`;
        });
        html += '</tr>';
    });
    
    html += '</tbody></table>';
    
    // Create Excel file
    const blob = new Blob([html], { type: 'application/vnd.ms-excel' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'ai-courses.xls';
    link.click();
    URL.revokeObjectURL(url);
}

function downloadFile(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadCourses();
    
    // Search
    document.getElementById('search-input').addEventListener('input', filterCourses);
    
    // Filters
    document.getElementById('provider-filter').addEventListener('change', filterCourses);
    document.getElementById('skill-filter').addEventListener('change', filterCourses);
    document.getElementById('difficulty-filter').addEventListener('change', filterCourses);
    document.getElementById('track-filter').addEventListener('change', filterCourses);
    
    // Clear filters
    document.getElementById('clear-filters').addEventListener('click', clearFilters);
    
    // Download buttons
    document.getElementById('download-csv').addEventListener('click', downloadCSV);
    document.getElementById('download-excel').addEventListener('click', downloadExcel);
    
    // Smooth scroll for navigation
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
});