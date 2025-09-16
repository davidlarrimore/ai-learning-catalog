// Global variables
let allCourses = [];
let filteredCourses = [];

// Fetch courses data
async function loadCourses() {
    try {
        const response = await fetch('data/courses.json');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
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
    const skillLevels = new Set(allCourses.map(c => c['Skill Level']).filter(s => s));
    const difficulties = new Set(allCourses.map(c => c.Difficulty).filter(d => d));
    const tracks = new Set();
    
    allCourses.forEach(course => {
        if (course.Track) {
            course.Track.split(',').forEach(track => {
                tracks.add(track.trim());
            });
        }
    });
    
    const providerFilter = document.getElementById('provider-filter');
    const skillFilter = document.getElementById('skill-filter');
    const difficultyFilter = document.getElementById('difficulty-filter');
    const trackFilter = document.getElementById('track-filter');
    
    // Clear existing options (keep the default "All" option)
    [providerFilter, skillFilter, difficultyFilter, trackFilter].forEach(filter => {
        if (filter) {
            while (filter.children.length > 1) {
                filter.removeChild(filter.lastChild);
            }
        }
    });
    
    // Add provider options
    [...providers].sort().forEach(provider => {
        const option = document.createElement('option');
        option.value = provider;
        option.textContent = provider;
        providerFilter?.appendChild(option);
    });
    
    // Add skill level options
    [...skillLevels].sort().forEach(skill => {
        const option = document.createElement('option');
        option.value = skill;
        option.textContent = skill;
        skillFilter?.appendChild(option);
    });
    
    // Add difficulty options
    [...difficulties].sort().forEach(difficulty => {
        const option = document.createElement('option');
        option.value = difficulty;
        option.textContent = difficulty;
        difficultyFilter?.appendChild(option);
    });
    
    // Add track options
    [...tracks].sort().forEach(track => {
        const option = document.createElement('option');
        option.value = track;
        option.textContent = track;
        trackFilter?.appendChild(option);
    });
}

// Display courses
function displayCourses() {
    const grid = document.getElementById('courses-grid');
    const noResults = document.getElementById('no-results');
    const resultsCount = document.getElementById('results-count');
    
    if (!grid) return;
    
    grid.innerHTML = '';
    
    if (filteredCourses.length === 0) {
        grid.style.display = 'none';
        if (noResults) noResults.style.display = 'block';
        if (resultsCount) resultsCount.textContent = '0 courses found';
        return;
    }
    
    grid.style.display = 'grid';
    if (noResults) noResults.style.display = 'none';
    if (resultsCount) {
        resultsCount.textContent = `${filteredCourses.length} course${filteredCourses.length !== 1 ? 's' : ''} found`;
    }
    
    filteredCourses.forEach(course => {
        const card = createCourseCard(course);
        grid.appendChild(card);
    });
}

// Create course card
function createCourseCard(course) {
    const card = document.createElement('div');
    card.className = 'course-card';
    
    // Determine skill level class
    const skillLevel = course['Skill Level'] || 'Unknown';
    const skillClass = skillLevel.toLowerCase().replace(/\s+/g, '-');
    
    // Determine hands-on badge
    const handsOn = course['Hands On'] === 'Yes' ? 
        '<span class="badge hands-on">Hands-on</span>' : '';
    
    // Clean up track display
    const track = course.Track ? 
        course.Track.split(',').slice(0, 3).map(t => t.trim()).join(', ') : 
        'General';
    
    card.innerHTML = `
        <div class="course-header">
            <div class="course-provider">${course.Provider || 'Unknown Provider'}</div>
            <div class="course-badges">
                <span class="badge skill-${skillClass}">${skillLevel}</span>
                ${handsOn}
            </div>
        </div>
        
        <h3 class="course-title">${course['Course Name'] || 'Untitled Course'}</h3>
        
        <p class="course-summary">${course.Summary || 'No description available.'}</p>
        
        <div class="course-meta">
            <div class="meta-item">
                <span class="meta-label">Track:</span>
                <span class="meta-value">${track}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Platform:</span>
                <span class="meta-value">${course.Platform || 'Not specified'}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Duration:</span>
                <span class="meta-value">${course.Length || 'Not specified'}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Difficulty:</span>
                <span class="meta-value">${course.Difficulty || 'Not specified'}</span>
            </div>
        </div>
        
        <div class="course-footer">
            <a href="${course.Link}" target="_blank" rel="noopener noreferrer" class="btn-primary">
                Start Learning
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M7 17L17 7M17 7H7M17 7V17"/>
                </svg>
            </a>
        </div>
    `;
    
    return card;
}

// Filter courses
function filterCourses() {
    const searchTerm = document.getElementById('search-input')?.value.toLowerCase() || '';
    const provider = document.getElementById('provider-filter')?.value || '';
    const skillLevel = document.getElementById('skill-filter')?.value || '';
    const difficulty = document.getElementById('difficulty-filter')?.value || '';
    const track = document.getElementById('track-filter')?.value || '';
    
    filteredCourses = allCourses.filter(course => {
        // Search filter
        const searchMatch = !searchTerm || 
            (course['Course Name'] && course['Course Name'].toLowerCase().includes(searchTerm)) ||
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
    const elements = [
        'search-input',
        'provider-filter', 
        'skill-filter', 
        'difficulty-filter', 
        'track-filter'
    ];
    
    elements.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.value = '';
        }
    });
    
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
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', filterCourses);
    }
    
    // Filters
    const filters = [
        'provider-filter',
        'skill-filter', 
        'difficulty-filter',
        'track-filter'
    ];
    
    filters.forEach(filterId => {
        const filter = document.getElementById(filterId);
        if (filter) {
            filter.addEventListener('change', filterCourses);
        }
    });
    
    // Clear filters
    const clearFiltersBtn = document.getElementById('clear-filters');
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', clearFilters);
    }
    
    // Download buttons
    const downloadCSVBtn = document.getElementById('download-csv');
    if (downloadCSVBtn) {
        downloadCSVBtn.addEventListener('click', downloadCSV);
    }
    
    const downloadExcelBtn = document.getElementById('download-excel');
    if (downloadExcelBtn) {
        downloadExcelBtn.addEventListener('click', downloadExcel);
    }
    
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