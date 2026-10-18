#!/usr/bin/env python3
"""LightPi shell 0.1 - Android-inspired touch launcher for Raspberry Pi.

Pure Python + Tkinter (no third-party packages). Runs under labwc/XWayland.
Features: lock screen, home screen, Wi-Fi (NetworkManager), file manager,
settings, on-screen keyboard and a Chromium launcher.
"""
import hashlib
import json
import os
import queue
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from urllib.parse import quote_plus

VERSION = "0.1"
CONFIG_DIR = Path.home() / ".config" / "lightpi"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = Path.home() / "lightpi.log"

BG = "#0F1419"
SURFACE = "#1B232C"
SURFACE2 = "#2A3643"
ACCENT = "#4FC3F7"
TEXT = "#E8EAED"
MUTED = "#9AA0A6"
DANGER = "#EF5350"
OK = "#66BB6A"

APP_COLORS = {
    "wifi": "#1E88E5",
    "files": "#FB8C00",
    "browser": "#43A047",
    "settings": "#8E24AA",
    "lock": "#546E7A",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg))


def hash_pin(pin, salt):
    return hashlib.sha256((salt + pin).encode()).hexdigest()


def run(cmd, timeout=25):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + ((r.stderr or "") if r.returncode else "")
        return r.returncode, out.strip()
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def split_nmcli(line):
    """Split an `nmcli -t` line on unescaped colons."""
    parts, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def cpu_temp():
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except Exception:
        return None


def mem_info():
    try:
        d = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":")
            d[k] = int(v.split()[0]) * 1024
        total, avail = d["MemTotal"], d["MemAvailable"]
        return total, total - avail
    except Exception:
        return None, None


def device_model():
    try:
        return Path("/proc/device-tree/model").read_bytes().decode().strip("\x00 \n")
    except Exception:
        return "Unknown device"


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class _OffsetCanvas:
    """Proxy that shifts every drawing call on a canvas by (dx, dy)."""

    def __init__(self, cv, dx, dy):
        self.cv, self.dx, self.dy = cv, dx, dy

    def _shift(self, args):
        return [a + (self.dx if i % 2 == 0 else self.dy) for i, a in enumerate(args)]

    def create_arc(self, *a, **k):
        return self.cv.create_arc(*self._shift(a), **k)

    def create_oval(self, *a, **k):
        return self.cv.create_oval(*self._shift(a), **k)

    def create_line(self, *a, **k):
        return self.cv.create_line(*self._shift(a), **k)

    def create_polygon(self, *a, **k):
        return self.cv.create_polygon(*self._shift(a), **k)

    def create_rectangle(self, *a, **k):
        return self.cv.create_rectangle(*self._shift(a), **k)


def draw_glyph(cv, name, size, fg="#FFFFFF", bgc=None):
    """Draw a simple icon glyph inside a size x size box."""
    s = size
    lw = max(2, int(s * 0.07))
    cx = s / 2
    if name == "wifi":
        cy = s * 0.70
        for r in (0.36, 0.25, 0.14):
            cv.create_arc(cx - s * r, cy - s * r, cx + s * r, cy + s * r,
                          start=45, extent=90, style="arc", outline=fg, width=lw)
        cv.create_oval(cx - s * .05, cy - s * .05, cx + s * .05, cy + s * .05,
                       fill=fg, outline=fg)
    elif name == "files":
        pts = [.20, .30, .42, .30, .48, .38, .80, .38, .80, .74, .20, .74]
        cv.create_polygon(*[p * s for p in pts], fill=fg, outline=fg)
    elif name == "browser":
        cv.create_oval(.22 * s, .22 * s, .78 * s, .78 * s, outline=fg, width=lw)
        cv.create_oval(.38 * s, .22 * s, .62 * s, .78 * s, outline=fg, width=max(1, lw - 1))
        cv.create_line(.22 * s, cx, .78 * s, cx, fill=fg, width=max(1, lw - 1))
    elif name == "settings":
        for y, kx in ((.32, .38), (.50, .62), (.68, .46)):
            cv.create_line(.22 * s, y * s, .78 * s, y * s, fill=fg, width=lw)
            r = .075 * s
            cv.create_oval(kx * s - r, y * s - r, kx * s + r, y * s + r,
                           fill=fg, outline=bgc or fg, width=lw)
    elif name == "lock":
        cv.create_rectangle(.30 * s, .46 * s, .70 * s, .76 * s, fill=fg, outline=fg)
        cv.create_arc(.36 * s, .22 * s, .64 * s, .66 * s, start=0, extent=180,
                      style="arc", outline=fg, width=lw)
    elif name == "back":
        cv.create_polygon(.62 * s, .22 * s, .62 * s, .78 * s, .28 * s, .50 * s,
                          fill=fg, outline=fg)
    elif name == "home":
        cv.create_oval(.24 * s, .24 * s, .76 * s, .76 * s, outline=fg, width=lw + 1)


