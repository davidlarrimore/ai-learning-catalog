// Global variables
let allCourses = [];
let filteredCourses = [];
let currentPage = 1;
let itemsPerPage = 12;
let totalPages = 1;

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
        
        // Initialize pagination and display courses
        updatePagination();
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

// Update pagination controls and info
function updatePagination() {
    totalPages = Math.ceil(filteredCourses.length / itemsPerPage);
    
    // Ensure current page is valid
    if (currentPage > totalPages && totalPages > 0) {
        currentPage = totalPages;
    } else if (currentPage < 1) {
        currentPage = 1;
    }
    
    // Update pagination display
    renderPagination();
    updatePaginationInfo();
}

// Render pagination controls
function renderPagination() {
    const paginationContainer = document.getElementById('pagination-container');
    if (!paginationContainer) {
        // Create pagination container if it doesn't exist
        const container = document.createElement('div');
        container.id = 'pagination-container';
        container.className = 'pagination-container';
        document.getElementById('courses-grid').insertAdjacentElement('afterend', container);
    }
    
    const container = document.getElementById('pagination-container');
    container.innerHTML = '';
    
    // Don't show pagination if there's only one page or no results
    if (totalPages <= 1) {
        return;
    }
    
    // Create main pagination wrapper
    const paginationWrapper = document.createElement('div');
    paginationWrapper.className = 'pagination';
    
    // Previous button
    const prevBtn = createPaginationButton('‹', currentPage - 1, currentPage === 1);
    prevBtn.title = 'Previous page';
    paginationWrapper.appendChild(prevBtn);
    
    // Page numbers
    const pageNumbers = generatePageNumbers();
    pageNumbers.forEach(page => {
        if (page === '...') {
            const ellipsis = createPaginationButton('...', null, true);
            ellipsis.classList.add('ellipsis');
            paginationWrapper.appendChild(ellipsis);
        } else {
            const pageBtn = createPaginationButton(page, page, false, page === currentPage);
            paginationWrapper.appendChild(pageBtn);
        }
    });
    
    // Next button
    const nextBtn = createPaginationButton('›', currentPage + 1, currentPage === totalPages);
    nextBtn.title = 'Next page';
    paginationWrapper.appendChild(nextBtn);
    
    container.appendChild(paginationWrapper);
    
    // Create pagination info and controls
    const infoContainer = document.createElement('div');
    infoContainer.className = 'pagination-info';
    
    // Page size selector
    const pageSizeSelector = document.createElement('div');
    pageSizeSelector.className = 'page-size-selector';
    pageSizeSelector.innerHTML = `
        <label for="page-size">Show:</label>
        <select id="page-size">
            <option value="6" ${itemsPerPage === 6 ? 'selected' : ''}>6</option>
            <option value="12" ${itemsPerPage === 12 ? 'selected' : ''}>12</option>
            <option value="24" ${itemsPerPage === 24 ? 'selected' : ''}>24</option>
            <option value="48" ${itemsPerPage === 48 ? 'selected' : ''}>48</option>
        </select>
    `;
    
    // Jump to page
    const jumpToPage = document.createElement('div');
    jumpToPage.className = 'jump-to-page';
    jumpToPage.innerHTML = `
        <label for="jump-page">Go to page:</label>
        <input type="number" id="jump-page" min="1" max="${totalPages}" value="${currentPage}">
        <button onclick="jumpToPage()">Go</button>
    `;
    
    infoContainer.appendChild(pageSizeSelector);
    infoContainer.appendChild(jumpToPage);
    
    container.appendChild(infoContainer);
    
    // Add event listener for page size change
    document.getElementById('page-size').addEventListener('change', function() {
        itemsPerPage = parseInt(this.value);
        currentPage = 1; // Reset to first page when changing page size
        updatePagination();
        displayCourses();
    });
}

