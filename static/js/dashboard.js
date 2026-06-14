/* =============================================================================
   Intelligent Solar Panel Management System — Dashboard JavaScript
   ---------------------------------------------------------------------------
   Handles:
     - Real-time data polling & display
     - Chart.js real-time charts (Voltage, Current, Power, Energy)
     - Solar tracking controls (mode, slider, buttons)
     - Camera capture & AI dust analysis (CNN integration)
     - System health monitoring
     - UART debugging panel
     - Simulation mode indicator
     - Chart export (CSV/PNG) and pause/resume
     - Toast notifications
     - Live clock
   ============================================================================= */

// ============================================================
//  CONFIGURATION
// ============================================================
const CONFIG = {
    pollIntervals: {
        liveData:     2000,   // 2s — electrical readings
        tracking:     3000,   // 3s — tracking status
        systemStatus: 5000,   // 5s — health check
        uartDebug:    3000,   // 3s — UART debug
    },
    charts: {
        maxPoints:    60,     // Rolling window size
        animation:    false,  // Disable for performance on Pi
    },
    api: {
        liveData:         '/api/live_data',
        history:          '/api/history',
        systemStatus:     '/api/system_status',
        tracking:         '/api/tracking',
        trackingSettings: '/api/tracking_settings',
        manualServo:      '/api/manual_servo',
        capture:          '/capture',
        analyze:          '/analyze',
        uartDebug:        '/api/uart_debug',
        aiStatus:         '/api/ai_status',
        exportCSV:        '/api/export_csv',
    },
};


// ============================================================
//  STATE
// ============================================================
const state = {
    charts: {},
    previousValues: {},
    isCapturing: false,
    isAnalyzing: false,
    chartsPaused: false,
    simulationMode: false,
};


// ============================================================
//  INITIALIZATION
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initCharts();
    initServoControls();
    initTrackingControls();
    initCameraControls();
    startPolling();
    // Immediate first fetch
    fetchLiveData();
    fetchTrackingStatus();
    fetchSystemStatus();
    fetchUARTDebug();
    fetchAIStatus();
});


// ============================================================
//  LIVE CLOCK
// ============================================================
function initClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

function updateClock() {
    const now = new Date();

    const dateEl = document.getElementById('header-date');
    const timeEl = document.getElementById('header-time');

    if (dateEl) {
        dateEl.textContent = now.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        });
    }

    if (timeEl) {
        timeEl.textContent = now.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true,
        });
    }
}


// ============================================================
//  DATA POLLING
// ============================================================
function startPolling() {
    setInterval(fetchLiveData, CONFIG.pollIntervals.liveData);
    setInterval(fetchTrackingStatus, CONFIG.pollIntervals.tracking);
    setInterval(fetchSystemStatus, CONFIG.pollIntervals.systemStatus);
    setInterval(fetchUARTDebug, CONFIG.pollIntervals.uartDebug);
}

