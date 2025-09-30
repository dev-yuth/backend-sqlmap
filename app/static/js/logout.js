// ------------------------------
// Attach Logout Button Event
// ------------------------------
document.addEventListener('DOMContentLoaded', () => {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        console.log("Logout button found, attaching event...");
        logoutBtn.addEventListener('click', logout); // ใช้ฟังก์ชันจาก dashboard.js
    } else {
        console.log("Logout button NOT found!");
    }
});
