// API Config
const API_BASE = window.location.origin;

// State Management
const state = {
    token: localStorage.getItem('token') || null,
    user: JSON.parse(localStorage.getItem('user')) || null,
    calls: [],
    currentPage: 1,
    limit: 10,
    filters: {
        search: '',
        startDate: '',
        endDate: ''
    },
    activeCall: {
        session_id: null,
        timerInterval: null,
        startTime: null
    }
};

// Toast Notifications Helper
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'info';
    if (type === 'success') icon = 'check-circle-2';
    if (type === 'error') icon = 'alert-octagon';
    
    toast.innerHTML = `
        <i data-lucide="${icon}"></i>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    lucide.createIcons();
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s reverse forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Inline Validation Helpers
function showInputError(inputId, errorMsg) {
    const input = document.getElementById(inputId);
    const errorSpan = document.getElementById(`${inputId}-error`);
    if (input) input.classList.add('error');
    if (errorSpan) {
        errorSpan.textContent = errorMsg;
        errorSpan.style.opacity = '1';
    }
}

function clearInputError(inputId) {
    const input = document.getElementById(inputId);
    const errorSpan = document.getElementById(`${inputId}-error`);
    if (input) input.classList.remove('error');
    if (errorSpan) {
        errorSpan.textContent = '';
        errorSpan.style.opacity = '0';
    }
}

// Form Validation logic
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(String(email).toLowerCase());
}

// Dynamic routing / Navigation between panels
function checkAuth() {
    const authScreen = document.getElementById('auth-screen');
    const mainApp = document.getElementById('main-app');
    
    if (state.token) {
        authScreen.classList.add('hidden');
        mainApp.classList.remove('hidden');
        
        // Update user display details
        const displayName = state.user?.display_name || 'Manager';
        document.getElementById('sidebar-username').textContent = displayName;
        document.getElementById('user-avatar-placeholder').textContent = displayName.charAt(0).toUpperCase();
        
        // Load stats & sessions
        loadDashboardData();
    } else {
        authScreen.classList.remove('hidden');
        mainApp.classList.add('hidden');
        showCard('signin-card');
    }
}

function showCard(cardId) {
    document.querySelectorAll('.auth-card').forEach(card => card.classList.add('hidden'));
    const target = document.getElementById(cardId);
    if (target) {
        target.classList.remove('hidden');
        target.classList.add('animate-fade-in');
    }
}

// -------------------------------------------------------------
// AUTH OPERATIONS
// -------------------------------------------------------------

// SIGN IN
document.getElementById('signin-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('signin-email').value.trim();
    const password = document.getElementById('signin-password').value;
    
    let valid = true;
    if (!email) {
        showInputError('signin-email', 'Email is required');
        valid = false;
    } else if (!validateEmail(email)) {
        showInputError('signin-email', 'Invalid email format');
        valid = false;
    } else {
        clearInputError('signin-email');
    }

    if (!password) {
        showInputError('signin-password', 'Password is required');
        valid = false;
    } else {
        clearInputError('signin-password');
    }

    if (!valid) return;

    try {
        const response = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await response.json();
        
        if (response.ok) {
            state.token = data.access_token;
            state.user = data.user;
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('user', JSON.stringify(data.user));
            showToast('Sign in successful!', 'success');
            checkAuth();
        } else {
            showInputError('signin-password', data.detail || 'Invalid email or password');
        }
    } catch (err) {
        showToast('Server connection failed.', 'error');
    }
});

// SIGN UP (Details submission)
document.getElementById('signup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('signup-name').value.trim();
    const email = document.getElementById('signup-email').value.trim();
    const password = document.getElementById('signup-password').value;

    let valid = true;
    if (!name) {
        showInputError('signup-name', 'Display name is required');
        valid = false;
    } else {
        clearInputError('signup-name');
    }

    if (!email) {
        showInputError('signup-email', 'Email is required');
        valid = false;
    } else if (!validateEmail(email)) {
        showInputError('signup-email', 'Invalid email format');
        valid = false;
    } else {
        clearInputError('signup-email');
    }

    if (!password) {
        showInputError('signup-password', 'Password is required');
        valid = false;
    } else if (password.length < 6) {
        showInputError('signup-password', 'Password must be at least 6 characters');
        valid = false;
    } else {
        clearInputError('signup-password');
    }

    if (!valid) return;

    try {
        const response = await fetch(`${API_BASE}/api/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, display_name: name })
        });
        const data = await response.json();

        if (response.ok) {
            showToast('Verification code sent to your email!', 'success');
            document.getElementById('signup-sent-email').textContent = email;
            // Preset the OTP code in the verify input for testing convenience
            if (data.otp_code) {
                document.getElementById('signup-otp').value = data.otp_code;
                showToast(`[Test Mode] Auto-filled OTP code: ${data.otp_code}`, 'info');
            }
            // Transition to OTP verification step
            document.querySelector('#signup-card .signup-step:not(.hidden)').classList.add('hidden');
            document.getElementById('signup-otp-form').classList.remove('hidden');
        } else {
            showInputError('signup-email', data.detail || 'Signup failed.');
        }
    } catch (err) {
        showToast('Server connection failed.', 'error');
    }
});

