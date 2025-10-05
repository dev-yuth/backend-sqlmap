// ==============================
// Dashboard Authentication & API Utilities
// ==============================

// ------------------------------
// Check Authentication
// ------------------------------
function checkAuth() {
    const accessCsrf = localStorage.getItem('access_csrf');
    
    if (!accessCsrf) {
        console.warn('No CSRF token found, redirecting to login');
        localStorage.clear();
        window.location.href = '/login';
        return false;
    }
    
    return true;
}

// ------------------------------
// Fetch with Authentication (CSRF + Cookies)
// ------------------------------
async function fetchWithAuth(url, options = {}) {
    const accessCsrf = localStorage.getItem('access_csrf');
    
    if (!accessCsrf) {
        localStorage.clear();
        window.location.href = '/login';
        throw new Error('No CSRF token');
    }
    
    const fetchOptions = {
        ...options,
        credentials: 'include', // ✅ ส่ง cookies
        headers: {
            'X-CSRF-TOKEN': accessCsrf, // ✅ ส่ง CSRF token
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...options.headers
        }
    };
    
    const response = await fetch(url, fetchOptions);
    
    // ถ้า 401 = token หมดอายุ -> ลอง refresh
    if (response.status === 401) {
        console.warn('Access token expired, attempting refresh...');
        const refreshed = await refreshToken();
        
        if (refreshed) {
            // ลองเรียก API อีกครั้งด้วย token ใหม่
            const newCsrf = localStorage.getItem('access_csrf');
            fetchOptions.headers['X-CSRF-TOKEN'] = newCsrf;
            return await fetch(url, fetchOptions);
        } else {
            // refresh ไม่สำเร็จ -> logout
            localStorage.clear();
            window.location.href = '/login';
            throw new Error('Session expired');
        }
    }
    
    // ถ้า 422 = CSRF token ไม่ถูกต้อง
    if (response.status === 422) {
        console.error('CSRF token mismatch');
        localStorage.clear();
        window.location.href = '/login';
        throw new Error('CSRF token invalid');
    }
    
    return response;
}

// ------------------------------
// Refresh Access Token (ใช้ refresh_csrf จาก localStorage)
// ------------------------------
async function refreshToken() {
    const refreshCsrf = localStorage.getItem('refresh_csrf');
    
    if (!refreshCsrf) {
        console.warn('No refresh CSRF token');
        return false;
    }
    
    try {
        const res = await fetch('/api/auth/refresh', {
            method: 'POST',
            credentials: 'include', // ✅ ส่ง refresh token จาก cookies
            headers: {
                'X-CSRF-TOKEN': refreshCsrf, // ✅ ส่ง refresh CSRF token
                'Content-Type': 'application/json'
            }
        });
        
        if (res.ok) {
            const data = await res.json();
            // ✅ อัพเดท access_csrf ใหม่
            localStorage.setItem('access_csrf', data.access_csrf);
            console.log('Token refreshed successfully');
            return true;
        } else {
            console.error('Token refresh failed');
            return false;
        }
    } catch (err) {
        console.error('Error refreshing token:', err);
        return false;
    }
}

// ✅ Refresh token ทุก 10 นาที (access token default หมดอายุ 15 นาที)
setInterval(refreshToken, 10 * 60 * 1000);

// ------------------------------
// Load Dashboard Info
// ------------------------------
async function loadDashboard() {
    if (!checkAuth()) return;
    
    try {
        const res = await fetchWithAuth('/api/user/me');
        
        if (!res.ok) {
            throw new Error('Failed to load user data');
        }
        
        const data = await res.json();
        
        // อัพเดท localStorage
        localStorage.setItem('user_id', data.id);
        localStorage.setItem('username', data.username);
        localStorage.setItem('is_admin', data.is_admin);
        
        // แสดงชื่อผู้ใช้
        const welcomeEl = document.getElementById('welcome');
        if (welcomeEl) {
            welcomeEl.textContent = 'Welcome, ' + data.username;
        }
        
        const userDisplay = document.getElementById('user-display');
        if (userDisplay) {
            userDisplay.textContent = data.username;
        }
        
        console.log('Dashboard loaded for:', data.username);
    } catch (err) {
        console.error('Error loading dashboard:', err);
        localStorage.clear();
        window.location.href = '/login';
    }
}

// ------------------------------
// Logout Function
// ------------------------------
async function logout() {
    const accessCsrf = localStorage.getItem('access_csrf');
    
    try {
        if (accessCsrf) {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'X-CSRF-TOKEN': accessCsrf,
                    'Content-Type': 'application/json'
                }
            });
        }
    } catch (err) {
        console.error('Logout error:', err);
    } finally {
        // ไม่ว่าจะสำเร็จหรือไม่ ให้ clear และ redirect
        localStorage.clear();
        window.location.href = '/login';
    }
}

// ------------------------------
// Initialize on Page Load
// ------------------------------
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    
    // Attach logout button if exists
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        console.log('Logout button found, attaching event...');
        logoutBtn.addEventListener('click', logout);
    }
});

// ✅ Export สำหรับใช้ในไฟล์อื่น
if (typeof window !== 'undefined') {
    window.checkAuth = checkAuth;
    window.fetchWithAuth = fetchWithAuth;
    window.refreshToken = refreshToken;
    window.logout = logout;
    window.loadDashboard = loadDashboard;
}