async function fetchJSON(url, options = {}) {
    try {
        const res = await fetch(url, options);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (err) {
        console.error(`Fetch error (${url}):`, err);
        return null;
    }
}


// ============================================================
//  SIMULATION MODE BANNER
// ============================================================
function updateSimulationBanner(isSimulation) {
    const banner = document.getElementById('simulation-banner');
    if (!banner) return;

    if (isSimulation && !state.simulationMode) {
        banner.style.display = 'flex';
        state.simulationMode = true;
    } else if (!isSimulation && state.simulationMode) {
        banner.style.display = 'none';
        state.simulationMode = false;
    }
}


// ============================================================
//  LIVE DATA — Electrical Monitoring
// ============================================================
async function fetchLiveData() {
    if (state.chartsPaused) return;

    const data = await fetchJSON(CONFIG.api.liveData);
    if (!data) return;

    updateMetricCard('voltage', data.voltage, 'V');
    updateMetricCard('current', data.current, 'A');
    updateMetricCard('power', data.power, 'W');
    updateMetricCard('energy', data.daily_energy, 'Wh');

    // Update simulation banner
    updateSimulationBanner(data.simulation);

    // Update last-update timestamp in header
    const lastUpdateEl = document.getElementById('header-last-update');
    if (lastUpdateEl && data.last_update) {
        const t = new Date(data.last_update);
        lastUpdateEl.textContent = t.toLocaleTimeString('en-US', {
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
        });
    }

    // Update charts
    updateCharts(data);
}

function updateMetricCard(type, value, unit) {
    const valueEl = document.getElementById(`metric-${type}-value`);
    if (!valueEl) return;

    const prev = state.previousValues[type];
    const formatted = formatNumber(value, type);

    // Only animate if value actually changed
    if (prev !== undefined && prev !== value) {
        valueEl.classList.add('value-updated');
        setTimeout(() => valueEl.classList.remove('value-updated'), 400);
    }

    valueEl.textContent = formatted;
    state.previousValues[type] = value;

    // Update trend indicator
    const trendEl = document.getElementById(`metric-${type}-trend`);
    if (trendEl && prev !== undefined) {
        const diff = value - prev;
        if (Math.abs(diff) < 0.001) {
            trendEl.className = 'metric-trend flat';
            trendEl.innerHTML = '━ Stable';
        } else if (diff > 0) {
            trendEl.className = 'metric-trend up';
            trendEl.innerHTML = `▲ +${formatNumber(Math.abs(diff), type)}`;
        } else {
            trendEl.className = 'metric-trend down';
            trendEl.innerHTML = `▼ -${formatNumber(Math.abs(diff), type)}`;
        }
    }
}

function formatNumber(value, type) {
    if (value === null || value === undefined) return '---';
    switch (type) {
        case 'voltage': return value.toFixed(1);
        case 'current': return value.toFixed(3);
        case 'power':   return value.toFixed(2);
        case 'energy':  return value.toFixed(2);
        default:        return value.toFixed(2);
    }
}


// ============================================================
//  UART DEBUG PANEL
// ============================================================
async function fetchUARTDebug() {
    const data = await fetchJSON(CONFIG.api.uartDebug);
    if (!data) return;

    setText('uart-last-packet', data.last_packet || '—');
    setText('uart-packet-count', data.packet_count || '0');
    setText('uart-port-info', `${data.port} @ ${data.baud_rate}`);

    // Format timestamp
    if (data.last_packet_time) {
        const t = new Date(data.last_packet_time);
        setText('uart-last-time', t.toLocaleTimeString('en-US', {
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
        }));
    }

    // Update status badge
    const badge = document.getElementById('uart-status-badge');
    if (badge) {
        if (data.simulation) {
            badge.textContent = 'Simulation';
            badge.className = 'uart-status-badge simulation';
        } else if (data.connected) {
            badge.textContent = 'Connected';
            badge.className = 'uart-status-badge connected';
        } else {
            badge.textContent = 'Disconnected';
            badge.className = 'uart-status-badge disconnected';
        }
    }
}


// ============================================================
//  CHART.JS — Real-Time Charts
// ============================================================
function initCharts() {
    const chartTheme = {
        gridColor: 'rgba(148, 163, 184, 0.08)',
        tickColor: '#64748b',
        fontFamily: "'Inter', sans-serif",
    };

    const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: CONFIG.charts.animation,
        interaction: {
            intersect: false,
            mode: 'index',
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#1e293b',
                titleColor: '#f1f5f9',
                bodyColor: '#94a3b8',
                borderColor: 'rgba(59, 130, 246, 0.3)',
                borderWidth: 1,
                cornerRadius: 8,
                padding: 10,
                titleFont: { family: chartTheme.fontFamily, weight: '600' },
                bodyFont: { family: "'JetBrains Mono', monospace" },
            },
        },
        scales: {
            x: {
                grid: { color: chartTheme.gridColor, drawBorder: false },
                ticks: {
                    color: chartTheme.tickColor,
                    font: { family: chartTheme.fontFamily, size: 10 },
                    maxTicksLimit: 8,
                    maxRotation: 0,
                },
            },
            y: {
                grid: { color: chartTheme.gridColor, drawBorder: false },
                ticks: {
                    color: chartTheme.tickColor,
                    font: { family: "'JetBrains Mono', monospace", size: 10 },
                },
                beginAtZero: true,
            },
        },
        elements: {
            point: { radius: 0, hoverRadius: 4 },
            line: { tension: 0.35, borderWidth: 2 },
        },
    };

    const chartConfigs = [
        {
            id: 'chart-voltage',
            label: 'Voltage (V)',
            borderColor: '#60a5fa',
            bgColor: 'rgba(96, 165, 250, 0.08)',
            yLabel: 'V',
        },
        {
            id: 'chart-current',
            label: 'Current (A)',
            borderColor: '#22d3ee',
            bgColor: 'rgba(34, 211, 238, 0.08)',
            yLabel: 'A',
        },
        {
            id: 'chart-power',
            label: 'Power (W)',
            borderColor: '#fbbf24',
            bgColor: 'rgba(251, 191, 36, 0.08)',
            yLabel: 'W',
        },
        {
            id: 'chart-energy',
            label: 'Energy (Wh)',
            borderColor: '#34d399',
            bgColor: 'rgba(52, 211, 153, 0.08)',
            yLabel: 'Wh',
        },
    ];

    chartConfigs.forEach(cfg => {
        const canvas = document.getElementById(cfg.id);
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        // Create gradient fill
        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, cfg.bgColor);
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

        state.charts[cfg.id] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: cfg.label,
                    data: [],
                    borderColor: cfg.borderColor,
                    backgroundColor: gradient,
                    fill: true,
                    pointBackgroundColor: cfg.borderColor,
                }],
            },
            options: {
                ...defaultOptions,
                scales: {
                    ...defaultOptions.scales,
                    y: {
                        ...defaultOptions.scales.y,
                        title: {
                            display: true,
                            text: cfg.yLabel,
                            color: chartTheme.tickColor,
                            font: { family: chartTheme.fontFamily, size: 11 },
                        },
                    },
                },
            },
        });
    });
}

