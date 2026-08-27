// نظام التوجيه الأحادي للصفحة (SPA Router)
const Router = {
    routes: {},

    // إضافة مسار جديد
    add(path, handler) {
        this.routes[path] = handler;
    },

    // معالجة تغيير الهاش وتوجيه المستخدم للصفحة المناسبة
    async resolve() {
        const hash = window.location.hash || "#/";
        
        // تنظيف المسار وتقسيمه
        const hashPath = hash.substring(1) || "/";
        const pathSegments = hashPath.split("/").filter(s => s !== "");
        
        let matchedRoute = null;
        let params = {};

        // البحث عن المسار المطابق
        for (const route in this.routes) {
            const routeSegments = route.split("/").filter(s => s !== "");
            
            if (routeSegments.length !== pathSegments.length) continue;

            let isMatch = true;
            const tempParams = {};

            for (let i = 0; i < routeSegments.length; i++) {
                if (routeSegments[i].startsWith(":")) {
                    const paramName = routeSegments[i].substring(1);
                    tempParams[paramName] = pathSegments[i];
                } else if (routeSegments[i] !== pathSegments[i]) {
                    isMatch = false;
                    break;
                }
            }

            if (isMatch) {
                matchedRoute = this.routes[route];
                params = tempParams;
                break;
            }
        }

        // إخفاء القائمة المتنقلة للموبايل تلقائياً عند الانتقال
        const nav = document.getElementById("main-nav");
        if (nav) nav.classList.remove("show");

        // استدعاء الصفحة إذا كانت موجودة، أو التوجيه للرئيسية
        if (matchedRoute) {
            try {
                await matchedRoute(params);
            } catch (error) {
                console.error("Route navigation error:", error);
                showToast("خطأ في التحميل", "تعذر تحميل الصفحة المطلوبة بشكل صحيح", "danger");
            }
        } else {
            console.warn("Route not found:", hashPath);
            if (this.routes["/404"]) {
                await this.routes["/404"]({ path: hashPath });
            } else {
                window.location.hash = "#/";
            }
        }
    },

    // تشغيل الموجه
    init() {
        window.addEventListener("hashchange", () => this.resolve());
        window.addEventListener("load", () => this.resolve());
    }
};
