// static/js/dashboard-common.js
// ฟังก์ชันร่วมที่ใช้ทั้ง Admin และ User Dashboard

const DashboardCommon = {
    // ตรวจสอบและตั้งค่า Authentication
    initAuth() {
        const accessCsrf = localStorage.getItem("access_csrf");
        if (!accessCsrf) {
            console.warn("No CSRF token found, redirecting to login");
            window.location.href = '/login';
            return false;
        }

        axios.defaults.withCredentials = true;
        axios.defaults.headers.common['X-CSRF-TOKEN'] = accessCsrf;
        return true;
    },

    // ดึงข้อมูล User Role
    getUserRole() {
        return localStorage.getItem("is_admin") === "true";
    },

    // จัดการ Authentication Error
    async handleAuthError(err, retryCallback) {
        if (err.response && err.response.status === 401) {
            console.warn("Token expired, attempting refresh...");
            const refreshed = await window.refreshToken();

            if (refreshed) {
                const newCsrf = localStorage.getItem("access_csrf");
                axios.defaults.headers.common['X-CSRF-TOKEN'] = newCsrf;
                
                if (retryCallback) {
                    retryCallback();
                }
                return true;
            } else {
                localStorage.clear();
                window.location.href = '/login';
                return false;
            }
        }
        return false;
    },

    // สร้าง Navbar
    renderNavbar(isAdmin) {
        const navLinks = document.getElementById("nav-links");
        navLinks.innerHTML = `
            <li class="nav-item"><a class="nav-link active" href="#">Dashboard</a></li>
            ${isAdmin ? `<li class="nav-item"><a class="nav-link" href="/sqlmap_urls">SQLMap URLs</a></li>` : ""}
            <li class="nav-item"><a class="nav-link" href="/sqlmap_basic">SQLMap Basic Scanner</a></li>
        `;
    },

    // Format วันที่
    formatDate(dateString) {
        return new Date(dateString).toLocaleString('th-TH');
    },

    // สร้าง Badge สถานะ
    statusBadge(isSuccess) {
        return isSuccess 
            ? '<span class="badge badge-success">✅ Success</span>' 
            : '<span class="badge badge-danger">❌ Failed</span>';
    },

    // สร้างปุ่ม PDF Download
    pdfButton(processId, hasPdf) {
        if (hasPdf) {
            return `<a href="/api/processes/${processId}/pdf" class="btn btn-sm btn-primary" target="_blank">📄 ดาวน์โหลด</a>`;
        }
        return '-';
    },

    // โหลดข้อมูลจาก API
    async fetchData(endpoint, onSuccess, onError) {
        try {
            const res = await axios.get(endpoint);
            if (onSuccess) onSuccess(res.data);
            return res.data;
        } catch (err) {
            console.error(`Error fetching data from ${endpoint}:`, err);
            if (onError) {
                await onError(err);
            }
            throw err;
        }
    },

    // ตั้งค่า Auto Refresh
    setupAutoRefresh(callbacks, intervalMs = 60000) {
        callbacks.forEach(callback => callback());
        return setInterval(() => {
            callbacks.forEach(callback => callback());
        }, intervalMs);
    }
};

// Export สำหรับใช้ใน HTML
window.DashboardCommon = DashboardCommon;