// =======================================================================
// الملف الرئيسي للتطبيق - أكاديمية الرواد التعليمية
// يتم فيه تعريف صفحات الـ SPA وربطها بالموجه (Router)
// =======================================================================

// ========== متغيرات الجلسة العامة ==========
let currentUser = null;

const IRAQI_SECONDARY_GRADES = [
    "الأول متوسط",
    "الثاني متوسط",
    "الثالث متوسط",
    "الرابع العلمي",
    "الرابع الأدبي",
    "الخامس العلمي",
    "الخامس الأدبي",
    "السادس العلمي",
    "السادس الأدبي"
];

// ========== دوال مساعدة عامة ==========

/**
 * تعقيم النصوص لمنع ثغرات XSS
 * يجب استخدامها على أي بيانات قادمة من المستخدم أو الـ API قبل إدخالها في HTML
 */
function escapeHTML(str) {
    if (str === null || str === undefined) return "";
    const text = String(str);
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

/** تحديث شريط التنقل حسب حالة المستخدم */
function updateNavbar() {
    const navLinks = document.getElementById("nav-links");
    if (!navLinks) return;

    // تفريغ القائمة وبناءها بـ DOM API بدل innerHTML
    navLinks.textContent = "";

    // دالة مساعدة لإنشاء رابط تنقل
    function addNavItem(href, iconClass, label, extraClasses, guestOnly) {
        const li = document.createElement("li");
        if (guestOnly) li.className = "guest-only";
        const a = document.createElement("a");
        a.href = href;
        a.className = "nav-link" + (extraClasses ? " " + extraClasses : "");
        const icon = document.createElement("i");
        icon.className = iconClass;
        a.appendChild(icon);
        a.appendChild(document.createTextNode(" " + label));
        li.appendChild(a);
        navLinks.appendChild(li);
        return a;
    }

    // روابط أساسية دائمة
    addNavItem("#/", "fa-solid fa-house", "الرئيسية");

    if (currentUser) {
        addNavItem("#/subjects-browse", "fa-solid fa-book-open", "استعراض المواد");

        if (currentUser.role === "student") {
            addNavItem("#/my-subjects", "fa-solid fa-graduation-cap", "موادي");
            addNavItem("#/my-submissions", "fa-solid fa-file-arrow-up", "تسليماتي");
        }

        if (currentUser.role === "teacher") {
            addNavItem("#/my-subject", "fa-solid fa-chalkboard-teacher", "مادتي");
        }

        if (currentUser.role === "owner") {
            addNavItem("#/admin", "fa-solid fa-shield-halved", "لوحة التحكم");
        }

        addNavItem("#/notifications", "fa-solid fa-bell", "التنبيهات");
        addNavItem("#/profile", "fa-solid fa-user-circle", escapeHTML(currentUser.first_name));

        const logoutLink = addNavItem("#", "fa-solid fa-right-from-bracket", "خروج", "btn-login");
        logoutLink.id = "logout-btn";
        logoutLink.addEventListener("click", async (e) => {
            e.preventDefault();
            const refreshToken = API.getRefreshToken();
            if (refreshToken) {
                try {
                    await API.post("/auth/logout", { refresh_token: refreshToken });
                } catch (err) {
                    /* session may already be expired */
                }
            }
            API.clearToken();
            currentUser = null;
            updateNavbar();
            window.location.hash = "#/";
            showToast("تسجيل الخروج", "تم تسجيل خروجك بنجاح", "info");
        });
    } else {
        addNavItem("#/login", "fa-solid fa-right-to-bracket", "تسجيل الدخول", "btn-login", true);
        addNavItem("#/register", "fa-solid fa-user-plus", "حساب جديد", "btn-register", true);
        addNavItem("#/verify-email", "fa-solid fa-envelope-circle-check", "تفعيل البريد", "btn-secondary", true);
    }
}

/** جلب بيانات المستخدم الحالي إن كان مسجل دخوله */
async function loadCurrentUser() {
    const token = API.getToken();
    if (!token) {
        currentUser = null;
        updateNavbar();
        return;
    }
    try {
        currentUser = await API.get("/auth/me");
        updateNavbar();
    } catch (e) {
        currentUser = null;
        API.clearToken();
        updateNavbar();
    }
}

/** صفحة عامة: رسالة فارغة (بيانات ثابتة فقط، لا مدخلات مستخدم) */
function renderEmpty(title, message) {
    const container = document.createElement("div");
    container.className = "container";
    const card = document.createElement("div");
    card.className = "card form-card";
    card.style.cssText = "text-align:center;padding:60px 24px;";
    const h2 = document.createElement("h2");
    h2.style.cssText = "margin-bottom:12px;color:var(--primary-color);";
    h2.textContent = title;
    const p = document.createElement("p");
    p.style.color = "var(--text-secondary)";
    p.textContent = message;
    card.appendChild(h2);
    card.appendChild(p);
    container.appendChild(card);
    return container;
}

function requireRole(role) {
    if (!currentUser) {
        window.location.hash = "#/login";
        return false;
    }
    if (role && currentUser.role !== role) {
        showToast("غير مصرح", "لا تملك صلاحية فتح هذه الصفحة", "warning");
        window.location.hash = "#/";
        return false;
    }
    return true;
}

function formatDate(value) {
    if (!value) return "";
    return new Date(value).toLocaleString("ar");
}

function setPage(content, child) {
    content.textContent = "";
    content.appendChild(child);
}

function getItems(payload) {
    return Array.isArray(payload) ? payload : (payload && Array.isArray(payload.items) ? payload.items : []);
}

function getPageMeta(payload, page, perPage) {
    if (payload && !Array.isArray(payload) && Array.isArray(payload.items)) {
        return {
            page: payload.page || page,
            per_page: payload.per_page || perPage,
            total: payload.total || payload.items.length,
            total_pages: payload.total_pages || 1
        };
    }
    return { page, per_page: perPage, total: getItems(payload).length, total_pages: 1 };
}

function renderPagination(meta, onPageChange) {
    const wrap = document.createElement("div");
    wrap.className = "pagination-bar";

    const prev = makeButton("السابق", "fa-solid fa-chevron-right", "btn btn-sm btn-secondary", () => {
        if (meta.page > 1) onPageChange(meta.page - 1);
    });
    prev.disabled = meta.page <= 1;

    const label = document.createElement("span");
    label.className = "pagination-label";
    label.textContent = "الصفحة " + meta.page + " من " + meta.total_pages;

    const next = makeButton("التالي", "fa-solid fa-chevron-left", "btn btn-sm btn-secondary", () => {
        if (meta.page < meta.total_pages) onPageChange(meta.page + 1);
    });
    next.disabled = meta.page >= meta.total_pages;

    wrap.appendChild(prev);
    wrap.appendChild(label);
    wrap.appendChild(next);
    return wrap;
}

function confirmAction(itemName, actionLabel) {
    return window.confirm("هل أنت متأكد من " + actionLabel + "؟\nالعنصر: " + itemName);
}

function renderPageShell(title, iconClass) {
    const container = document.createElement("div");
    container.className = "container";

    const backBtn = makeButton("رجوع", "fa-solid fa-arrow-right", "btn btn-sm btn-secondary page-back-btn", () => {
        history.back();
    });
    container.appendChild(backBtn);

    const heading = document.createElement("h2");
    heading.style.cssText = "margin-bottom:24px;color:var(--primary-color);";
    heading.innerHTML = `<i class="${iconClass}"></i> `;
    heading.appendChild(document.createTextNode(title));
    container.appendChild(heading);

    return container;
}

function renderListItem(title, description, metaItems, actions) {
    const item = document.createElement("div");
    item.className = "homework-item";

    const details = document.createElement("div");
    details.className = "item-details";

    const h4 = document.createElement("h4");
    h4.textContent = title;
    details.appendChild(h4);

    if (description) {
        const p = document.createElement("p");
        p.style.cssText = "color:var(--text-secondary);font-size:14px;margin-bottom:8px;";
        p.textContent = description;
        details.appendChild(p);
    }

    const meta = document.createElement("div");
    meta.className = "item-meta";
    metaItems.filter(Boolean).forEach(text => {
        const span = document.createElement("span");
        span.textContent = text;
        meta.appendChild(span);
    });
    details.appendChild(meta);
    item.appendChild(details);

    const actionWrap = document.createElement("div");
    actionWrap.className = "item-actions";
    actions.filter(Boolean).forEach(action => actionWrap.appendChild(action));
    item.appendChild(actionWrap);

    return item;
}

function makeButton(label, iconClass, className, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = className || "btn btn-sm btn-secondary";
    btn.innerHTML = `<i class="${iconClass}"></i> `;
    btn.appendChild(document.createTextNode(label));
    if (onClick) btn.addEventListener("click", onClick);
    return btn;
}

function makeLinkButton(label, iconClass, href, className) {
    const link = document.createElement("a");
    link.className = className || "btn btn-sm btn-secondary";
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener";
    link.innerHTML = `<i class="${iconClass}"></i> `;
    link.appendChild(document.createTextNode(label));
    return link;
}


// ========== تعريف صفحات التطبيق ==========

// --- الصفحة الرئيسية ---
Router.add("/", async () => {
    const content = document.getElementById("main-content");
    // بيانات ثابتة بالكامل - لا خطر XSS هنا
    content.innerHTML = `
        <div class="welcome-hero">
            <h1>🎓 مرحباً بك في أكاديمية الرواد</h1>
            <p>منصة تعليمية رائدة تجمع الطلاب والمدرسين في مكان واحد. سجّل الآن وابدأ رحلة التعلم!</p>
            <div style="margin-top:32px; display:flex; justify-content:center; gap:16px; flex-wrap:wrap;">
                ${!currentUser ? `
                    <a href="#/register" class="btn btn-primary"><i class="fa-solid fa-user-plus"></i> إنشاء حساب</a>
                    <a href="#/login" class="btn btn-secondary"><i class="fa-solid fa-right-to-bracket"></i> تسجيل الدخول</a>
                ` : `
                    <a href="#/subjects-browse" class="btn btn-primary"><i class="fa-solid fa-book-open"></i> استعراض المواد</a>
                `}
            </div>
        </div>
    `;
});

// --- صفحة تسجيل الدخول ---
Router.add("/login", async () => {
    const content = document.getElementById("main-content");
    // بيانات ثابتة بالكامل - لا خطر XSS هنا
    content.innerHTML = `
        <div class="container">
            <div class="card form-card">
                <h2 class="form-title"><i class="fa-solid fa-right-to-bracket"></i> تسجيل الدخول</h2>
                <form id="login-form">
                    <div class="form-group">
                        <label class="form-label">اسم المستخدم أو البريد الإلكتروني</label>
                        <input type="text" class="form-input" id="login-username" required placeholder="أدخل اسم المستخدم أو بريدك">
                    </div>
                    <div class="form-group">
                        <label class="form-label">كلمة المرور</label>
                        <input type="password" class="form-input" id="login-password" required placeholder="أدخل كلمة المرور">
                    </div>
                    <div class="form-footer">
                        <a href="#/reset-password" style="color:var(--primary-light);font-size:14px;">نسيت كلمة المرور؟</a>
                        <button type="submit" class="btn btn-primary"><i class="fa-solid fa-sign-in-alt"></i> دخول</button>
                    </div>
                </form>
                <p style="text-align:center;margin-top:20px;color:var(--text-secondary);font-size:14px;">
                    ليس لديك حساب؟ <a href="#/register" style="color:var(--primary-light);font-weight:700;">سجّل الآن</a>
                    <br>
                    لديك كود تفعيل؟ <a href="#/verify-email" style="color:var(--primary-light);font-weight:700;">فعّل البريد</a>
                </p>
            </div>
        </div>
    `;

    document.getElementById("login-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("login-username").value.trim();
        const password = document.getElementById("login-password").value;
        try {
            const result = await API.post("/auth/login", { username, password });
            API.setSession(result.access_token, result.refresh_token);
            await loadCurrentUser();
            showToast("مرحباً!", "تم تسجيل الدخول بنجاح", "success");
            window.location.hash = "#/";
        } catch (err) {
            if (err.message.includes("تفعيل البريد")) {
                const emailGuess = username.includes("@") ? username : "";
                if (emailGuess) sessionStorage.setItem("pending_verification_email", emailGuess);
                showToast("يحتاج تفعيل", "أدخل كود التفعيل المرسل إلى بريدك ثم سجّل الدخول.", "warning");
                window.location.hash = "#/verify-email";
                return;
            }
            showToast("خطأ في الدخول", err.message, "danger");
        }
    });
});