// SIGN UP (OTP Verification)
document.getElementById('signup-otp-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('signup-email').value.trim();
    const otp = document.getElementById('signup-otp').value.trim();

    if (!otp || otp.length !== 6) {
        showInputError('signup-otp', 'Enter 6-digit OTP code');
        return;
    }
    clearInputError('signup-otp');

    try {
        const response = await fetch(`${API_BASE}/api/auth/verify-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, otp })
        });
        const data = await response.json();

        if (response.ok) {
            showToast('Account activated! You can now sign in.', 'success');
            showCard('signin-card');
        } else {
            showInputError('signup-otp', data.detail || 'Invalid or expired OTP');
        }
    } catch (err) {
        showToast('Server connection failed.', 'error');
    }
});

// FORGOT PASSWORD (OTP Request)
document.getElementById('forgot-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('forgot-email').value.trim();

    if (!email || !validateEmail(email)) {
        showInputError('forgot-email', 'Valid email is required');
        return;
    }
    clearInputError('forgot-email');

    try {
        const response = await fetch(`${API_BASE}/api/auth/forgot-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await response.json();

        if (response.ok) {
            showToast('If email matches, reset OTP has been sent!', 'success');
            // Preset the OTP code in input for testing convenience
            if (data.otp_code) {
                document.getElementById('forgot-otp').value = data.otp_code;
                showToast(`[Test Mode] Auto-filled OTP code: ${data.otp_code}`, 'info');
            }
            // Transition to password reset step
            document.querySelector('#forgot-card .forgot-step:not(.hidden)').classList.add('hidden');
            document.getElementById('forgot-reset-form').classList.remove('hidden');
        } else {
            showToast('Failed to trigger password recovery.', 'error');
        }
    } catch (err) {
        showToast('Server connection failed.', 'error');
    }
});

