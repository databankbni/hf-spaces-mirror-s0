const API_URL = ""; 
let chartCounter = 0;
let appState = {
    gridData: [], columns: [], sheets: [], activeSheet: "Sheet 1",
    selection: { start: null, end: null }, isResizing: false, resizeCol: null, startX: 0, startWidth: 0, colWidths: [],
    activeCellCoord: null, currentView: 'grid',
    savedCharts: [] 
};

let latestStats = { revenue: "$0", profit: "$0", margin: "0%", count: "0" };

const colorPalettes = {
    corporate: ['#0ea5e9', '#0284c7', '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#64748b', '#334155'],
    emerald: ['#14b8a6', '#0d9488', '#10b981', '#059669', '#34d399', '#0f766e', '#06b6d4', '#0891b2'],
    cyberpunk: ['#38bdf8', '#0ea5e9', '#8b5cf6', '#a855f7', '#c084fc', '#e879f9', '#2dd4bf', '#22d3ee']
};

const chartResizeObserver = new ResizeObserver(entries => {
    for (let entry of entries) {
        const plotDiv = entry.target.querySelector('.js-plotly-plot');
        if (plotDiv) Plotly.Plots.resize(plotDiv);
    }
});

document.addEventListener("DOMContentLoaded", () => { 
    fetchState(); 
    setupGlobalEvents(); 
});

function toggleTheme() {
    const body = document.body;
    const current = body.getAttribute('data-theme');
    const target = current === 'light' ? 'dark' : 'light';
    body.setAttribute('data-theme', target);
    document.querySelector('#theme-toggle i').className = target === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
    if(appState.currentView === 'visual') document.querySelectorAll('.js-plotly-plot').forEach(p => Plotly.Plots.resize(p));
}

function toggleAIPanel() {
    const panel = document.getElementById('ai-panel');
    const icon = document.getElementById('ai-toggle-icon');
    const gridPanel = document.getElementById('main-grid-panel');
    
    panel.classList.toggle('collapsed');
    gridPanel.classList.toggle('shifted');
    
    if(panel.classList.contains('collapsed')) {
        icon.classList.remove('fa-chevron-right'); icon.classList.add('fa-chevron-left');
    } else {
        icon.classList.remove('fa-chevron-left'); icon.classList.add('fa-chevron-right');
    }
    
    setTimeout(() => { document.querySelectorAll('.js-plotly-plot').forEach(p => Plotly.Plots.resize(p)); }, 350);
}

async function syncDataToBackend() {
    try {
        await fetch(`${API_URL}/sheet/update`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({data: appState.gridData, columns: appState.columns})
        });
        updateBusinessStats();
    } catch(e) { console.error("Sync error:", e); }
}

async function fetchState() {
    try {
        const res = await fetch(`${API_URL}/grid`);
        const data = await res.json();
        appState.sheets = data.sheets || ["Sheet 1"];
        appState.activeSheet = data.active || "Sheet 1";
        let cols = data.columns || ["Date","Department","Revenue","Expenses","Status"];
        if (!data.data || data.data.length === 0) data.data = Array.from({length: 30}, () => { let r={}; cols.forEach(c=>r[c]=""); return r; });
        renderTabs(); initGrid(data.data, cols); updateBusinessStats(); 
    } catch(e) { console.error(e); }
}

async function promoteHeader() {
    try {
        const res = await fetch(`${API_URL}/promote-header`, { method: "POST" });
        const data = await res.json();
        if(data.status === "success") fetchState();
    } catch(e) {}
}

function openDataModeler() {
    const colContainer = document.getElementById('modeler-cols');
    colContainer.innerHTML = '';
    appState.columns.forEach(col => {
        colContainer.innerHTML += `<div style="margin-bottom:6px;"><label style="color:var(--text-main); font-size:13px; cursor:pointer;"><input type="checkbox" class="modeler-checkbox" value="${col}" checked style="margin-right:8px;"> ${col}</label></div>`;
    });
    document.getElementById('data-modeler-modal').classList.remove('hidden');
}

async function applyDataModel() {
    const checkboxes = document.querySelectorAll('.modeler-checkbox');
    const selectedCols = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);
    const filterText = document.getElementById('modeler-filter').value.trim();
    document.getElementById('data-modeler-modal').classList.add('hidden');
    try {
        const payload = { selected_cols: selectedCols, filter_val: filterText };
        const res = await fetch(`${API_URL}/model-data`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const data = await res.json();
        if(data.status === "success") fetchState();
    } catch(e) { alert("Modeler Error"); }
}

async function generatePivot() {
    if(appState.columns.length < 2) return;
    const groupCol = prompt(`Enter exact column name to Pivot/Group By:`, appState.columns[0]);
    if(!groupCol) return;
    try {
        const res = await fetch(`${API_URL}/pivot`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({group_col: groupCol}) });
        const data = await res.json();
        if(data.status === "success") fetchState();
    } catch(e) {}
}