// Create pagination button
function createPaginationButton(text, page, disabled = false, active = false) {
    const button = document.createElement('button');
    button.className = 'pagination-btn';
    button.textContent = text;
    button.disabled = disabled;
    
    if (active) {
        button.classList.add('active');
    }
    
    if (!disabled && page !== null) {
        button.addEventListener('click', () => {
            if (page !== currentPage) {
                currentPage = page;
                updatePagination();
                displayCourses();
                
                // Scroll to top of courses section
                document.getElementById('courses-grid').scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'start' 
                });
            }
        });
    }
    
    return button;
}

// Generate page numbers with ellipsis
function generatePageNumbers() {
    const pages = [];
    const maxVisiblePages = 7;
    
    if (totalPages <= maxVisiblePages) {
        // Show all pages if total is small
        for (let i = 1; i <= totalPages; i++) {
            pages.push(i);
        }
    } else {
        // Always show first page
        pages.push(1);
        
        if (currentPage > 4) {
            pages.push('...');
        }
        
        // Show pages around current page
        const start = Math.max(2, currentPage - 1);
        const end = Math.min(totalPages - 1, currentPage + 1);
        
        for (let i = start; i <= end; i++) {
            if (i !== 1 && i !== totalPages) {
                pages.push(i);
            }
        }
        
        if (currentPage < totalPages - 3) {
            pages.push('...');
        }
        
        // Always show last page
        if (totalPages > 1) {
            pages.push(totalPages);
        }
    }
    
    return pages;
}

// Update pagination info text
function updatePaginationInfo() {
    const start = (currentPage - 1) * itemsPerPage + 1;
    const end = Math.min(currentPage * itemsPerPage, filteredCourses.length);
    const total = filteredCourses.length;
    
    const resultsCount = document.getElementById('results-count');
    if (total === 0) {
        resultsCount.textContent = '0 courses found';
    } else {
        resultsCount.textContent = `Showing ${start}-${end} of ${total} course${total !== 1 ? 's' : ''}`;
    }
}

// Jump to specific page
function jumpToPage() {
    const input = document.getElementById('jump-page');
    const pageNumber = parseInt(input.value);
    
    if (pageNumber >= 1 && pageNumber <= totalPages) {
        currentPage = pageNumber;
        updatePagination();
        displayCourses();
        
        // Scroll to top of courses section
        document.getElementById('courses-grid').scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    } else {
        input.value = currentPage; // Reset to current page if invalid
    }
}

// Display courses for current page
function displayCourses() {
    const grid = document.getElementById('courses-grid');
    const noResults = document.getElementById('no-results');
    
    grid.innerHTML = '';
    
    if (filteredCourses.length === 0) {
        grid.style.display = 'none';
        noResults.style.display = 'block';
        updatePaginationInfo();
        return;
    }
    
    grid.style.display = 'grid';
    noResults.style.display = 'none';
    
    // Calculate start and end indices for current page
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, filteredCourses.length);
    
    // Display courses for current page
    const coursesToShow = filteredCourses.slice(startIndex, endIndex);
    
    coursesToShow.forEach(course => {
        const card = createCourseCard(course);
        grid.appendChild(card);
    });
    
    updatePaginationInfo();
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
    
    // Reset to first page when filtering
    currentPage = 1;
    updatePagination();
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

// Keyboard navigation for pagination
function setupKeyboardNavigation() {
    document.addEventListener('keydown', function(e) {
        // Only handle pagination keys when not typing in an input
        if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT') {
            return;
        }
        
        if (e.key === 'ArrowLeft' && currentPage > 1) {
            e.preventDefault();
            currentPage--;
            updatePagination();
            displayCourses();
            scrollToCourses();
        } else if (e.key === 'ArrowRight' && currentPage < totalPages) {
            e.preventDefault();
            currentPage++;
            updatePagination();
            displayCourses();
            scrollToCourses();
        }
    });
}

// Scroll to courses section
function scrollToCourses() {
    document.getElementById('courses-grid').scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start' 
    });
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadCourses();
    setupKeyboardNavigation();
    
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