// ------------------------------
// Refresh Access Token
// ------------------------------
async function refreshToken() {
    const refresh_token = localStorage.getItem('refresh_token');
    if (!refresh_token) {
        return window.location.href = '/login';
    }

    const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + refresh_token }
    });

    if (res.ok) {
        const data = await res.json();
        localStorage.setItem('access_token', data.access_token);
    } else {
        localStorage.clear();
        window.location.href = '/login';
    }
}

// ต่ออายุ token ทุก 5 นาที
setInterval(refreshToken, 5 * 60 * 1000);

// ------------------------------
// Load Dashboard Info
// ------------------------------
async function loadDashboard() {
    const token = localStorage.getItem('access_token');
    if (!token) return window.location.href = '/login';

    const res = await fetch('/api/user/me', {
        headers: { 'Authorization': 'Bearer ' + token }
    });

    if (!res.ok) {
        localStorage.clear();
        return window.location.href = '/login';
    }

    const data = await res.json();
    const welcomeEl = document.getElementById('welcome');
    if (welcomeEl) {
        welcomeEl.innerText = 'Welcome, ' + data.username;
    }
}

// ------------------------------
// Logout Function (แชร์ให้ logout.js ใช้)
// ------------------------------
async function logout() {
    const token = localStorage.getItem('access_token');
    if (token) {
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
    }
    localStorage.clear();
    window.location.href = '/login';
}

// ให้เรียก loadDashboard() ตั้งแต่เริ่ม
loadDashboard();