// FORGOT PASSWORD (OTP & New Password Submission)
document.getElementById('forgot-reset-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('forgot-email').value.trim();
    const otp = document.getElementById('forgot-otp').value.trim();
    const newPassword = document.getElementById('forgot-new-password').value;

    let valid = true;
    if (!otp || otp.length !== 6) {
        showInputError('forgot-otp', 'Enter 6-digit OTP code');
        valid = false;
    } else {
        clearInputError('forgot-otp');
    }

    if (!newPassword || newPassword.length < 6) {
        showInputError('forgot-new-password', 'New password must be at least 6 characters');
        valid = false;
    } else {
        clearInputError('forgot-new-password');
    }

    if (!valid) return;

    try {
        const response = await fetch(`${API_BASE}/api/auth/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, otp, new_password: newPassword })
        });
        const data = await response.json();

        if (response.ok) {
            showToast('Password reset successfully! Log in to continue.', 'success');
            showCard('signin-card');
        } else {
            showInputError('forgot-otp', data.detail || 'Reset failed. Verify details.');
        }
    } catch (err) {
        showToast('Server connection failed.', 'error');
    }
});

// Auth Screen Transitions Navigation
document.getElementById('goto-signup').addEventListener('click', () => showCard('signup-card'));
document.getElementById('goto-forgot').addEventListener('click', () => showCard('forgot-card'));
document.getElementById('goto-signin-from-signup').addEventListener('click', () => showCard('signin-card'));
document.getElementById('goto-signin-from-forgot').addEventListener('click', () => showCard('signin-card'));

document.getElementById('back-to-signup-details').addEventListener('click', () => {
    document.getElementById('signup-otp-form').classList.add('hidden');
    document.getElementById('signup-form').classList.remove('hidden');
});

document.getElementById('back-to-forgot-email').addEventListener('click', () => {
    document.getElementById('forgot-reset-form').classList.add('hidden');
    document.getElementById('forgot-form').classList.remove('hidden');
});

// LOGOUT
document.getElementById('logout-btn').addEventListener('click', () => {
    state.token = null;
    state.user = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    showToast('Signed out successfully.', 'info');
    checkAuth();
});

// -------------------------------------------------------------
// DASHBOARD & CALLS LOGS
// -------------------------------------------------------------

async function loadDashboardData() {
    try {
        const response = await fetch(`${API_BASE}/api/calls?page=1&limit=50`, {
            headers: { 'Authorization': `Bearer ${state.token}` }
        });
        if (response.status === 401) {
            // Token expired
            state.token = null;
            localStorage.removeItem('token');
            checkAuth();
            return;
        }
        const data = await response.json();
        if (response.ok) {
            state.calls = data.calls || [];
            updateStats();
            renderCallsTable();
        }
    } catch (err) {
        showToast('Failed to fetch dashboard call sessions.', 'error');
    }
}

function updateStats() {
    const totalCalls = state.calls.length;
    const driftCalls = state.calls.filter(c => c.drift_detected).length;
    
    let totalRevenue = 0;
    state.calls.forEach(c => {
        try {
            const summary = typeof c.order_summary === 'string' ? JSON.parse(c.order_summary) : c.order_summary;
            if (summary && summary.total) {
                totalRevenue += summary.total;
            }
        } catch(e) {}
    });

    document.getElementById('stat-total-calls').textContent = totalCalls;
    document.getElementById('stat-drift-calls').textContent = driftCalls;
    document.getElementById('stat-total-orders').textContent = `$${totalRevenue.toFixed(2)}`;
}

function renderCallsTable() {
    const tbody = document.getElementById('session-table-body');
    tbody.innerHTML = '';

    // Filter calls based on search input and date ranges
    const filtered = state.calls.filter(call => {
        // Search filter
        const query = state.filters.search.toLowerCase();
        const matchesCaller = call.caller_id.toLowerCase().includes(query);
        const matchesId = call.id.toLowerCase().includes(query);
        
        let matchesItems = false;
        try {
            const summary = typeof call.order_summary === 'string' ? JSON.parse(call.order_summary) : call.order_summary;
            if (summary && summary.items) {
                matchesItems = summary.items.some(item => item.name.toLowerCase().includes(query));
            }
        } catch(e){}

        const matchesSearch = matchesCaller || matchesId || matchesItems;

        // Date filter
        let matchesDate = true;
        const callDate = new Date(call.started_at);
        
        if (state.filters.startDate) {
            const start = new Date(state.filters.startDate);
            start.setHours(0,0,0,0);
            matchesDate = matchesDate && (callDate >= start);
        }
        if (state.filters.endDate) {
            const end = new Date(state.filters.endDate);
            end.setHours(23,59,59,999);
            matchesDate = matchesDate && (callDate <= end);
        }

        return matchesSearch && matchesDate;
    });

    // Pagination slice
    const startIndex = (state.currentPage - 1) * state.limit;
    const paginated = filtered.slice(startIndex, startIndex + state.limit);

    // Update pagination controls
    const totalCount = filtered.length;
    document.getElementById('pagination-info').textContent = `Showing ${Math.min(startIndex + 1, totalCount)} to ${Math.min(startIndex + state.limit, totalCount)} of ${totalCount} sessions`;
    
    document.getElementById('prev-page-btn').disabled = state.currentPage === 1;
    document.getElementById('next-page-btn').disabled = startIndex + state.limit >= totalCount;

    if (paginated.length === 0) {
        tbody.innerHTML = `
            <tr class="state-row">
                <td colspan="5">
                    <div class="empty-state">
                        <i data-lucide="phone-off"></i>
                        <span>No call sessions matched the filters.</span>
                    </div>
                </td>
            </tr>
        `;
        lucide.createIcons();
        return;
    }

    paginated.forEach(call => {
        const row = document.createElement('tr');
        row.setAttribute('data-id', call.id);
        
        // Parse dates
        const dateObj = new Date(call.started_at);
        const dateStr = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
        const timeStr = dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        
        // Calculate duration
        let durationStr = '--';
        if (call.ended_at) {
            const diffMs = new Date(call.ended_at) - dateObj;
            const diffSecs = Math.max(0, Math.floor(diffMs / 1000));
            const mins = Math.floor(diffSecs / 60);
            const secs = diffSecs % 60;
            durationStr = `${mins}m ${secs}s`;
        }

        // Parse order summary
        let orderDesc = 'Empty Order';
        let orderTotal = 0;
        try {
            const summary = typeof call.order_summary === 'string' ? JSON.parse(call.order_summary) : call.order_summary;
            if (summary && summary.items && summary.items.length > 0) {
                orderDesc = summary.items.map(i => `${i.name} (x${i.quantity})`).join(', ');
                orderTotal = summary.total || 0;
            }
        } catch(e){}

        // Drift status badge
        const driftBadge = call.drift_detected 
            ? `<span class="badge danger"><i data-lucide="alert-triangle"></i> Drifted</span>`
            : `<span class="badge success"><i data-lucide="check"></i> Re-anchored</span>`;

        row.innerHTML = `
            <td>
                <div class="caller-cell-wrapper">
                    <i data-lucide="phone" class="caller-icon"></i>
                    <span>${call.caller_id}</span>
                </div>
            </td>
            <td>
                <div class="date-cell-wrapper">
                    <span>${dateStr}</span>
                    <span class="date-sub">${timeStr}</span>
                </div>
            </td>
            <td>${durationStr}</td>
            <td>${driftBadge}</td>
            <td>
                <div class="date-cell-wrapper">
                    <span class="order-items-badge" title="${orderDesc}">${orderDesc}</span>
                    <span class="order-val">$${orderTotal.toFixed(2)}</span>
                </div>
            </td>
        `;

        row.addEventListener('click', () => {
            document.querySelectorAll('#session-table tr').forEach(r => r.classList.remove('selected'));
            row.classList.add('selected');
            openSessionDetails(call.id);
        });

        tbody.appendChild(row);
    });

    lucide.createIcons();
}

// -------------------------------------------------------------
// DETAIL PREVIEW TABULAR PANEL
// -------------------------------------------------------------

async function openSessionDetails(sessionId) {
    try {
        const response = await fetch(`${API_BASE}/api/calls/${sessionId}`, {
            headers: { 'Authorization': `Bearer ${state.token}` }
        });
        const call = await response.json();
        
        if (response.ok) {
            document.getElementById('detail-empty-state').classList.add('hidden');
            document.getElementById('detail-content-wrapper').classList.remove('hidden');

            document.getElementById('detail-caller-id').textContent = call.caller_id;
            
            // Format dates
            const dateObj = new Date(call.started_at);
            const fullDateStr = `${dateObj.toLocaleDateString()} - ${dateObj.toLocaleTimeString()}`;
            document.getElementById('detail-date').textContent = fullDateStr;

            // Duration
            let durationStr = '--';
            if (call.ended_at) {
                const diffMs = new Date(call.ended_at) - dateObj;
                const diffSecs = Math.max(0, Math.floor(diffMs / 1000));
                const mins = Math.floor(diffSecs / 60);
                const secs = diffSecs % 60;
                durationStr = `${mins}m ${secs}s`;
            }
            document.getElementById('detail-duration').textContent = durationStr;

            // Drift Status
            const driftBadge = document.getElementById('detail-drift-badge');
            if (call.drift_detected) {
                driftBadge.textContent = 'Drift Detected';
                driftBadge.className = 'badge danger';
            } else {
                driftBadge.textContent = 'Re-anchored';
                driftBadge.className = 'badge success';
            }

            // Transcript Feed
            const transcriptFeed = document.getElementById('transcript-feed');
            transcriptFeed.innerHTML = '';
            
            let history = [];
            try {
                history = typeof call.transcript === 'string' ? JSON.parse(call.transcript) : call.transcript;
            } catch(e){}

            if (!history || history.length === 0) {
                transcriptFeed.innerHTML = `<p class="loading-state">No transcript records available.</p>`;
            } else {
                history.forEach(turn => {
                    const bubbleWrapper = document.createElement('div');
                    // Map "agent" to "assistant" to use the correct CSS styling class
                    const speakerClass = (turn.speaker === 'agent' || turn.speaker === 'assistant') ? 'assistant' : turn.speaker;
                    bubbleWrapper.className = `chat-bubble-wrapper ${speakerClass}`;
                    
                    const time = turn.timestamp ? new Date(turn.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}) : '';
                    const roleLabel = (turn.speaker === 'agent' || turn.speaker === 'assistant') ? 'ASSISTANT' : turn.speaker.toUpperCase();

                    bubbleWrapper.innerHTML = `
                        <div class="bubble-meta">
                            <span>${roleLabel}</span>
                            <span>${time}</span>
                        </div>
                        <div class="chat-bubble">
                            ${turn.text}
                        </div>
                    `;
                    transcriptFeed.appendChild(bubbleWrapper);
                });
            }

            // Order items rows
            const itemsTbody = document.getElementById('order-items-tbody');
            itemsTbody.innerHTML = '';
            
            let summary = { items: [], total: 0.0 };
            try {
                summary = typeof call.order_summary === 'string' ? JSON.parse(call.order_summary) : call.order_summary;
            } catch(e){}

            const items = summary?.items || [];
            if (items.length === 0) {
                itemsTbody.innerHTML = `<tr><td colspan="4" class="text-center" style="color: var(--text-secondary); text-align: center; padding: 20px;">No items ordered.</td></tr>`;
            } else {
                items.forEach(item => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${item.name}</td>
                        <td>${item.quantity}</td>
                        <td>$${item.price.toFixed(2)}</td>
                        <td>$${(item.quantity * item.price).toFixed(2)}</td>
                    `;
                    itemsTbody.appendChild(row);
                });
            }
            document.getElementById('order-total-amount').textContent = `$${(summary?.total || 0).toFixed(2)}`;
        }
    } catch(err) {
        showToast('Error loading session details.', 'error');
    }
}

