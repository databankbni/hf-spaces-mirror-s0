/**
 * Estimates Data Extractor - Frontend Application
 * Handles UI interactions, file uploads, and processing status polling
 */

// ─── State ──────────────────────────────────────────────────────────────────
let selectedFile = null;
let selectedExistingFile = null;
let currentJobId = null;
let pollInterval = null;
let totalReportsProcessed = 0;
let totalCompanies = 0;

// ─── DOM Elements ───────────────────────────────────────────────────────────
const el = {
    // Nav
    sidebar: document.getElementById('sidebar'),
    menuToggle: document.getElementById('menuToggle'),
    navItems: document.querySelectorAll('.nav-item'),
    pages: document.querySelectorAll('.page'),
    breadcrumb: document.getElementById('breadcrumbPage'),
    
    // Extract page
    reportType: document.getElementById('reportType'),
    existingFilesGroup: document.getElementById('existingFilesGroup'),
    existingFilesList: document.getElementById('existingFilesList'),
    dropZone: document.getElementById('dropZone'),
    fileInput: document.getElementById('fileInput'),
    selectedFile: document.getElementById('selectedFile'),
    selectedFileName: document.getElementById('selectedFileName'),
    selectedFileSize: document.getElementById('selectedFileSize'),
    removeFile: document.getElementById('removeFile'),
    processBtn: document.getElementById('processBtn'),
    
    // Processing
    processingCard: document.getElementById('processingCard'),
    processingTitle: document.getElementById('processingTitle'),
    procFileName: document.getElementById('procFileName'),
    procReportType: document.getElementById('procReportType'),
    progressPercent: document.getElementById('progressPercent'),
    progressStatus: document.getElementById('progressStatus'),
    progressFill: document.getElementById('progressFill'),
    elapsedTime: document.getElementById('elapsedTime'),
    pageProgress: document.getElementById('pageProgress'),
    companiesFound: document.getElementById('companiesFound'),
    estRemaining: document.getElementById('estRemaining'),
    statusMessage: document.getElementById('statusMessage'),
    downloadBtn: document.getElementById('downloadBtn'),
    
    // Stats
    statReportsProcessed: document.getElementById('statReportsProcessed'),
    
    // Tabs
    tabButtons: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    reportUrl: document.getElementById('reportUrl'),
    
    // Other pages
    reportsList: document.getElementById('reportsList'),
    activityList: document.getElementById('activityList'),
    
    // Header
    liveClock: document.getElementById('liveClock'),
    toastContainer: document.getElementById('toastContainer')
};

// ─── Initialize ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initDropZone();
    initTabs();
    initClock();
    loadReportTypes();
    loadJobs();
    loadStats();
});

// ─── Navigation ─────────────────────────────────────────────────────────────
function initNavigation() {
    el.navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            
            // Update active nav
            el.navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            
            // Show page
            el.pages.forEach(p => p.classList.remove('active'));
            const pageEl = document.getElementById(`page-${page}`);
            if (pageEl) {
                // Force reflow for animation
                void pageEl.offsetWidth;
                pageEl.classList.add('active');
            }
            
            // Update breadcrumb
            el.breadcrumb.textContent = item.querySelector('span').textContent;
            
            // Close mobile sidebar
            el.sidebar.classList.remove('open');
            
            // Refresh data for specific pages
            if (page === 'reports') loadJobs();
            if (page === 'activity') loadJobs();
        });
    });
    
    el.menuToggle.addEventListener('click', () => {
        el.sidebar.classList.toggle('open');
    });
}

function initTabs() {
    el.tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            
            // Update active tab button
            el.tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Show active tab content
            el.tabContents.forEach(c => c.classList.remove('active'));
            document.getElementById(`tab-${tabId}`).classList.add('active');
            
            // Reset selections when switching tabs
            if (tabId === 'url') {
                selectedFile = null;
                el.selectedFile.style.display = 'none';
            } else {
                el.reportUrl.value = '';
            }
            updateProcessButton();
        });
    });
    
    el.reportUrl.addEventListener('input', updateProcessButton);
}

