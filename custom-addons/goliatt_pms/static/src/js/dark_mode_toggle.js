/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";

function getColorScheme() {
    const parts = document.cookie.split(";").map(c => c.trim());
    for (const part of parts) {
        if (part.startsWith("color_scheme=")) {
            return part.substring(13);
        }
    }
    return "light";
}

function applyTheme(scheme) {
    // Bootstrap 5 dark mode activation
    document.documentElement.setAttribute("data-bs-theme", scheme);
    // Odoo also checks for this class
    document.body.classList.toggle("o_dark", scheme === "dark");
}

class DarkModeToggle extends Component {
    static template = "goliatt_pms.DarkModeToggle";
    static props = ["*"];

    setup() {
        this.state = useState({
            isDark: getColorScheme() === "dark",
        });
        onMounted(() => {
            // Apply theme on initial load based on cookie
            applyTheme(this.state.isDark ? "dark" : "light");
        });
    }

    toggleTheme() {
        const newScheme = this.state.isDark ? "light" : "dark";
        document.cookie = `color_scheme=${newScheme}; path=/; max-age=31536000`;
        this.state.isDark = !this.state.isDark;
        // Apply immediately via Bootstrap data attribute
        applyTheme(newScheme);
        // Also reload to get the proper dark CSS bundle from server
        window.location.reload(true);
    }
}

const systrayItem = {
    Component: DarkModeToggle,
};

registry.category("systray").add("DarkModeToggle", systrayItem, { sequence: 99 });

// Apply dark theme immediately on script load (before OWL mounts)
// This prevents flash of light theme
if (getColorScheme() === "dark") {
    document.documentElement.setAttribute("data-bs-theme", "dark");
}