// Tab Switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        btn.classList.add('active');
        const tabId = btn.getAttribute('data-tab');
        document.getElementById(tabId).classList.add('active');
    });
});

// Filters & Search event bindings
document.getElementById('global-search').addEventListener('input', (e) => {
    state.filters.search = e.target.value;
    state.currentPage = 1;
    renderCallsTable();
});

document.getElementById('filter-start-date').addEventListener('change', (e) => {
    state.filters.startDate = e.target.value;
    state.currentPage = 1;
    renderCallsTable();
});

document.getElementById('filter-end-date').addEventListener('change', (e) => {
    state.filters.endDate = e.target.value;
    state.currentPage = 1;
    renderCallsTable();
});

document.getElementById('clear-filters-btn').addEventListener('click', () => {
    document.getElementById('filter-start-date').value = '';
    document.getElementById('filter-end-date').value = '';
    state.filters.startDate = '';
    state.filters.endDate = '';
    state.currentPage = 1;
    renderCallsTable();
});

// Pagination
document.getElementById('prev-page-btn').addEventListener('click', () => {
    if (state.currentPage > 1) {
        state.currentPage--;
        renderCallsTable();
    }
});

document.getElementById('next-page-btn').addEventListener('click', () => {
    state.currentPage++;
    renderCallsTable();
});

