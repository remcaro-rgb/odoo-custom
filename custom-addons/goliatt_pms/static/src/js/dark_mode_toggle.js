/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { cookie } from "@web/core/browser/cookie";

class DarkModeToggle extends Component {
    static template = "goliatt_pms.DarkModeToggle";
    static props = ["*"];

    setup() {
        this.state = useState({
            isDark: cookie.get("color_scheme") === "dark",
        });
    }

    toggleTheme() {
        const newScheme = this.state.isDark ? "light" : "dark";
        cookie.set("color_scheme", newScheme);
        this.state.isDark = !this.state.isDark;
        window.location.reload();
    }
}

const systrayItem = {
    Component: DarkModeToggle,
};

registry.category("systray").add("DarkModeToggle", systrayItem, { sequence: 99 });