// --- صفحة تفعيل البريد الإلكتروني ---
Router.add("/verify-email", async () => {
    const content = document.getElementById("main-content");
    const pendingEmail = sessionStorage.getItem("pending_verification_email") || "";
    content.innerHTML = `
        <div class="container">
            <div class="card form-card">
                <h2 class="form-title"><i class="fa-solid fa-envelope-circle-check"></i> تفعيل البريد الإلكتروني</h2>
                <form id="verify-email-form">
                    <div class="form-group">
                        <label class="form-label">البريد الإلكتروني</label>
                        <input type="email" class="form-input" id="verify-email-address" required value="${escapeHTML(pendingEmail)}" placeholder="أدخل البريد الذي سجلت به">
                    </div>
                    <div class="form-group">
                        <label class="form-label">كود التفعيل</label>
                        <input type="text" class="form-input" id="verify-email-code" required inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="أدخل الكود المرسل إلى بريدك">
                    </div>
                    <div class="form-footer">
                        <button type="button" class="btn btn-secondary" id="resend-code-btn"><i class="fa-solid fa-rotate-right"></i> إعادة إرسال الكود</button>
                        <button type="submit" class="btn btn-primary"><i class="fa-solid fa-check"></i> تفعيل</button>
                    </div>
                </form>
                <p style="text-align:center;margin-top:20px;color:var(--text-secondary);font-size:14px;">
                    بعد التفعيل يمكنك <a href="#/login" style="color:var(--primary-light);font-weight:700;">تسجيل الدخول</a> بكلمة المرور التي اخترتها.
                </p>
            </div>
        </div>
    `;

    document.getElementById("verify-email-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("verify-email-address").value.trim();
        const code = document.getElementById("verify-email-code").value.trim();
        try {
            await API.post("/auth/verify-email", { email, code });
            sessionStorage.removeItem("pending_verification_email");
            showToast("تم التفعيل", "تم تفعيل بريدك بنجاح. يمكنك تسجيل الدخول الآن.", "success");
            window.location.hash = "#/login";
        } catch (err) {
            showToast("خطأ في التفعيل", err.message, "danger");
        }
    });

    document.getElementById("resend-code-btn").addEventListener("click", async () => {
        const email = document.getElementById("verify-email-address").value.trim();
        if (!email) {
            showToast("تنبيه", "أدخل البريد الإلكتروني أولاً", "warning");
            return;
        }
        try {
            await API.post("/auth/resend-code", { email });
            sessionStorage.setItem("pending_verification_email", email);
            showToast("تم الإرسال", "تم إرسال كود جديد إلى بريدك.", "success");
        } catch (err) {
            showToast("تعذر الإرسال", err.message, "danger");
        }
    });
});