function updateCharts(data) {
    if (state.chartsPaused) return;

    const time = data.last_update
        ? new Date(data.last_update).toLocaleTimeString('en-US', {
              hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
          })
        : new Date().toLocaleTimeString('en-US', {
              hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
          });

    const chartData = {
        'chart-voltage': data.voltage,
        'chart-current': data.current,
        'chart-power':   data.power,
        'chart-energy':  data.daily_energy,
    };

    Object.entries(chartData).forEach(([chartId, value]) => {
        const chart = state.charts[chartId];
        if (!chart) return;

        chart.data.labels.push(time);
        chart.data.datasets[0].data.push(value);

        // Trim to max points
        if (chart.data.labels.length > CONFIG.charts.maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }

        chart.update('none'); // No animation for performance
    });

    // Update chart header live values
    const chartValues = {
        'chart-voltage-value': `${data.voltage.toFixed(1)} V`,
        'chart-current-value': `${data.current.toFixed(3)} A`,
        'chart-power-value':   `${data.power.toFixed(2)} W`,
        'chart-energy-value':  `${data.daily_energy.toFixed(2)} Wh`,
    };

    Object.entries(chartValues).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    });
}


// ============================================================
//  CHART CONTROLS — Pause/Resume, Export CSV, Export PNG
// ============================================================
function toggleChartUpdates() {
    state.chartsPaused = !state.chartsPaused;
    const btn = document.getElementById('btn-toggle-charts');
    if (btn) {
        btn.innerHTML = state.chartsPaused ? '▶ Resume Updates' : '⏸ Pause Updates';
        btn.classList.toggle('paused', state.chartsPaused);
    }
    showToast(state.chartsPaused ? 'Chart updates paused' : 'Chart updates resumed', 'info');
}