// ─── Clock ──────────────────────────────────────────────────────────────────
function initClock() {
    function updateClock() {
        const now = new Date();
        const options = { 
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: true
        };
        el.liveClock.textContent = now.toLocaleTimeString('en-US', options) + 
            ' · ' + now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    updateClock();
    setInterval(updateClock, 1000);
}

// ─── Report Types ───────────────────────────────────────────────────────────
async function loadReportTypes() {
    try {
        const res = await fetch('/api/report-types');
        const types = await res.json();
        
        el.reportType.innerHTML = '<option value="" disabled selected>Select report type...</option>';
        
        // Group processors by their group attribute
        const grouped = {};
        const nonGrouped = [];
        
        types.forEach(type => {
            if (type.group) {
                if (!grouped[type.group]) grouped[type.group] = [];
                grouped[type.group].push(type);
            } else {
                nonGrouped.push(type);
            }
        });
        
        // Add non-grouped options first
        nonGrouped.forEach(type => {
            const opt = document.createElement('option');
            opt.value = type.name;
            opt.textContent = type.name;
            if (type.files) opt.dataset.files = JSON.stringify(type.files);
            el.reportType.appendChild(opt);
        });
        
        // Add grouped options with optgroup
        for (const [groupName, groupTypes] of Object.entries(grouped)) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = groupName;
            groupTypes.forEach(type => {
                const opt = document.createElement('option');
                opt.value = type.name;
                // Use the full name for the display text
                opt.textContent = type.name;
                if (type.files) opt.dataset.files = JSON.stringify(type.files);
                optgroup.appendChild(opt);
            });
            el.reportType.appendChild(optgroup);
        }
        
        // Auto-select if only one type
        if (types.length === 1) {
            el.reportType.selectedIndex = 1;
            showExistingFiles(types[0]);
        }
        
        el.reportType.addEventListener('change', () => {
            const selected = types.find(t => t.name === el.reportType.value);
            if (selected) showExistingFiles(selected);
            updateProcessButton();
        });
        
    } catch (err) {
        console.error('Failed to load report types:', err);
        el.reportType.innerHTML = '<option value="" disabled selected>Error loading types</option>';
    }
}

function showExistingFiles(typeInfo) {
    const files = typeInfo.files.filter(f => 
        f.toLowerCase().endsWith('.pdf') || f.toLowerCase().endsWith('.xlsx') || f.toLowerCase().endsWith('.xls')
    );
    
    if (files.length === 0) {
        el.existingFilesGroup.style.display = 'none';
        return;
    }
    
    el.existingFilesGroup.style.display = 'block';
    el.existingFilesList.innerHTML = '';
    
    files.forEach(filename => {
        const ext = filename.split('.').pop().toUpperCase();
        const item = document.createElement('div');
        item.className = 'existing-file-item';
        item.innerHTML = `
            <div class="existing-file-icon">${ext}</div>
            <div class="existing-file-name">${filename}</div>
        `;
        item.addEventListener('click', () => {
            // Deselect all
            el.existingFilesList.querySelectorAll('.existing-file-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
            
            selectedExistingFile = { report_type: typeInfo.name, filename: filename };
            selectedFile = null;
            el.selectedFile.style.display = 'none';
            updateProcessButton();
        });
        el.existingFilesList.appendChild(item);
    });
}

// ─── Drag & Drop ────────────────────────────────────────────────────────────
function initDropZone() {
    const dz = el.dropZone;
    
    ['dragenter', 'dragover'].forEach(evt => {
        dz.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dz.classList.add('drag-over');
        });
    });
    
    ['dragleave', 'drop'].forEach(evt => {
        dz.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dz.classList.remove('drag-over');
        });
    });
    
    dz.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFile(files[0]);
    });
    
    dz.addEventListener('click', () => el.fileInput.click());
    
    el.fileInput.addEventListener('change', () => {
        if (el.fileInput.files.length > 0) {
            handleFile(el.fileInput.files[0]);
        }
    });
    
    el.removeFile.addEventListener('click', () => {
        selectedFile = null;
        el.selectedFile.style.display = 'none';
        el.fileInput.value = '';
        updateProcessButton();
    });
    
    el.processBtn.addEventListener('click', startProcessing);
}

function handleFile(file) {
    const validExtensions = ['.pdf', '.xlsx', '.xls'];
    const fileName = file.name.toLowerCase();
    const isValid = validExtensions.some(ext => fileName.endsWith(ext));

    if (!isValid) {
        showToast('Only PDF and Excel files are supported', 'error');
        return;
    }
    
    selectedFile = file;
    selectedExistingFile = null;
    
    // Deselect existing files
    el.existingFilesList.querySelectorAll('.existing-file-item').forEach(i => i.classList.remove('selected'));
    
    // Show file info
    el.selectedFileName.textContent = file.name;
    el.selectedFileSize.textContent = formatFileSize(file.size);
    el.selectedFile.style.display = 'flex';
    
    updateProcessButton();
}