// -------------------------------------------------------------
// LIVE SIMULATOR MANAGEMENT
// -------------------------------------------------------------

const startSimBtn = document.getElementById('start-sim-call-btn');
const endSimBtn = document.getElementById('end-sim-call-btn');

startSimBtn.addEventListener('click', async () => {
    const callerId = document.getElementById('sim-caller-id').value.trim() || "+15550199";
    
    startSimBtn.disabled = true;
    startSimBtn.innerHTML = `
        <div class="spinner" style="width: 16px; height: 16px;"></div>
        <span>Connecting...</span>
    `;

    try {
        const response = await fetch(`${API_BASE}/webhook/call/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caller_id: callerId })
        });
        const data = await response.json();
        
        if (response.ok) {
            state.activeCall.session_id = data.session_id;
            state.activeCall.startTime = new Date();
            
            showToast('Voice session successfully activated!', 'success');
            
            // Switch simulator screen to active recording state
            document.getElementById('mic-ready-state').classList.add('hidden');
            document.getElementById('mic-active-state').classList.remove('hidden');
            document.getElementById('active-session-id-display').textContent = data.session_id.substring(0, 8) + '...';
            document.getElementById('live-indicator-badge').classList.remove('hidden');
            
            // Start local timer ticking
            state.activeCall.timerInterval = setInterval(updateCallTimer, 1000);
            
            // Update active drift indicator styling dynamically
            document.getElementById('live-drift-indicator').className = "live-stat-badge";
            document.getElementById('live-drift-indicator').innerHTML = `
                <i data-lucide="shield-check"></i>
                <span>Normal Session</span>
            `;
            lucide.createIcons();
            
        } else {
            showToast('Failed to start call session.', 'error');
        }
    } catch(err) {
        showToast('Connection error starting session.', 'error');
    } finally {
        startSimBtn.disabled = false;
        startSimBtn.innerHTML = `
            <i data-lucide="phone"></i>
            <span>Start Local Call Session</span>
        `;
        lucide.createIcons();
    }
});

endSimBtn.addEventListener('click', async () => {
    const sessionId = state.activeCall.session_id;
    if (!sessionId) return;

    endSimBtn.disabled = true;
    endSimBtn.innerHTML = `
        <div class="spinner" style="width: 16px; height: 16px;"></div>
        <span>Finalizing Order...</span>
    `;

    try {
        const response = await fetch(`${API_BASE}/webhook/call/end`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        
        if (response.ok) {
            showToast('Voice session finalized. Data saved to SQLite!', 'success');
            
            // Clear timer
            clearInterval(state.activeCall.timerInterval);
            state.activeCall.timerInterval = null;
            state.activeCall.session_id = null;
            
            // Switch simulator screen back to ready state
            document.getElementById('mic-ready-state').classList.remove('hidden');
            document.getElementById('mic-active-state').classList.add('hidden');
            document.getElementById('live-indicator-badge').classList.add('hidden');

            // Refresh logs list and select the newly created call
            await loadDashboardData();
            openSessionDetails(sessionId);
        } else {
            showToast('Failed to end call session cleanly.', 'error');
        }
    } catch(err) {
        showToast('Connection error ending session.', 'error');
    } finally {
        endSimBtn.disabled = false;
        endSimBtn.innerHTML = `
            <i data-lucide="phone-off"></i>
            <span>Hang Up &amp; Finalize Order</span>
        `;
        lucide.createIcons();
    }
});

function updateCallTimer() {
    const diff = new Date() - state.activeCall.startTime;
    const totalSecs = Math.floor(diff / 1000);
    const mins = String(Math.floor(totalSecs / 60)).padStart(2, '0');
    const secs = String(totalSecs % 60).padStart(2, '0');
    document.getElementById('active-session-timer').textContent = `${mins}:${secs}`;
    
    // Periodically inspect active drift state in background for active session badge
    if (totalSecs % 4 === 0) {
        checkActiveDriftStatus(state.activeCall.session_id);
    }
}

async function checkActiveDriftStatus(sessionId) {
    if (!sessionId) return;
    try {
        const response = await fetch(`${API_BASE}/api/calls/${sessionId}`, {
            headers: { 'Authorization': `Bearer ${state.token}` }
        });
        if (response.ok) {
            const data = await response.json();
            const driftIndicator = document.getElementById('live-drift-indicator');
            if (data.drift_detected) {
                driftIndicator.className = "live-stat-badge warning";
                driftIndicator.innerHTML = `
                    <i data-lucide="alert-triangle" style="color: var(--warning-color)"></i>
                    <span style="color: var(--warning-color)">Drift Corrected</span>
                `;
            } else {
                driftIndicator.className = "live-stat-badge";
                driftIndicator.innerHTML = `
                    <i data-lucide="shield-check" style="color: var(--success-color)"></i>
                    <span style="color: var(--success-color)">Re-anchored</span>
                `;
            }
            lucide.createIcons();
        }
    } catch(e){}
}

// -------------------------------------------------------------
// APP INITIALIZATION
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    checkAuth();
    
    // Inline validation listener binders
    const signinEmail = document.getElementById('signin-email');
    if (signinEmail) {
        signinEmail.addEventListener('input', () => {
            if (signinEmail.value.trim() && validateEmail(signinEmail.value.trim())) {
                clearInputError('signin-email');
            }
        });
    }

    const signupEmail = document.getElementById('signup-email');
    if (signupEmail) {
        signupEmail.addEventListener('input', () => {
            if (signupEmail.value.trim() && validateEmail(signupEmail.value.trim())) {
                clearInputError('signup-email');
            }
        });
    }

    const signupPassword = document.getElementById('signup-password');
    if (signupPassword) {
        signupPassword.addEventListener('input', () => {
            if (signupPassword.value.length >= 6) {
                clearInputError('signup-password');
            }
        });
    }
});
