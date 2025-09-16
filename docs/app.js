// AI Training Catalog JavaScript
// Full JavaScript content should be pasted here

let allCourses = [];
let filteredCourses = [];

async function loadCourses() {
    try {
        const response = await fetch('data/courses.json');
        allCourses = await response.json();
        filteredCourses = [...allCourses];
        
        updateStats();
        populateFilters();
        displayCourses();
        
        document.getElementById('loading').style.display = 'none';
    } catch (error) {
        console.error('Error loading courses:', error);
        document.getElementById('loading').innerHTML = '<p>Error loading courses. Please try again later.</p>';
    }
}

// Add the rest of the JavaScript here

document.addEventListener('DOMContentLoaded', loadCourses);