// --- صفحة التسجيل ---
Router.add("/register", async () => {
    const content = document.getElementById("main-content");
    let subjects = [];
    try { subjects = getItems(await API.getPage("/subjects", 1, 100)); } catch (e) { /* ignore */ }

    // بناء الهيكل الثابت للنموذج أولاً
    content.innerHTML = `
        <div class="container">
            <div class="card form-card">
                <h2 class="form-title"><i class="fa-solid fa-user-plus"></i> إنشاء حساب جديد</h2>
                <form id="register-form">
                    <div class="form-group">
                        <label class="form-label">نوع الحساب</label>
                        <select class="form-input" id="reg-role" required>
                            <option value="student">طالب</option>
                            <option value="teacher">مدرس</option>
                            <option value="tutor">مدرس خصوصي</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">الاسم الأول</label>
                        <input type="text" class="form-input" id="reg-first-name" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">الاسم الأخير</label>
                        <input type="text" class="form-input" id="reg-last-name" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-input" id="reg-username" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">البريد الإلكتروني</label>
                        <input type="email" class="form-input" id="reg-email" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">كلمة المرور</label>
                        <input type="password" class="form-input" id="reg-password" required minlength="8">
                    </div>

                    <!-- حقول الطالب -->
                    <div id="student-fields">
                        <div class="form-group">
                            <label class="form-label">الصف الدراسي</label>
                            <select class="form-input" id="reg-grade"></select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">الشعبة</label>
                            <select class="form-input" id="reg-section">
                                <option value="">بدون شعبة</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">المجموعة</label>
                            <select class="form-input" id="reg-group">
                                <option value="">بدون مجموعة</option>
                            </select>
                        </div>
                    </div>

                    <!-- حقول المدرس -->
                    <div id="teacher-fields" style="display:none;">
                        <div class="form-group">
                            <label class="form-label">المادة</label>
                            <select class="form-input" id="reg-subject"></select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">كود التسجيل</label>
                            <input type="text" class="form-input" id="reg-teacher-code" placeholder="كود التسجيل المقدم من الإدارة">
                        </div>
                    </div>

                    <!-- حقول المدرس الخصوصي -->
                    <div id="tutor-fields" style="display:none;">
                        <div class="form-group">
                            <label class="form-label">التخصص</label>
                            <input type="text" class="form-input" id="reg-specialty" placeholder="مثال: رياضيات">
                        </div>
                        <div class="form-group">
                            <label class="form-label">سعر الساعة</label>
                            <input type="number" class="form-input" id="reg-hourly-rate" step="0.5" placeholder="بالدينار">
                        </div>
                    </div>

                    <div class="form-footer">
                        <button type="submit" class="btn btn-primary"><i class="fa-solid fa-user-plus"></i> تسجيل</button>
                    </div>
                </form>
                <p style="text-align:center;margin-top:20px;color:var(--text-secondary);font-size:14px;">
                    لديك حساب؟ <a href="#/login" style="color:var(--primary-light);font-weight:700;">سجّل الدخول</a>
                </p>
            </div>
        </div>
    `;

    // ملء قائمة المواد بأمان عبر DOM API
    const subjectSelect = document.getElementById("reg-subject");
    subjects.forEach(s => {
        const option = document.createElement("option");
        option.value = s.id;
        option.textContent = s.name + " - " + s.grade_level;
        subjectSelect.appendChild(option);
    });

    const gradeSelect = document.getElementById("reg-grade");
    const sectionSelect = document.getElementById("reg-section");
    const groupSelect = document.getElementById("reg-group");
    IRAQI_SECONDARY_GRADES.forEach(grade => {
        const option = document.createElement("option");
        option.value = grade;
        option.textContent = grade;
        gradeSelect.appendChild(option);
    });

    async function loadRegisterSections() {
        sectionSelect.innerHTML = '<option value="">بدون شعبة</option>';
        groupSelect.innerHTML = '<option value="">بدون مجموعة</option>';
        try {
            const payload = await API.getPage("/admin/sections?grade_level=" + encodeURIComponent(gradeSelect.value), 1, 100);
            getItems(payload).forEach(section => {
                const option = document.createElement("option");
                option.value = section.id;
                option.textContent = section.name;
                sectionSelect.appendChild(option);
            });
        } catch (err) {
            showToast("تنبيه", "تعذر تحميل شعب هذا الصف حالياً", "warning");
        }
    }

    async function loadRegisterGroups() {
        groupSelect.innerHTML = '<option value="">بدون مجموعة</option>';
        if (!sectionSelect.value) return;
        try {
            const payload = await API.getPage("/admin/groups?section_id=" + encodeURIComponent(sectionSelect.value), 1, 100);
            getItems(payload).forEach(group => {
                const option = document.createElement("option");
                option.value = group.id;
                option.textContent = group.name;
                groupSelect.appendChild(option);
            });
        } catch (err) {
            showToast("تنبيه", "تعذر تحميل مجموعات هذه الشعبة حالياً", "warning");
        }
    }

    gradeSelect.addEventListener("change", loadRegisterSections);
    sectionSelect.addEventListener("change", loadRegisterGroups);
    await loadRegisterSections();

    // إظهار/إخفاء حقول حسب نوع الحساب
    document.getElementById("reg-role").addEventListener("change", (e) => {
        document.getElementById("student-fields").style.display = e.target.value === "student" ? "block" : "none";
        document.getElementById("teacher-fields").style.display = e.target.value === "teacher" ? "block" : "none";
        document.getElementById("tutor-fields").style.display = e.target.value === "tutor" ? "block" : "none";
    });

    document.getElementById("register-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const role = document.getElementById("reg-role").value;
        const body = {
            first_name: document.getElementById("reg-first-name").value.trim(),
            last_name: document.getElementById("reg-last-name").value.trim(),
            username: document.getElementById("reg-username").value.trim(),
            email: document.getElementById("reg-email").value.trim(),
            password: document.getElementById("reg-password").value,
            role
        };

        if (role === "student") {
            body.grade_level = gradeSelect.value;
            if (sectionSelect.value) body.section_id = parseInt(sectionSelect.value);
            if (groupSelect.value) body.group_id = parseInt(groupSelect.value);
        }
        if (role === "teacher") {
            body.subject_id = parseInt(document.getElementById("reg-subject").value);
            body.teacher_code = document.getElementById("reg-teacher-code").value.trim();
        }
        if (role === "tutor") {
            body.specialty = document.getElementById("reg-specialty").value.trim();
            body.hourly_rate = parseFloat(document.getElementById("reg-hourly-rate").value);
        }

        try {
            await API.post("/auth/register", body);
            sessionStorage.setItem("pending_verification_email", body.email);
            showToast("تم التسجيل!", "أرسلنا كود التفعيل إلى بريدك. أدخل الكود لتفعيل الحساب.", "success");
            window.location.hash = "#/verify-email";
        } catch (err) {
            showToast("خطأ في التسجيل", err.message, "danger");
        }
    });
});

// --- استعراض المواد ---
Router.add("/subjects-browse", async () => {
    await renderSubjectsBrowse(1);
});

async function renderSubjectsBrowse(page) {
    const content = document.getElementById("main-content");
    const perPage = 10;
    try {
        const payload = await API.getPage("/subjects", page, perPage);
        const subjects = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);

        // بناء الصفحة بـ DOM API بدلاً من innerHTML مع بيانات API
        const container = document.createElement("div");
        container.className = "container";

        const heading = document.createElement("h2");
        heading.style.cssText = "margin-bottom:24px;color:var(--primary-color);";
        heading.innerHTML = '<i class="fa-solid fa-book-open"></i> ';
        heading.appendChild(document.createTextNode("المواد الدراسية المتاحة"));
        container.appendChild(heading);

        const grid = document.createElement("div");
        grid.className = "subjects-grid";

        if (subjects.length === 0) {
            const emptyMsg = document.createElement("p");
            emptyMsg.style.color = "var(--text-secondary)";
            emptyMsg.textContent = "لا توجد مواد حالياً.";
            grid.appendChild(emptyMsg);
        } else {
            subjects.forEach(s => {
                const card = document.createElement("div");
                card.className = "card subject-card";

                const badge = document.createElement("span");
                badge.className = "subject-badge";
                badge.textContent = s.grade_level;
                card.appendChild(badge);

                const title = document.createElement("h3");
                title.className = "subject-title";
                title.textContent = s.name;
                card.appendChild(title);

                const desc = document.createElement("p");
                desc.className = "subject-desc";
                desc.textContent = s.description || "لا يوجد وصف";
                card.appendChild(desc);

                if (currentUser && currentUser.role === "student") {
                    const btnWrap = document.createElement("div");
                    btnWrap.style.cssText = "display:flex;gap:8px;";
                    const enrollBtn = document.createElement("button");
                    enrollBtn.className = "btn btn-primary btn-sm";
                    enrollBtn.innerHTML = '<i class="fa-solid fa-plus"></i> ';
                    enrollBtn.appendChild(document.createTextNode("تسجيل"));
                    enrollBtn.addEventListener("click", async () => {
                        try {
                            await API.post("/subjects/" + s.id + "/enroll");
                            showToast("تم التسجيل!", "تم تسجيلك في المادة بنجاح", "success");
                        } catch (err) {
                            showToast("تنبيه", err.message, "warning");
                        }
                    });
                    btnWrap.appendChild(enrollBtn);
                    card.appendChild(btnWrap);
                }

                grid.appendChild(card);
            });
        }

        container.appendChild(grid);
        container.appendChild(renderPagination(meta, renderSubjectsBrowse));
        content.textContent = "";
        content.appendChild(container);
    } catch (err) {
        content.textContent = "";
        content.appendChild(renderEmpty("خطأ", "تعذر تحميل المواد الدراسية."));
    }
}

// --- صفحة التنبيهات ---
Router.add("/notifications", async () => {
    await renderNotifications(1);
});

