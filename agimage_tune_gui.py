#!/usr/bin/env python3
"""AG Image Tune — self-contained Windows GUI (single file).

Everything is in this one file: the soft-glow effect, the folder-processing
loop, and the Tkinter interface. There are no imports from other project
modules and no path tricks, so it can be dropped anywhere and compiled into a
single .exe with PyInstaller:

    py -m pip install pillow pyinstaller
    pyinstaller --onefile --windowed --name AGImageTune agimage_tune_gui.py

The result is dist/AGImageTune.exe — one file, no Python required on the
target machine.
"""
import json
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageTk

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

IMAGE_TYPES = [
    ("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
    ("All files", "*.*"),
]


# Colour palettes for the two UI themes. ttk's 'clam' engine honours these
# overrides on every platform, unlike the native 'vista' theme (which ignores
# most colour changes on Windows).
THEMES = {
    "light": {
        "label": "Light",
        "bg": "#f4f4f4",
        "fg": "#1b1b1b",
        "surface": "#ffffff",
        "surface_alt": "#e7e7e7",
        "border": "#c2c2c2",
        "accent": "#2563eb",
        "accent_fg": "#ffffff",
        "hover": "#e0e6f0",
        "select_bg": "#2563eb",
        "select_fg": "#ffffff",
        "disabled_fg": "#9e9e9e",
        "text_bg": "#ffffff",
        "text_fg": "#1b1b1b",
        "trough": "#e0e0e0",
    },
    "dark": {
        "label": "Dark",
        "bg": "#1e1e1e",
        "fg": "#e6e6e6",
        "surface": "#2d2d2d",
        "surface_alt": "#3a3a3a",
        "border": "#4a4a4a",
        "accent": "#4f9cf9",
        "accent_fg": "#0b0b0b",
        "hover": "#3d4652",
        "select_bg": "#2f6fb3",
        "select_fg": "#ffffff",
        "disabled_fg": "#6e6e6e",
        "text_bg": "#1e1e1e",
        "text_fg": "#e6e6e6",
        "trough": "#333333",
    },
}
DEFAULT_THEME = "light"

# Theme choice persists here; a home-dir path survives PyInstaller one-file
# builds (which unpack __file__ into a temp dir at runtime).
CONFIG_PATH = Path.home() / ".agimage_tune.json"


# ---------------------------------------------------------------------------
# LAB chroma curve — a Python port of this GIMP workflow:
#     Colors > Components > Decompose  (model LAB, "Decompose to layers")
#     Curves on layer "A" and layer "B"  (e.g. the points 30->0 and 220->255)
#     Colors > Components > Compose
# The same functions plus a command-line front end live in lab_tune.py, which
# test_lab_tune.py exercises; keep the two copies in sync.
#
# Pillow's "LAB" mode is D50-referenced CIE Lab encoded as L* * 255/100,
# a* + 128, b* + 128 — the same numbers GIMP puts in the "L", "A" and "B"
# layers, so the control points can be typed straight across.
# ---------------------------------------------------------------------------
IDENTITY_POINTS = ((0, 0), (255, 255))
DEFAULT_LAB_POINTS = ((30, 0), (220, 255))


def build_curve_lut(points, size=256):
    """Piecewise-linear curve -> list of `size` output values.

    `points` is an iterable of (x, y) pairs in 0..255, x strictly increasing.
    Missing endpoints x=0 and x=size-1 are added as (0,0) and (255,255),
    matching GIMP's Curves behaviour.
    """
    pts = sorted((int(x), int(y)) for x, y in points)

    seen = set()
    clean = []
    for x, y in pts:
        if x in seen:
            raise ValueError(f"duplicate control point at x={x}")
        seen.add(x)
        clean.append((x, y))
    pts = clean

    if pts and pts[0][0] < 0:
        raise ValueError("control point x must be >= 0")
    if pts and pts[-1][0] > size - 1:
        raise ValueError(f"control point x must be <= {size - 1}")

    if not pts or pts[0][0] != 0:
        pts.insert(0, (0, 0))
    if pts[-1][0] != size - 1:
        pts.append((size - 1, size - 1))

    lut = []
    for i in range(size):
        k = 0
        while k < len(pts) - 2 and pts[k + 1][0] < i:
            k += 1
        x0, y0 = pts[k]
        x1, y1 = pts[k + 1]
        value = y0 if x1 == x0 else y0 + (y1 - y0) * (i - x0) / (x1 - x0)
        lut.append(max(0, min(255, int(round(value)))))
    return lut


def apply_ab_curves(lab, a_lut=None, b_lut=None):
    """Remap the a*/b* bands of a Pillow "LAB" image; L is left untouched."""
    lightness, a_chan, b_chan = lab.split()
    if a_lut is not None:
        a_chan = a_chan.point(a_lut)
    if b_lut is not None:
        b_chan = b_chan.point(b_lut)
    return Image.merge("LAB", (lightness, a_chan, b_chan))


def lab_ab_curve(img, a_points=IDENTITY_POINTS, b_points=IDENTITY_POINTS):
    """Remap the Lab a* and b* channels of `img` and return an RGB image."""
    alpha = img.getchannel("A") if "A" in img.getbands() else None
    lab = img.convert("RGB").convert("LAB")
    merged = apply_ab_curves(lab, build_curve_lut(a_points),
                             build_curve_lut(b_points))
    rgb = merged.convert("RGB")
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def soft_glow(img, blur=3.5, top_opacity=25.0, merged_opacity=80.0,
              lab_a_points=None, lab_b_points=None):
    """Apply the AG Image Tune soft-glow effect to a single image.

    When `lab_a_points` / `lab_b_points` are given, the Lab a*/b* channels are
    remapped first (the GIMP "Decompose to LAB + Curves" step). Pass None for
    a channel to leave it alone.
    """
    if lab_a_points or lab_b_points:
        img = lab_ab_curve(img,
                           lab_a_points or IDENTITY_POINTS,
                           lab_b_points or IDENTITY_POINTS)
    base = img.convert("RGB")
    dup1 = base.copy()

    # Top layer: desaturate (LUMA) -> gaussian blur -> invert.
    top = ImageOps.grayscale(base).convert("RGB")
    top = top.filter(ImageFilter.GaussianBlur(blur))
    top = ImageOps.invert(top)

    # Merge down #1: dup1 with top at top_opacity.
    merged = Image.blend(dup1, top, top_opacity / 100.0)

    # Flatten: base + merged in soft-light mode at merged_opacity.
    soft = ImageChops.soft_light(base, merged)
    return Image.blend(base, soft, merged_opacity / 100.0)


def process_folder(src, dst, on_log=None, on_progress=None, is_cancelled=None,
                   **kwargs):
    """Process every supported image in src into dst (top level, non-recursive).

    Optional callbacks (used by the GUI):
      on_log(str)              — receive each progress/error line (default: print)
      on_progress(done, total) — called after each file (default: no-op)
      is_cancelled() -> bool   — polled before each file; True aborts the run
    """
    log = on_log if on_log is not None else print
    src_p, dst_p = Path(src), Path(dst)
    if not src_p.is_dir():
        log(f"ERROR: source folder not found: {src_p}")
        return
    dst_p.mkdir(parents=True, exist_ok=True)

    files = [f for f in src_p.iterdir()
             if f.is_file() and f.suffix.lower() in SUPPORTED]
    files.sort()
    if not files:
        log("No supported images found (jpg/png/webp/bmp/tif).")
        return

    total = len(files)
    for i, f in enumerate(files, 1):
        if is_cancelled is not None and is_cancelled():
            log(f"Cancelled after {i - 1}/{total} image(s).")
            return
        try:
            out = soft_glow(Image.open(f), **kwargs)
            out_path = dst_p / f.name
            out.save(out_path)
            log(f"[{i}/{total}] {f.name} -> {out_path}")
        except Exception as e:  # noqa: BLE001
            log(f"[{i}/{total}] ERROR {f.name}: {e}")
        if on_progress is not None:
            on_progress(i, total)

    log(f"Done: {total} image(s) processed.")


class AgImageApp:
    """Main application window."""

    def __init__(self, root):
        self.root = root
        root.title("AG Image Tune 2.0 — Batch Soft Glow")
        root.minsize(620, 520)

        self.style = ttk.Style(root)
        self._theme_var = tk.StringVar(value=DEFAULT_THEME)

        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()
        self.blur_var = tk.DoubleVar(value=3.5)
        self.top_var = tk.DoubleVar(value=25.0)
        self.merged_var = tk.DoubleVar(value=80.0)
        self.blur_label = tk.StringVar(value="3.5")
        self.top_label = tk.StringVar(value="25 %")
        self.merged_label = tk.StringVar(value="80 %")

        # LAB chroma curve: 4 numbers per channel (x1, y1, x2, y2).
        self.lab_on = tk.BooleanVar(value=False)
        self.lab_vars = {
            ch: [tk.IntVar(value=v) for v in (30, 0, 220, 255)]
            for ch in ("A", "B")
        }
        self.lab_widgets = []

        self._cancel = threading.Event()
        self._thread = None
        self._queue = queue.Queue()
        self._about_win = None

        self._build_toolbar()
        self._build_ui()
        # Restore the saved LAB points *before* applying the theme, because
        # _apply_theme saves the current state back to the config file.
        self._load_lab()
        self._apply_theme(self._load_theme())

    # ----- UI construction ------------------------------------------------
    def _build_ui(self):
        # Folders
        frm = ttk.LabelFrame(self.root, text="Folders", padding=10)
        frm.pack(fill="x", padx=10, pady=6)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Source:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.src_var).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Browse…", command=self._pick_src).grid(
            row=0, column=2)

        ttk.Label(frm, text="Destination:").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.dst_var).grid(
            row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Browse…", command=self._pick_dst).grid(
            row=1, column=2)

        # Settings
        frm2 = ttk.LabelFrame(self.root, text="Effect settings", padding=10)
        frm2.pack(fill="x", padx=10, pady=6)
        frm2.columnconfigure(1, weight=1)

        self._slider(frm2, 0, "Blur radius", self.blur_var, self.blur_label,
                     0.0, 20.0, lambda v: f"{v:.1f}")
        self._slider(frm2, 1, "Glow opacity", self.top_var, self.top_label,
                     0.0, 100.0, lambda v: f"{v:.0f} %")
        self._slider(frm2, 2, "Soft-light opacity", self.merged_var,
                     self.merged_label, 0.0, 100.0, lambda v: f"{v:.0f} %")

        # LAB chroma curve (optional pre-step)
        frm5 = ttk.LabelFrame(self.root, text="LAB chroma curve (optional)",
                              padding=10)
        frm5.pack(fill="x", padx=10, pady=6)

        ttk.Checkbutton(
            frm5,
            text="Remap the Lab a*/b* channels first "
                 "(GIMP: Decompose to LAB → Curves → Compose)",
            variable=self.lab_on, command=self._lab_toggle
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))

        for col, head in enumerate(("Channel", "point 1  in / out",
                                    "", "point 2  in / out", "")):
            ttk.Label(frm5, text=head).grid(row=1, column=col, sticky="w", padx=3)

        for i, ch in enumerate(("A", "B")):
            row = 2 + i
            ttk.Label(frm5, text=ch).grid(row=row, column=0, sticky="w", padx=3)
            for j, var in enumerate(self.lab_vars[ch]):
                spin = ttk.Spinbox(frm5, from_=0, to=255, width=5,
                                   textvariable=var, justify="center")
                spin.grid(row=row, column=1 + j, padx=3, pady=2)
                self.lab_widgets.append(spin)

        ttk.Label(frm5, text="(values are the layer numbers from GIMP's Curves "
                             "dialog: input → output)").grid(
            row=4, column=0, columnspan=5, sticky="w", pady=(6, 0))
        self._lab_toggle()

        # Actions
        frm3 = ttk.Frame(self.root)
        frm3.pack(fill="x", padx=10, pady=6)
        self.preview_btn = ttk.Button(frm3, text="Preview one image…",
                                      command=self._preview)
        self.preview_btn.pack(side="left")
        self.cancel_btn = ttk.Button(frm3, text="Cancel", command=self._cancel_run,
                                     state="disabled")
        self.cancel_btn.pack(side="right", padx=6)
        self.run_btn = ttk.Button(frm3, text="Process folder", command=self._start)
        self.run_btn.pack(side="right")

        # Progress
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=6)

        # Log
        frm4 = ttk.LabelFrame(self.root, text="Log", padding=6)
        frm4.pack(fill="both", expand=True, padx=10, pady=6)
        self.txt = tk.Text(frm4, height=10, wrap="none", state="disabled")
        sb = ttk.Scrollbar(frm4, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _slider(self, parent, row, text, var, label_var, lo, hi, fmt):
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Scale(parent, from_=lo, to=hi, variable=var,
                  command=lambda _v: label_var.set(fmt(var.get()))
                  ).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Label(parent, textvariable=label_var, width=9,
                  anchor="e").grid(row=row, column=2)

    # ----- LAB chroma curve ----------------------------------------------
    def _lab_toggle(self):
        state = "normal" if self.lab_on.get() else "disabled"
        for spin in self.lab_widgets:
            spin.configure(state=state)

    def _lab_points(self):
        """(a_points, b_points) or (None, None) when the option is off.

        Raises ValueError with a readable message if the numbers can't form a
        curve (a repeated input value), so the caller can show a dialog.
        """
        if not self.lab_on.get():
            return None, None
        out = []
        for ch in ("A", "B"):
            vars_ = self.lab_vars[ch]
            try:
                x1, y1, x2, y2 = (v.get() for v in vars_)
            except tk.TclError:
                raise ValueError(
                    f"Channel {ch}: every box needs a whole number 0–255.")
            points = ((x1, y1), (x2, y2))
            build_curve_lut(points)  # validates; raises ValueError if unusable
            out.append(points)
        return out[0], out[1]

    def _log(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    # ----- Folder pickers -------------------------------------------------
    def _pick_src(self):
        path = filedialog.askdirectory(title="Choose the source folder")
        if not path:
            return
        self.src_var.set(path)
        # Suggest a destination next to the source if none is set yet.
        if not self.dst_var.get().strip():
            self.dst_var.set(path.rstrip("\\/") + "_glow")

    def _pick_dst(self):
        path = filedialog.askdirectory(title="Choose the destination folder")
        if path:
            self.dst_var.set(path)

    # ----- Preview --------------------------------------------------------
    def _preview(self):
        path = filedialog.askopenfilename(title="Choose an image to preview",
                                          filetypes=IMAGE_TYPES)
        if not path:
            return
        try:
            a_pts, b_pts = self._lab_points()
        except ValueError as e:  # noqa: BLE001
            messagebox.showerror("LAB chroma curve", str(e))
            return
        try:
            src = Image.open(path)
            result = soft_glow(src, blur=self.blur_var.get(),
                               top_opacity=self.top_var.get(),
                               merged_opacity=self.merged_var.get(),
                               lab_a_points=a_pts, lab_b_points=b_pts)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Preview", f"Could not open or process image:\n{e}")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Preview — {Path(path).name}")
        win.resizable(False, False)
        win.configure(bg=THEMES[self._theme_var.get()]["bg"])

        before = self._thumb(src.convert("RGB"))
        after = self._thumb(result)

        frm = ttk.Frame(win, padding=10)
        frm.pack()
        ttk.Label(frm, text="Original").grid(row=0, column=0, padx=6)
        ttk.Label(frm, text="Result").grid(row=0, column=1, padx=6)
        ttk.Label(frm, image=before).grid(row=1, column=0, padx=6)
        ttk.Label(frm, image=after).grid(row=1, column=1, padx=6)

        # Keep references alive for the lifetime of the window.
        win._before = before  # type: ignore[attr-defined]
        win._after = after    # type: ignore[attr-defined]

    @staticmethod
    def _thumb(img, max_w=460):
        img.thumbnail((max_w, max_w * 4))
        return ImageTk.PhotoImage(img)

    # ----- Batch run ------------------------------------------------------
    def _start(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if not src:
            messagebox.showwarning("Missing source", "Choose the source folder first.")
            return
        if not Path(src).is_dir():
            messagebox.showerror("Bad source", f"Source folder does not exist:\n{src}")
            return
        if not dst:
            messagebox.showwarning("Missing destination",
                                   "Choose the destination folder first.")
            return
        if Path(src).resolve() == Path(dst).resolve():
            messagebox.showerror(
                "Same folder",
                "Source and destination are the same folder.\n"
                "The originals would be overwritten — choose a different destination.")
            return

        try:
            a_pts, b_pts = self._lab_points()
        except ValueError as e:  # noqa: BLE001
            messagebox.showerror("LAB chroma curve", str(e))
            return

        kwargs = {
            "blur": self.blur_var.get(),
            "top_opacity": self.top_var.get(),
            "merged_opacity": self.merged_var.get(),
            "lab_a_points": a_pts,
            "lab_b_points": b_pts,
        }
        self._cancel.clear()
        self._set_running(True)
        self.progress.configure(value=0, maximum=100)
        self._log(f"Processing {src} -> {dst}")
        self._log(f"Settings: blur={kwargs['blur']:.1f}, "
                  f"top={kwargs['top_opacity']:.0f}%, "
                  f"merged={kwargs['merged_opacity']:.0f}%")
        if a_pts or b_pts:
            for ch, pts in (("A", a_pts), ("B", b_pts)):
                if pts:
                    self._log(f"LAB {ch} curve: {pts[0][0]}->{pts[0][1]}, "
                              f"{pts[1][0]}->{pts[1][1]}")
                else:
                    self._log(f"LAB {ch} curve: unchanged")
        self._save_config()

        self._thread = threading.Thread(
            target=self._worker, args=(src, dst, kwargs), daemon=True)
        self._thread.start()
        self.root.after(80, self._poll)

    def _worker(self, src, dst, kwargs):
        worked = {"any": False}

        def on_progress(done, total):
            worked["any"] = True
            self._queue.put(("progress", done, total))

        try:
            process_folder(
                src, dst,
                on_log=lambda m: self._queue.put(("log", m)),
                on_progress=on_progress,
                is_cancelled=lambda: self._cancel.is_set(),
                **kwargs)
        except Exception as e:  # noqa: BLE001
            self._queue.put(("log", f"FATAL: {e}"))
        finally:
            self._queue.put(("done", worked["any"]))

    def _poll(self):
        finished = False
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1])
                elif kind == "progress":
                    self.progress.configure(maximum=msg[2], value=msg[1])
                elif kind == "done":
                    finished = True
                    self._set_running(False)
                    if not self._cancel.is_set() and msg[1]:
                        messagebox.showinfo("AG Image Tune", "Processing complete.")
        except queue.Empty:
            pass
        if not finished:
            self.root.after(80, self._poll)

    def _cancel_run(self):
        self._cancel.set()
        self._log("Cancelling… (the current image will finish first)")

    def _set_running(self, running):
        run_state = "disabled" if running else "normal"
        self.run_btn.configure(state=run_state)
        self.preview_btn.configure(state=run_state)
        self.cancel_btn.configure(state="normal" if running else "disabled")

    # ----- Theme ----------------------------------------------------------
    def _build_toolbar(self):
        # A themed toolbar instead of the native menu bar: the native bar is
        # drawn by Windows and ignores our colour overrides (it stays white in
        # the dark theme), whereas ttk widgets honour them.
        self.toolbar = ttk.Frame(self.root, padding=(10, 6))
        self.toolbar.pack(fill="x")

        self.theme_menu = tk.Menu(self.toolbar, tearoff=0)
        self.theme_menu.add_radiobutton(
            label="Light theme", value="light", variable=self._theme_var,
            command=lambda: self._apply_theme("light"))
        self.theme_menu.add_radiobutton(
            label="Dark theme", value="dark", variable=self._theme_var,
            command=lambda: self._apply_theme("dark"))

        self.theme_btn = ttk.Menubutton(self.toolbar, text="Theme ▾",
                                        menu=self.theme_menu)
        self.theme_btn.pack(side="left")

        self.about_btn = ttk.Button(self.toolbar, text="About",
                                    command=self._show_about)
        self.about_btn.pack(side="right")

    def _show_about(self):
        # One modal About at a time: refocus the existing one instead of
        # stacking duplicates.
        if self._about_win is not None and self._about_win.winfo_exists():
            self._about_win.lift()
            self._about_win.focus_force()
            return

        t = THEMES[self._theme_var.get()]
        win = tk.Toplevel(self.root)
        win.title("About AG Image Tune")
        win.resizable(False, False)
        win.configure(bg=t["bg"])
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self._close_about)
        self._about_win = win

        frm = ttk.Frame(win, padding=20)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="AG Image Tune 2.0",
                  font=("Segoe UI", 13, "bold")).pack(pady=(0, 4))
        ttk.Label(frm, text="Batch soft-glow image processor").pack(
            pady=(0, 14))
        ttk.Label(frm, text="Andrew Golubev").pack()

        link = ttk.Label(
            frm,
            text="https://github.com/AndrewGolubev/agimage-tune",
            foreground=t["accent"], cursor="hand2",
            font=("Segoe UI", 9, "underline"))
        link.pack(pady=(2, 18))
        link.bind("<Button-1>",
                  lambda _e: webbrowser.open(
                      "https://github.com/AndrewGolubev/agimage-tune"))

        ttk.Button(frm, text="OK", command=self._close_about).pack()

        # Center over the main window (the popup's size isn't known until its
        # layout has been computed).
        win.update_idletasks()
        width = win.winfo_reqwidth()
        height = win.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        win.geometry(f"+{x}+{y}")

        # Modal: block the main window until this dialog is closed. Wrapped in
        # try/except because grab_set can fail if the window isn't viewable yet.
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _close_about(self):
        if self._about_win is not None:
            self._about_win.destroy()
            self._about_win = None

    def _load_theme(self):
        data = self._load_config()
        if data.get("theme") in THEMES:
            return data["theme"]
        return DEFAULT_THEME

    def _load_lab(self):
        """Restore the LAB curve controls; silently ignores anything malformed."""
        data = self._load_config().get("lab")
        if not isinstance(data, dict):
            return
        try:
            self.lab_on.set(bool(data.get("on", False)))
            points = data.get("points", {})
            for ch in ("A", "B"):
                vals = points.get(ch)
                if isinstance(vals, list) and len(vals) == 4:
                    for var, value in zip(self.lab_vars[ch], vals):
                        var.set(int(value))
        except (TypeError, ValueError, tk.TclError):
            pass
        self._lab_toggle()

    @staticmethod
    def _load_config():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _save_config(self):
        try:
            data = self._load_config()
            data["theme"] = self._theme_var.get()
            data["lab"] = {
                "on": bool(self.lab_on.get()),
                "points": {ch: [int(v.get()) for v in self.lab_vars[ch]]
                           for ch in ("A", "B")},
            }
            CONFIG_PATH.write_text(json.dumps(data, indent=2),
                                   encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def _apply_theme(self, name):
        t = THEMES[name]
        self._theme_var.set(name)
        s = self.style

        # 'clam' honours colour overrides on every platform; the native
        # Windows theme ('vista') ignores most of them.
        if s.theme_use() != "clam":
            try:
                s.theme_use("clam")
            except tk.TclError:
                pass

        self.root.configure(bg=t["bg"])

        s.configure(
            ".",
            background=t["bg"], foreground=t["fg"],
            fieldbackground=t["surface"], bordercolor=t["border"],
            troughcolor=t["trough"],
            lightcolor=t["surface"], darkcolor=t["surface_alt"],
            selectbackground=t["select_bg"], selectforeground=t["select_fg"],
        )
        s.configure("TFrame", background=t["bg"])
        s.configure("TLabel", background=t["bg"], foreground=t["fg"])
        s.configure("TLabelframe", background=t["bg"], bordercolor=t["border"],
                    lightcolor=t["bg"], darkcolor=t["bg"])
        s.configure("TLabelframe.Label", background=t["bg"],
                    foreground=t["fg"])

        s.configure("TButton", background=t["surface"], foreground=t["fg"],
                    bordercolor=t["border"], lightcolor=t["surface"],
                    darkcolor=t["surface"], padding=(10, 4))
        s.map("TButton",
              background=[("active", t["hover"]), ("pressed", t["hover"]),
                          ("disabled", t["surface_alt"])],
              foreground=[("disabled", t["disabled_fg"])])

        s.configure("TEntry", fieldbackground=t["surface"],
                    foreground=t["fg"], bordercolor=t["border"],
                    lightcolor=t["surface"], darkcolor=t["surface"],
                    insertcolor=t["fg"])
        s.map("TEntry",
              fieldbackground=[("disabled", t["surface_alt"])],
              foreground=[("disabled", t["disabled_fg"])])

        s.configure("TMenubutton", background=t["surface"],
                    foreground=t["fg"], bordercolor=t["border"],
                    lightcolor=t["surface"], darkcolor=t["surface"],
                    padding=(10, 4))
        s.map("TMenubutton",
              background=[("active", t["hover"]), ("pressed", t["hover"])])

        s.configure("Horizontal.TScale", background=t["bg"],
                    troughcolor=t["trough"], bordercolor=t["border"],
                    lightcolor=t["surface"], darkcolor=t["border"])
        s.configure("Vertical.TScale", background=t["bg"],
                    troughcolor=t["trough"])

        s.configure("Horizontal.TProgressbar", background=t["accent"],
                    troughcolor=t["trough"], bordercolor=t["border"],
                    lightcolor=t["accent"], darkcolor=t["accent"])

        s.configure("Vertical.TScrollbar", background=t["surface_alt"],
                    troughcolor=t["bg"], bordercolor=t["border"],
                    arrowcolor=t["fg"], lightcolor=t["surface_alt"],
                    darkcolor=t["surface_alt"])
        s.map("Vertical.TScrollbar", background=[("active", t["hover"])])

        # The log is a plain tk.Text, not a ttk widget — style it directly.
        self.txt.configure(bg=t["text_bg"], fg=t["text_fg"],
                           insertbackground=t["fg"],
                           selectbackground=t["select_bg"],
                           selectforeground=t["select_fg"])

        self.theme_menu.configure(bg=t["surface"], fg=t["fg"],
                                  activebackground=t["accent"],
                                  activeforeground=t["accent_fg"],
                                  selectcolor=t["accent"],
                                  disabledforeground=t["disabled_fg"],
                                  activeborderwidth=0, borderwidth=0)

        self._save_config()


def main():
    # Crisp text on high-DPI Windows displays.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    root = tk.Tk()
    AgImageApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