function exportToCSV() {
    if (appState.gridData.length === 0) return;
    let csvContent = "data:text/csv;charset=utf-8," + appState.columns.join(",") + "\n";
    appState.gridData.forEach(row => {
        let rowArray = appState.columns.map(col => `"${row[col] || ''}"`);
        csvContent += rowArray.join(",") + "\n";
    });
    const link = document.createElement("a"); link.href = encodeURI(csvContent); link.download = `${appState.activeSheet}.csv`;
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
}

function initGrid(data = null, columns = null) {
    const container = document.getElementById("spreadsheet"); 
    if(!container) return; container.innerHTML = "";
    appState.columns = columns || ["A","B","C"];
    appState.gridData = data || [];
    if (appState.colWidths.length !== appState.columns.length) appState.colWidths = appState.columns.map(() => 140);
    container.style.gridTemplateColumns = `40px ` + appState.colWidths.map(w => `${w}px`).join(" ");

    const fragment = document.createDocumentFragment();
    createCell(fragment, "corner", '<i class="fa-solid fa-th"></i>', selectAll);
    appState.columns.forEach((col, i) => {
        const h = document.createElement("div"); h.className = "header"; h.innerText = col; h.onclick = (e) => selectColumn(i, e); 
        const handle = document.createElement("div"); handle.className = "resizer"; handle.onmousedown = (e) => startResize(e, i);
        h.appendChild(handle); fragment.appendChild(h);
    });

    const renderLimit = Math.min(appState.gridData.length, 100); 
    for(let r = 0; r < renderLimit; r++) {
        const row = appState.gridData[r];
        createCell(fragment, "header", r + 1, () => selectRow(r));
        appState.columns.forEach((col, c) => {
            const cell = document.createElement("div");
            cell.className = "cell"; cell.contentEditable = true; cell.innerText = row[col] || ""; cell.dataset.r = r; cell.dataset.c = c;
            if (String(row[col]).includes("TOTAL")) cell.classList.add("total-row-highlight");
            cell.onfocus = () => activateFormulaTracking(cell, r, col);
            cell.onmousedown = (e) => startSelect(e, r, c);
            cell.onmouseenter = (e) => updateSelect(e, r, c);
            cell.onkeydown = (e) => handleKey(e, r, c, cell);
            cell.onblur = () => { evaluateFormula(cell); handleUpdate(cell, r, col); };
            fragment.appendChild(cell);
        });
    }
    container.appendChild(fragment);
}

function activateFormulaTracking(cell, r, col) {
    appState.activeCellCoord = {r, col};
    const formulaBar = document.getElementById("grid-formula-bar");
    formulaBar.disabled = false; formulaBar.value = cell.dataset.formula || cell.innerText;
}

async function updateBusinessStats() {
    try {
        const res = await fetch(`${API_URL}/business-stats`);
        const stats = await res.json();
        latestStats.revenue = '$' + stats.revenue.toLocaleString('en-US', {minimumFractionDigits: 2});
        latestStats.expenses = '$' + stats.expenses.toLocaleString('en-US', {minimumFractionDigits: 2});
        latestStats.profit = '$' + stats.profit.toLocaleString('en-US', {minimumFractionDigits: 2});
        
        document.getElementById('stat-count').innerText = stats.count;
        document.getElementById('stat-revenue').innerText = latestStats.revenue;
        document.getElementById('stat-expenses').innerText = latestStats.expenses;
        document.getElementById('stat-profit').innerText = latestStats.profit;
    } catch (e) {}
}