async function renderNotifications(page) {
    const content = document.getElementById("main-content");
    if (!currentUser) { window.location.hash = "#/login"; return; }
    const perPage = 10;

    try {
        const payload = await API.getPage("/users/notifications", page, perPage);
        const notifications = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);

        // بناء الصفحة بـ DOM API
        const container = document.createElement("div");
        container.className = "container";
        container.style.cssText = "max-width:800px;margin:0 auto;";

        const headerRow = document.createElement("div");
        headerRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;";

        const heading = document.createElement("h2");
        heading.style.color = "var(--primary-color)";
        heading.innerHTML = '<i class="fa-solid fa-bell"></i> ';
        heading.appendChild(document.createTextNode("التنبيهات"));
        headerRow.appendChild(heading);

        const markReadBtn = document.createElement("button");
        markReadBtn.className = "btn btn-sm btn-secondary";
        markReadBtn.id = "mark-read-btn";
        markReadBtn.innerHTML = '<i class="fa-solid fa-check-double"></i> ';
        markReadBtn.appendChild(document.createTextNode("تعليم الكل كمقروء"));
        markReadBtn.addEventListener("click", async () => {
            try {
                await API.post("/users/notifications/read");
                showToast("تم", "تم تعليم جميع التنبيهات كمقروءة", "success");
                Router.resolve();
            } catch (e) { /* ignore */ }
        });
        headerRow.appendChild(markReadBtn);
        container.appendChild(headerRow);

        if (notifications.length === 0) {
            const emptyMsg = document.createElement("p");
            emptyMsg.style.cssText = "color:var(--text-secondary);text-align:center;";
            emptyMsg.textContent = "لا توجد تنبيهات حالياً.";
            container.appendChild(emptyMsg);
        } else {
            notifications.forEach(n => {
                const card = document.createElement("div");
                card.className = "card";
                card.style.cssText = "border-right:4px solid " + (n.is_read ? "var(--border-color)" : "var(--primary-light)") + "; margin-bottom:12px;";

                const h4 = document.createElement("h4");
                h4.style.cssText = "font-size:16px;font-weight:700;";
                h4.textContent = n.title;
                card.appendChild(h4);

                const p = document.createElement("p");
                p.style.cssText = "color:var(--text-secondary);font-size:14px;margin-top:4px;";
                p.textContent = n.message;
                card.appendChild(p);

                const small = document.createElement("small");
                small.style.cssText = "color:var(--text-muted);font-size:12px;";
                small.textContent = new Date(n.created_at).toLocaleString("ar");
                card.appendChild(small);

                container.appendChild(card);
            });
            container.appendChild(renderPagination(meta, renderNotifications));
        }

        content.textContent = "";
        content.appendChild(container);
    } catch (e) {
        content.textContent = "";
        content.appendChild(renderEmpty("خطأ", "تعذر تحميل التنبيهات."));
    }
}

// --- مواد الطالب ---
Router.add("/my-subjects", async () => {
    await renderMySubjects(1);
});

async function renderMySubjects(page) {
    const content = document.getElementById("main-content");
    if (!requireRole("student")) return;
    const perPage = 10;

    try {
        const payload = await API.getPage("/subjects/my/enrolled", page, perPage);
        const subjects = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("موادي المسجلة", "fa-solid fa-graduation-cap");
        const grid = document.createElement("div");
        grid.className = "subjects-grid";

        if (subjects.length === 0) {
            grid.appendChild(renderEmpty("لا توجد مواد", "لم تسجل في أي مادة بعد."));
        } else {
            subjects.forEach(s => {
                const card = document.createElement("div");
                card.className = "card subject-card";

                const badge = document.createElement("span");
                badge.className = "subject-badge";
                badge.textContent = s.grade_level;
                card.appendChild(badge);

                const title = document.createElement("h3");
                title.className = "subject-title";
                title.textContent = s.name;
                card.appendChild(title);

                const desc = document.createElement("p");
                desc.className = "subject-desc";
                desc.textContent = s.description || "لا يوجد وصف";
                card.appendChild(desc);

                const actions = document.createElement("div");
                actions.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;";
                actions.appendChild(makeButton("المحاضرات", "fa-solid fa-video", "btn btn-sm btn-secondary", async () => {
                    await showSubjectLectures(s.id, s.name);
                }));
                actions.appendChild(makeButton("الواجبات", "fa-solid fa-clipboard-list", "btn btn-sm btn-primary", async () => {
                    await showSubjectHomeworks(s.id, s.name);
                }));
                actions.appendChild(makeButton("إلغاء التسجيل", "fa-solid fa-xmark", "btn btn-sm btn-danger", async () => {
                    if (!confirmAction(s.name, "إلغاء التسجيل")) return;
                    try {
                        await API.post("/subjects/" + s.id + "/unenroll");
                        showToast("تم", "تم إلغاء تسجيلك من المادة", "success");
                        renderMySubjects(page);
                    } catch (err) {
                        showToast("خطأ", err.message, "danger");
                    }
                }));
                card.appendChild(actions);
                grid.appendChild(card);
            });
        }

        container.appendChild(grid);
        container.appendChild(renderPagination(meta, renderMySubjects));
        setPage(content, container);
    } catch (err) {
        setPage(content, renderEmpty("خطأ", "تعذر تحميل موادك."));
    }
}

async function showSubjectLectures(subjectId, subjectName, page = 1) {
    const content = document.getElementById("main-content");
    const perPage = 10;
    try {
        const payload = await API.getPage("/lectures/subject/" + subjectId, page, perPage);
        const lectures = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("محاضرات " + subjectName, "fa-solid fa-video");
        const list = document.createElement("div");
        list.className = "lectures-list";
        if (lectures.length === 0) {
            list.appendChild(renderEmpty("لا توجد محاضرات", "لم تتم إضافة محاضرات لهذه المادة بعد."));
        } else {
            lectures.forEach(l => {
                list.appendChild(renderListItem(
                    l.title,
                    l.description || "",
                    ["البداية: " + formatDate(l.start_time), "النهاية: " + formatDate(l.end_time)],
                    []
                ));
            });
        }
        container.appendChild(list);
        container.appendChild(renderPagination(meta, (nextPage) => showSubjectLectures(subjectId, subjectName, nextPage)));
        setPage(content, container);
    } catch (err) {
        showToast("خطأ", err.message, "danger");
    }
}

async function showSubjectHomeworks(subjectId, subjectName, page = 1) {
    const content = document.getElementById("main-content");
    const perPage = 10;
    try {
        const payload = await API.getPage("/homeworks/subject/" + subjectId, page, perPage);
        const homeworks = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("واجبات " + subjectName, "fa-solid fa-clipboard-list");
        const list = document.createElement("div");
        list.className = "homeworks-list";
        if (homeworks.length === 0) {
            list.appendChild(renderEmpty("لا توجد واجبات", "لم تتم إضافة واجبات لهذه المادة بعد."));
        } else {
            homeworks.forEach(hw => {
                const actions = [];
                if (hw.file_url) actions.push(makeLinkButton("الملف", "fa-solid fa-download", hw.file_url));
                actions.push(makeButton("تسليم", "fa-solid fa-upload", "btn btn-sm btn-primary", () => renderSubmitHomework(hw)));
                list.appendChild(renderListItem(
                    hw.title,
                    hw.description,
                    ["الموعد النهائي: " + formatDate(hw.deadline)],
                    actions
                ));
            });
        }
        container.appendChild(list);
        container.appendChild(renderPagination(meta, (nextPage) => showSubjectHomeworks(subjectId, subjectName, nextPage)));
        setPage(content, container);
    } catch (err) {
        showToast("خطأ", err.message, "danger");
    }
}

