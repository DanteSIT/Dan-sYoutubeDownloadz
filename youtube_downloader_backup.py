import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import yt_dlp
import threading
import os
import subprocess
import re
import shutil
import json
import time
import urllib.request
import platform
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
#  HISTORY FILE  (stored next to the script)
# ─────────────────────────────────────────────
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download_history.json")


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────
#  STYLE CONSTANTS
# ─────────────────────────────────────────────
BG        = "#0d0d0d"
PANEL     = "#141414"
CARD      = "#1a1a1a"
BORDER    = "#2a2a2a"
ACCENT    = "#ff0000"
GREEN     = "#00e676"
YELLOW    = "#ffea00"
PURPLE    = "#ce93d8"
CYAN      = "#00e5ff"
TEXT      = "#f0f0f0"
MUTED     = "#888888"
FONT_MAIN = ("Consolas", 10)
FONT_HEAD = ("Arial", 11, "bold")
FONT_BIG  = ("Arial", 16, "bold")


# ─────────────────────────────────────────────
#  TOOLTIP HELPER
# ─────────────────────────────────────────────
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0,0,0,0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, bg="#222", fg="white",
                 font=("Arial", 9), relief="solid", bd=1, padx=6, pady=3).pack()

    def hide(self, _=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# ─────────────────────────────────────────────
#  DEPENDENCY MANAGER
# ─────────────────────────────────────────────
class DependencyManager:
    @staticmethod
    def check_system_tool(tool_name):
        """Check if a system tool is installed"""
        return shutil.which(tool_name) is not None
    
    @staticmethod
    def check_python_package(package_name):
        """Check if a Python package is installed"""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False
    
    @staticmethod
    def get_missing_dependencies():
        """Returns lists of missing system tools and Python packages"""
        missing_tools = []
        missing_packages = []
        
        # Check system tools
        if not DependencyManager.check_system_tool("ffmpeg"):
            missing_tools.append("ffmpeg")
        if not DependencyManager.check_system_tool("atomicparsley") and \
           not DependencyManager.check_system_tool("AtomicParsley"):
            missing_tools.append("atomicparsley")
        
        # Check Python packages
        if not DependencyManager.check_python_package("PIL"):
            missing_packages.append("pillow")
        
        return missing_tools, missing_packages
    
    @staticmethod
    def install_dependencies(missing_tools, missing_packages):
        """Attempt to install missing dependencies"""
        system = platform.system()
        success_count = 0
        failed_items = []
        
        # Install Python packages via pip
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])
                success_count += 1
            except subprocess.CalledProcessError:
                failed_items.append(f"Python package: {package}")
        
        # Install system tools
        if missing_tools:
            if system == "Linux":
                # Try to detect package manager and install
                if shutil.which("apt-get"):
                    for tool in missing_tools:
                        try:
                            subprocess.check_call(["sudo", "apt-get", "install", "-y", "-qq", tool],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            success_count += 1
                        except subprocess.CalledProcessError:
                            failed_items.append(f"System tool (apt): {tool}")
                elif shutil.which("dnf"):
                    for tool in missing_tools:
                        try:
                            subprocess.check_call(["sudo", "dnf", "install", "-y", "-q", tool],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            success_count += 1
                        except subprocess.CalledProcessError:
                            failed_items.append(f"System tool (dnf): {tool}")
                elif shutil.which("pacman"):
                    for tool in missing_tools:
                        try:
                            subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "-q", tool],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            success_count += 1
                        except subprocess.CalledProcessError:
                            failed_items.append(f"System tool (pacman): {tool}")
                else:
                    failed_items.extend([f"System tool (manual): {t}" for t in missing_tools])
            elif system == "Windows":
                # On Windows, provide manual installation instructions
                for tool in missing_tools:
                    failed_items.append(f"System tool (Windows): {tool}")
        
        return success_count, failed_items


# ─────────────────────────────────────────────
#  QUEUE ITEM  (one URL in batch mode)
# ─────────────────────────────────────────────
class QueueItem:
    def __init__(self, url, quality, audio_only):
        self.url        = url
        self.quality    = quality
        self.audio_only = audio_only
        self.status     = "Queued"
        self.title      = url[:60]


# ─────────────────────────────────────────────
#  MAIN APP
# ─────────────────────────────────────────────
class YouTubeDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Downloader  ·  by Dante Lespoir")
        self.root.geometry("620x920")
        self.root.minsize(540, 700)
        self.root.configure(bg=BG)

        # State
        self.url_var        = tk.StringVar()
        self.save_path      = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.quality_var    = tk.StringVar(value="1. Fetch Info First")
        self.audio_var      = tk.BooleanVar(value=False)
        self.playlist_var   = tk.BooleanVar(value=False)
        self.size_dict      = {}
        self.is_vr          = False
        self.is_playlist    = False
        self.info_data      = None
        self.download_queue = []
        self.history        = load_history()
        self._thumb_job     = None

        self._apply_ttk_style()
        
            # Check dependencies BEFORE building UI to avoid duplicate windows
            missing_tools, missing_packages = DependencyManager.get_missing_dependencies()
            if missing_tools or missing_packages:
                self._build_ui()
                self._check_and_install_dependencies(missing_tools, missing_packages)
            else:
                self._build_ui()
        
        self.audio_var.trace_add("write", self._on_audio_toggle)

    # ── TTK styling ──────────────────────────
    def _apply_ttk_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARD, background=CARD,
                        foreground=TEXT, selectbackground=CARD, selectforeground=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)],
                  foreground=[("readonly", TEXT)])
        style.configure("red.Horizontal.TProgressbar",
                        troughcolor=BORDER, background=ACCENT, thickness=8)
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor=BORDER, background=GREEN, thickness=8)
        style.configure("TCheckbutton", background=BG, foreground=TEXT,
                        font=FONT_MAIN)
        style.map("TCheckbutton", background=[("active", BG)])

    # ── Tool check ───────────────────────────
    def _check_and_install_dependencies(self):
    def _check_and_install_dependencies(self, missing_tools, missing_packages):
        """Check for missing dependencies and offer to install them"""
            return  # All dependencies present
        
        # Build message
        msg_parts = ["The following dependencies are missing:\n"]
        if missing_tools:
            msg_parts.append("System Tools:\n")
            for tool in missing_tools:
                msg_parts.append(f"  • {tool}\n")
        if missing_packages:
            msg_parts.append("\nPython Packages:\n")
            for pkg in missing_packages:
                msg_parts.append(f"  • {pkg}\n")
        
        msg_parts.append("\nWould you like to install them now?")
        msg = "".join(msg_parts)
        
        if messagebox.askyesno("Missing Dependencies", msg):
            self._install_dependencies_thread(missing_tools, missing_packages)
    
    def _install_dependencies_thread(self, missing_tools, missing_packages):
        """Install dependencies in a separate thread"""
        def install():
            success_count, failed_items = DependencyManager.install_dependencies(
                missing_tools, missing_packages)
            
            self.root.after(0, lambda: self._show_installation_result(success_count, failed_items))
        
        threading.Thread(target=install, daemon=True).start()
    
    def _show_installation_result(self, success_count, failed_items):
        """Show installation result dialog"""
        if not failed_items:
            messagebox.showinfo("Installation Complete",
                f"✓ Successfully installed {success_count} dependencies!\n\n"
                "The application is ready to use.")
        else:
            msg = f"Installed {success_count} dependencies.\n\n"
            msg += f"Failed to install {len(failed_items)}:\n\n"
            for item in failed_items:
                msg += f"  • {item}\n"
            
            if platform.system() == "Windows":
                msg += "\nFor Windows, you can manually download:\n"
                msg += "  • FFmpeg: https://ffmpeg.org/download.html\n"
                msg += "  • AtomicParsley: https://github.com/wez/atomicparsley/releases"
            elif platform.system() == "Linux":
                msg += "\nPlease manually install using your package manager or contact support."
            
            messagebox.showwarning("Installation Partial", msg)

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build_ui(self):
        # ── Header bar ──
        hdr = tk.Frame(self.root, bg=ACCENT, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="▶  VIDEO DOWNLOADER", font=("Arial", 17, "bold"),
                 bg=ACCENT, fg="white").pack(side="left", padx=20)
        tk.Label(hdr, text="by Dante Lespoir", font=("Arial", 9),
                 bg=ACCENT, fg="#ffcccc").pack(side="right", padx=20)

        # ── Notebook tabs ──
        nb_frame = tk.Frame(self.root, bg=BG)
        nb_frame.pack(fill="both", expand=True)

        self.nb = ttk.Notebook(nb_frame)
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        # Tab style
        style = ttk.Style()
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        font=("Arial", 10, "bold"), padding=[14, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", CARD)],
                  foreground=[("selected", TEXT)])

        self.tab_main    = tk.Frame(self.nb, bg=BG)
        self.tab_queue   = tk.Frame(self.nb, bg=BG)
        self.tab_history = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_main,    text="  ⬇  Download  ")
        self.nb.add(self.tab_queue,   text="  ☰  Queue  ")
        self.nb.add(self.tab_history, text="  🕘  History  ")

        self._build_main_tab()
        self._build_queue_tab()
        self._build_history_tab()

    # ──────────────────────────────────────────
    #  MAIN TAB
    # ──────────────────────────────────────────
    def _build_main_tab(self):
        p = tk.Frame(self.tab_main, bg=BG)
        p.pack(fill="both", expand=True, padx=22, pady=16)

        # ── URL row ──
        self._label(p, "VIDEO URL")
        url_row = tk.Frame(p, bg=BG)
        url_row.pack(fill="x", pady=(4, 0))
        self.url_entry = tk.Entry(url_row, textvariable=self.url_var,
                                  font=("Consolas", 11), bg=CARD, fg=TEXT,
                                  insertbackground=TEXT, relief="flat")
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.url_entry.bind("<KeyRelease>", self._on_url_change)
        btn_paste = self._btn(url_row, "📋", BORDER, TEXT, self._paste_url, width=3)
        btn_paste.pack(side="right", padx=(6, 0), ipady=9)
        Tooltip(btn_paste, "Paste from clipboard")

        # ── Playlist checkbox ──
        cb_row = tk.Frame(p, bg=BG)
        cb_row.pack(fill="x", pady=(6, 0))
        self.playlist_cb = ttk.Checkbutton(cb_row, text=" Download entire playlist",
                                           variable=self.playlist_var)
        self.playlist_cb.pack(side="left")
        Tooltip(self.playlist_cb, "If URL is a playlist, download all videos")

        self.audio_cb = ttk.Checkbutton(cb_row, text=" Audio only (MP3)",
                                        variable=self.audio_var)
        self.audio_cb.pack(side="right")
        Tooltip(self.audio_cb, "Extract audio as 320kbps MP3")

        # Separator
        self._sep(p)

        # ── Thumbnail preview ──
        thumb_row = tk.Frame(p, bg=BG)
        thumb_row.pack(fill="x", pady=(0, 8))

        self.thumb_canvas = tk.Canvas(thumb_row, width=160, height=90,
                                      bg=CARD, highlightthickness=1,
                                      highlightbackground=BORDER)
        self.thumb_canvas.pack(side="left")
        self.thumb_canvas.create_text(80, 45, text="No Preview", fill=MUTED,
                                      font=("Arial", 9), tags="placeholder")

        # Video info panel next to thumb
        info_side = tk.Frame(thumb_row, bg=BG)
        info_side.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.title_lbl = tk.Label(info_side, text="—", font=("Arial", 10, "bold"),
                                  bg=BG, fg=TEXT, wraplength=340, justify="left", anchor="w")
        self.title_lbl.pack(fill="x")
        self.meta_lbl = tk.Label(info_side, text="", font=("Consolas", 9),
                                 bg=BG, fg=MUTED, justify="left", anchor="w")
        self.meta_lbl.pack(fill="x", pady=(4, 0))
        self.vr_badge = tk.Label(info_side, text="", font=("Arial", 9, "bold"),
                                 bg=BG, fg=PURPLE)
        self.vr_badge.pack(anchor="w", pady=(4, 0))

        # ── Path selection ──
        self._label(p, "SAVE TO")
        path_row = tk.Frame(p, bg=CARD, relief="flat")
        path_row.pack(fill="x", pady=(4, 0))
        tk.Entry(path_row, textvariable=self.save_path, font=("Consolas", 10),
                 bg=CARD, fg=TEXT, state="readonly", relief="flat").pack(
                 side="left", fill="x", expand=True, padx=8, ipady=8)
        self._btn(path_row, "Browse", "#333", TEXT, self._browse_folder).pack(
                 side="right", padx=6, pady=4, ipadx=8)

        # ── Quality row ──
        self._sep(p)
        q_row = tk.Frame(p, bg=BG)
        q_row.pack(fill="x", pady=(0, 6))
        self._label(q_row, "QUALITY", pack_side="left")

        self.fetch_btn = self._btn(q_row, "🔍  FETCH INFO", ACCENT, "white", self._fetch_info)
        self.fetch_btn.pack(side="right", ipadx=12, ipady=5)

        self.quality_combo = ttk.Combobox(p, textvariable=self.quality_var,
                                          state="readonly", font=("Consolas", 11))
        self.quality_combo.pack(fill="x", pady=(4, 0), ipady=4)
        self.quality_combo.set("1. Fetch Info First")

        # ── Info / log box ──
        self._sep(p)
        self._label(p, "OUTPUT LOG")
        self.info_text = scrolledtext.ScrolledText(
            p, height=7, font=("Consolas", 10),
            bg="#0a0a0a", fg=CYAN, relief="flat",
            insertbackground=CYAN)
        self.info_text.pack(fill="x", pady=(4, 0))
        self.info_text.tag_config("ok",   foreground=GREEN)
        self.info_text.tag_config("warn", foreground=YELLOW)
        self.info_text.tag_config("err",  foreground=ACCENT)
        self.info_text.tag_config("vr",   foreground=PURPLE)

        # ── Progress ──
        self._sep(p)
        prog_frame = tk.Frame(p, bg=PANEL, pady=10)
        prog_frame.pack(fill="x")
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal",
                                        mode="determinate",
                                        style="red.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=12, pady=(0, 6))
        stat_row = tk.Frame(prog_frame, bg=PANEL)
        stat_row.pack(fill="x", padx=12)
        self.speed_lbl = tk.Label(stat_row, text="Speed: —", font=FONT_MAIN,
                                  bg=PANEL, fg=GREEN)
        self.speed_lbl.pack(side="left")
        self.eta_lbl = tk.Label(stat_row, text="ETA: —", font=FONT_MAIN,
                                bg=PANEL, fg=YELLOW)
        self.eta_lbl.pack(side="left", padx=16)
        self.got_lbl = tk.Label(stat_row, text="Got: —", font=FONT_MAIN,
                                bg=PANEL, fg=CYAN)
        self.got_lbl.pack(side="left")
        self.status_lbl = tk.Label(stat_row, text="IDLE", font=("Arial", 10, "bold"),
                                   bg=PANEL, fg=MUTED)
        self.status_lbl.pack(side="right")

        # ── Buttons ──
        btn_row = tk.Frame(p, bg=BG)
        btn_row.pack(fill="x", pady=(10, 0))
        self.download_btn = self._btn(btn_row, "⬇  START DOWNLOAD", GREEN, "black",
                                      self._start_download,
                                      font=("Arial", 13, "bold"))
        self.download_btn.pack(side="left", fill="x", expand=True, ipady=12)
        self.download_btn.config(state="disabled")

        self.queue_btn = self._btn(btn_row, "+ QUEUE", BORDER, TEXT,
                                   self._add_to_queue, font=("Arial", 10, "bold"))
        self.queue_btn.pack(side="right", padx=(8, 0), ipady=12, ipadx=10)
        self.queue_btn.config(state="disabled")
        Tooltip(self.queue_btn, "Add to batch queue instead of downloading now")

    # ──────────────────────────────────────────
    #  QUEUE TAB
    # ──────────────────────────────────────────
    def _build_queue_tab(self):
        p = tk.Frame(self.tab_queue, bg=BG)
        p.pack(fill="both", expand=True, padx=22, pady=16)

        self._label(p, "DOWNLOAD QUEUE")
        tk.Label(p, text="Add items from the Download tab, then press Run All.",
                 font=("Consolas", 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 8))

        # Queue listbox
        list_frame = tk.Frame(p, bg=CARD)
        list_frame.pack(fill="both", expand=True)
        self.queue_lb = tk.Listbox(list_frame, bg=CARD, fg=TEXT,
                                   font=("Consolas", 10), selectbackground=BORDER,
                                   relief="flat", activestyle="none")
        self.queue_lb.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(list_frame, bg=CARD, troughcolor=CARD)
        sb.pack(side="right", fill="y")
        self.queue_lb.config(yscrollcommand=sb.set)
        sb.config(command=self.queue_lb.yview)

        # Queue buttons
        qb_row = tk.Frame(p, bg=BG)
        qb_row.pack(fill="x", pady=(10, 0))
        self.run_queue_btn = self._btn(qb_row, "▶  RUN ALL", GREEN, "black",
                                       self._run_queue, font=("Arial", 11, "bold"))
        self.run_queue_btn.pack(side="left", ipadx=14, ipady=8)

        self._btn(qb_row, "✕  Remove Selected", BORDER, TEXT,
                  self._remove_queue_item).pack(side="left", padx=(8, 0), ipadx=10, ipady=8)
        self._btn(qb_row, "Clear All", "#2a0000", ACCENT,
                  self._clear_queue).pack(side="right", ipadx=10, ipady=8)

        # Queue progress
        self.queue_progress_lbl = tk.Label(p, text="", font=("Consolas", 10),
                                           bg=BG, fg=MUTED)
        self.queue_progress_lbl.pack(anchor="w", pady=(8, 0))
        self.queue_bar = ttk.Progressbar(p, orient="horizontal", mode="determinate",
                                         style="green.Horizontal.TProgressbar")
        self.queue_bar.pack(fill="x", pady=(4, 0))

    # ──────────────────────────────────────────
    #  HISTORY TAB
    # ──────────────────────────────────────────
    def _build_history_tab(self):
        p = tk.Frame(self.tab_history, bg=BG)
        p.pack(fill="both", expand=True, padx=22, pady=16)

        self._label(p, "DOWNLOAD HISTORY")

        cols = ("date", "title", "quality", "path")
        self.hist_tree = ttk.Treeview(p, columns=cols, show="headings",
                                      style="hist.Treeview")
        style = ttk.Style()
        style.configure("hist.Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, font=("Consolas", 9), rowheight=22)
        style.configure("hist.Treeview.Heading", background=PANEL,
                        foreground=MUTED, font=("Arial", 9, "bold"))
        style.map("hist.Treeview", background=[("selected", BORDER)])

        self.hist_tree.heading("date",    text="Date")
        self.hist_tree.heading("title",   text="Title")
        self.hist_tree.heading("quality", text="Quality")
        self.hist_tree.heading("path",    text="Save Path")
        self.hist_tree.column("date",    width=110, anchor="w")
        self.hist_tree.column("title",   width=220, anchor="w")
        self.hist_tree.column("quality", width=70,  anchor="center")
        self.hist_tree.column("path",    width=180, anchor="w")

        sb = ttk.Scrollbar(p, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=sb.set)
        self.hist_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        btn_row = tk.Frame(self.tab_history, bg=BG)
        btn_row.pack(fill="x", padx=22, pady=(6, 12))
        self._btn(btn_row, "Clear History", "#2a0000", ACCENT,
                  self._clear_history).pack(side="right", ipadx=10, ipady=6)

        self._refresh_history_tree()

    # ══════════════════════════════════════════
    #  UI HELPERS
    # ══════════════════════════════════════════
    def _label(self, parent, text, pack_side=None):
        lbl = tk.Label(parent, text=text, font=("Arial", 8, "bold"),
                       bg=BG, fg=MUTED, pady=4)
        if pack_side:
            lbl.pack(side=pack_side, padx=(0, 8))
        else:
            lbl.pack(anchor="w")
        return lbl

    def _btn(self, parent, text, bg, fg, cmd, width=None, font=FONT_HEAD):
        b = tk.Button(parent, text=text, bg=bg, fg=fg, font=font,
                      relief="flat", cursor="hand2", command=cmd,
                      activebackground=bg, activeforeground=fg)
        if width:
            b.config(width=width)
        return b

    def _sep(self, parent):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=10)

    def _log(self, msg, tag=""):
        self.info_text.insert(tk.END, msg + "\n", tag)
        self.info_text.see(tk.END)

    def _set_status(self, text, color=MUTED):
        self.status_lbl.config(text=text, fg=color)

    # ══════════════════════════════════════════
    #  URL / CLIPBOARD
    # ══════════════════════════════════════════
    def _paste_url(self):
        try:
            clip = self.root.clipboard_get().strip()
            self.url_var.set(clip)
            self._on_url_change()
        except Exception:
            pass

    def _on_url_change(self, *_):
        # Reset preview when URL changes
        self._reset_preview()
        # Cancel any pending thumb load
        if self._thumb_job:
            self.root.after_cancel(self._thumb_job)
        # Debounce: don't fire on every keystroke
        self._thumb_job = self.root.after(1200, lambda: None)  # just debounce placeholder

    def _reset_preview(self):
        self.thumb_canvas.delete("all")
        self.thumb_canvas.create_text(80, 45, text="No Preview",
                                      fill=MUTED, font=("Arial", 9),
                                      tags="placeholder")
        self.title_lbl.config(text="—")
        self.meta_lbl.config(text="")
        self.vr_badge.config(text="")
        self.quality_combo.set("1. Fetch Info First")
        self.download_btn.config(state="disabled")
        self.queue_btn.config(state="disabled")
        self.is_vr = False
        self.info_data = None

    # ══════════════════════════════════════════
    #  FETCH INFO
    # ══════════════════════════════════════════
    def _fetch_info(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please enter a video URL first.")
            return
        self.info_text.delete("1.0", tk.END)
        self._log("@ Fetching info…")
        self.fetch_btn.config(state="disabled")
        self._set_status("FETCHING…", YELLOW)
        threading.Thread(target=self._fetch_thread, args=(url,), daemon=True).start()

    def _fetch_thread(self, url):
        try:
            noplaylist = not self.playlist_var.get()
            opts = {
                'quiet': True,
                'noplaylist': noplaylist,
                'nocheckcertificate': True,
                'extract_flat': self.playlist_var.get(),   # fast playlist scan
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            self.root.after(0, lambda: self._process_fetched(info, url))
        except Exception as e:
            self.root.after(0, lambda: self._fetch_error(str(e)))

    def _process_fetched(self, info, url):
        self.info_data = info
        is_playlist  = info.get("_type") == "playlist"
        self.is_playlist = is_playlist

        # ── Playlist mode ──────────────────────
        if is_playlist:
            entries = info.get("entries", [])
            count   = len(entries)
            self._log(f"PLAYLIST: {info.get('title', 'Unknown')}", "ok")
            self._log(f"{count} video(s) found.")
            self.title_lbl.config(text=f"📋  {info.get('title', 'Playlist')}")
            self.meta_lbl.config(text=f"{count} videos")
            self.quality_combo['values'] = ["Best Available", "1080p", "720p", "480p", "360p"]
            self.quality_combo.current(0)
            self.download_btn.config(state="normal")
            self.queue_btn.config(state="normal")
            self._set_status("READY", GREEN)
            self.fetch_btn.config(state="normal")
            return

        # ── Single video ───────────────────────
        title     = info.get("title", "Unknown")
        duration  = info.get("duration", 0)
        uploader  = info.get("uploader", "")
        view_cnt  = info.get("view_count", 0)
        thumb_url = info.get("thumbnail", "")

        # VR / 360 detection
        tags        = info.get("tags") or []
        description = info.get("description") or ""
        projection  = str(info.get("projection", "")).lower()
        spherical   = info.get("spherical", False)
        formats     = info.get("formats", [])

        is_vr = (
            spherical or
            projection in ("equirectangular", "360", "vr180") or
            any("360" in str(t).lower() or "vr" in str(t).lower() for t in tags) or
            "360" in title.lower() or
            any(str(f.get("format_note","")).lower() in ("360","vr","equirectangular")
                for f in formats)
        )
        self.is_vr = is_vr

        # Build resolution list
        res_list  = []
        size_dict = {}
        table_lines = [f"TITLE : {title}", "─" * 60]

        if is_vr:
            table_lines.append("⚠  VR / 360° video detected – spherical metadata will be preserved.")

        for res in [4320, 2160, 1440, 1080, 720, 480, 360, 240]:
            matching = [f for f in formats if f.get("height") == res]
            if matching:
                res_list.append(f"{res}p")
                max_size  = max(f.get("filesize") or 0 for f in matching)
                size_dict[f"{res}p"] = max_size
                size_str  = self._fmt_size(max_size) if max_size > 0 else "size N/A"
                table_lines.append(f"  ✔  {res}p  —  {size_str}")

        self.size_dict = size_dict
        table_text = "\n".join(table_lines)

        # Format duration
        if duration:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60
            dur_str = (f"{hours}:{minutes:02d}:{seconds:02d}" if hours else
                       f"{minutes}:{seconds:02d}")
        else:
            dur_str = "—"
        views_str = f"{view_cnt:,}" if view_cnt else "—"

        self._log(table_text, "vr" if is_vr else "")
        self.title_lbl.config(text=title)
        self.meta_lbl.config(text=f"⏱ {dur_str}   👁 {views_str} views   ↑ {uploader}")

        if is_vr:
            self.vr_badge.config(text="🔮  360° / VR  —  spherical metadata will be preserved")

        # Quality dropdown
        opts = ["Best Available"] + sorted(set(res_list), key=lambda x: int(x[:-1]), reverse=True)
        self.quality_combo['values'] = opts
        self.quality_combo.current(0)
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        self._set_status("READY", GREEN)
        self.fetch_btn.config(state="normal")

        # Load thumbnail in background
        if thumb_url:
            threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()

    def _fetch_error(self, msg):
        self._log(f"ERROR: {msg}", "err")
        self._set_status("ERROR", ACCENT)
        self.fetch_btn.config(state="normal")

    # ══════════════════════════════════════════
    #  THUMBNAIL LOADER
    # ══════════════════════════════════════════
    def _load_thumbnail(self, url):
        try:
            from PIL import Image, ImageTk
            import io
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).resize((160, 90), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, lambda: self._set_thumb(photo))
        except ImportError:
            # Pillow not installed — show URL text hint
            self.root.after(0, lambda: self.thumb_canvas.create_text(
                80, 45, text="Install Pillow\nfor previews",
                fill=MUTED, font=("Arial", 8), justify="center"))
        except Exception:
            pass  # Silent fail — thumbnail is non-critical

    def _set_thumb(self, photo):
        self._thumb_photo = photo   # prevent GC
        self.thumb_canvas.delete("all")
        self.thumb_canvas.create_image(0, 0, anchor="nw", image=photo)

    # ══════════════════════════════════════════
    #  AUDIO TOGGLE
    # ══════════════════════════════════════════
    def _on_audio_toggle(self, *_):
        if self.audio_var.get():
            self.quality_combo.config(state="disabled")
            self.quality_var.set("Audio Only (MP3)")
        else:
            self.quality_combo.config(state="readonly")
            if self.info_data:
                self.quality_combo.current(0)

    # ══════════════════════════════════════════
    #  BROWSE FOLDER
    # ══════════════════════════════════════════
    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.save_path.get())
        if folder:
            self.save_path.set(folder)

    # ══════════════════════════════════════════
    #  DOWNLOAD
    # ══════════════════════════════════════════
    def _start_download(self):
        url      = self.url_var.get().strip()
        quality  = self.quality_var.get()
        audio    = self.audio_var.get()
        playlist = self.playlist_var.get()
        if not url:
            return
        self.download_btn.config(state="disabled")
        self.queue_btn.config(state="disabled")
        self._set_status("STARTING…", YELLOW)
        threading.Thread(
            target=self._download_thread,
            args=(url, quality, audio, playlist, self.is_vr),
            daemon=True
        ).start()

    def _download_thread(self, url, quality, audio_only, playlist, is_vr):
        success, title = self._run_download(url, quality, audio_only, playlist, is_vr)
        if success:
            self.root.after(0, lambda: self._on_complete(url, quality if not audio_only else "MP3", title))
        else:
            self.root.after(0, lambda: self._on_failed())

    def _build_ydl_opts(self, quality, audio_only, playlist, is_vr, hook=None, post_hook=None):
        save = self.save_path.get()
        opts = {
            'outtmpl':              os.path.join(save, '%(playlist_index)s-%(title)s [%(height)sp].%(ext)s')
                                    if playlist else
                                    os.path.join(save, '%(title)s [%(height)sp].%(ext)s'),
            'merge_output_format':  'mp4',
            'nocolor':              True,
            'nocheckcertificate':   True,
            'noplaylist':           not playlist,
        }
        if hook:      opts['progress_hooks']      = [hook]
        if post_hook: opts['postprocessor_hooks'] = [post_hook]

        if audio_only:
            opts['format'] = 'bestaudio/best'
            opts['outtmpl'] = os.path.join(save, '%(title)s.%(ext)s')
            opts['postprocessors'] = [{
                'key':            'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
            return opts

        h = "best" if quality == "Best Available" else quality.replace("p", "")

        if is_vr:
            # For 360/VR: use -c copy to avoid re-encode that strips spherical atom
            if h == "best":
                opts['format'] = "bestvideo+bestaudio/best"
            else:
                opts['format'] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
            opts['merge_output_format'] = 'mp4'
            opts['postprocessor_args'] = {
                'ffmpeg': ['-c', 'copy', '-map_metadata', '0',
                           '-movflags', 'use_metadata_tags']
            }
        else:
            if h == "best":
                opts['format'] = "bestvideo+bestaudio/best"
            else:
                opts['format'] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"

        return opts

    def _run_download(self, url, quality, audio_only, playlist, is_vr):
        title = "Unknown"
        opts  = self._build_ydl_opts(quality, audio_only, playlist, is_vr,
                                     hook=self._progress_hook,
                                     post_hook=self._postprocess_hook)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url)
                if info:
                    title = info.get("title", url[:40])
            return True, title
        except Exception as e:
            # Fallback: single-file, no merge needed
            self.root.after(0, lambda: self._log("⚠ Primary failed, trying fallback…", "warn"))
            h = "best" if quality == "Best Available" else quality.replace("p", "")
            fb_fmt = "best" if h == "best" else f"best[height<={h}][ext=mp4]/best"
            opts2  = self._build_ydl_opts(fb_fmt, audio_only, playlist, False)
            opts2['format'] = fb_fmt
            try:
                with yt_dlp.YoutubeDL(opts2) as ydl:
                    info = ydl.extract_info(url)
                    if info:
                        title = info.get("title", url[:40])
                return True, title
            except Exception as e2:
                self.root.after(0, lambda: self._log(f"ERROR: {e2}", "err"))
                return False, title

    # ── Progress hooks ───────────────────────
    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            raw_p = self._strip_ansi(d.get('_percent_str', '0%')).replace('%','').strip()
            speed = self._strip_ansi(d.get('_speed_str', '—'))
            eta   = self._strip_ansi(d.get('_eta_str', '—'))
            got   = self._strip_ansi(d.get('_downloaded_bytes_str', '—'))
            try:
                pct = float(raw_p)
                self.root.after(0, lambda: self.progress.config(value=pct))
                self.root.after(0, lambda: self.speed_lbl.config(text=f"Speed: {speed}"))
                self.root.after(0, lambda: self.eta_lbl.config(text=f"ETA: {eta}"))
                self.root.after(0, lambda: self.got_lbl.config(text=f"Got: {got}"))
                self.root.after(0, lambda: self._set_status(f"DOWNLOADING {pct:.0f}%", YELLOW))
            except Exception:
                pass
        elif d['status'] == 'finished':
            self.root.after(0, lambda: self._set_status("PROCESSING…", PURPLE))

    def _postprocess_hook(self, d):
        if d['status'] == 'started':
            self.root.after(0, lambda: self._set_status("⚙  MERGING…", PURPLE))

    # ── Completion ───────────────────────────
    def _on_complete(self, url, quality, title):
        self._set_status("COMPLETE ✓", GREEN)
        self.progress.config(value=100)
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        self._log(f"✔ Done: {title}", "ok")

        # Save to history
        entry = {
            "date":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title":   title,
            "quality": quality,
            "path":    self.save_path.get(),
            "url":     url,
        }
        self.history.insert(0, entry)
        self.history = self.history[:200]   # cap at 200 entries
        save_history(self.history)
        self._refresh_history_tree()

        if messagebox.askyesno("Done ✓", f"'{title}' downloaded!\n\nOpen folder?"):
            self._open_folder(self.save_path.get())

    def _on_failed(self):
        self._set_status("FAILED", ACCENT)
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        messagebox.showerror("Download Failed",
            "All attempts failed.\nCheck your internet connection and FFmpeg install.")

    # ══════════════════════════════════════════
    #  QUEUE MANAGEMENT
    # ══════════════════════════════════════════
    def _add_to_queue(self):
        url     = self.url_var.get().strip()
        quality = self.quality_var.get()
        audio   = self.audio_var.get()
        if not url:
            return
        item = QueueItem(url, quality, audio)
        if self.info_data:
            item.title = self.info_data.get("title", url)[:70]
        self.download_queue.append(item)
        self._refresh_queue_lb()
        self._log(f"+ Queued: {item.title}", "ok")
        self.nb.select(self.tab_queue)

    def _refresh_queue_lb(self):
        self.queue_lb.delete(0, tk.END)
        for i, item in enumerate(self.download_queue):
            tag = "MP3" if item.audio_only else item.quality
            self.queue_lb.insert(tk.END, f"  [{item.status:8s}]  {tag:12s}  {item.title}")

    def _remove_queue_item(self):
        sel = self.queue_lb.curselection()
        if sel:
            del self.download_queue[sel[0]]
            self._refresh_queue_lb()

    def _clear_queue(self):
        if messagebox.askyesno("Clear Queue", "Remove all queued items?"):
            self.download_queue.clear()
            self._refresh_queue_lb()

    def _run_queue(self):
        if not self.download_queue:
            messagebox.showinfo("Queue Empty", "Add items to the queue first.")
            return
        self.run_queue_btn.config(state="disabled")
        threading.Thread(target=self._queue_thread, daemon=True).start()

    def _queue_thread(self):
        total = len(self.download_queue)
        for idx, item in enumerate(self.download_queue):
            if item.status == "Done":
                continue
            item.status = "Working"
            self.root.after(0, self._refresh_queue_lb)
            self.root.after(0, lambda i=idx, t=total: self.queue_progress_lbl.config(
                text=f"Processing {i+1} / {t}  —  {self.download_queue[i].title[:50]}"))
            self.root.after(0, lambda i=idx, t=total: self.queue_bar.config(value=(i/t)*100))

            success, title = self._run_download(
                item.url, item.quality, item.audio_only, False, False)

            item.status = "Done" if success else "Failed"
            if success:
                entry = {
                    "date":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "title":   title,
                    "quality": item.quality if not item.audio_only else "MP3",
                    "path":    self.save_path.get(),
                    "url":     item.url,
                }
                self.history.insert(0, entry)
                save_history(self.history)
            self.root.after(0, self._refresh_queue_lb)
            self.root.after(0, self._refresh_history_tree)

        self.root.after(0, lambda: self.queue_bar.config(value=100))
        self.root.after(0, lambda: self.queue_progress_lbl.config(
            text="Queue complete ✓", ))
        self.root.after(0, lambda: self.run_queue_btn.config(state="normal"))
        self.root.after(0, lambda: messagebox.showinfo(
            "Queue Done", f"Finished {total} item(s)."))

    # ══════════════════════════════════════════
    #  HISTORY
    # ══════════════════════════════════════════
    def _refresh_history_tree(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        for e in self.history:
            self.hist_tree.insert("", "end", values=(
                e.get("date", ""),
                e.get("title", "")[:55],
                e.get("quality", ""),
                e.get("path", ""),
            ))

    def _clear_history(self):
        if messagebox.askyesno("Clear History", "Delete all download history?"):
            self.history.clear()
            save_history(self.history)
            self._refresh_history_tree()

    # ══════════════════════════════════════════
    #  UTILITY
    # ══════════════════════════════════════════
    @staticmethod
    def _strip_ansi(text):
        return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', str(text))

    @staticmethod
    def _fmt_size(size_bytes):
        if not size_bytes:
            return "Unknown"
        for unit in ('B','KB','MB','GB'):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    @staticmethod
    def _open_folder(path):
        path = os.path.realpath(path)
        if os.name == 'nt':
            os.startfile(path)
        else:
            subprocess.Popen(['xdg-open', path])


# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = YouTubeDownloader(root)
    root.mainloop()