class OptimizedCCTVManager {
    constructor() {
        this.cameras = [];
        this.recordingStates = {};
        this.statusUpdateInterval = null;
        this.motionCheckInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.startOptimizedUpdates();
        this.updateSystemStatus(true);
    }

    setupEventListeners() {
        // Optimize update intervals
        this.statusUpdateInterval = setInterval(() => {
            this.loadCameraStatus();
        }, 10000); // Every 10 seconds instead of 30

        this.motionCheckInterval = setInterval(() => {
            this.checkMotionAlerts();
        }, 2000); // Every 2 seconds instead of 5
    }

    async loadCameraStatus() {
        try {
            const response = await fetch('/api/camera_status', {
                cache: 'no-cache'
            });
            const status = await response.json();
            this.updateStatusDisplay(status);
            this.updateSystemStatus(true);
        } catch (error) {
            console.error('Status load error:', error);
            this.updateSystemStatus(false);
        }
    }

    updateStatusDisplay(status) {
        const statusPanel = document.getElementById('statusPanel');
        if (!statusPanel) return;

        // Clear only if needed
        if (statusPanel.children.length !== Object.keys(status).length) {
            statusPanel.innerHTML = '';
        }

        Object.entries(status).forEach(([camera, info], index) => {
            let statusCard = statusPanel.children[index];
            
            if (!statusCard) {
                statusCard = document.createElement('div');
                statusCard.className = 'col-md-3 mb-3';
                statusPanel.appendChild(statusCard);
            }

            const isOnline = info.status === 'online';
            statusCard.innerHTML = `
                <div class="status-card">
                    <div class="status-icon">
                        <i class="fas fa-${isOnline ? 'check-circle text-success' : 'times-circle text-danger'}"></i>
                    </div>
                    <h6>${camera.charAt(0).toUpperCase() + camera.slice(1)}</h6>
                    <small class="text-muted">${isOnline ? 'Online' : 'Offline'}</small>
                </div>
            `;

            // Update status badge efficiently
            const statusBadge = document.getElementById(`status-${camera}`);
            if (statusBadge) {
                statusBadge.textContent = isOnline ? 'Online' : 'Offline';
                statusBadge.className = `badge ${isOnline ? 'bg-success' : 'bg-danger'} ms-2`;
            }
        });
    }

    updateSystemStatus(isOnline) {
        const systemStatus = document.getElementById('systemStatus');
        if (systemStatus) {
            systemStatus.innerHTML = isOnline 
                ? '<i class="fas fa-circle text-success pulse"></i> System Online'
                : '<i class="fas fa-circle text-danger pulse"></i> System Error';
        }
    }

    async checkMotionAlerts() {
        try {
            const response = await fetch('/api/motion_alerts');
            const alerts = await response.json();
            
            Object.entries(alerts).forEach(([camera, alert]) => {
                const motionIndicator = document.getElementById(`motion-${camera}`);
                if (motionIndicator) {
                    motionIndicator.style.display = 'block';
                    // Auto-hide after 2 seconds
                    setTimeout(() => {
                        motionIndicator.style.display = 'none';
                    }, 2000);
                }
            });
        } catch (error) {
            // Fail silently for performance
        }
    }

    async toggleRecording(camera) {
        const action = this.recordingStates[camera] ? 'stop' : 'start';
        try {
            const response = await fetch(`/api/recording/${camera}/${action}`, {
                method: 'POST'
            });
            const result = await response.json();
            
            this.recordingStates[camera] = result.recording;
            const recIndicator = document.getElementById(`rec-${camera}`);
            if (recIndicator) {
                recIndicator.style.display = result.recording ? 'block' : 'none';
            }

            this.showToast('success', `Recording ${result.recording ? 'started' : 'stopped'} for ${camera}`);
        } catch (error) {
            this.showToast('error', 'Recording control failed');
        }
    }

    refreshCamera(camera) {
        const img = document.querySelector(`#camera-${camera} .camera-feed`);
        if (img) {
            // Simple refresh without delay
            img.src = `/video_feed/${camera}?t=${Date.now()}`;
        }
    }

    fullscreenCamera(camera) {
        const cameraCard = document.getElementById(`camera-${camera}`);
        if (cameraCard) {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                cameraCard.requestFullscreen();
            }
        }
    }

    async showRecordings() {
        try {
            const response = await fetch('/api/recordings');
            const recordings = await response.json();
            
            const recordingsList = document.getElementById('recordingsList');
            recordingsList.innerHTML = recordings.length === 0 
                ? '<p class="text-center text-muted">No recordings available.</p>'
                : this.generateRecordingsTable(recordings);

            const modal = new bootstrap.Modal(document.getElementById('recordingsModal'));
            modal.show();
        } catch (error) {
            this.showToast('error', 'Failed to load recordings');
        }
    }

    generateRecordingsTable(recordings) {
        return `
            <table class="table table-dark table-striped">
                <thead>
                    <tr>
                        <th>Filename</th>
                        <th>Size</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    ${recordings.map(rec => `
                        <tr>
                            <td>${rec.filename}</td>
                            <td>${this.formatFileSize(rec.size)}</td>
                            <td>${new Date(rec.created).toLocaleString()}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    showToast(type, message) {
        const toastElement = document.getElementById(type === 'error' ? 'errorToast' : 'successToast');
        const toastBody = document.getElementById(type === 'error' ? 'errorToastBody' : 'successToastBody');
        
        if (toastElement && toastBody) {
            toastBody.textContent = message;
            const toast = new bootstrap.Toast(toastElement);
            toast.show();
        }
    }

    startOptimizedUpdates() {
        // Load status immediately
        this.loadCameraStatus();
    }

    destroy() {
        if (this.statusUpdateInterval) {
            clearInterval(this.statusUpdateInterval);
        }
        if (this.motionCheckInterval) {
            clearInterval(this.motionCheckInterval);
        }
    }
}

// Initialize manager
const cctvManager = new OptimizedCCTVManager();

// Optimized global functions
function toggleRecording(camera) {
    cctvManager.toggleRecording(camera);
}

function refreshCamera(camera) {
    cctvManager.refreshCamera(camera);
}

function fullscreenCamera(camera) {
    cctvManager.fullscreenCamera(camera);
}

function showRecordings() {
    cctvManager.showRecordings();
}

function toggleFullscreen() {
    if (document.fullscreenElement) {
        document.exitFullscreen();
    } else {
        document.documentElement.requestFullscreen();
    }
}

function refreshAllCameras() {
    document.querySelectorAll('.camera-feed').forEach(img => {
        const camera = img.alt.split(' ')[0];
        img.src = `/video_feed/${camera}?t=${Date.now()}`;
    });
}

function toggleAllRecording() {
    document.querySelectorAll('[id^="camera-"]').forEach(card => {
        const camera = card.id.replace('camera-', '');
        cctvManager.toggleRecording(camera);
    });
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    cctvManager.destroy();
});