function updateProcessButton() {
    const hasReportType = el.reportType.value !== '';
    const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
    
    let hasFileSource = false;
    if (activeTab === 'upload') {
        hasFileSource = selectedFile !== null || selectedExistingFile !== null;
    } else {
        hasFileSource = el.reportUrl.value.trim() !== '';
    }
    
    el.processBtn.disabled = !(hasReportType && hasFileSource);
}

// ─── Processing ─────────────────────────────────────────────────────────────
async function startProcessing() {
    const reportType = el.reportType.value;
    
    if (!reportType) {
        showToast('Please select a report type', 'error');
        return;
    }
    
    el.processBtn.disabled = true;
    el.processingCard.style.display = 'block';
    el.downloadBtn.style.display = 'none';
    
    // Reset processing UI
    el.progressFill.style.width = '0%';
    el.progressPercent.textContent = '0%';
    el.progressStatus.textContent = 'Starting...';
    el.processingTitle.textContent = 'Processing';
    
    try {
        let res;
        const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
        
        if (selectedExistingFile) {
            // Process existing file
            res = await fetch('/api/use-existing', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(selectedExistingFile)
            });
            el.procFileName.textContent = selectedExistingFile.filename;
        } else if (activeTab === 'upload' && selectedFile) {
            // Upload and process
            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('report_type', reportType);
            
            res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            el.procFileName.textContent = selectedFile.name;
        } else if (activeTab === 'url') {
            const url = el.reportUrl.value.trim();
            res = await fetch('/api/download-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url, report_type: reportType })
            });
            el.procFileName.textContent = url.split('/').pop() || 'Remote File';
        }
        
        const data = await res.json();
        
        if (data.error) {
            showToast(data.error, 'error');
            el.processBtn.disabled = false;
            return;
        }
        
        el.procReportType.textContent = reportType;
        currentJobId = data.job_id;
        
        showToast('Processing started!', 'info');
        
        // Start polling
        startPolling(data.job_id);
        
    } catch (err) {
        showToast('Failed to start processing: ' + err.message, 'error');
        el.processBtn.disabled = false;
    }
}

