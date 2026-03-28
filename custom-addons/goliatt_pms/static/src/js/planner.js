/** @odoo-module **/
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const CELL_WIDTH = 44;
const ROW_HEIGHT = 32;
const HEADER_HEIGHT = 52 + 42;
const LABEL_WIDTH = 140;
const DAYS_TO_SHOW = 28;

class PmsPlanner extends Component {
    static template = "goliatt_pms.PlannerView";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            dates: [],
            rooms: [],
            reservations: [],
            bars: [],
            periodLabel: "",
            startDate: null,
        });

        this._dragging = null;
        this._resizing = null;
        this._moved = false; // track if mouse actually moved during drag

        // Bind global handlers once
        this._onDocMouseMove = this._onDocMouseMove.bind(this);
        this._onDocMouseUp = this._onDocMouseUp.bind(this);

        onMounted(() => {
            this._setStartDate(this._today());
            this._loadData();
        });
    }

    // ── Date helpers ──────────────────────────────────────

    _today() {
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }
    _toISO(d) { return d.toISOString().slice(0, 10); }
    _addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r; }
    _diffDays(a, b) { return Math.round((b - a) / 86400000); }
    _dayNames() { return ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]; }
    _monthNames() { return ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]; }

    _setStartDate(d) {
        this.state.startDate = d;
        const dates = [];
        const today = this._toISO(this._today());
        for (let i = 0; i < DAYS_TO_SHOW; i++) {
            const dt = this._addDays(d, i);
            const dow = dt.getDay();
            dates.push({
                date: dt, iso: this._toISO(dt), dayNum: dt.getDate(),
                dayName: this._dayNames()[dow],
                isWeekend: dow === 0 || dow === 6,
                isToday: this._toISO(dt) === today,
            });
        }
        this.state.dates = dates;
        const end = this._addDays(d, DAYS_TO_SHOW - 1);
        this.state.periodLabel = `${this._monthNames()[d.getMonth()]} ${d.getDate()} — ${this._monthNames()[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
    }

    // ── Data loading ──────────────────────────────────────

    async _loadData() {
        const startISO = this._toISO(this.state.startDate);
        const endISO = this._toISO(this._addDays(this.state.startDate, DAYS_TO_SHOW));

        const rooms = await this.orm.searchRead("pms.room", [["active", "=", true]],
            ["name", "room_type_id", "floor", "status", "housekeeping_status"],
            { order: "name", limit: 200 });
        this.state.rooms = rooms.map(r => ({
            id: r.id, name: r.name,
            room_type: r.room_type_id ? r.room_type_id[1] : "",
            floor: r.floor, status: r.status,
        }));

        const reservations = await this.orm.searchRead("pms.reservation",
            [["checkin_date", "<", endISO], ["checkout_date", ">", startISO], ["state", "not in", ["cancelled"]]],
            ["name", "guest_id", "checkin_date", "checkout_date", "room_id", "room_type_id", "state", "adults", "nights", "daily_rate"],
            { order: "checkin_date", limit: 500 });
        this.state.reservations = reservations;
        this._computeBars();
    }

    _computeBars() {
        // Defer to next frame so the DOM cells are rendered
        requestAnimationFrame(() => this._computeBarsFromDOM());
    }

    _computeBarsFromDOM() {
        const bars = [];
        const startDate = this.state.startDate;
        const roomIndexMap = {};
        this.state.rooms.forEach((r, idx) => { roomIndexMap[r.id] = idx; });

        // Build a lookup of cell positions from actual DOM elements
        const container = document.querySelector(".pms-planner");
        if (!container) return;
        const containerRect = container.getBoundingClientRect();
        const scrollLeft = container.scrollLeft;
        const scrollTop = container.scrollTop;

        // Map: roomId -> { top, height } from DOM cells
        const roomPositions = {};
        // Map: dateIdx -> { left, width } from DOM cells
        const datePositions = {};

        const cells = container.querySelectorAll(".pms-planner-cell");
        for (const cell of cells) {
            const roomId = parseInt(cell.dataset.roomId);
            const dateStr = cell.dataset.date;
            if (!roomId || !dateStr) continue;

            const rect = cell.getBoundingClientRect();
            const relTop = rect.top - containerRect.top + scrollTop;
            const relLeft = rect.left - containerRect.left + scrollLeft;

            if (!roomPositions[roomId]) {
                roomPositions[roomId] = { top: relTop, height: rect.height };
            }

            const dateIdx = this.state.dates.findIndex(d => d.iso === dateStr);
            if (dateIdx >= 0 && !datePositions[dateIdx]) {
                datePositions[dateIdx] = { left: relLeft, width: rect.width };
            }
        }

        for (const res of this.state.reservations) {
            if (!res.room_id) continue;
            const roomId = res.room_id[0];
            const rp = roomPositions[roomId];
            if (!rp) continue;

            const checkin = new Date(res.checkin_date + "T00:00:00");
            const checkout = new Date(res.checkout_date + "T00:00:00");
            const startOffset = Math.max(0, this._diffDays(startDate, checkin));
            const endOffset = Math.min(DAYS_TO_SHOW, this._diffDays(startDate, checkout));
            if (endOffset <= 0 || startOffset >= DAYS_TO_SHOW) continue;

            const dp0 = datePositions[startOffset];
            const dp1 = datePositions[Math.min(endOffset - 1, DAYS_TO_SHOW - 1)];
            if (!dp0 || !dp1) continue;

            const left = dp0.left;
            const width = (dp1.left + dp1.width) - dp0.left - 2;
            const top = rp.top + 2;
            const barHeight = rp.height - 4;

            bars.push({
                id: res.id,
                left, top, width: Math.max(width, 20), barHeight,
                guestName: res.guest_id ? res.guest_id[1] : res.name,
                state: res.state, nights: res.nights,
                checkinDate: res.checkin_date, checkoutDate: res.checkout_date,
                roomId,
            });
        }
        this.state.bars = bars;
    }

    // ── Navigation ────────────────────────────────────────

    onPrevPeriod() { this._setStartDate(this._addDays(this.state.startDate, -14)); this._loadData(); }
    onNextPeriod() { this._setStartDate(this._addDays(this.state.startDate, 14)); this._loadData(); }
    onToday() { this._setStartDate(this._addDays(this._today(), -3)); this._loadData(); }
    onRefresh() { this._loadData(); }

    // ── Cell click → create reservation ───────────────────

    async onCellClick(ev) {
        if (this._moved) return; // was a drag, not a click
        const roomId = parseInt(ev.currentTarget.dataset.roomId);
        const dateStr = ev.currentTarget.dataset.date;
        if (!roomId || !dateStr) return;

        const room = await this.orm.read("pms.room", [roomId], ["room_type_id", "property_id"]);
        if (!room.length) return;

        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("New Reservation"),
            res_model: "pms.reservation",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_property_id: room[0].property_id[0],
                default_room_type_id: room[0].room_type_id[0],
                default_room_id: roomId,
                default_checkin_date: dateStr,
                default_checkout_date: this._toISO(this._addDays(new Date(dateStr + "T00:00:00"), 1)),
            },
        });
    }

    // ── Bar double-click → open reservation ───────────────

    onBarDblClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const resId = parseInt(ev.currentTarget.dataset.resId);
        if (!resId) return;

        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Reservation"),
            res_model: "pms.reservation",
            res_id: resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        });
    }

    // ── Drag start (bar mousedown) ────────────────────────

    onBarMouseDown(ev) {
        if (ev.target.classList.contains("resize-handle")) return;
        ev.preventDefault();
        ev.stopPropagation();

        const resId = parseInt(ev.currentTarget.dataset.resId);
        const bar = this.state.bars.find(b => b.id === resId);
        if (!bar || bar.state === "checked_out") return;

        this._moved = false;
        this._dragging = {
            resId,
            startX: ev.clientX,
            startY: ev.clientY,
            origLeft: bar.left,
            origTop: bar.top,
        };

        // Attach global listeners
        document.addEventListener("mousemove", this._onDocMouseMove);
        document.addEventListener("mouseup", this._onDocMouseUp);
        document.body.style.cursor = "grabbing";
        document.body.style.userSelect = "none";
    }

    // ── Resize start (handle mousedown) ───────────────────

    onResizeMouseDown(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        const resId = parseInt(ev.currentTarget.dataset.resId);
        const bar = this.state.bars.find(b => b.id === resId);
        if (!bar || bar.state === "checked_out") return;

        this._moved = false;
        this._resizing = {
            resId,
            startX: ev.clientX,
            origWidth: bar.width,
        };

        document.addEventListener("mousemove", this._onDocMouseMove);
        document.addEventListener("mouseup", this._onDocMouseUp);
        document.body.style.cursor = "ew-resize";
        document.body.style.userSelect = "none";
    }

    // ── Global mousemove (during drag or resize) ──────────

    _onDocMouseMove(ev) {
        this._moved = true;

        if (this._dragging) {
            const dx = ev.clientX - this._dragging.startX;
            const dy = ev.clientY - this._dragging.startY;
            const bar = this.state.bars.find(b => b.id === this._dragging.resId);
            if (bar) {
                bar.left = this._dragging.origLeft + dx;
                bar.top = this._dragging.origTop + dy;
            }
        }

        if (this._resizing) {
            const dx = ev.clientX - this._resizing.startX;
            const bar = this.state.bars.find(b => b.id === this._resizing.resId);
            if (bar) {
                bar.width = Math.max(CELL_WIDTH, this._resizing.origWidth + dx);
            }
        }
    }

    // ── Global mouseup (end drag or resize) ───────────────

    async _onDocMouseUp(ev) {
        // Always clean up global listeners first
        document.removeEventListener("mousemove", this._onDocMouseMove);
        document.removeEventListener("mouseup", this._onDocMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";

        if (this._dragging && this._moved) {
            const { resId } = this._dragging;
            const bar = this.state.bars.find(b => b.id === resId);
            if (bar) {
                // Find which cell the bar center lands on
                const centerX = ev.clientX;
                const centerY = ev.clientY;
                const cell = document.elementFromPoint(centerX, centerY);
                let newCheckin = null;
                let newRoom = null;
                if (cell && cell.classList.contains("pms-planner-cell")) {
                    newCheckin = cell.dataset.date;
                    const roomId = parseInt(cell.dataset.roomId);
                    newRoom = this.state.rooms.find(r => r.id === roomId);
                }
                if (!newCheckin || !newRoom) {
                    // Fallback: use pixel math
                    const container = document.querySelector(".pms-planner");
                    const containerRect = container ? container.getBoundingClientRect() : { left: 0, top: 0 };
                    const cells = container ? container.querySelectorAll(".pms-planner-cell") : [];
                    // Find nearest cell
                    let minDist = Infinity;
                    for (const c of cells) {
                        const r = c.getBoundingClientRect();
                        const cx = r.left + r.width / 2;
                        const cy = r.top + r.height / 2;
                        const dist = Math.abs(cx - centerX) + Math.abs(cy - centerY);
                        if (dist < minDist) {
                            minDist = dist;
                            newCheckin = c.dataset.date;
                            const rid = parseInt(c.dataset.roomId);
                            newRoom = this.state.rooms.find(rm => rm.id === rid);
                        }
                    }
                }

                if (newCheckin && newRoom) {
                    const res = this.state.reservations.find(r => r.id === resId);
                    if (res) {
                        const nights = res.nights || 1;
                        const newCheckout = this._toISO(this._addDays(new Date(newCheckin + "T00:00:00"), nights));
                        try {
                            await this.orm.write("pms.reservation", [resId], {
                                checkin_date: newCheckin,
                                checkout_date: newCheckout,
                                room_id: newRoom.id,
                            });
                            this.notification.add(_t("Reservation moved"), { type: "success" });
                        } catch (e) {
                            this.notification.add(_t("Could not move reservation"), { type: "danger" });
                        }
                    }
                }
            }
            this._dragging = null;
            await this._loadData();
            return;
        }
        this._dragging = null;

        if (this._resizing && this._moved) {
            const { resId } = this._resizing;
            const bar = this.state.bars.find(b => b.id === resId);
            if (bar) {
                const newNights = Math.max(1, Math.round(bar.width / CELL_WIDTH));
                const res = this.state.reservations.find(r => r.id === resId);
                if (res) {
                    const newCheckout = this._toISO(this._addDays(new Date(res.checkin_date + "T00:00:00"), newNights));
                    try {
                        await this.orm.write("pms.reservation", [resId], { checkout_date: newCheckout });
                        this.notification.add(_t("Stay adjusted to " + newNights + " nights"), { type: "success" });
                    } catch (e) {
                        this.notification.add(_t("Could not adjust stay"), { type: "danger" });
                    }
                }
            }
            this._resizing = null;
            await this._loadData();
            return;
        }
        this._resizing = null;

        // Always reset _moved so next cell click works
        setTimeout(() => { this._moved = false; }, 50);
    }

    // ── Stubs (grid-level — not used now) ─────────────────
    onCellMouseDown() {}
    onGridMouseMove() {}
    onGridMouseUp() {}
}

registry.category("actions").add("pms_planner", PmsPlanner);