// --- BI STUDIO (Absolute Canvas Engine) ---
function switchVizMode(mode) {
    document.querySelectorAll('.viz-tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${mode}`).classList.add('active');
    document.getElementById('viz-builder-mode').classList.add('hidden');
    document.getElementById('viz-canvas-mode').classList.add('hidden');
    document.getElementById(`viz-${mode}-mode`).classList.remove('hidden');
    if(mode === 'canvas') document.querySelectorAll('.js-plotly-plot').forEach(p => Plotly.Plots.resize(p));
}

// True Custom Absolute Drag & Resize Logic (Fixes all Flexbox bugs)
function makeAbsoluteDraggableAndResizable(elmnt) {
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    const header = elmnt.querySelector('.slide-hover-menu');
    const resizer = elmnt.querySelector('.resize-handle');

    if (header) { header.onmousedown = dragMouseDown; }
    if (resizer) { resizer.onmousedown = resizeMouseDown; }

    function dragMouseDown(e) {
        e.preventDefault(); e.stopPropagation();
        pos3 = e.clientX; pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
        document.querySelectorAll('.dash-card-slide').forEach(c => c.style.zIndex = 1);
        elmnt.style.zIndex = 10;
    }

    function elementDrag(e) {
        e.preventDefault();
        pos1 = pos3 - e.clientX; pos2 = pos4 - e.clientY;
        pos3 = e.clientX; pos4 = e.clientY;
        
        const parent = elmnt.parentElement;
        let newTop = elmnt.offsetTop - pos2;
        let newLeft = elmnt.offsetLeft - pos1;
        
        // Bounds checking
        if(newTop < 0) newTop = 0;
        if(newLeft < 0) newLeft = 0;
        if(newTop + elmnt.offsetHeight > parent.offsetHeight) newTop = parent.offsetHeight - elmnt.offsetHeight;
        if(newLeft + elmnt.offsetWidth > parent.offsetWidth) newLeft = parent.offsetWidth - elmnt.offsetWidth;

        elmnt.style.top = newTop + "px";
        elmnt.style.left = newLeft + "px";
    }

    function resizeMouseDown(e) {
        e.preventDefault(); e.stopPropagation();
        pos3 = e.clientX; pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementResize;
        document.querySelectorAll('.dash-card-slide').forEach(c => c.style.zIndex = 1);
        elmnt.style.zIndex = 10;
    }

    function elementResize(e) {
        e.preventDefault();
        let deltaX = e.clientX - pos3;
        let deltaY = e.clientY - pos4;
        pos3 = e.clientX; pos4 = e.clientY;
        
        let newWidth = elmnt.offsetWidth + deltaX;
        let newHeight = elmnt.offsetHeight + deltaY;
        
        // Minimum limits
        if(newWidth < 150) newWidth = 150;
        if(newHeight < 100) newHeight = 100;

        // Parent bounds checking
        const parent = elmnt.parentElement;
        if (elmnt.offsetLeft + newWidth > parent.offsetWidth) newWidth = parent.offsetWidth - elmnt.offsetLeft;
        if (elmnt.offsetTop + newHeight > parent.offsetHeight) newHeight = parent.offsetHeight - elmnt.offsetTop;

        elmnt.style.width = newWidth + "px";
        elmnt.style.height = newHeight + "px";
    }

    function closeDragElement() { 
        document.onmouseup = null; 
        document.onmousemove = null; 
        const plot = elmnt.querySelector('.js-plotly-plot');
        if(plot) Plotly.Plots.resize(plot);
    }
}

async function previewChart() { 
    const type = document.getElementById("chart-type").value; 
    const x = document.getElementById("x-axis").value; 
    const y = document.getElementById("y-axis").value;
    const agg = document.getElementById("y-agg").value;
    
    document.getElementById('preview-chart-area').innerHTML = "";
    await renderPlotlyChart(type, x, y, agg, 'preview-chart-area', false);
}

async function saveToBoard() {
    const board = document.getElementById('presentation-board');
    if (board.children.length >= 6) {
        alert("Gestalt Principles Alert: A presentation slide should contain a maximum of 6 elements to maintain cognitive clarity and prevent overcrowding.");
        return;
    }

    const type = document.getElementById("chart-type").value; 
    const x = document.getElementById("x-axis").value; 
    const y = document.getElementById("y-axis").value;
    const agg = document.getElementById("y-agg").value;
    
    appState.savedCharts.push({type, x, y, agg});
    
    chartCounter++;
    const targetDivId = `board-chart-${chartCounter}`;
    
    const div = document.createElement('div');
    div.className = "dash-card-slide";
    // Initialize default absolute size and position
    div.style.top = "20px"; div.style.left = "20px"; div.style.width = "400px"; div.style.height = "300px";
    div.ondblclick = () => zoomChart(type, x, y, agg);
    
    div.innerHTML = `
        <div class="slide-hover-menu">
            <span><i class="fa-solid fa-arrows-up-down-left-right"></i> Drag</span>
            <button onclick="this.parentElement.parentElement.remove()" class="close-btn"><i class="fa-solid fa-xmark"></i></button>
        </div>
        <div class="chart-wrapper"><div id="${targetDivId}" style="height:100%; width:100%;"></div></div>
        <div class="resize-handle"><i class="fa-solid fa-caret-down" style="transform: rotate(-45deg);"></i></div>
    `;
    board.appendChild(div);

    makeAbsoluteDraggableAndResizable(div);
    chartResizeObserver.observe(div); 

    switchVizMode('canvas');

    requestAnimationFrame(async () => {
        await renderPlotlyChart(type, x, y, agg, targetDivId, false, null, true);
    });
}

async function generateKPI() {
    const board = document.getElementById('presentation-board');
    if (board.children.length >= 6) { alert("Slide full (Max 6 elements)."); return; }

    const x = document.getElementById("x-axis").value; 
    const y = document.getElementById("y-axis").value;
    const agg = document.getElementById("y-agg").value;
    
    chartCounter++;

    const div = document.createElement('div');
    div.className = "dash-card-slide";
    div.style.top = "20px"; div.style.left = "20px"; div.style.width = "250px"; div.style.height = "150px";

    div.innerHTML = `
        <div class="slide-hover-menu">
            <span><i class="fa-solid fa-arrows-up-down-left-right"></i> Drag</span>
            <button onclick="this.parentElement.parentElement.remove()" class="close-btn"><i class="fa-solid fa-xmark"></i></button>
        </div>
        <div style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:100%; padding:20px; pointer-events:none;">
            <div style="font-size: 12px; color: var(--text-dim); text-transform: uppercase;">${y} (${agg})</div>
            <div id="kpi-val-${chartCounter}" style="font-size: 40px; font-weight: 700; color: var(--accent);">...</div>
        </div>
        <div class="resize-handle"><i class="fa-solid fa-caret-down" style="transform: rotate(-45deg);"></i></div>
    `;
    board.appendChild(div);
    makeAbsoluteDraggableAndResizable(div);
    chartResizeObserver.observe(div);
    switchVizMode('canvas');

    const payload = { type: 'bar', x, y, agg }; 
    const res = await fetch(`${API_URL}/visualize/chart`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); 
    const d = await res.json(); 
    if(d.chart_data && d.chart_data.y.length > 0) {
        let total = d.chart_data.y.reduce((a,b)=>a+b,0);
        document.getElementById(`kpi-val-${chartCounter}`).innerText = total > 1000 ? (total/1000).toFixed(1) + 'k' : total.toFixed(0);
    }
}

async function zoomChart(type, x, y, agg) {
    document.getElementById('chart-zoom-modal').classList.remove('hidden');
    document.getElementById('zoomed-chart-area').innerHTML = "";
    await renderPlotlyChart(type, x, y, agg, 'zoomed-chart-area', false);
    setTimeout(() => { Plotly.Plots.resize(document.getElementById('zoomed-chart-area')); }, 100);
}

// Master Plotly Mapping Engine
async function renderPlotlyChart(type, x, y, agg, targetId, isPrintLayout=false, kpiId=null, isSlideMode=false) {
    const currentTheme = document.getElementById("chart-theme").value || 'corporate';
    const activePalette = colorPalettes[currentTheme];
    const isLight = document.body.getAttribute('data-theme') === 'light' || isPrintLayout;
    
    const fontColor = isLight ? '#0f172a' : '#cbd5e1';
    const gridColor = isLight ? '#e2e8f0' : '#334155';
    const bgColor = isSlideMode ? 'rgba(0,0,0,0)' : (isLight ? '#ffffff' : 'rgba(0,0,0,0)'); 

    const payload = { type, x, y, agg }; 
    const res = await fetch(`${API_URL}/visualize/chart`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); 
    const d = await res.json(); 
    
    if (d.chart_data && document.getElementById(targetId)) { 
        let trace = { x: d.chart_data.x, y: d.chart_data.y, marker: { color: activePalette[0] } }; 
        let layoutParams = {};

        if (type.includes('pie') || type.includes('donut')) { trace.labels = d.chart_data.x; trace.values = d.chart_data.y; trace.type = 'pie'; trace.marker = {colors: activePalette}; if(type==='donut') trace.hole = 0.6;
        } else if (type === 'line' || type === 'timeline') { trace.type = 'scatter'; trace.mode = 'lines+markers'; trace.line = { shape: 'spline', color: activePalette[1] };
        } else if (type === 'line-log') { trace.type = 'scatter'; trace.mode = 'lines'; layoutParams.yaxis = { type: 'log', gridcolor: gridColor };
        } else if (type === 'scatter') { trace.type = 'scatter'; trace.mode = 'markers'; trace.marker = { size: 10, color: activePalette[2] };
        } else if (type === 'scatter-connect') { trace.type = 'scatter'; trace.mode = 'lines+markers'; trace.line = { color: activePalette[0] };
        } else if (type === 'bubble' || type === 'circle-pack') { trace.type = 'scatter'; trace.mode = 'markers'; trace.marker = { size: d.chart_data.y, sizeref: Math.max(...d.chart_data.y)/30, sizemode: 'area', color: activePalette[3] };
        } else if (type === 'area') { trace.type = 'scatter'; trace.mode = 'lines'; trace.fill = 'tozeroy'; trace.line = { color: activePalette[0] };
        } else if (type === 'area-stacked') { trace.type = 'scatter'; trace.mode = 'lines'; trace.fill = 'tonexty'; trace.stackgroup = 'one';
        } else if (type === 'bar-stacked') { trace.type = 'bar'; layoutParams.barmode = 'stack';
        } else if (type === 'box') { trace.type = 'box'; trace.name = y; trace.marker = { color: activePalette[4] };
        } else if (type === 'violin' || type === 'density') { trace.type = 'violin'; trace.y = d.chart_data.y; trace.x = d.chart_data.x; trace.box = {visible: true}; trace.line = {color: activePalette[0]};
        } else if (type === 'waterfall') { trace.type = 'waterfall'; trace.measure = d.chart_data.x.map((_, i) => i === d.chart_data.x.length -1 ? 'total' : 'relative');
        } else if (type === 'funnel') { trace.type = 'funnel'; trace.y = d.chart_data.x; trace.x = d.chart_data.y; trace.marker = {color: activePalette};
        } else if (type === 'radar') { trace.type = 'scatterpolar'; trace.r = d.chart_data.y; trace.theta = d.chart_data.x; trace.fill = 'toself'; layoutParams.polar = { radialaxis: { visible: true, gridcolor: gridColor }, angularaxis: { gridcolor: gridColor }, bgcolor: 'transparent' };
        } else if (type === 'heatmap') { trace.type = 'heatmap'; trace.z = [d.chart_data.y]; trace.x = d.chart_data.x; trace.colorscale = 'Blues';
        } else if (type === 'treemap') { trace.type = 'treemap'; trace.labels = d.chart_data.x; trace.parents = Array(d.chart_data.x.length).fill('Dataset'); trace.values = d.chart_data.y; trace.textinfo = "label+value";
        } else if (type === 'sunburst') { trace.type = 'sunburst'; trace.labels = d.chart_data.x; trace.parents = Array(d.chart_data.x.length).fill('Root'); trace.values = d.chart_data.y;
        } else if (type === 'radial-bar') { trace.type = 'barpolar'; trace.r = d.chart_data.y; trace.theta = d.chart_data.x; trace.marker = { color: activePalette }; layoutParams.polar = { bgcolor: 'transparent' };
        } else if (type === 'candlestick' || type === 'ohlc') { trace.type = type; trace.x = d.chart_data.x; trace.close = d.chart_data.y; trace.open = d.chart_data.y.map(v=>v*0.9); trace.high = d.chart_data.y.map(v=>v*1.1); trace.low = d.chart_data.y.map(v=>v*0.8);
        } else if (type === 'sankey') { trace.type = 'sankey'; trace.node = {label: d.chart_data.x}; trace.link = {source: Array.from(d.chart_data.x.keys()), target: Array.from(d.chart_data.x.keys()).map(i=>(i+1)%d.chart_data.x.length), value: d.chart_data.y};
        } else { trace.type = 'bar'; trace.marker = {color: activePalette}; }
        
        const layout = { 
            title: { text: `${y} by ${x}`, font: { size: 14, color: fontColor } }, 
            paper_bgcolor: bgColor, plot_bgcolor: bgColor, font: { color: fontColor }, 
            xaxis: { gridcolor: gridColor, zerolinecolor: gridColor }, yaxis: { gridcolor: gridColor, zerolinecolor: gridColor },
            ...layoutParams, margin: { t: 40, l: 40, r: 20, b: 40 }, autosize: true
        }; 
        Plotly.newPlot(targetId, [trace], layout, {responsive: true, displayModeBar: false}); 
    }
}

// Full Slide Export Engine
async function exportSlide(format) {
    const slide = document.getElementById('presentation-board');
    if (slide.children.length === 0) return alert("The slide is empty. Please add charts first.");
    
    // Hide UI controls temporarily
    document.querySelectorAll('.slide-hover-menu').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.resize-handle').forEach(el => el.style.display = 'none');
    
    // Set explicit theme background for export based on active theme
    const isLight = document.body.getAttribute('data-theme') === 'light';
    const bgCol = isLight ? '#ffffff' : '#1e293b';

    try {
        const canvas = await html2canvas(slide, { scale: 2, backgroundColor: bgCol, useCORS: true }); 
        const imgData = canvas.toDataURL('image/png');
        
        if (format === 'png' || format === 'jpg') {
            const link = document.createElement('a');
            link.download = `Enterprise_Slide.${format}`;
            link.href = format === 'jpg' ? canvas.toDataURL('image/jpeg', 0.9) : imgData;
            link.click();
        } else if (format === 'pdf') {
            const pdf = new jspdf.jsPDF({ orientation: 'landscape', unit: 'px', format: [canvas.width, canvas.height] });
            pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
            pdf.save('Enterprise_Slide.pdf');
        }
    } catch(e) {
        console.error(e);
        alert("Export failed. Please check browser permissions.");
    } finally {
        // Restore controls
        document.querySelectorAll('.slide-hover-menu').forEach(el => el.style.display = '');
        document.querySelectorAll('.resize-handle').forEach(el => el.style.display = '');
    }
}

// --- PUBLISHER (DOCS/PPT) ---
function formatDoc(cmd, value=null) { document.execCommand(cmd, false, value); document.getElementById('report-pages-container').focus(); }
function insertTable() {
    const html = `<table style="width:100%; border-collapse:collapse; margin: 15px 0;">
        <tr><th style="border:1px solid #cbd5e1; padding:8px;">Header 1</th><th style="border:1px solid #cbd5e1; padding:8px;">Header 2</th></tr>
        <tr><td style="border:1px solid #cbd5e1; padding:8px;">Data</td><td style="border:1px solid #cbd5e1; padding:8px;">Data</td></tr>
    </table><p>&#8203;</p>`;
    document.execCommand('insertHTML', false, html);
}
function insertMedia(type) {
    if(type === 'image') {
        const url = prompt("Enter Image URL:");
        if(url) document.execCommand('insertHTML', false, `<img src="${url}" style="max-width:100%; border-radius:8px; margin: 10px 0;" />`);
    }
}

async function insertSavedChart() {
    if (appState.savedCharts.length === 0) return alert("No charts saved! Go to BI Studio and click 'Save to Slide'.");
    chartCounter++;
    const targetId = `report-saved-chart-${chartCounter}`;
    
    const htmlStr = `<br><div class="report-chart-wrapper" contenteditable="false" style="resize: both; overflow: hidden; width: 600px; height: 350px; max-width: 100%; margin: 10px auto; border: 1px dashed #cbd5e1; border-radius: 8px; position: relative;">
        <div id="${targetId}" style="width: 100%; height: 100%;"></div>
    </div><br><p>&#8203;</p>`;
    
    document.execCommand('insertHTML', false, htmlStr);
    const config = appState.savedCharts[appState.savedCharts.length - 1];
    
    setTimeout(async () => { 
        await renderPlotlyChart(config.type, config.x, config.y, config.agg, targetId, true); 
        const wrapper = document.getElementById(targetId).parentElement;
        chartResizeObserver.observe(wrapper);
    }, 100);
}

function adjustPageLayout() {
    const layout = document.getElementById("page-layout-size").value;
    document.querySelectorAll('.page-canvas').forEach(page => { page.className = `page-canvas ${layout}`; });
}

function addBlankPage() {
    const container = document.getElementById('report-pages-container');
    const layout = document.getElementById("page-layout-size").value;
    const pageCount = container.children.length + 1;
    const newPage = document.createElement('div');
    newPage.className = `page-canvas ${layout}`;
    newPage.contentEditable = true; newPage.spellcheck = false; newPage.id = `page-${pageCount}`;
    newPage.innerHTML = `<h1>Page ${pageCount}</h1><p>Start typing here...</p>`;
    container.appendChild(newPage); 
    newPage.focus();
    return newPage;
}

document.getElementById('report-pages-container').addEventListener('input', function(e) {
    const page = e.target.closest('.page-canvas');
    if(page && page.scrollHeight > page.clientHeight + 2 && !page.classList.contains('ppt-slide')) {
        addBlankPage();
    }
});

async function publisherAI(action) {
    const selection = window.getSelection().toString();
    if (!selection) return alert("Highlight text first!");
    document.getElementById("ai-input-container").classList.add("ai-processing");
    try {
        const res = await fetch(`${API_URL}/publisher-ai`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: action, text: selection }) });
        const data = await res.json();
        document.execCommand('insertHTML', false, `<span>${data.result}</span>`);
        document.getElementById("ai-input-container").classList.remove("ai-processing");
    } catch(e) { document.getElementById("ai-input-container").classList.remove("ai-processing"); alert("AI Formatting failed."); }
}