function exportCSV() {
    window.location.href = CONFIG.api.exportCSV;
    showToast('Downloading CSV data...', 'info');
}

function exportChartPNG() {
    // Export the power chart as PNG (most informative)
    const chart = state.charts['chart-power'];
    if (!chart) {
        showToast('No chart data to export', 'warning');
        return;
    }

    // Create a temporary link to download
    const link = document.createElement('a');
    link.download = `solar_power_chart_${new Date().toISOString().slice(0,10)}.png`;
    link.href = chart.toBase64Image();
    link.click();
    showToast('Chart PNG exported', 'success');
}


// ============================================================
//  SOLAR TRACKING
// ============================================================
async function fetchTrackingStatus() {
    const data = await fetchJSON(CONFIG.api.tracking);
    if (!data) return;

    // Update display values
    setText('tracking-mode-display', data.mode === 'auto' ? 'Automatic' : 'Manual');
    setText('tracking-solar-time', data.solar_time_formatted || '—');
    setText('tracking-hour-angle', `${data.hour_angle}°`);
    setText('tracking-servo-angle-display', `${data.servo_angle}°`);

    // Update servo gauge
    updateServoGauge(data.servo_angle);

    // Update mode toggle
    const autoBtn = document.getElementById('mode-auto-btn');
    const manualBtn = document.getElementById('mode-manual-btn');
    if (autoBtn && manualBtn) {
        autoBtn.classList.toggle('active', data.mode === 'auto');
        manualBtn.classList.toggle('active', data.mode === 'manual');
    }

    // Update tracking status badge — use tracking_status_text from backend
    const badge = document.getElementById('tracking-status-badge');
    if (badge) {
        const statusText = data.tracking_status_text || 'Unknown';

        if (data.tracking_active && data.within_window) {
            badge.className = 'tracking-badge active';
            badge.innerHTML = `<span class="metric-status"></span> ${statusText}`;
        } else if (data.mode === 'auto' && !data.within_window) {
            badge.className = 'tracking-badge outside-hours';
            badge.innerHTML = `🌙 ${statusText}`;
        } else if (data.mode === 'manual') {
            badge.className = 'tracking-badge manual';
            badge.innerHTML = `🎛️ ${statusText}`;
        } else {
            badge.className = 'tracking-badge disabled';
            badge.innerHTML = `⏸ ${statusText}`;
        }
    }

    // Update slider position (only if user isn't actively dragging)
    const slider = document.getElementById('servo-slider');
    if (slider && !slider.matches(':active')) {
        slider.value = data.servo_angle;
    }

    // Update schedule display
    setText('tracking-schedule', `${data.start_time} — ${data.end_time}`);
    setText('tracking-interval-display', `Every ${data.interval_minutes} min`);
}

function updateServoGauge(angle) {
    const needle = document.getElementById('servo-gauge-needle');
    if (needle) {
        // Map 0°–180° to -90°–+90° rotation
        const rotation = angle - 90;
        needle.style.transform = `translateX(-50%) rotate(${rotation}deg)`;
    }

    const angleDisplay = document.getElementById('servo-angle-main');
    if (angleDisplay) {
        angleDisplay.textContent = `${angle.toFixed(1)}°`;
    }
}

function initServoControls() {
    // Servo slider
    const slider = document.getElementById('servo-slider');
    if (slider) {
        slider.addEventListener('input', (e) => {
            const angle = parseFloat(e.target.value);
            updateServoGauge(angle);
            setText('servo-slider-value', `${angle}°`);
        });

        slider.addEventListener('change', (e) => {
            const angle = parseFloat(e.target.value);
            sendServoAngle(angle);
        });
    }
}

async function sendServoAngle(angle) {
    const data = await fetchJSON(CONFIG.api.manualServo, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ angle }),
    });
    if (data) {
        showToast(`Servo moved to ${angle.toFixed(1)}°`, 'info');
    }
}