function startPolling(jobId) {
    if (pollInterval) clearInterval(pollInterval);
    
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/status/${jobId}`);
            const job = await res.json();
            
            updateProcessingUI(job);
            updateLocalHistory(job);
            
            if (job.status === 'completed' || job.status === 'error') {
                clearInterval(pollInterval);
                pollInterval = null;
                
                if (job.status === 'completed') {
                    totalReportsProcessed++;
                    el.statReportsProcessed.textContent = totalReportsProcessed;
                    
                    saveStats();
                    showToast(`Completed! Extracted ${job.companies_found} companies.`, 'success');
                    loadJobs();
                } else {
                    showToast('Processing failed: ' + job.error, 'error');
                }
                
                el.processBtn.disabled = false;
            }
        } catch (err) {
            console.error('Polling error:', err);
        }
    }, 1500);
}

// ─── Local Storage Management ────────────────────────────────────────────────
function updateLocalHistory(job) {
    let history = JSON.parse(localStorage.getItem('extractor_history_full') || '[]');
    
    // Remove jobs older than 24 hours
    const now = new Date().getTime();
    const twentyFourHours = 24 * 60 * 60 * 1000;
    history = history.filter(j => (now - (j.timestamp || now)) < twentyFourHours);
    
    // Set timestamp if not present
    const jobWithTime = Object.assign({}, job, { timestamp: now });
    
    // Update existing or add new
    const existingIdx = history.findIndex(j => j.job_id === job.job_id);
    if (existingIdx >= 0) {
        history[existingIdx] = Object.assign(history[existingIdx], job);
    } else {
        history.push(jobWithTime);
    }
    
    localStorage.setItem('extractor_history_full', JSON.stringify(history));
}

function loadStats() {
    totalReportsProcessed = parseInt(localStorage.getItem('stat_reports') || '0');
    el.statReportsProcessed.textContent = totalReportsProcessed;
}

function saveStats() {
    localStorage.setItem('stat_reports', totalReportsProcessed);
    localStorage.setItem('stat_companies', totalCompanies);
}

function updateProcessingUI(job) {
    el.progressPercent.textContent = job.progress + '%';
    el.progressFill.style.width = job.progress + '%';
    el.progressStatus.textContent = job.message;
    el.pageProgress.textContent = `${job.current_page} / ${job.total_pages}`;
    el.companiesFound.textContent = job.companies_found;
    el.statusMessage.querySelector('span').textContent = job.message;
    
    // Elapsed time
    const elapsed = job.elapsed_time;
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    el.elapsedTime.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
    
    // Estimated remaining
    if (job.progress > 5 && job.progress < 100) {
        const estimatedTotal = elapsed / (job.progress / 100);
        const remaining = Math.max(0, Math.ceil(estimatedTotal - elapsed));
        const remMins = Math.floor(remaining / 60);
        const remSecs = remaining % 60;
        el.estRemaining.textContent = `~${remMins}:${remSecs.toString().padStart(2, '0')}`;
    } else if (job.progress >= 100) {
        el.estRemaining.textContent = 'Done';
    }
    
    // Update title
    if (job.status === 'completed') {
        el.processingTitle.textContent = '✅ Completed';
        el.statusMessage.querySelector('.status-message-dot').style.background = 'var(--accent-green)';
        
        // Show download button
        el.downloadBtn.href = `/api/download/${job.output_file}`;
        el.downloadBtn.setAttribute('download', job.output_file);
        el.downloadBtn.style.display = 'flex';
        
        // Stop spinning
        document.querySelector('.spinning')?.classList.remove('spinning');
    } else if (job.status === 'error') {
        el.processingTitle.textContent = '❌ Error';
        el.statusMessage.querySelector('.status-message-dot').style.background = 'var(--accent-red)';
    }
}

// ─── Jobs / Reports ─────────────────────────────────────────────────────────
async function loadJobs() {
    try {
        const res = await fetch('/api/jobs');
        const jobs = await res.json();
        
        // Reports list
        if (jobs.filter(j => j.status === 'completed').length > 0) {
            el.reportsList.innerHTML = '';
            jobs.filter(j => j.status === 'completed').reverse().forEach(job => {
                const item = document.createElement('div');
                item.className = 'report-item';
                item.innerHTML = `
                    <div class="report-item-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                    </div>
                    <div class="report-item-info">
                        <div class="report-item-name">${job.output_file || job.filename}</div>
                        <div class="report-item-meta">${job.report_type} · ${job.companies_found} companies · ${formatElapsed(job.elapsed_time)}</div>
                    </div>
                    <a href="/api/download/${job.output_file}" class="report-item-download" download="${job.output_file}">Download</a>
                `;
                el.reportsList.appendChild(item);
            });
        }
        
        // Activity list (Render strictly from local storage to persist 24h client-side)
        let historyJobs = JSON.parse(localStorage.getItem('extractor_history_full') || '[]');
        
        // Ensure we respect 24 hours
        const now = new Date().getTime();
        historyJobs = historyJobs.filter(j => (now - (j.timestamp || now)) < (24 * 60 * 60 * 1000));
        
        if (historyJobs.length > 0) {
            el.activityList.innerHTML = '';
            // reverse to show newest first
            [...historyJobs].reverse().forEach(job => {
                const dotClass = job.status === 'completed' ? 'success' : 
                                 job.status === 'error' ? 'error' : 
                                 job.status === 'processing' ? 'processing' : 'queued';
                const item = document.createElement('div');
                item.className = 'activity-item';
                item.innerHTML = `
                    <div class="activity-dot ${dotClass}"></div>
                    <div class="activity-info">
                        <div class="activity-title">${job.filename} (${job.report_type})</div>
                        <div class="activity-detail">${job.message} · ${formatElapsed(job.elapsed_time)}</div>
                    </div>
                `;
                el.activityList.appendChild(item);
            });
        } else {
            el.activityList.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.5" class="empty-icon">
                        <polyline points="52 32 44 32 38 48 26 16 20 32 12 32"/>
                    </svg>
                    <h3>No activity yet</h3>
                    <p>Start processing a report to see activity</p>
                </div>
            `;
        }
        
    } catch (err) {
        console.error('Failed to load jobs:', err);
    }
}

// ─── Toast Notifications ────────────────────────────────────────────────────
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ';
    toast.innerHTML = `<span style="font-size:1.1rem;">${icon}</span> ${message}`;
    
    el.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ─── Utilities ──────────────────────────────────────────────────────────────
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatElapsed(seconds) {
    if (!seconds) return '--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
}