function renderSubmitHomework(homework) {
    const content = document.getElementById("main-content");
    const container = renderPageShell("تسليم واجب: " + homework.title, "fa-solid fa-upload");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="submit-homework-form">
            <div class="form-group">
                <label class="form-label">ملف الإجابة</label>
                <input type="file" class="form-input" id="submission-file" required>
            </div>
            <div class="form-footer">
                <button type="submit" class="btn btn-primary"><i class="fa-solid fa-upload"></i> تسليم الواجب</button>
            </div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);

    document.getElementById("submit-homework-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById("submission-file");
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        try {
            await API.postForm("/homeworks/" + homework.id + "/submit", formData);
            showToast("تم", "تم تسليم الواجب بنجاح", "success");
            window.location.hash = "#/my-submissions";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

// --- تسليمات الطالب ---
Router.add("/my-submissions", async () => {
    await renderMySubmissions(1);
});

async function renderMySubmissions(page) {
    const content = document.getElementById("main-content");
    if (!requireRole("student")) return;
    const perPage = 10;

    try {
        const payload = await API.getPage("/homeworks/my/submissions", page, perPage);
        const submissions = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("تسليماتي", "fa-solid fa-file-arrow-up");
        const tableWrap = document.createElement("div");
        tableWrap.className = "table-container";
        const table = document.createElement("table");
        table.className = "modern-table";
        table.innerHTML = "<thead><tr><th>رقم الواجب</th><th>الحالة</th><th>الدرجة</th><th>تاريخ التسليم</th><th>الملف</th></tr></thead><tbody></tbody>";
        const tbody = table.querySelector("tbody");
        submissions.forEach(s => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${s.homework_id}</td>
                <td><span class="badge-status ${escapeHTML(s.status)}">${escapeHTML(s.status)}</span></td>
                <td>${s.grade === null || s.grade === undefined ? "لم تصحح بعد" : escapeHTML(s.grade)}</td>
                <td>${escapeHTML(formatDate(s.submitted_at))}</td>
                <td><a class="btn btn-sm btn-secondary" href="${escapeHTML(s.file_url)}" target="_blank" rel="noopener"><i class="fa-solid fa-download"></i> فتح</a></td>
            `;
            tbody.appendChild(tr);
        });
        tableWrap.appendChild(table);
        container.appendChild(submissions.length ? tableWrap : renderEmpty("لا توجد تسليمات", "لم تسلم أي واجب بعد."));
        container.appendChild(renderPagination(meta, renderMySubmissions));
        setPage(content, container);
    } catch (err) {
        setPage(content, renderEmpty("خطأ", "تعذر تحميل تسليماتك."));
    }
}

// --- مادة المدرس ---
Router.add("/my-subject", async () => {
    const content = document.getElementById("main-content");
    if (!requireRole("teacher")) return;

    try {
        const subject = await API.get("/subjects/my/taught");
        if (!subject) {
            setPage(content, renderEmpty("لا توجد مادة", "لم يتم ربط حسابك بأي مادة بعد."));
            return;
        }

        const container = renderPageShell("مادتي: " + subject.name, "fa-solid fa-chalkboard-teacher");
        const actions = document.createElement("div");
        actions.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;";
        actions.appendChild(makeButton("إضافة محاضرة", "fa-solid fa-plus", "btn btn-primary", () => renderLectureForm(subject)));
        actions.appendChild(makeButton("إضافة واجب", "fa-solid fa-plus", "btn btn-accent", () => renderHomeworkForm(subject)));
        actions.appendChild(makeButton("عرض المحاضرات", "fa-solid fa-video", "btn btn-secondary", () => showTeacherLectures(subject)));
        actions.appendChild(makeButton("عرض الواجبات", "fa-solid fa-clipboard-list", "btn btn-secondary", () => showTeacherHomeworks(subject)));
        container.appendChild(actions);

        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `<h3 class="subject-title">${escapeHTML(subject.name)}</h3><p class="subject-desc">${escapeHTML(subject.description || "لا يوجد وصف")}</p><span class="badge-status submitted">${escapeHTML(subject.grade_level)}</span>`;
        container.appendChild(card);
        setPage(content, container);
    } catch (err) {
        setPage(content, renderEmpty("خطأ", "تعذر تحميل مادة المدرس."));
    }
});

function renderLectureForm(subject) {
    const content = document.getElementById("main-content");
    const container = renderPageShell("إضافة محاضرة", "fa-solid fa-video");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="lecture-form">
            <div class="form-group"><label class="form-label">العنوان</label><input class="form-input" id="lecture-title" required></div>
            <div class="form-group"><label class="form-label">الوصف</label><textarea class="form-input form-textarea" id="lecture-description"></textarea></div>
            <div class="form-group"><label class="form-label">وقت البداية</label><input type="datetime-local" class="form-input" id="lecture-start" required></div>
            <div class="form-group"><label class="form-label">وقت النهاية</label><input type="datetime-local" class="form-input" id="lecture-end" required></div>
            <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-save"></i> حفظ</button></div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);

    document.getElementById("lecture-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await API.post("/lectures", {
                title: document.getElementById("lecture-title").value.trim(),
                description: document.getElementById("lecture-description").value.trim(),
                start_time: document.getElementById("lecture-start").value,
                end_time: document.getElementById("lecture-end").value
            });
            showToast("تم", "تمت إضافة المحاضرة", "success");
            showTeacherLectures(subject);
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

function renderHomeworkForm(subject) {
    const content = document.getElementById("main-content");
    const container = renderPageShell("إضافة واجب", "fa-solid fa-clipboard-list");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="homework-form">
            <div class="form-group"><label class="form-label">العنوان</label><input class="form-input" id="homework-title" required></div>
            <div class="form-group"><label class="form-label">الوصف</label><textarea class="form-input form-textarea" id="homework-description" required></textarea></div>
            <div class="form-group"><label class="form-label">الموعد النهائي</label><input type="datetime-local" class="form-input" id="homework-deadline" required></div>
            <div class="form-group"><label class="form-label">ملف مرفق اختياري</label><input type="file" class="form-input" id="homework-file"></div>
            <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-save"></i> حفظ</button></div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);

    document.getElementById("homework-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData();
        formData.append("title", document.getElementById("homework-title").value.trim());
        formData.append("description", document.getElementById("homework-description").value.trim());
        formData.append("deadline", document.getElementById("homework-deadline").value);
        const file = document.getElementById("homework-file").files[0];
        if (file) formData.append("file", file);
        try {
            await API.postForm("/homeworks", formData);
            showToast("تم", "تمت إضافة الواجب", "success");
            showTeacherHomeworks(subject);
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

async function showTeacherLectures(subject, page = 1) {
    const content = document.getElementById("main-content");
    const perPage = 10;
    try {
        const payload = await API.getPage("/lectures/subject/" + subject.id, page, perPage);
        const lectures = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("محاضرات " + subject.name, "fa-solid fa-video");
        const list = document.createElement("div");
        list.className = "lectures-list";
        lectures.forEach(l => {
            list.appendChild(renderListItem(
                l.title,
                l.description || "",
                ["البداية: " + formatDate(l.start_time), "النهاية: " + formatDate(l.end_time)],
                [
                    makeButton("حذف", "fa-solid fa-trash", "btn btn-sm btn-danger", async () => {
                        if (!confirmAction(l.title, "حذف المحاضرة")) return;
                        try {
                            await API.delete("/lectures/" + l.id);
                            showToast("تم", "تم حذف المحاضرة", "success");
                            showTeacherLectures(subject, page);
                        } catch (err) {
                            showToast("خطأ", err.message, "danger");
                        }
                    })
                ]
            ));
        });
        container.appendChild(lectures.length ? list : renderEmpty("لا توجد محاضرات", "لم تضف محاضرات بعد."));
        container.appendChild(renderPagination(meta, (nextPage) => showTeacherLectures(subject, nextPage)));
        setPage(content, container);
    } catch (err) {
        showToast("خطأ", err.message, "danger");
    }
}

async function showTeacherHomeworks(subject, page = 1) {
    const content = document.getElementById("main-content");
    const perPage = 10;
    try {
        const payload = await API.getPage("/homeworks/subject/" + subject.id, page, perPage);
        const homeworks = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("واجبات " + subject.name, "fa-solid fa-clipboard-list");
        const list = document.createElement("div");
        list.className = "homeworks-list";
        homeworks.forEach(hw => {
            const actions = [];
            if (hw.file_url) actions.push(makeLinkButton("الملف", "fa-solid fa-download", hw.file_url));
            actions.push(makeButton("التسليمات", "fa-solid fa-list-check", "btn btn-sm btn-primary", () => showHomeworkSubmissions(hw)));
            actions.push(makeButton("حذف", "fa-solid fa-trash", "btn btn-sm btn-danger", async () => {
                if (!confirmAction(hw.title, "حذف الواجب")) return;
                try {
                    await API.delete("/homeworks/" + hw.id);
                    showToast("تم", "تم حذف الواجب", "success");
                    showTeacherHomeworks(subject, page);
                } catch (err) {
                    showToast("خطأ", err.message, "danger");
                }
            }));
            list.appendChild(renderListItem(hw.title, hw.description, ["الموعد النهائي: " + formatDate(hw.deadline)], actions));
        });
        container.appendChild(homeworks.length ? list : renderEmpty("لا توجد واجبات", "لم تضف واجبات بعد."));
        container.appendChild(renderPagination(meta, (nextPage) => showTeacherHomeworks(subject, nextPage)));
        setPage(content, container);
    } catch (err) {
        showToast("خطأ", err.message, "danger");
    }
}

async function showHomeworkSubmissions(homework, page = 1) {
    const content = document.getElementById("main-content");
    const perPage = 10;
    try {
        const payload = await API.getPage("/homeworks/" + homework.id + "/submissions", page, perPage);
        const submissions = getItems(payload);
        const meta = getPageMeta(payload, page, perPage);
        const container = renderPageShell("تسليمات: " + homework.title, "fa-solid fa-list-check");
        const tableWrap = document.createElement("div");
        tableWrap.className = "table-container";
        const table = document.createElement("table");
        table.className = "modern-table";
        table.innerHTML = "<thead><tr><th>الطالب</th><th>الحالة</th><th>الدرجة</th><th>الملف</th><th>تصحيح</th></tr></thead><tbody></tbody>";
        const tbody = table.querySelector("tbody");
        submissions.forEach(s => {
            const tr = document.createElement("tr");
            const studentName = s.student ? s.student.first_name + " " + s.student.last_name : "طالب";
            tr.innerHTML = `
                <td>${escapeHTML(studentName)}</td>
                <td><span class="badge-status ${escapeHTML(s.status)}">${escapeHTML(s.status)}</span></td>
                <td>${s.grade === null || s.grade === undefined ? "لم تصحح بعد" : escapeHTML(s.grade)}</td>
                <td><a class="btn btn-sm btn-secondary" href="${escapeHTML(s.file_url)}" target="_blank" rel="noopener"><i class="fa-solid fa-download"></i> فتح</a></td>
                <td></td>
            `;
            tr.querySelector("td:last-child").appendChild(makeButton("رصد", "fa-solid fa-check", "btn btn-sm btn-primary", async () => {
                const grade = prompt("أدخل الدرجة:");
                if (grade === null) return;
                const notes = prompt("ملاحظات المدرس (اختياري):") || "";
                try {
                    await API.post("/homeworks/submissions/" + s.id + "/grade", { grade: parseFloat(grade), teacher_notes: notes });
                    showToast("تم", "تم رصد الدرجة", "success");
                    showHomeworkSubmissions(homework);
                } catch (err) {
                    showToast("خطأ", err.message, "danger");
                }
            }));
            tbody.appendChild(tr);
        });
        tableWrap.appendChild(table);
        container.appendChild(submissions.length ? tableWrap : renderEmpty("لا توجد تسليمات", "لم يسلم الطلاب هذا الواجب بعد."));
        container.appendChild(renderPagination(meta, (nextPage) => showHomeworkSubmissions(homework, nextPage)));
        setPage(content, container);
    } catch (err) {
        showToast("خطأ", err.message, "danger");
    }
}

// --- لوحة المدير ---
Router.add("/admin", async () => {
    await renderAdmin(1);
});

async function renderAdmin(page) {
    const content = document.getElementById("main-content");
    if (!requireRole("owner")) return;
    const perPage = 10;

    try {
        const stats = await API.get("/admin/stats");
        const subjectsPayload = await API.getPage("/subjects", 1, 100);
        const usersPayload = await API.getPage("/admin/users", page, perPage);
        const codesPayload = await API.getPage("/admin/codes", 1, 5);
        const sectionsPayload = await API.getPage("/admin/sections", 1, 100);
        const groupsPayload = await API.getPage("/admin/groups", 1, 100);
        const subjects = getItems(subjectsPayload);
        const users = getItems(usersPayload);
        const codes = getItems(codesPayload);
        const sections = getItems(sectionsPayload);
        const groups = getItems(groupsPayload);
        const usersMeta = getPageMeta(usersPayload, page, perPage);

        const container = renderPageShell("لوحة التحكم", "fa-solid fa-shield-halved");
        const statGrid = document.createElement("div");
        statGrid.className = "stats-grid";
        [
            ["المستخدمون", stats.counts.total_users, "fa-solid fa-users", "primary"],
            ["الطلاب", stats.counts.students, "fa-solid fa-user-graduate", "success"],
            ["المدرسون", stats.counts.teachers, "fa-solid fa-chalkboard-user", "warning"],
            ["المواد", stats.counts.subjects, "fa-solid fa-book", "accent"]
        ].forEach(([label, value, icon, color]) => {
            const card = document.createElement("div");
            card.className = "stat-card";
            card.innerHTML = `<div class="stat-icon ${color}"><i class="${icon}"></i></div><div class="stat-info"><h3>${label}</h3><div class="stat-number">${value}</div></div>`;
            statGrid.appendChild(card);
        });
        container.appendChild(statGrid);

        const actions = document.createElement("div");
        actions.style.cssText = "display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;";
        actions.appendChild(makeButton("إضافة مادة", "fa-solid fa-plus", "btn btn-primary", renderSubjectForm));
        actions.appendChild(makeButton("إضافة شعبة", "fa-solid fa-layer-group", "btn btn-secondary", renderSectionForm));
        actions.appendChild(makeButton("إضافة مجموعة", "fa-solid fa-users-rectangle", "btn btn-secondary", () => renderGroupForm(sections)));
        actions.appendChild(makeButton("توليد كود مدرس", "fa-solid fa-key", "btn btn-accent", () => renderTeacherCodeForm(subjects)));
        container.appendChild(actions);

        const usersTable = document.createElement("div");
        usersTable.className = "table-container";
        usersTable.innerHTML = "<table class='modern-table'><thead><tr><th>الاسم</th><th>الدور</th><th>البريد</th><th>الحالة</th><th>إجراءات</th></tr></thead><tbody></tbody></table>";
        const tbody = usersTable.querySelector("tbody");
        users.forEach(u => {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${escapeHTML(u.first_name + " " + u.last_name)}</td><td>${escapeHTML(u.role)}</td><td>${escapeHTML(u.email)}</td><td>${u.is_blocked ? "محظور" : "نشط"}</td><td></td>`;
            const actionCell = tr.querySelector("td:last-child");
            actionCell.appendChild(makeButton(u.is_blocked ? "إلغاء الحظر" : "حظر", "fa-solid fa-ban", "btn btn-sm btn-secondary", async () => {
                if (!confirmAction(u.first_name + " " + u.last_name, u.is_blocked ? "إلغاء الحظر" : "حظر المستخدم")) return;
                try {
                    await API.post("/admin/users/" + u.id + "/block");
                    showToast("تم", "تم تحديث حالة المستخدم", "success");
                    renderAdmin(page);
                } catch (err) {
                    showToast("خطأ", err.message, "danger");
                }
            }));
            actionCell.appendChild(makeButton("حذف", "fa-solid fa-trash", "btn btn-sm btn-danger", async () => {
                if (!confirmAction(u.first_name + " " + u.last_name, "حذف المستخدم")) return;
                try {
                    await API.delete("/admin/users/" + u.id);
                    showToast("تم", "تم حذف المستخدم", "success");
                    renderAdmin(page);
                } catch (err) {
                    showToast("خطأ", err.message, "danger");
                }
            }));
            tbody.appendChild(tr);
        });
        container.appendChild(usersTable);
        container.appendChild(renderPagination(usersMeta, renderAdmin));

        const subjectsCard = document.createElement("div");
        subjectsCard.className = "card";
        subjectsCard.style.marginTop = "24px";
        const subjectsTitle = document.createElement("h3");
        subjectsTitle.className = "subject-title";
        subjectsTitle.textContent = "المواد";
        subjectsCard.appendChild(subjectsTitle);
        subjects.forEach(s => {
            subjectsCard.appendChild(renderListItem(
                s.name,
                s.description || "",
                [s.grade_level],
                [
                    makeButton("حذف", "fa-solid fa-trash", "btn btn-sm btn-danger", async () => {
                        if (!confirmAction(s.name, "حذف المادة")) return;
                        try {
                            await API.delete("/subjects/" + s.id);
                            showToast("تم", "تم حذف المادة", "success");
                            renderAdmin(page);
                        } catch (err) {
                            showToast("خطأ", err.message, "danger");
                        }
                    })
                ]
            ));
        });
        container.appendChild(subjectsCard);

        const sectionsCard = document.createElement("div");
        sectionsCard.className = "card";
        sectionsCard.style.marginTop = "24px";
        const sectionsTitle = document.createElement("h3");
        sectionsTitle.className = "subject-title";
        sectionsTitle.textContent = "الشعب";
        sectionsCard.appendChild(sectionsTitle);
        if (sections.length === 0) {
            const empty = document.createElement("p");
            empty.className = "subject-desc";
            empty.textContent = "لا توجد شعب بعد.";
            sectionsCard.appendChild(empty);
        }
        sections.forEach(section => {
            const sectionGroups = groups.filter(group => group.section_id === section.id).map(group => group.name).join("، ");
            sectionsCard.appendChild(renderListItem(
                section.name,
                section.description || "المجموعات: " + (sectionGroups || "لا توجد"),
                [section.grade_level],
                [
                    makeButton("حذف", "fa-solid fa-trash", "btn btn-sm btn-danger", async () => {
                        if (!confirmAction(section.name, "حذف الشعبة")) return;
                        try {
                            await API.delete("/admin/sections/" + section.id);
                            showToast("تم", "تم حذف الشعبة", "success");
                            renderAdmin(page);
                        } catch (err) {
                            showToast("خطأ", err.message, "danger");
                        }
                    })
                ]
            ));
        });
        container.appendChild(sectionsCard);

        const groupsCard = document.createElement("div");
        groupsCard.className = "card";
        groupsCard.style.marginTop = "24px";
        const groupsTitle = document.createElement("h3");
        groupsTitle.className = "subject-title";
        groupsTitle.textContent = "المجموعات";
        groupsCard.appendChild(groupsTitle);
        if (groups.length === 0) {
            const empty = document.createElement("p");
            empty.className = "subject-desc";
            empty.textContent = "لا توجد مجموعات بعد.";
            groupsCard.appendChild(empty);
        }
        groups.forEach(group => {
            const section = sections.find(item => item.id === group.section_id);
            groupsCard.appendChild(renderListItem(
                group.name,
                group.description || "",
                [section ? section.grade_level : "", section ? section.name : "الشعبة غير معروفة"],
                [
                    makeButton("حذف", "fa-solid fa-trash", "btn btn-sm btn-danger", async () => {
                        if (!confirmAction(group.name, "حذف المجموعة")) return;
                        try {
                            await API.delete("/admin/groups/" + group.id);
                            showToast("تم", "تم حذف المجموعة", "success");
                            renderAdmin(page);
                        } catch (err) {
                            showToast("خطأ", err.message, "danger");
                        }
                    })
                ]
            ));
        });
        container.appendChild(groupsCard);

        const codeCard = document.createElement("div");
        codeCard.className = "card";
        codeCard.style.marginTop = "24px";
        codeCard.innerHTML = `<h3 class="subject-title">آخر أكواد المدرسين</h3><p class="subject-desc">${codes.slice(0, 5).map(c => escapeHTML(c.code)).join(" - ") || "لا توجد أكواد"}</p>`;
        container.appendChild(codeCard);

        setPage(content, container);
    } catch (err) {
        setPage(content, renderEmpty("خطأ", "تعذر تحميل لوحة التحكم."));
    }
}

function fillGradeSelect(select) {
    IRAQI_SECONDARY_GRADES.forEach(grade => {
        const option = document.createElement("option");
        option.value = grade;
        option.textContent = grade;
        select.appendChild(option);
    });
}

function renderSubjectForm() {
    const content = document.getElementById("main-content");
    const container = renderPageShell("إضافة مادة", "fa-solid fa-book");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="subject-form">
            <div class="form-group"><label class="form-label">اسم المادة</label><input class="form-input" id="subject-name" required></div>
            <div class="form-group"><label class="form-label">الصف الدراسي</label><select class="form-input" id="subject-grade" required></select></div>
            <div class="form-group"><label class="form-label">الوصف</label><textarea class="form-input form-textarea" id="subject-description"></textarea></div>
            <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-save"></i> حفظ</button></div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);
    fillGradeSelect(document.getElementById("subject-grade"));
    document.getElementById("subject-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await API.post("/subjects", {
                name: document.getElementById("subject-name").value.trim(),
                grade_level: document.getElementById("subject-grade").value,
                description: document.getElementById("subject-description").value.trim()
            });
            showToast("تم", "تمت إضافة المادة", "success");
            window.location.hash = "#/admin";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

function renderSectionForm() {
    const content = document.getElementById("main-content");
    const container = renderPageShell("إضافة شعبة", "fa-solid fa-layer-group");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="section-form">
            <div class="form-group"><label class="form-label">الصف الدراسي</label><select class="form-input" id="section-grade" required></select></div>
            <div class="form-group"><label class="form-label">اسم الشعبة</label><input class="form-input" id="section-name" required placeholder="مثال: شعبة أ"></div>
            <div class="form-group"><label class="form-label">الوصف</label><textarea class="form-input form-textarea" id="section-description"></textarea></div>
            <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-save"></i> حفظ</button></div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);
    fillGradeSelect(document.getElementById("section-grade"));
    document.getElementById("section-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await API.post("/admin/sections", {
                grade_level: document.getElementById("section-grade").value,
                name: document.getElementById("section-name").value.trim(),
                description: document.getElementById("section-description").value.trim()
            });
            showToast("تم", "تمت إضافة الشعبة", "success");
            window.location.hash = "#/admin";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

function renderGroupForm(sections) {
    const content = document.getElementById("main-content");
    const container = renderPageShell("إضافة مجموعة", "fa-solid fa-users-rectangle");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="group-form">
            <div class="form-group"><label class="form-label">الشعبة</label><select class="form-input" id="group-section" required></select></div>
            <div class="form-group"><label class="form-label">اسم المجموعة</label><input class="form-input" id="group-name" required placeholder="مثال: مجموعة 1"></div>
            <div class="form-group"><label class="form-label">الوصف</label><textarea class="form-input form-textarea" id="group-description"></textarea></div>
            <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-save"></i> حفظ</button></div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);

    const select = document.getElementById("group-section");
    sections.forEach(section => {
        const option = document.createElement("option");
        option.value = section.id;
        option.textContent = section.grade_level + " - " + section.name;
        select.appendChild(option);
    });
    if (sections.length === 0) {
        showToast("تنبيه", "أضف شعبة أولاً قبل إنشاء مجموعة", "warning");
    }

    document.getElementById("group-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!select.value) {
            showToast("تنبيه", "يجب اختيار شعبة", "warning");
            return;
        }
        try {
            await API.post("/admin/groups", {
                section_id: parseInt(select.value),
                name: document.getElementById("group-name").value.trim(),
                description: document.getElementById("group-description").value.trim()
            });
            showToast("تم", "تمت إضافة المجموعة", "success");
            window.location.hash = "#/admin";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

function renderTeacherCodeForm(subjects) {
    const content = document.getElementById("main-content");
    const container = renderPageShell("توليد كود مدرس", "fa-solid fa-key");
    const card = document.createElement("div");
    card.className = "card form-card";
    card.innerHTML = `
        <form id="teacher-code-form">
            <div class="form-group"><label class="form-label">المادة</label><select class="form-input" id="code-subject"></select></div>
            <div class="form-group"><label class="form-label">عدد أيام الصلاحية</label><input type="number" class="form-input" id="code-days" value="7" min="1" required></div>
            <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-key"></i> توليد</button></div>
        </form>
    `;
    container.appendChild(card);
    setPage(content, container);

    const select = document.getElementById("code-subject");
    subjects.forEach(s => {
        const option = document.createElement("option");
        option.value = s.id;
        option.textContent = s.name + " - " + s.grade_level;
        select.appendChild(option);
    });

    document.getElementById("teacher-code-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            const result = await API.post("/admin/codes", {
                subject_id: parseInt(select.value),
                expires_in_days: parseInt(document.getElementById("code-days").value)
            });
            showToast("تم توليد الكود", result.code, "success");
            window.location.hash = "#/admin";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
}

Router.add("/terms", async () => {
    setPage(document.getElementById("main-content"), renderEmpty("الشروط والأحكام", "هذه صفحة تعريفية مختصرة لاستخدام المنصة بشكل مسؤول."));
});

Router.add("/privacy", async () => {
    setPage(document.getElementById("main-content"), renderEmpty("سياسة الخصوصية", "تحافظ المنصة على بيانات المستخدمين وتستخدمها لتقديم الخدمات التعليمية فقط."));
});

Router.add("/404", async () => {
    const content = document.getElementById("main-content");
    const container = document.createElement("div");
    container.className = "container not-found-page";
    container.innerHTML = `
        <div class="not-found-icon"><i class="fa-solid fa-map-location-dot"></i></div>
        <h1>الصفحة غير موجودة</h1>
        <p>الرابط الذي تحاول فتحه غير صحيح أو تم نقله.</p>
        <div class="not-found-actions">
            <a href="#/" class="btn btn-primary"><i class="fa-solid fa-house"></i> الرئيسية</a>
            <a href="mailto:info@alrwad.edu" class="btn btn-secondary"><i class="fa-solid fa-headset"></i> الدعم الفني</a>
        </div>
    `;
    setPage(content, container);
});

// --- صفحة الملف الشخصي ---
Router.add("/profile", async () => {
    const content = document.getElementById("main-content");
    if (!currentUser) { window.location.hash = "#/login"; return; }

    const roleLabels = { student: "طالب", teacher: "مدرس", tutor: "مدرس خصوصي", owner: "مدير المنصة" };

    // بناء الصفحة بـ DOM API
    const container = renderPageShell("الملف الشخصي", "fa-solid fa-user-circle");
    container.classList.add("profile-page");

    const profileGrid = document.createElement("div");
    profileGrid.className = "profile-grid";

    const summary = document.createElement("div");
    summary.className = "card profile-summary";
    summary.innerHTML = `
        <div class="profile-avatar">
            ${currentUser.avatar_url ? `<img src="${escapeHTML(currentUser.avatar_url)}" alt="صورة المستخدم">` : `<i class="fa-solid fa-user"></i>`}
        </div>
        <h3>${escapeHTML(currentUser.first_name + " " + currentUser.last_name)}</h3>
        <p>@${escapeHTML(currentUser.username)}</p>
        <span class="badge-status submitted">${escapeHTML(roleLabels[currentUser.role] || currentUser.role)}</span>
        <p class="profile-bio">${escapeHTML(currentUser.bio || "لا توجد نبذة شخصية")}</p>
        <p class="profile-email"><i class="fa-solid fa-envelope"></i> ${escapeHTML(currentUser.email)}</p>
    `;
    profileGrid.appendChild(summary);

    const forms = document.createElement("div");
    forms.className = "profile-forms";
    forms.innerHTML = `
        <div class="card">
            <h3 class="form-title">تعديل البيانات الأساسية</h3>
            <form id="profile-info-form">
                <div class="form-group"><label class="form-label">الاسم الأول</label><input class="form-input" id="profile-first-name" value="${escapeHTML(currentUser.first_name)}" required></div>
                <div class="form-group"><label class="form-label">الاسم الأخير</label><input class="form-input" id="profile-last-name" value="${escapeHTML(currentUser.last_name)}" required></div>
                <div class="form-group"><label class="form-label">البريد الإلكتروني</label><input type="email" class="form-input" id="profile-email" value="${escapeHTML(currentUser.email)}" required></div>
                <div class="form-group"><label class="form-label">النبذة الشخصية</label><textarea class="form-input form-textarea" id="profile-bio">${escapeHTML(currentUser.bio || "")}</textarea></div>
                <div class="form-footer"><button class="btn btn-primary" type="submit"><i class="fa-solid fa-save"></i> حفظ البيانات</button></div>
            </form>
        </div>
        <div class="card">
            <h3 class="form-title">تغيير كلمة المرور</h3>
            <form id="profile-password-form">
                <div class="form-group"><label class="form-label">كلمة المرور الحالية</label><input type="password" class="form-input" id="current-password" required></div>
                <div class="form-group"><label class="form-label">كلمة المرور الجديدة</label><input type="password" class="form-input" id="new-password" required minlength="8"></div>
                <div class="form-group"><label class="form-label">تأكيد كلمة المرور الجديدة</label><input type="password" class="form-input" id="new-password-confirm" required minlength="8"></div>
                <div class="form-footer"><button class="btn btn-accent" type="submit"><i class="fa-solid fa-key"></i> تغيير كلمة المرور</button></div>
            </form>
        </div>
        <div class="card">
            <h3 class="form-title">تغيير الصورة الشخصية</h3>
            <form id="profile-avatar-form">
                <div class="form-group"><label class="form-label">الصورة الجديدة</label><input type="file" class="form-input" id="profile-avatar" accept=".png,.jpg,.jpeg,.webp" required></div>
                <div class="form-footer"><button class="btn btn-secondary" type="submit"><i class="fa-solid fa-upload"></i> رفع الصورة</button></div>
            </form>
        </div>
    `;
    profileGrid.appendChild(forms);
    container.appendChild(profileGrid);
    setPage(content, container);

    document.getElementById("profile-info-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            currentUser = await API.put("/users/profile", {
                first_name: document.getElementById("profile-first-name").value.trim(),
                last_name: document.getElementById("profile-last-name").value.trim(),
                email: document.getElementById("profile-email").value.trim(),
                bio: document.getElementById("profile-bio").value.trim()
            });
            updateNavbar();
            showToast("تم", "تم تحديث بياناتك الشخصية", "success");
            Router.resolve();
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });

    document.getElementById("profile-password-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const nextPassword = document.getElementById("new-password").value;
        const confirmPassword = document.getElementById("new-password-confirm").value;
        if (nextPassword !== confirmPassword) {
            showToast("تنبيه", "كلمة المرور الجديدة وتأكيدها غير متطابقين", "warning");
            return;
        }
        try {
            await API.post("/users/change-password", {
                current_password: document.getElementById("current-password").value,
                new_password: nextPassword,
                new_password_confirm: confirmPassword
            });
            showToast("تم", "تم تغيير كلمة المرور بنجاح", "success");
            e.target.reset();
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });

    document.getElementById("profile-avatar-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const file = document.getElementById("profile-avatar").files[0];
        const formData = new FormData();
        formData.append("file", file);
        try {
            await API.postForm("/users/avatar", formData);
            await loadCurrentUser();
            showToast("تم", "تم تحديث الصورة الشخصية", "success");
            Router.resolve();
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
});

// --- صفحة استعادة كلمة المرور ---
Router.add("/reset-password", async () => {
    const content = document.getElementById("main-content");
    // بيانات ثابتة بالكامل - لا خطر XSS هنا
    content.innerHTML = `
        <div class="container">
            <div class="card form-card">
                <h2 class="form-title"><i class="fa-solid fa-key"></i> استعادة كلمة المرور</h2>
                <form id="reset-request-form">
                    <div class="form-group">
                        <label class="form-label">البريد الإلكتروني</label>
                        <input type="email" class="form-input" id="reset-email" required placeholder="أدخل بريدك الإلكتروني المسجل">
                    </div>
                    <div class="form-footer">
                        <button type="submit" class="btn btn-primary"><i class="fa-solid fa-paper-plane"></i> إرسال رمز الاستعادة</button>
                    </div>
                </form>
                <div id="verify-section" style="display:none;margin-top:24px;">
                    <hr style="margin-bottom:20px;border:none;border-top:1px solid var(--border-color);">
                    <form id="reset-verify-form">
                        <div class="form-group">
                            <label class="form-label">رمز التحقق</label>
                            <input type="text" class="form-input" id="reset-code" required placeholder="أدخل الرمز المكون من 6 أرقام">
                        </div>
                        <div class="form-group">
                            <label class="form-label">كلمة المرور الجديدة</label>
                            <input type="password" class="form-input" id="reset-new-password" required minlength="8">
                        </div>
                        <div class="form-group">
                            <label class="form-label">تأكيد كلمة المرور الجديدة</label>
                            <input type="password" class="form-input" id="reset-new-password-confirm" required minlength="8">
                        </div>
                        <div class="form-footer">
                            <button type="submit" class="btn btn-accent"><i class="fa-solid fa-check"></i> تأكيد وتغيير كلمة المرور</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    `;

    document.getElementById("reset-request-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
            await API.post("/auth/forgot-password", { email: document.getElementById("reset-email").value.trim() });
            showToast("تم الإرسال", "إذا كان البريد مسجلاً فسيصلك رمز الاستعادة", "success");
            document.getElementById("verify-section").style.display = "block";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });

    document.getElementById("reset-verify-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const newPassword = document.getElementById("reset-new-password").value;
        const confirmPassword = document.getElementById("reset-new-password-confirm").value;
        if (newPassword !== confirmPassword) {
            showToast("تنبيه", "كلمة المرور الجديدة وتأكيدها غير متطابقين", "warning");
            return;
        }
        try {
            await API.post("/auth/reset-password", {
                email: document.getElementById("reset-email").value.trim(),
                code: document.getElementById("reset-code").value.trim(),
                new_password: newPassword,
                new_password_confirm: confirmPassword
            });
            showToast("تم!", "تم تغيير كلمة المرور بنجاح", "success");
            window.location.hash = "#/login";
        } catch (err) {
            showToast("خطأ", err.message, "danger");
        }
    });
});


