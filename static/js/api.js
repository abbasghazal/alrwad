// ملف إدارة طلبات الـ API وحفظ الجلسات
const API_BASE_URL = "/api";

const API = {
    // جلب التوكين المحفوظ من التخزين المحلي
    getToken() {
        return localStorage.getItem("alrwad_token");
    },

    getRefreshToken() {
        return localStorage.getItem("alrwad_refresh_token");
    },

    // حفظ التوكين في التخزين المحلي
    setToken(token) {
        localStorage.setItem("alrwad_token", token);
    },

    setRefreshToken(token) {
        if (token) localStorage.setItem("alrwad_refresh_token", token);
    },

    setSession(accessToken, refreshToken) {
        this.setToken(accessToken);
        this.setRefreshToken(refreshToken);
    },

    // مسح التوكين لتسجيل الخروج
    clearToken() {
        localStorage.removeItem("alrwad_token");
        localStorage.removeItem("alrwad_refresh_token");
    },

    isTokenExpired() {
        const token = this.getToken();
        if (!token) return false;
        try {
            const payload = JSON.parse(atob(token.split(".")[1]));
            return payload.exp && Date.now() >= payload.exp * 1000;
        } catch (e) {
            return true;
        }
    },

    async refreshAccessToken() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) return false;
        try {
            const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.access_token) return false;
            this.setSession(data.access_token, data.refresh_token || refreshToken);
            return true;
        } catch (e) {
            return false;
        }
    },

    // إظهار وإخفاء مؤشر التحميل العام
    showLoader() {
        const loader = document.getElementById("loading-overlay");
        if (loader) loader.classList.remove("hidden");
    },

    hideLoader() {
        const loader = document.getElementById("loading-overlay");
        if (loader) loader.classList.add("hidden");
    },

    // الطلب الأساسي الموحد لجميع طلبات الـ HTTP
    async request(endpoint, options = {}) {
        this.showLoader();

        if (this.isTokenExpired() && !["/auth/login", "/auth/refresh"].includes(endpoint)) {
            const refreshed = await this.refreshAccessToken();
            if (!refreshed) {
                this.clearToken();
                window.location.hash = "#/login";
                showToast("انتهت الجلسة", "انتهت صلاحية الجلسة، يرجى تسجيل الدخول مجدداً", "warning");
                this.hideLoader();
                throw new Error("انتهت صلاحية الجلسة");
            }
        }
        
        const token = this.getToken();
        const headers = options.headers || {};

        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }

        // إعداد الطلب وتحديد نوع المحتوى إذا كان JSON
        const isFormData = options.body instanceof FormData;
        if (!isFormData && !headers["Content-Type"]) {
            headers["Content-Type"] = "application/json";
        }

        const config = {
            ...options,
            headers
        };

        // تحويل الجسم البرمجي لـ JSON إذا لم يكن FormData
        if (options.body && !isFormData && typeof options.body === "object") {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                // معالجة انتهاء صلاحية الجلسة أو عدم الصلاحية
                if (response.status === 401 && !["/auth/login", "/auth/refresh"].includes(endpoint)) {
                    const refreshed = await this.refreshAccessToken();
                    if (refreshed) return this.request(endpoint, options);
                    this.clearToken();
                    window.location.hash = "#/login";
                    showToast("انتهت الجلسة", "انتهت صلاحية الجلسة، يرجى تسجيل الدخول مجدداً", "warning");
                }
                throw new Error(data.detail || "تعذر تنفيذ الطلب حالياً");
            }

            return data;
        } catch (error) {
            console.error("API Request Error:", error);
            throw error;
        } finally {
            this.hideLoader();
        }
    },

    // طرق الاختصار السريعة (HTTP Methods)
    get(endpoint) {
        return this.request(endpoint, { method: "GET" });
    },

    getPage(endpoint, page = 1, perPage = 10) {
        const separator = endpoint.includes("?") ? "&" : "?";
        return this.request(`${endpoint}${separator}page=${page}&per_page=${perPage}`, { method: "GET" });
    },

    post(endpoint, body) {
        return this.request(endpoint, { method: "POST", body });
    },

    put(endpoint, body) {
        return this.request(endpoint, { method: "PUT", body });
    },

    patch(endpoint, body) {
        return this.request(endpoint, { method: "PATCH", body });
    },

    delete(endpoint) {
        return this.request(endpoint, { method: "DELETE" });
    },

    // طلب خاص برفع الملفات أو النماذج المعقدة
    postForm(endpoint, formData) {
        return this.request(endpoint, {
            method: "POST",
            body: formData,
            headers: {} // يترك فارغاً ليقوم المتصفح بتوليد Boundary لـ FormData تلقائياً
        });
    }
};

// دالة عامة لإظهار التنبيهات العائمة
function showToast(title, message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    let icon = "fa-info-circle";
    if (type === "success") icon = "fa-check-circle";
    if (type === "danger") icon = "fa-exclamation-circle";
    if (type === "warning") icon = "fa-exclamation-triangle";

    toast.innerHTML = `
        <span class="toast-icon"><i class="fa-solid ${icon}"></i></span>
        <div class="toast-content">
            <h4>${title}</h4>
            <p>${message}</p>
        </div>
        <button class="toast-close">&times;</button>
    `;

    // زر الإغلاق
    toast.querySelector(".toast-close").addEventListener("click", () => {
        toast.style.animation = "slideOutLeft 0.3s forwards";
        setTimeout(() => toast.remove(), 300);
    });

    container.appendChild(toast);

    // الحذف التلقائي بعد 4 ثوانٍ
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = "slideOutLeft 0.3s forwards";
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}