# --------------------------------------------------------------------------
# widgets
# --------------------------------------------------------------------------
class ScrollList(tk.Frame):
    """Touch-scrollable list of tappable rows (drag to scroll, tap to select)."""

    def __init__(self, app, parent, on_select):
        super().__init__(parent, bg=SURFACE)
        self.app = app
        self.on_select = on_select
        self.cv = tk.Canvas(self, bg=SURFACE, highlightthickness=0, bd=0,
                            yscrollincrement=app.S(40))
        self.cv.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=SURFACE)
        self.win = self.cv.create_window(0, 0, window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self.win, width=e.width))
        self.inner.bind("<Configure>",
                        lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self._bind_wheel(self.cv)
        self.press_y = 0
        self.dragging = False
        self.pressed = None

    def _bind_wheel(self, w):
        w.bind("<Button-4>", lambda e: self.cv.yview_scroll(-2, "units"))
        w.bind("<Button-5>", lambda e: self.cv.yview_scroll(2, "units"))

    def set_items(self, items):
        for w in self.inner.winfo_children():
            w.destroy()
        S = self.app.S
        if not items:
            tk.Label(self.inner, text="Nothing here", bg=SURFACE, fg=MUTED,
                     font=self.app.font(20), pady=S(20)).pack(fill="x")
        for i, text in enumerate(items):
            lbl = tk.Label(self.inner, text=text, anchor="w", bg=SURFACE, fg=TEXT,
                           font=self.app.font(21), padx=S(18), pady=S(15))
            lbl.pack(fill="x")
            tk.Frame(self.inner, bg=SURFACE2, height=1).pack(fill="x")
            lbl.bind("<ButtonPress-1>", lambda e, i=i, l=lbl: self._press(e, i, l))
            lbl.bind("<B1-Motion>", self._motion)
            lbl.bind("<ButtonRelease-1>", self._release)
            self._bind_wheel(lbl)
        self.cv.yview_moveto(0)

    def _press(self, e, i, lbl):
        self.press_y = e.y_root
        self.dragging = False
        self.pressed = (i, lbl)
        lbl.configure(bg=SURFACE2)
        self.cv.scan_mark(0, e.y_root)

    def _motion(self, e):
        if abs(e.y_root - self.press_y) > self.app.S(10):
            if not self.dragging and self.pressed:
                try:
                    self.pressed[1].configure(bg=SURFACE)
                except tk.TclError:
                    pass
            self.dragging = True
        if self.dragging:
            self.cv.scan_dragto(0, e.y_root, gain=1)

    def _release(self, e):
        if not self.pressed:
            return
        idx, lbl = self.pressed
        self.pressed = None
        try:
            lbl.configure(bg=SURFACE)
        except tk.TclError:
            pass
        if not self.dragging:
            self.on_select(idx)


class OSK(tk.Frame):
    """On-screen keyboard docked above the navigation bar."""

    def __init__(self, app):
        super().__init__(app.root, bg=SURFACE, padx=app.S(6), pady=app.S(6))
        self.app = app
        self.target = None
        self.on_enter = None
        self.layer = "abc"
        self.shift = False
        self.shown = False

    def show(self, target, on_enter=None, numeric=False):
        if target is not self.target:
            self.layer = "123" if numeric else "abc"
            self.shift = False
        self.target = target
        self.on_enter = on_enter
        self._build()
        if not self.shown:
            self.pack(side="bottom", fill="x", after=self.app.nav)
            self.shown = True

    def hide(self):
        if self.shown:
            self.pack_forget()
            self.shown = False
        self.target = None

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        for c in range(20):
            self.columnconfigure(c, weight=1, uniform="k")
        if self.layer == "123":
            rows = ["1234567890", "@#$%&-+()/", "*\"':;!?"]
        else:
            rows = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
            if self.shift:
                rows = [r.upper() for r in rows]
        for i, ch in enumerate(rows[0]):
            self._key(ch, 0, i * 2, 2)
        off = 0 if self.layer == "123" else 1
        for i, ch in enumerate(rows[1]):
            self._key(ch, 1, off + i * 2, 2)
        if self.layer == "123":
            tk.Frame(self, bg=SURFACE).grid(row=2, column=0, columnspan=3)
        else:
            self._key("Shift", 2, 0, 3, special="SHIFT",
                      color=ACCENT if self.shift else SURFACE2)
        for i, ch in enumerate(rows[2]):
            self._key(ch, 2, 3 + i * 2, 2)
        self._key("Del", 2, 17, 3, special="BS", color=SURFACE2)
        self._key("abc" if self.layer == "123" else "?123", 3, 0, 3,
                  special="LAYER", color=SURFACE2)
        self._key(",", 3, 3, 2)
        self._key("Space", 3, 5, 8, special="SPACE")
        self._key(".", 3, 13, 2)
        self._key("Done", 3, 15, 5, special="ENTER", color=ACCENT)

    def _key(self, label, row, col, span, special=None, color="#34414F"):
        fg = "#000000" if color == ACCENT else TEXT
        b = tk.Button(self, text=label, bg=color, fg=fg, activebackground=ACCENT,
                      activeforeground="#000000", bd=0, highlightthickness=0,
                      relief="flat", font=self.app.font(22),
                      command=lambda: self.press(special or label))
        b.grid(row=row, column=col, columnspan=span, sticky="nsew",
               padx=self.app.S(3), pady=self.app.S(3), ipady=self.app.S(8))

    def press(self, key):
        t = self.target
        if key == "SHIFT":
            self.shift = not self.shift
            self._build()
            return
        if key == "LAYER":
            self.layer = "abc" if self.layer == "123" else "123"
            self._build()
            return
        if key == "ENTER":
            if self.on_enter:
                self.on_enter()
            else:
                self.hide()
            return
        if t is None:
            return
        try:
            if key == "BS":
                pos = t.index(tk.INSERT)
                if pos > 0:
                    t.delete(pos - 1)
            elif key == "SPACE":
                t.insert(tk.INSERT, " ")
            else:
                t.insert(tk.INSERT, key)
                if self.shift and self.layer == "abc":
                    self.shift = False
                    self._build()
        except tk.TclError:
            pass


class NavBar(tk.Canvas):
    """Android-style bottom navigation: back / home / lock."""

    def __init__(self, app):
        super().__init__(app.root, bg=SURFACE, height=app.S(58),
                         highlightthickness=0, bd=0)
        self.app = app
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonRelease-1>", self.click)

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        size = int(h * 0.62)
        for i, name in enumerate(("back", "home", "lock")):
            cx = w * (i * 2 + 1) / 6
            draw_glyph(_OffsetCanvas(self, cx - size / 2, (h - size) / 2),
                       name, size, fg=TEXT)

    def click(self, e):
        third = self.winfo_width() / 3
        if e.x < third:
            self.app.go_back()
        elif e.x < 2 * third:
            self.app.go_home()
        else:
            self.app.lock()


# --------------------------------------------------------------------------
# main app
# --------------------------------------------------------------------------
class App:
    def __init__(self, fullscreen=True, size=None):
        self.root = tk.Tk()
        self.root.title("LightPi")
        self.root.configure(bg=BG)
        self.root.report_callback_exception = self._log_exc
        if size:
            self.root.geometry(f"{size[0]}x{size[1]}+0+0")
        self.sw = size[0] if size else self.root.winfo_screenwidth()
        self.sh = size[1] if size else self.root.winfo_screenheight()
        self.scale = min(2.5, max(0.8, self.sh / 720))
        fams = set(tkfont.families())
        self.family = "Roboto" if "Roboto" in fams else "DejaVu Sans"
        self.cfg = load_config()
        self.q = queue.Queue()
        self.history = []
        self.current = None
        self.child = None
        self.ssid = ""
        self.live = []          # labels refreshed by the clock tick
        self.lock_frame = None
        self.nets = []
        self.wifi_enabled = True
        self.tick_n = 0

        self._build_chrome()
        if fullscreen and not size:
            self.root.attributes("-fullscreen", True)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.show(self.page_home, push=False)
        self.lock()
        self._tick()
        self._poll()

    # ---- infrastructure --------------------------------------------------
    def S(self, v):
        return int(v * self.scale)

    def font(self, px, bold=False):
        return (self.family, -self.S(px), "bold" if bold else "normal")

    def _log_exc(self, exc, val, tb):
        import traceback
        try:
            with open(LOG_FILE, "a") as fh:
                fh.write("".join(traceback.format_exception(exc, val, tb)))
        except OSError:
            pass

    def bg(self, fn, cb=None):
        def work():
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001
                res = exc
            self.q.put((cb, res))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                cb, res = self.q.get_nowait()
                if cb:
                    cb(res)
        except queue.Empty:
            pass
        if self.child is not None and self.child.poll() is not None:
            self.child = None
            self.root.deiconify()
            self.root.attributes("-fullscreen", True)
        self.root.after(120, self._poll)

    def _build_chrome(self):
        S = self.S
        self.status = tk.Frame(self.root, bg=BG, height=S(40))
        self.status.pack(side="top", fill="x")
        self.status.pack_propagate(False)
        self.status_clock = tk.Label(self.status, text="", bg=BG, fg=TEXT,
                                     font=self.font(20, True), padx=S(18))
        self.status_clock.pack(side="left")
        self.status_right = tk.Label(self.status, text="", bg=BG, fg=MUTED,
                                     font=self.font(18), padx=S(18))
        self.status_right.pack(side="right")
        self.nav = NavBar(self)
        self.nav.pack(side="bottom", fill="x")
        self.kb = OSK(self)
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(side="top", fill="both", expand=True)

    def _tick(self):
        now = time.strftime("%H:%M")
        date = time.strftime("%A, %d %B")
        self.status_clock.configure(text=now)
        if self.tick_n % 15 == 0:
            self.bg(self._read_status, self._set_status)
        self.tick_n += 1
        for key, w in list(self.live):
            try:
                w.configure(text=now if key == "time" else date)
            except tk.TclError:
                self.live.remove((key, w))
        self.root.after(1000, self._tick)

    def _read_status(self):
        rc, out = run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=8)
        ssid = ""
        if rc == 0:
            for line in out.splitlines():
                p = split_nmcli(line)
                if p and p[0] == "yes":
                    ssid = p[1]
                    break
        return ssid, cpu_temp()

    def _set_status(self, res):
        if isinstance(res, Exception):
            return
        ssid, t = res
        self.ssid = ssid
        txt = ssid if ssid else "No Wi-Fi"
        if t is not None:
            txt += f"   {t:.0f}\u00b0C"
        self.status_right.configure(text=txt)

    # ---- navigation ------------------------------------------------------
    def show(self, builder, *args, push=True):
        if push and self.current:
            self.history.append(self.current)
        self.kb.hide()
        for w in self.content.winfo_children():
            w.destroy()
        self.live = [(k, w) for k, w in self.live if w.winfo_exists()]
        self.current = (builder, args)
        builder(*args)

    def go_back(self):
        if self.lock_frame:
            return
        if self.history:
            builder, args = self.history.pop()
            self.show(builder, *args, push=False)
        else:
            self.go_home()

    def go_home(self):
        if self.lock_frame:
            return
        self.history.clear()
        self.show(self.page_home, push=False)

    # ---- UI helpers ------------------------------------------------------
    def button(self, parent, text, cmd, kind="normal"):
        colors = {"normal": (SURFACE2, TEXT), "accent": (ACCENT, "#000000"),
                  "danger": (DANGER, "#FFFFFF"), "ok": (OK, "#000000")}
        bgc, fgc = colors.get(kind, colors["normal"])
        return tk.Button(parent, text=text, command=cmd, bg=bgc, fg=fgc,
                         activebackground=ACCENT, activeforeground="#000000",
                         bd=0, relief="flat", highlightthickness=0,
                         font=self.font(20), padx=self.S(22), pady=self.S(12))

    def entry(self, parent, secret=False, on_enter=None, numeric=False, width=24):
        e = tk.Entry(parent, bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
                     relief="flat", font=self.font(22), width=width,
                     show="*" if secret else "", highlightthickness=2,
                     highlightbackground=SURFACE2, highlightcolor=ACCENT)

        def show_kb(_e=None):
            self.kb.show(e, on_enter, numeric)

        e.bind("<FocusIn>", show_kb)
        e.bind("<Button-1>", show_kb)
        if on_enter:
            e.bind("<Return>", lambda _e: on_enter())
        return e

    def header(self, parent, title):
        tk.Label(parent, text=title, bg=BG, fg=TEXT, font=self.font(32, True),
                 anchor="w").pack(fill="x", padx=self.S(24), pady=(self.S(10), self.S(6)))

    def dialog(self, title, message="", entry=None, buttons=None):
        """Modal card over the content area. entry: None | 'text' | 'secret' | 'pin'.

        buttons: list of (label, callback(value), kind) - callback may be None.
        """
        S = self.S
        buttons = buttons or [("OK", None, "accent")]
        norm = [b if len(b) == 3 else (b[0], b[1], "normal") for b in buttons]
        scrim = tk.Frame(self.content, bg=BG)
        scrim.place(x=0, y=0, relwidth=1, relheight=1)
        card = tk.Frame(scrim, bg=SURFACE, padx=S(28), pady=S(22))
        card.place(relx=0.5, rely=0.04 if entry else 0.25, anchor="n")
        wrap = min(S(620), self.sw - S(120))
        tk.Label(card, text=title, bg=SURFACE, fg=TEXT, font=self.font(26, True),
                 wraplength=wrap, justify="left").pack(anchor="w")
        if message:
            tk.Label(card, text=message, bg=SURFACE, fg=MUTED, font=self.font(19),
                     wraplength=wrap, justify="left").pack(anchor="w", pady=(S(8), 0))
        ent = None

        def close(fn):
            val = ent.get() if ent else None
            scrim.destroy()
            self.kb.hide()
            if fn:
                fn(val)

        if entry:
            ent = self.entry(card, secret=entry in ("secret", "pin"),
                             numeric=(entry == "pin"), width=22)
            ent.pack(fill="x", pady=(S(14), 0), ipady=S(6))
            ent.bind("<Return>", lambda _e: close(norm[-1][1]))
            ent.focus_set()
            self.kb.show(ent, None, numeric=(entry == "pin"))
        row = tk.Frame(card, bg=SURFACE)
        row.pack(anchor="e", pady=(S(18), 0))
        for label, fn, kind in norm:
            self.button(row, label, lambda fn=fn: close(fn), kind).pack(side="left", padx=S(6))
        return scrim

    # ---- icons & home ----------------------------------------------------
    def icon(self, parent, name, size, bgc=BG):
        cv = tk.Canvas(parent, width=size, height=size, bg=bgc, highlightthickness=0)
        color = APP_COLORS.get(name, SURFACE2)
        round_rect(cv, 1, 1, size - 1, size - 1, size * 0.26, fill=color, outline=color)
        draw_glyph(cv, name, size, bgc=color)
        return cv

    def page_home(self):
        S = self.S
        c = self.content
        top = tk.Frame(c, bg=BG)
        top.pack(fill="x", pady=(S(18), S(6)))
        t = tk.Label(top, text=time.strftime("%H:%M"), bg=BG, fg=TEXT,
                     font=self.font(78, True))
        t.pack()
        d = tk.Label(top, text=time.strftime("%A, %d %B"), bg=BG, fg=MUTED,
                     font=self.font(24))
        d.pack()
        self.live += [("time", t), ("date", d)]

        apps = [("Wi-Fi", "wifi", lambda: self.show(self.page_wifi)),
                ("Files", "files", lambda: self.show(self.page_files)),
                ("Browser", "browser", lambda: self.show(self.page_browser)),
                ("Settings", "settings", lambda: self.show(self.page_settings)),
                ("Lock", "lock", self.lock)]
        grid = tk.Frame(c, bg=BG)
        grid.pack(expand=True)
        cols = max(3, min(5, self.sw // S(200)))
        size = S(104)
        for i, (label, name, cmd) in enumerate(apps):
            cell = tk.Frame(grid, bg=BG, padx=S(24), pady=S(14))
            cell.grid(row=i // cols, column=i % cols)
            ic = self.icon(cell, name, size)
            ic.pack()
            lb = tk.Label(cell, text=label, bg=BG, fg=TEXT, font=self.font(20))
            lb.pack(pady=(S(8), 0))
            for w in (cell, ic, lb):
                w.bind("<ButtonRelease-1>", lambda e, cmd=cmd: cmd())

    # ---- lock screen -----------------------------------------------------
    def lock(self):
        if self.lock_frame:
            return
        S = self.S
        self.kb.hide()
        f = tk.Frame(self.root, bg=BG)
        f.place(x=0, y=0, relwidth=1, relheight=1)
        f.lift()
        self.lock_frame = f
        inner = tk.Frame(f, bg=BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        t = tk.Label(inner, text=time.strftime("%H:%M"), bg=BG, fg=TEXT,
                     font=self.font(110, True))
        t.pack()
        d = tk.Label(inner, text=time.strftime("%A, %d %B"), bg=BG, fg=MUTED,
                     font=self.font(28))
        d.pack()
        self.live += [("time", t), ("date", d)]
        if self.cfg.get("pin_hash"):
            self.pin_buf = ""
            self.pin_msg = tk.Label(inner, text="Enter PIN", bg=BG, fg=MUTED,
                                    font=self.font(22))
            self.pin_msg.pack(pady=(S(20), S(4)))
            self.pin_dots = tk.Label(inner, text=" ", bg=BG, fg=ACCENT, font=self.font(34))
            self.pin_dots.pack(pady=(0, S(8)))
            pad = tk.Frame(inner, bg=BG)
            pad.pack()
            keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Del", "0", "OK"]
            for i, k in enumerate(keys):
                kind = "accent" if k == "OK" else "normal"
                b = self.button(pad, k, lambda k=k: self._pin_key(k), kind)
                b.configure(width=4, pady=S(8))
                b.grid(row=i // 3, column=i % 3, padx=S(5), pady=S(4))
        else:
            tk.Label(inner, text="Tap to unlock", bg=BG, fg=ACCENT,
                     font=self.font(24)).pack(pady=(S(30), 0))
            for w in (f, inner, t, d):
                w.bind("<ButtonRelease-1>", lambda e: self.unlock())

    def _pin_key(self, k):
        if k == "Del":
            self.pin_buf = self.pin_buf[:-1]
        elif k == "OK":
            salt = self.cfg.get("pin_salt", "")
            if hash_pin(self.pin_buf, salt) == self.cfg.get("pin_hash"):
                self.unlock()
                return
            self.pin_buf = ""
            self.pin_msg.configure(text="Wrong PIN", fg=DANGER)
        else:
            if len(self.pin_buf) < 8:
                self.pin_buf += k
            self.pin_msg.configure(text="Enter PIN", fg=MUTED)
        self.pin_dots.configure(text=("\u25cf " * len(self.pin_buf)) or " ")

    def unlock(self):
        if self.lock_frame:
            self.lock_frame.destroy()
            self.lock_frame = None
            self.live = [(k, w) for k, w in self.live if w.winfo_exists()]

    # ---- Wi-Fi -----------------------------------------------------------
    def page_wifi(self):
        S = self.S
        c = self.content
        self.header(c, "Wi-Fi")
        bar = tk.Frame(c, bg=BG)
        bar.pack(fill="x", padx=S(24), pady=(0, S(8)))
        self.wifi_status = tk.Label(bar, text="Scanning...", bg=BG, fg=MUTED,
                                    font=self.font(20), anchor="w")
        self.wifi_status.pack(side="left", fill="x", expand=True)
        self.wifi_toggle = self.button(bar, "Turn off", self._wifi_toggle)
        self.wifi_toggle.pack(side="right", padx=(S(8), 0))
        self.button(bar, "Refresh", self._wifi_scan, "accent").pack(side="right")
        self.wifi_list = ScrollList(self, c, self._wifi_select)
        self.wifi_list.pack(fill="both", expand=True, padx=S(24), pady=(0, S(12)))
        self._wifi_scan()

    @staticmethod
    def _alive(w):
        try:
            return bool(w.winfo_exists())
        except tk.TclError:
            return False

    def _wifi_scan(self):
        if not self._alive(self.wifi_status):
            return
        self.wifi_status.configure(text="Scanning...", fg=MUTED)

        def work():
            rc, out = run(["nmcli", "radio", "wifi"], timeout=8)
            if rc != 0:
                return ("error", out)
            if out.strip() != "enabled":
                return ("off", [])
            rc, out = run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                           "dev", "wifi", "list", "--rescan", "yes"], timeout=30)
            if rc != 0:
                return ("error", out)
            seen, nets = set(), []
            for line in out.splitlines():
                p = split_nmcli(line)
                if len(p) < 4 or not p[1] or p[1] in seen:
                    continue
                seen.add(p[1])
                nets.append({"inuse": p[0] == "*", "ssid": p[1],
                             "signal": int(p[2] or 0),
                             "secured": p[3] not in ("", "--")})
            nets.sort(key=lambda n: (not n["inuse"], -n["signal"]))
            return ("ok", nets)

        self.bg(work, self._wifi_done)

    def _wifi_done(self, res):
        if not self._alive(self.wifi_status):
            return
        if isinstance(res, Exception):
            res = ("error", str(res))
        state, data = res
        if state == "error":
            self.wifi_status.configure(text=f"Wi-Fi unavailable: {data[:60]}", fg=DANGER)
            self.wifi_list.set_items([])
            return
        self.wifi_enabled = state == "ok"
        self.wifi_toggle.configure(text="Turn off" if self.wifi_enabled else "Turn on")
        if state == "off":
            self.wifi_status.configure(text="Wi-Fi is turned off", fg=MUTED)
            self.nets = []
            self.wifi_list.set_items([])
            return
        self.nets = data
        cur = next((n["ssid"] for n in data if n["inuse"]), None)
        self.wifi_status.configure(
            text=f"Connected to {cur}" if cur else "Not connected",
            fg=OK if cur else MUTED)
        items = []
        for n in data:
            mark = "\u25cf " if n["inuse"] else "    "
            sec = "   (secured)" if n["secured"] else ""
            items.append(f"{mark}{n['ssid']}    {n['signal']}%{sec}")
        self.wifi_list.set_items(items)

    def _wifi_toggle(self):
        cmd = "off" if self.wifi_enabled else "on"
        self.bg(lambda: run(["nmcli", "radio", "wifi", cmd]),
                lambda _r: self.root.after(1500, self._wifi_scan))

    def _wifi_select(self, idx):
        n = self.nets[idx]
        if n["inuse"]:
            self.dialog(n["ssid"], "You are connected to this network.", buttons=[
                ("Close", None), ("Disconnect", lambda _v: self._wifi_disconnect(), "danger")])
        elif n["secured"]:
            self.dialog(f"Connect to {n['ssid']}", "Enter the Wi-Fi password.",
                        entry="secret", buttons=[
                            ("Cancel", None),
                            ("Connect", lambda pw: self._wifi_connect(n["ssid"], pw), "accent")])
        else:
            self._wifi_connect(n["ssid"], None)

    def _wifi_disconnect(self):
        ssid = self.ssid
        self.bg(lambda: run(["nmcli", "connection", "down", "id", ssid]),
                lambda _r: self._wifi_scan())

    def _wifi_connect(self, ssid, password):
        if self._alive(self.wifi_status):
            self.wifi_status.configure(text=f"Connecting to {ssid}...", fg=ACCENT)

        def work():
            if not password:
                rc, out = run(["nmcli", "-t", "-f", "NAME", "connection", "show"], timeout=8)
                saved = rc == 0 and ssid in [split_nmcli(x)[0] for x in out.splitlines()]
                if saved:
                    return run(["nmcli", "connection", "up", "id", ssid], timeout=45)
                return run(["nmcli", "dev", "wifi", "connect", ssid], timeout=45)
            rc, out = run(["nmcli", "dev", "wifi", "connect", ssid, "password", password],
                          timeout=45)
            if rc != 0:
                run(["nmcli", "connection", "delete", "id", ssid], timeout=8)
            return rc, out

        def done(res):
            if isinstance(res, Exception):
                res = (1, str(res))
            rc, out = res
            if not self._alive(self.wifi_status):
                return
            if rc == 0:
                self._wifi_scan()
            else:
                self.wifi_status.configure(text=f"Could not connect: {out[:70]}", fg=DANGER)

        self.bg(work, done)

    # ---- files -----------------------------------------------------------
    def page_files(self, path=None):
        S = self.S
        c = self.content
        p = Path(path) if path else Path.home()
        bar = tk.Frame(c, bg=BG)
        bar.pack(fill="x", padx=S(24), pady=(S(12), S(8)))
        up = self.button(bar, "Up", lambda: self.show(self.page_files, str(p.parent), push=False))
        up.pack(side="left")
        if p == p.parent:
            up.configure(state="disabled")
        tk.Label(bar, text=str(p), bg=BG, fg=TEXT, font=self.font(22, True),
                 anchor="w").pack(side="left", padx=S(16))
        entries = []
        err = None
        try:
            entries = sorted((e for e in p.iterdir() if not e.name.startswith(".")),
                             key=lambda e: (not self._isdir(e), e.name.lower()))
        except OSError as exc:
            err = str(exc)

        def select(i):
            e = entries[i]
            if self._isdir(e):
                self.show(self.page_files, str(e))
            else:
                self.show(self.page_view, str(e))

        lst = ScrollList(self, c, select)
        lst.pack(fill="both", expand=True, padx=S(24), pady=(0, S(12)))
        items = []
        for e in entries:
            if self._isdir(e):
                items.append(f"\u25b8  {e.name}/")
            else:
                try:
                    items.append(f"    {e.name}     {fmt_size(e.stat().st_size)}")
                except OSError:
                    items.append(f"    {e.name}")
        lst.set_items(items)
        if err:
            self.dialog("Cannot open folder", err)

    @staticmethod
    def _isdir(e):
        try:
            return e.is_dir()
        except OSError:
            return False

    def page_view(self, path):
        S = self.S
        c = self.content
        p = Path(path)
        bar = tk.Frame(c, bg=BG)
        bar.pack(fill="x", padx=S(24), pady=(S(12), S(8)))
        tk.Label(bar, text=p.name, bg=BG, fg=TEXT, font=self.font(24, True),
                 anchor="w").pack(side="left")
        self.button(bar, "Delete", lambda: self._confirm_delete(p), "danger").pack(side="right")
        body = tk.Frame(c, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=S(24), pady=(0, S(12)))
        try:
            size = p.stat().st_size
            if size > 400_000:
                raise ValueError(f"File is too large to preview ({fmt_size(size)}).")
            text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            text = "(Binary file - no preview available.)"
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
        sb = tk.Scrollbar(body, width=S(26))
        tx = tk.Text(body, bg=SURFACE, fg=TEXT, font=("DejaVu Sans Mono", -S(18)), bd=0,
                     highlightthickness=0, wrap="word", padx=S(12), pady=S(10),
                     yscrollcommand=sb.set)
        sb.configure(command=tx.yview)
        sb.pack(side="right", fill="y")
        tx.pack(side="left", fill="both", expand=True)
        tx.insert("1.0", text)
        tx.configure(state="disabled")
        tx.bind("<ButtonPress-1>", lambda e: tx.scan_mark(e.x, e.y))
        tx.bind("<B1-Motion>", lambda e: tx.scan_dragto(e.x, e.y, gain=2))

    def _confirm_delete(self, p):
        def do(_v):
            try:
                p.unlink()
            except OSError as exc:
                self.dialog("Could not delete", str(exc))
                return
            self.go_back()
        self.dialog("Delete file?", f"{p.name} will be permanently deleted.", buttons=[
            ("Cancel", None), ("Delete", do, "danger")])

    # ---- browser ---------------------------------------------------------
    def page_browser(self):
        S = self.S
        c = self.content
        self.header(c, "Browser")
        box = tk.Frame(c, bg=BG)
        box.pack(fill="x", padx=S(24))
        self.url_entry = self.entry(box, on_enter=self._browser_go, width=40)
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=S(8))
        self.url_entry.insert(0, self.cfg.get("homepage", "https://duckduckgo.com"))
        self.button(box, "Go", self._browser_go, "accent").pack(side="left", padx=(S(10), 0))
        tk.Label(c, text="Type a web address or a search, then tap Go.", bg=BG, fg=MUTED,
                 font=self.font(18), anchor="w").pack(fill="x", padx=S(24), pady=(S(10), S(6)))
        quick = tk.Frame(c, bg=BG)
        quick.pack(fill="x", padx=S(24), pady=S(6))
        for name, url in (("DuckDuckGo", "https://duckduckgo.com"),
                          ("Wikipedia", "https://wikipedia.org"),
                          ("OpenStreetMap", "https://openstreetmap.org"),
                          ("YouTube", "https://youtube.com")):
            self.button(quick, name, lambda u=url: self.launch_browser(u)).pack(
                side="left", padx=(0, S(10)), pady=S(4))
        if not self._browser_bin():
            tk.Label(c, text="Chromium is not installed on this system.", bg=BG,
                     fg=DANGER, font=self.font(20)).pack(padx=S(24), pady=S(20), anchor="w")

    @staticmethod
    def _browser_bin():
        return shutil.which("chromium") or shutil.which("chromium-browser")

    def _browser_go(self):
        self.launch_browser(self.url_entry.get().strip())

    def launch_browser(self, text):
        binary = self._browser_bin()
        if not binary:
            self.dialog("Browser missing", "Chromium is not installed.")
            return
        text = text or "https://duckduckgo.com"
        if "://" in text:
            url = text
        elif "." in text and " " not in text:
            url = "https://" + text
        else:
            url = "https://duckduckgo.com/?q=" + quote_plus(text)
        self.kb.hide()
        cmd = [binary, "--ozone-platform=wayland", "--start-maximized", "--no-first-run",
               "--password-store=basic", "--renderer-process-limit=2",
               "--disable-session-crashed-bubble", url]
        try:
            self.child = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.dialog("Could not start browser", str(exc))
            return
        self.root.withdraw()

    # ---- settings --------------------------------------------------------
    def page_settings(self):
        S = self.S
        c = self.content
        self.header(c, "Settings")
        wrap = tk.Frame(c, bg=BG)
        wrap.pack(fill="both", expand=True, padx=S(24), pady=(0, S(12)))
        wrap.columnconfigure(0, weight=3, uniform="s")
        wrap.columnconfigure(1, weight=2, uniform="s")
        wrap.rowconfigure(0, weight=1)

        about = tk.Frame(wrap, bg=SURFACE, padx=S(22), pady=S(16))
        about.grid(row=0, column=0, sticky="nsew", padx=(0, S(10)))
        tk.Label(about, text="About", bg=SURFACE, fg=ACCENT,
                 font=self.font(22, True)).pack(anchor="w", pady=(0, S(8)))
        total, used = mem_info()
        du = shutil.disk_usage("/")
        t = cpu_temp()
        rc, ips = run(["hostname", "-I"], timeout=4)
        rows = [("Device", device_model()),
                ("LightPi", f"v{VERSION}"),
                ("Hostname", socket.gethostname()),
                ("IP address", (ips.split()[0] if rc == 0 and ips else "not connected")),
                ("Wi-Fi", self.ssid or "not connected"),
                ("Memory", f"{fmt_size(used)} / {fmt_size(total)}" if total else "n/a"),
                ("Storage", f"{fmt_size(du.used)} / {fmt_size(du.total)}"),
                ("CPU temp", f"{t:.0f}\u00b0C" if t is not None else "n/a"),
                ("Kernel", os.uname().release)]
        for k, v in rows:
            r = tk.Frame(about, bg=SURFACE)
            r.pack(fill="x", pady=S(3))
            tk.Label(r, text=k, bg=SURFACE, fg=MUTED, font=self.font(19),
                     width=11, anchor="w").pack(side="left")
            tk.Label(r, text=v, bg=SURFACE, fg=TEXT, font=self.font(19),
                     anchor="w").pack(side="left")

        ctl = tk.Frame(wrap, bg=SURFACE, padx=S(22), pady=S(16))
        ctl.grid(row=0, column=1, sticky="nsew", padx=(S(10), 0))
        tk.Label(ctl, text="Controls", bg=SURFACE, fg=ACCENT,
                 font=self.font(22, True)).pack(anchor="w", pady=(0, S(8)))
        has_pin = bool(self.cfg.get("pin_hash"))
        self.button(ctl, "Change lock PIN" if has_pin else "Set lock PIN",
                    self._set_pin_dialog).pack(fill="x", pady=S(4))
        if has_pin:
            self.button(ctl, "Remove lock PIN", self._remove_pin).pack(fill="x", pady=S(4))
        self.button(ctl, "Restart LightPi", self._restart_shell).pack(fill="x", pady=S(4))
        self.button(ctl, "Reboot", lambda: self._power("reboot")).pack(fill="x", pady=S(4))
        self.button(ctl, "Shut down", lambda: self._power("poweroff"),
                    "danger").pack(fill="x", pady=S(4))

    def _set_pin_dialog(self):
        def save(val):
            if not val or not val.isdigit() or not 4 <= len(val) <= 8:
                self.dialog("Invalid PIN", "Use 4 to 8 digits.")
                return
            salt = secrets.token_hex(8)
            self.cfg["pin_salt"] = salt
            self.cfg["pin_hash"] = hash_pin(val, salt)
            save_config(self.cfg)
            self.show(self.page_settings, push=False)
        self.dialog("Set lock PIN", "Choose 4 to 8 digits.", entry="pin", buttons=[
            ("Cancel", None), ("Save", save, "accent")])

    def _remove_pin(self):
        self.cfg.pop("pin_hash", None)
        self.cfg.pop("pin_salt", None)
        save_config(self.cfg)
        self.show(self.page_settings, push=False)

    def _restart_shell(self):
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _power(self, action):
        def do(_v):
            rc, _ = run(["sudo", "-n", "systemctl", action], timeout=10)
            if rc != 0:
                run(["systemctl", action], timeout=10)
        label = "Reboot now?" if action == "reboot" else "Shut down now?"
        self.dialog(label, buttons=[("Cancel", None), ("Yes", do, "danger")])


def main():
    app = App()
    app.root.mainloop()


if __name__ == "__main__":
    main()