async function generateAIReport() {
    const container = document.getElementById('report-pages-container');
    const activePage = container.lastElementChild;
    activePage.innerHTML = `<h1>Automated Report</h1><p><i>Generating AI narrative... Please wait.</i></p><br>`;
    try {
        const payload = { report_type: "Strategic Business Summary", layout_style: document.getElementById('page-layout-size').value };
        const res = await fetch(`${API_URL}/generate-report`, { method: 'POST', headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const data = await res.json();
        activePage.innerHTML = data.narrative;
    } catch (e) { activePage.innerHTML = '<span style="color:red;">Error connecting to AI.</span>'; }
}

async function handleUpdate(cell, r, col) { 
    appState.gridData[r][col] = cell.innerText.trim(); 
    await syncDataToBackend(); 
    if(appState.currentView === 'grid') {
        const xSelect = document.getElementById("x-axis"); const ySelect = document.getElementById("y-axis"); 
        xSelect.innerHTML = ""; ySelect.innerHTML = ""; 
        appState.columns.forEach(c => { xSelect.appendChild(new Option(c, c)); ySelect.appendChild(new Option(c, c)); });
    }
}

function createCell(p, c, h, click) { const d=document.createElement("div"); d.className=c; d.innerHTML=h; if(click) d.onclick=click; p.appendChild(d); }
function evaluateFormula(cell) { let val = cell.innerText.trim(); if (val.startsWith("=")) { cell.dataset.formula = val; try { const formula = val.substring(1).toUpperCase(); let parsed = "0"; if (!val.toUpperCase().includes("SUM")) { parsed = formula; appState.columns.forEach((col) => { appState.gridData.forEach((row, rIdx) => { const ref = `${col}${rIdx+1}`; if (parsed.includes(ref)) { parsed = parsed.replace(ref, parseFloat(row[col]) || 0); } }); }); } try { cell.innerText = eval(parsed); cell.classList.add("has-formula"); } catch(e) { cell.innerText = "#ERR:CALC"; } } catch(e) { cell.innerText = "#REF!"; } } }
function handleKey(e, r, c, cell) { if (e.key === "Enter") { e.preventDefault(); cell.blur(); const next = document.querySelector(`.cell[data-r='${r+1}'][data-c='${c}']`); if (next) next.focus(); } }
function startResize(e, i) { e.stopPropagation(); appState.isResizing = true; appState.resizeCol = i; appState.startX = e.pageX; appState.startWidth = appState.colWidths[i]; document.body.style.cursor = "col-resize"; document.addEventListener("mousemove", onResize); document.addEventListener("mouseup", endResize); }
function onResize(e) { if (!appState.isResizing) return; appState.colWidths[appState.resizeCol] = Math.max(60, appState.startWidth + (e.pageX - appState.startX)); initGrid(appState.gridData, appState.columns); }
function endResize() { appState.isResizing = false; document.body.style.cursor = "default"; document.removeEventListener("mousemove", onResize); document.removeEventListener("mouseup", endResize); }
function renderTabs() { const b = document.getElementById("sheet-tabs"); b.innerHTML = ""; appState.sheets.forEach(s => { const t = document.createElement("div"); t.className = `sheet-tab ${s === appState.activeSheet ? 'active' : ''}`; const sp = document.createElement("span"); sp.innerText = s; sp.onclick = () => switchSheet(s); const cl = document.createElement("span"); cl.className = "close-tab"; cl.innerHTML = '×'; cl.onclick = (e) => { e.stopPropagation(); const fd = new FormData(); fd.append("name", s); fetch(`${API_URL}/sheet/close`, {method:"POST", body:fd}).then(fetchState); }; t.appendChild(sp); t.appendChild(cl); b.appendChild(t); }); }
async function switchSheet(n) { const fd=new FormData(); fd.append("name",n); const res=await fetch(`${API_URL}/sheet/switch`,{method:"POST",body:fd}); const d=await res.json(); appState.activeSheet=d.active; renderTabs(); initGrid(d.data,d.columns); updateBusinessStats();}
function selectAll() { appState.selection = { start: {r: 0, c: 0}, end: {r: Math.min(appState.gridData.length - 1, 99), c: appState.columns.length - 1} }; renderSelection(); }
function selectColumn(colIndex, e) { if(e.target.classList.contains('resizer')) return; appState.selection = { start: {r: 0, c: colIndex}, end: {r: Math.min(appState.gridData.length - 1, 99), c: colIndex} }; renderSelection(); }
function selectRow(r) { appState.selection = { start: {r: r, c: 0}, end: {r: r, c: appState.columns.length - 1} }; renderSelection(); }
function startSelect(e,r,c){ appState.selection={start:{r,c},end:{r,c}}; renderSelection(); }
function updateSelect(e,r,c){ if(e.buttons===1){ appState.selection.end={r,c}; renderSelection(); } }
function renderSelection(){ document.querySelectorAll(".selected").forEach(e=>e.classList.remove("selected")); const {start,end}=appState.selection; if(!start)return; const rMin=Math.min(start.r,end.r), rMax=Math.max(start.r,end.r), cMin=Math.min(start.c,end.c), cMax=Math.max(start.c,end.c); for(let r=rMin;r<=rMax;r++) for(let c=cMin;c<=cMax;c++) { const el=document.querySelector(`.cell[data-r='${r}'][data-c='${c}']`); if(el) el.classList.add("selected"); } calculateStats(); }
function calculateStats(){ const {start,end}=appState.selection; if(!start)return; let sum=0, count=0; const rMin=Math.min(start.r,end.r), rMax=Math.max(start.r,end.r), cMin=Math.min(start.c,end.c), cMax=Math.max(start.c,end.c); for(let r=rMin;r<=rMax;r++) for(let c=cMin;c<=cMax;c++) { const val=appState.gridData[r]?.[appState.columns[c]]; if(val && !isNaN(parseFloat(val))){ sum+=parseFloat(val); count++; } } if (count > 0) document.getElementById("sel-range").innerText = `SUM: ${sum.toFixed(2)} | COUNT: ${count}`; else document.getElementById("sel-range").innerText = "Ready"; }

function toggleView(v) { 
    appState.currentView = v;
    document.querySelectorAll('.view-section').forEach(el => el.classList.add('hidden')); 
    document.getElementById(`view-${v}`).classList.remove('hidden'); 
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active')); 
    document.getElementById(`btn-nav-${v}`).classList.add('active'); 
    
    document.getElementById('main-sidebar').classList.remove('mobile-open');

    if(v==='visual') {
        const xSelect = document.getElementById("x-axis"); const ySelect = document.getElementById("y-axis"); 
        xSelect.innerHTML = ""; ySelect.innerHTML = ""; 
        appState.columns.forEach(c => { xSelect.appendChild(new Option(c, c)); ySelect.appendChild(new Option(c, c)); });
        setTimeout(() => document.querySelectorAll('.js-plotly-plot').forEach(p => Plotly.Plots.resize(p)), 100);
    }
}

async function sendToAI(isSilent=false, commandText="") {
    const input = document.getElementById("ai-input"); const v = commandText || input.value.trim(); if(!v) return;
    if(!isSilent) { addChat("user", v); input.value = ""; }
    document.getElementById("ai-input-container").classList.add("ai-processing");
    try {
        const payload = { message: v, context: appState.currentView };
        const res = await fetch(`${API_URL}/chat`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
        const d = await res.json(); document.getElementById("ai-input-container").classList.remove("ai-processing");
        if (d.response) {
            let responseText = d.response; let thinkingHTML = ""; 
            const thinkMatch = responseText.match(/THINKING:([\s\S]*?)FINAL ANSWER:([\s\S]*)/);
            if (thinkMatch) {
                thinkingHTML = `<details class="thinking-box"><summary>▶ Telemetry Engine</summary><div class="thinking-content">${thinkMatch[1].trim().replace(/\n/g, '<br>')}</div></details>`;
                responseText = thinkMatch[2].trim();
            }
            
            if (responseText.includes("<<GRID_MERGE:")) {
                const match = responseText.match(/<<GRID_MERGE:([\s\S]*?)>>/);
                if(match && match[1]) {
                    const newData = JSON.parse(match[1]);
                    const keys = Object.keys(newData[0]);
                    keys.forEach(k => { if(!appState.columns.includes(k)) appState.columns.push(k); });
                    appState.gridData.forEach((row, i) => { if(newData[i]) Object.assign(row, newData[i]); });
                    
                    await syncDataToBackend(); 
                    initGrid(appState.gridData, appState.columns);
                    
                    if (appState.currentView === 'visual') {
                        const xSelect = document.getElementById("x-axis"); const ySelect = document.getElementById("y-axis");
                        xSelect.innerHTML = ""; ySelect.innerHTML = "";
                        appState.columns.forEach(c => { xSelect.appendChild(new Option(c, c)); ySelect.appendChild(new Option(c, c)); });
                    }
                    addChat("ai", `${thinkingHTML}✅ I have merged the new data directly into your active table. You can visualize it immediately.`);
                    return;
                }
            }

            if (responseText.includes("<<CHART_ACTION:")) {
                const match = responseText.match(/<<CHART_ACTION:(.*?)>>/);
                if(match && match[1]) {
                    const config = JSON.parse(match[1]); toggleView('visual'); switchVizMode('preview');
                    addChat("ai", `${thinkingHTML}📊 Rendering preview requested.`);
                    document.getElementById("chart-type").value = config.type || "bar";
                    document.getElementById("x-axis").value = config.x; document.getElementById("y-axis").value = config.y;
                    previewChart();
                    return;
                }
            } 
            
            addChat("ai", thinkingHTML + responseText);
        }
    } catch(e) { document.getElementById("ai-input-container").classList.remove("ai-processing"); addChat("ai", "⚠️ Connection timeout."); }
}

function addChat(role, htmlContent) {
    const box = document.getElementById("chat-box");
    const msg = document.createElement("div"); msg.className = `message ${role === 'ai' || role === 'system' ? 'system-message' : 'user-message'}`;
    const bubble = document.createElement("div"); bubble.className = "bubble";
    if(role === 'user') bubble.innerText = htmlContent;
    else bubble.innerHTML = htmlContent.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    msg.appendChild(bubble); box.appendChild(msg); box.scrollTop = box.scrollHeight;
}

function setupGlobalEvents() {
    document.getElementById("btn-add-sheet").onclick = () => { const fd=new FormData(); fd.append("name",`Worksheet ${appState.sheets.length+1}`); fetch(`${API_URL}/sheet/add`,{method:"POST",body:fd}).then(fetchState); };
    document.getElementById("up").onchange = (e) => { 
        document.getElementById("btn-clean").innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Uploading...";
        const fd=new FormData(); fd.append("file",e.target.files[0]); fd.append("mode","replace"); 
        fetch(`${API_URL}/upload`,{method:"POST",body:fd}).then(fetchState).then(()=> { document.getElementById("btn-clean").innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Deep Clean'; }); 
    };
    document.getElementById("btn-clean").onclick = async () => { document.getElementById("btn-clean").innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Normalizing..."; const res=await fetch(`${API_URL}/cleanup`,{method:"POST"}); const d=await res.json(); if(d.status) initGrid(appState.gridData, appState.columns); fetchState(); document.getElementById("btn-clean").innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Deep Clean'; };
    document.getElementById("send-btn").onclick = () => sendToAI();
    document.getElementById("ai-input").onkeydown = (e) => { if(e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); sendToAI(); }};
    document.getElementById("grid-formula-bar").oninput = (e) => {
        if(!appState.activeCellCoord) return;
        const targetCell = document.querySelector(`.cell[data-r='${appState.activeCellCoord.r}'][data-c='${appState.activeCellCoord.c}']`);
        if(targetCell) { targetCell.innerText = e.target.value; appState.gridData[appState.activeCellCoord.r][appState.activeCellCoord.col] = e.target.value; syncDataToBackend(); }
    };
}