async function sendServoAction(action) {
    const data = await fetchJSON(CONFIG.api.manualServo, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
    });
    if (data) {
        showToast(`Servo: ${action}`, 'info');
        fetchTrackingStatus();
    }
}

async function setTrackingMode(mode) {
    const data = await fetchJSON(CONFIG.api.tracking, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
    });
    if (data) {
        showToast(`Mode: ${mode === 'auto' ? 'Automatic' : 'Manual'}`, 'success');
        fetchTrackingStatus();
    }
}

function initTrackingControls() {
    // Load current settings
    fetchJSON(CONFIG.api.trackingSettings).then(data => {
        if (!data) return;
        const startInput = document.getElementById('config-start-time');
        const endInput = document.getElementById('config-end-time');
        const intervalInput = document.getElementById('config-interval');
        if (startInput) startInput.value = data.start_time;
        if (endInput) endInput.value = data.end_time;
        if (intervalInput) intervalInput.value = data.interval_minutes;
    });
}

async function saveTrackingSettings() {
    const startTime = document.getElementById('config-start-time')?.value;
    const endTime = document.getElementById('config-end-time')?.value;
    const interval = parseInt(document.getElementById('config-interval')?.value || '1');

    const data = await fetchJSON(CONFIG.api.trackingSettings, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start_time: startTime,
            end_time: endTime,
            interval: interval,
        }),
    });

    if (data) {
        showToast('Tracking settings saved', 'success');
    }
}


// ============================================================
//  AI STATUS
// ============================================================
async function fetchAIStatus() {
    const data = await fetchJSON(CONFIG.api.aiStatus);
    if (!data) return;

    setText('ai-model-file', data.model_file || '—');
    setText('ai-inference-script', data.inference_script || '—');
    setText('ai-model-type', data.model_type || 'CNN');

    const statusEl = document.getElementById('ai-status-text');
    if (statusEl) {
        if (data.available) {
            statusEl.innerHTML = '<span class="metric-status"></span> Online';
            statusEl.className = 'ai-status-value ai-online';
        } else {
            statusEl.innerHTML = '❌ Offline';
            statusEl.className = 'ai-status-value ai-offline';
        }
    }
}


// ============================================================
//  CAMERA & AI DUST DETECTION (CNN Integration)
// ============================================================
function initCameraControls() {
    // nothing extra needed — buttons call functions directly via onclick
}

async function captureImage() {
    if (state.isCapturing) return;
    state.isCapturing = true;

    const btn = document.getElementById('btn-capture');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Capturing...';
    }

    showToast('Capturing image...', 'info');

    const data = await fetchJSON(CONFIG.api.capture, { method: 'POST' });

    if (data && data.success) {
        // Update preview image with cache-busting
        const img = document.getElementById('camera-image');
        const placeholder = document.getElementById('camera-placeholder');
        if (img) {
            img.src = `/static/images/latest.jpg?t=${Date.now()}`;
            img.style.display = 'block';
        }
        if (placeholder) {
            placeholder.style.display = 'none';
        }

        // Update camera metadata
        const metaEl = document.getElementById('camera-metadata');
        if (metaEl) {
            metaEl.style.display = 'flex';
            setText('camera-meta-filename', `📁 ${data.filename || 'latest.jpg'}`);
            const captureTime = data.timestamp ? new Date(data.timestamp) : new Date();
            setText('camera-meta-timestamp', `🕐 ${captureTime.toLocaleTimeString('en-US', {
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
            })}`);
            setText('camera-meta-resolution', `📐 ${data.resolution || 'Unknown'}`);
        }

        showToast('Image captured successfully', 'success');
    } else {
        showToast(data?.message || 'Capture failed', 'error');
    }

    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '📸 Capture Image';
    }
    state.isCapturing = false;
}