// ========== لوحة بريد المطور (Dev Panel) ==========
async function loadDevEmails() {
    const list = document.getElementById("dev-emails-list");
    const badge = document.getElementById("dev-email-count");
    if (badge) badge.textContent = "API";
    if (!list) return;
    list.textContent = "";
    const msg = document.createElement("p");
    msg.className = "empty-text";
    msg.textContent = "رسائل التفعيل والاستعادة ترسل الآن عبر Email API الحقيقي.";
    list.appendChild(msg);
}


// ========== تشغيل التطبيق عند التحميل ==========
(async function init() {
    // جلب بيانات المستخدم
    await loadCurrentUser();

    // تفعيل الموجه
    Router.init();

    // إعداد قائمة الموبايل
    const mobileBtn = document.getElementById("mobile-menu-btn");
    const mainNav = document.getElementById("main-nav");
    if (mobileBtn && mainNav) {
        mobileBtn.addEventListener("click", () => {
            mainNav.classList.toggle("show");
        });
    }

    // إعداد لوحة المطور
    const devBtn = document.getElementById("dev-panel-btn");
    const devPanel = document.getElementById("dev-panel");
    const devClose = document.getElementById("dev-panel-close");
    const devClear = document.getElementById("dev-clear-emails");
    const devRefresh = document.getElementById("dev-refresh-emails");

    if (devBtn && devPanel) {
        devBtn.addEventListener("click", () => {
            devPanel.classList.toggle("hidden");
            loadDevEmails();
        });
    }

    if (devClose) devClose.addEventListener("click", () => devPanel.classList.add("hidden"));

    if (devClear) {
        devClear.addEventListener("click", () => {
            showToast("تنبيه", "لا يوجد صندوق بريد محاكي لمسحه", "info");
        });
    }

    if (devRefresh) devRefresh.addEventListener("click", () => loadDevEmails());

    // تحميل الإيميلات المحاكية عند التشغيل
    loadDevEmails();
})();