async function analyzeDust() {
    if (state.isAnalyzing) return;
    state.isAnalyzing = true;

    const btn = document.getElementById('btn-analyze');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Running CNN inference...';
    }

    // Show loading state in prediction area
    const predEl = document.getElementById('prediction-value');
    if (predEl) {
        predEl.textContent = '...';
        predEl.className = 'prediction-value loading';
    }
    setText('confidence-text', 'Processing...');
    setText('recommendation-text', 'Running CNN inference on captured image...');

    showToast('Running CNN inference...', 'info');

    const data = await fetchJSON(CONFIG.api.analyze, { method: 'POST' });

    if (data && data.success) {
        displayPrediction(data);
        showToast(`Result: ${data.prediction} (${data.confidence_pct})`, 'success');
    } else {
        showToast(data?.message || 'Analysis failed', 'error');
        clearPrediction();
    }

    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '🤖 Analyze Dust';
    }
    state.isAnalyzing = false;
}

function displayPrediction(data) {
    const isDusty = data.prediction?.toLowerCase() === 'dusty';

    // Prediction value
    const predEl = document.getElementById('prediction-value');
    if (predEl) {
        predEl.textContent = data.prediction?.toUpperCase() || '—';
        predEl.className = `prediction-value ${isDusty ? 'dusty' : 'clean'}`;
    }

    // Prediction card styling
    const card = document.getElementById('prediction-result-card');
    if (card) {
        card.className = `prediction-result ${isDusty ? 'dusty' : 'clean'}`;
    }

    // Confidence bar
    const bar = document.getElementById('confidence-bar');
    if (bar) {
        const pct = (data.confidence * 100).toFixed(1);
        bar.style.width = `${pct}%`;
        bar.className = `confidence-bar-fill ${isDusty ? 'dusty' : ''}`;
    }

    // Confidence text
    const confText = document.getElementById('confidence-text');
    if (confText) {
        confText.textContent = data.confidence_pct || '0.0%';
    }

    // Recommendation
    const recEl = document.getElementById('recommendation-text');
    if (recEl) {
        recEl.textContent = data.recommendation || '—';
    }

    // Timestamp
    const tsEl = document.getElementById('analysis-timestamp');
    if (tsEl && data.timestamp) {
        const t = new Date(data.timestamp);
        tsEl.textContent = `Analyzed: ${t.toLocaleString()}`;
    }
}

function clearPrediction() {
    setText('prediction-value', '—');
    setText('confidence-text', '—');
    setText('recommendation-text', 'Capture and analyze an image to see results');
    setText('analysis-timestamp', '');
    const bar = document.getElementById('confidence-bar');
    if (bar) bar.style.width = '0%';
}


// ============================================================
//  SYSTEM HEALTH
// ============================================================
async function fetchSystemStatus() {
    const data = await fetchJSON(CONFIG.api.systemStatus);
    if (!data) return;

    // Update simulation banner from system status
    if (data.simulation_active !== undefined) {
        updateSimulationBanner(data.simulation_active);
    }

    const components = ['esp32', 'uart', 'raspberry_pi', 'camera', 'ai_model', 'dashboard'];

    components.forEach(key => {
        const comp = data[key];
        if (!comp) return;

        const indicator = document.getElementById(`health-${key}-indicator`);
        const statusText = document.getElementById(`health-${key}-status`);
        const detailText = document.getElementById(`health-${key}-detail`);

        if (indicator) {
            indicator.className = `health-indicator ${comp.status}`;
        }
        if (statusText) {
            statusText.textContent = comp.status.toUpperCase();
            statusText.className = `health-status-text ${comp.status}`;
        }
        if (detailText) {
            detailText.textContent = comp.detail;
        }
    });

    // Update header system status badge
    const allOnline = components.every(key => data[key]?.status === 'online');
    const badge = document.getElementById('system-status-badge');
    if (badge) {
        badge.className = `system-status-badge ${allOnline ? 'online' : 'offline'}`;
        badge.innerHTML = allOnline
            ? '<span class="metric-status"></span> System Online'
            : '⚠ Partial Offline';
    }
}


// ============================================================
//  TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${icons[type] || 'ℹ️'}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Auto-dismiss after 4s
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}


// ============================================================
//  UTILITY
// ============================================================
function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}
