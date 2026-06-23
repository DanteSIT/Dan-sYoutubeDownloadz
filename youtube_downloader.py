import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import yt_dlp
import threading
import os
import subprocess
import re
import shutil
import json
import urllib.request
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Optional

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG & CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download_history.json")
MAX_HISTORY_ENTRIES = 200
THUMBNAIL_SIZE = (160, 90)

# Color Palette (Modern Dark Theme)
COLORS = {
    "bg": "#0a0a0a",
    "panel": "#121212",
    "card": "#1e1e1e",
    "border": "#2d2d2d",
    "hover": "#252525",
    "accent": "#ff6b6b",
    "success": "#51cf66",
    "warning": "#ffd43b",
    "info": "#74c0fc",
    "text": "#e0e0e0",
    "text_muted": "#888888",
}

# Fonts
FONTS = {
    "main": ("Segoe UI", 10),
    "header": ("Segoe UI", 11, "bold"),
    "title": ("Segoe UI", 16, "bold"),
    "code": ("Consolas", 9),
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UTILITY FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_history() -> List[Dict]:
    """Load download history from file"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history: List[Dict]) -> None:
    """Save download history to file"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from text"""
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', str(text))


def format_file_size(size_bytes: int) -> str:
    """Format bytes to human-readable size"""
    if not size_bytes:
        return "Unknown"
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_duration(duration: int) -> str:
    """Format seconds to HH:MM:SS or MM:SS"""
    if not duration:
        return "—"
    hours = duration // 3600
    minutes = (duration % 3600) // 60
    seconds = duration % 60
    return (f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}")


def open_folder(path: str) -> None:
    """Open folder in system file manager"""
    path = os.path.realpath(path)
    if os.name == 'nt':
        os.startfile(path)
    else:
        subprocess.Popen(['xdg-open', path])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOOLTIP CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Tooltip:
    """Enhanced tooltip with better positioning"""
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=self.text, bg="#2d2d2d", fg="#e0e0e0",
                 font=("Segoe UI", 9), relief="solid", bd=1, padx=6, pady=3).pack()

    def hide(self, _=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DEPENDENCY MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DependencyManager:
    """Manages system and Python dependency checks and installation"""
    
    SYSTEM_TOOLS = ["ffmpeg", "atomicparsley"]
    PYTHON_PACKAGES = ["pillow"]
    
    @staticmethod
    def check_system_tool(tool_name: str) -> bool:
        """Check if a system tool is installed"""
        return shutil.which(tool_name) is not None
    
    @staticmethod
    def check_python_package(package_name: str) -> bool:
        """Check if a Python package is installed"""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False
    
    @staticmethod
    def get_missing_dependencies() -> Tuple[List[str], List[str]]:
        """Returns lists of missing system tools and Python packages"""
        missing_tools = [t for t in DependencyManager.SYSTEM_TOOLS 
                        if not DependencyManager.check_system_tool(t)]
        missing_packages = [p for p in DependencyManager.PYTHON_PACKAGES 
                           if not DependencyManager.check_python_package(p)]
        return missing_tools, missing_packages
    
    @staticmethod
    def install_dependencies(missing_tools: List[str], missing_packages: List[str]) -> Tuple[int, List[str]]:
        """Attempt to install missing dependencies"""
        system = platform.system()
        success_count = 0
        failed_items = []
        
        # Install Python packages via pip
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                success_count += 1
            except subprocess.CalledProcessError:
                failed_items.append(f"Python: {package}")
        
        # Install system tools
        if missing_tools:
            if system == "Linux":
                if shutil.which("apt-get"):
                    for tool in missing_tools:
                        try:
                            subprocess.check_call(["sudo", "apt-get", "install", "-y", "-qq", tool],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            success_count += 1
                        except subprocess.CalledProcessError:
                            failed_items.append(f"Apt: {tool}")
                elif shutil.which("dnf"):
                    for tool in missing_tools:
                        try:
                            subprocess.check_call(["sudo", "dnf", "install", "-y", "-q", tool],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            success_count += 1
                        except subprocess.CalledProcessError:
                            failed_items.append(f"DNF: {tool}")
                elif shutil.which("pacman"):
                    for tool in missing_tools:
                        try:
                            subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "-q", tool],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            success_count += 1
                        except subprocess.CalledProcessError:
                            failed_items.append(f"Pacman: {tool}")
                else:
                    failed_items.extend([f"Manual: {t}" for t in missing_tools])
            elif system == "Windows":
                failed_items.extend([f"Windows: {t}" for t in missing_tools])
        
        return success_count, failed_items


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATA MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class QueueItem:
    """Represents a queued download"""
    def __init__(self, url: str, quality: str, audio_only: bool):
        self.url = url
        self.quality = quality
        self.audio_only = audio_only
        self.status = "Queued"
        self.title = url[:60]
    
    def __str__(self) -> str:
        tag = "MP3" if self.audio_only else self.quality
        return f"[{self.status:8s}]  {tag:12s}  {self.title}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN APPLICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class YouTubeDownloader:
    """Main application class for video downloading"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube Downloader")
        self.root.geometry("700x950")
        self.root.minsize(600, 750)
        self.root.configure(bg=COLORS["bg"])
        
        # State variables
        self.url_var = tk.StringVar()
        self.save_path = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.quality_var = tk.StringVar(value="Fetch Info First")
        self.audio_var = tk.BooleanVar(value=False)
        self.playlist_var = tk.BooleanVar(value=False)
        
        # Data storage
        self.size_dict: Dict[str, int] = {}
        self.is_vr = False
        self.is_playlist = False
        self.info_data: Optional[Dict] = None
        self.download_queue: List[QueueItem] = []
        self.history = load_history()
        self._thumb_job: Optional[str] = None
        self._thumb_photo: Optional[object] = None
        
        # Setup UI
        self._setup_styles()
        self._build_ui()
        
        # Check dependencies
        missing_tools, missing_packages = DependencyManager.get_missing_dependencies()
        if missing_tools or missing_packages:
            self._check_and_install_dependencies(missing_tools, missing_packages)
        
        # Trace variable changes
        self.audio_var.trace_add("write", self._on_audio_toggle)
    
    def _setup_styles(self):
        """Configure TTK styles"""
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("TCombobox", 
                       fieldbackground=COLORS["card"],
                       background=COLORS["card"],
                       foreground=COLORS["text"],
                       selectbackground=COLORS["border"],
                       selectforeground=COLORS["text"])
        style.map("TCombobox",
                 fieldbackground=[("readonly", COLORS["card"])],
                 foreground=[("readonly", COLORS["text"])])
        
        style.configure("red.Horizontal.TProgressbar",
                       troughcolor=COLORS["border"],
                       background=COLORS["accent"],
                       thickness=8)
        style.configure("green.Horizontal.TProgressbar",
                       troughcolor=COLORS["border"],
                       background=COLORS["success"],
                       thickness=8)
        
        style.configure("TCheckbutton",
                       background=COLORS["bg"],
                       foreground=COLORS["text"],
                       font=FONTS["main"])
        style.map("TCheckbutton",
                 background=[("active", COLORS["bg"])])
    
    def _build_ui(self):
        """Build the main UI"""
        # Header
        self._build_header()
        
        # Notebook (tabs)
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)
        
        style = ttk.Style()
        style.configure("TNotebook",
                       background=COLORS["bg"],
                       borderwidth=0)
        style.configure("TNotebook.Tab",
                       background=COLORS["panel"],
                       foreground=COLORS["text_muted"],
                       font=("Segoe UI", 10, "bold"),
                       padding=[14, 8])
        style.map("TNotebook.Tab",
                 background=[("selected", COLORS["card"])],
                 foreground=[("selected", COLORS["text"])])
        
        # Tabs
        self.tab_main = tk.Frame(self.nb, bg=COLORS["bg"])
        self.tab_queue = tk.Frame(self.nb, bg=COLORS["bg"])
        self.tab_history = tk.Frame(self.nb, bg=COLORS["bg"])
        
        self.nb.add(self.tab_main, text="  ⬇  Download  ")
        self.nb.add(self.tab_queue, text="  ☰  Queue  ")
        self.nb.add(self.tab_history, text="  🕘  History  ")
        
        self._build_main_tab()
        self._build_queue_tab()
        self._build_history_tab()
    
    def _build_header(self):
        """Build header section"""
        hdr = tk.Frame(self.root, bg=COLORS["accent"], height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        
        tk.Label(hdr, text="▶  YOUTUBE DOWNLOADER", 
                font=("Segoe UI", 16, "bold"),
                bg=COLORS["accent"], fg="white").pack(side="left", padx=20, pady=12)
        tk.Label(hdr, text="by Dante Lespoir", 
                font=("Segoe UI", 9),
                bg=COLORS["accent"], fg="#ffcccc").pack(side="right", padx=20, pady=12)
    
    def _build_main_tab(self):
        """Build main download tab"""
        p = tk.Frame(self.tab_main, bg=COLORS["bg"])
        p.pack(fill="both", expand=True, padx=20, pady=16)
        
        # URL Input
        self._label(p, "VIDEO URL")
        url_row = tk.Frame(p, bg=COLORS["bg"])
        url_row.pack(fill="x", pady=(4, 0))
        self.url_entry = tk.Entry(url_row, textvariable=self.url_var,
                                  font=FONTS["code"], bg=COLORS["card"],
                                  fg=COLORS["text"], insertbackground=COLORS["text"],
                                  relief="solid", bd=1)
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.url_entry.bind("<KeyRelease>", self._on_url_change)
        
        btn_paste = self._btn(url_row, "📋", COLORS["border"], COLORS["text"],
                             self._paste_url, width=3)
        btn_paste.pack(side="right", padx=(6, 0), ipady=8)
        Tooltip(btn_paste, "Paste from clipboard")
        
        # Options
        cb_row = tk.Frame(p, bg=COLORS["bg"])
        cb_row.pack(fill="x", pady=(8, 0))
        self.playlist_cb = ttk.Checkbutton(cb_row, text=" Download entire playlist",
                                           variable=self.playlist_var)
        self.playlist_cb.pack(side="left")
        Tooltip(self.playlist_cb, "If URL is a playlist, download all videos")
        
        self.audio_cb = ttk.Checkbutton(cb_row, text=" Audio only (MP3)",
                                        variable=self.audio_var)
        self.audio_cb.pack(side="right")
        Tooltip(self.audio_cb, "Extract audio as 320kbps MP3")
        
        self._sep(p)
        
        # Thumbnail & Info
        thumb_row = tk.Frame(p, bg=COLORS["bg"])
        thumb_row.pack(fill="x", pady=(0, 8))
        
        self.thumb_canvas = tk.Canvas(thumb_row, width=160, height=90,
                                      bg=COLORS["card"], highlightthickness=1,
                                      highlightbackground=COLORS["border"])
        self.thumb_canvas.pack(side="left")
        self.thumb_canvas.create_text(80, 45, text="No Preview", fill=COLORS["text_muted"],
                                      font=("Segoe UI", 9), tags="placeholder")
        
        info_side = tk.Frame(thumb_row, bg=COLORS["bg"])
        info_side.pack(side="left", fill="both", expand=True, padx=(12, 0))
        
        self.title_lbl = tk.Label(info_side, text="—", font=("Segoe UI", 10, "bold"),
                                  bg=COLORS["bg"], fg=COLORS["text"],
                                  wraplength=380, justify="left", anchor="w")
        self.title_lbl.pack(fill="x")
        
        self.meta_lbl = tk.Label(info_side, text="", font=FONTS["code"],
                                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                                 justify="left", anchor="w")
        self.meta_lbl.pack(fill="x", pady=(4, 0))
        
        self.vr_badge = tk.Label(info_side, text="", font=("Segoe UI", 9, "bold"),
                                 bg=COLORS["bg"], fg=COLORS["info"])
        self.vr_badge.pack(anchor="w", pady=(4, 0))
        
        # Save Path
        self._label(p, "SAVE TO")
        path_row = tk.Frame(p, bg=COLORS["card"], relief="solid", bd=1)
        path_row.pack(fill="x", pady=(4, 0))
        tk.Entry(path_row, textvariable=self.save_path, font=FONTS["code"],
                bg=COLORS["card"], fg=COLORS["text"], state="readonly",
                relief="flat", bd=0).pack(side="left", fill="x", expand=True, padx=8, ipady=8)
        self._btn(path_row, "Browse", COLORS["border"], COLORS["text"],
                 self._browse_folder).pack(side="right", padx=6, pady=4, ipadx=8)
        
        # Quality
        self._sep(p)
        q_row = tk.Frame(p, bg=COLORS["bg"])
        q_row.pack(fill="x", pady=(0, 6))
        self._label(q_row, "QUALITY", pack_side="left")
        
        self.fetch_btn = self._btn(q_row, "🔍  FETCH INFO", COLORS["accent"],
                                  "white", self._fetch_info)
        self.fetch_btn.pack(side="right", ipadx=12, ipady=5)
        
        self.quality_combo = ttk.Combobox(p, textvariable=self.quality_var,
                                          state="readonly", font=FONTS["code"])
        self.quality_combo.pack(fill="x", pady=(4, 0), ipady=4)
        self.quality_combo.set("Fetch Info First")
        
        # Log Output
        self._sep(p)
        self._label(p, "OUTPUT LOG")
        self.info_text = scrolledtext.ScrolledText(
            p, height=6, font=FONTS["code"],
            bg="#0a0a0a", fg=COLORS["info"], relief="flat",
            insertbackground=COLORS["info"], bd=0)
        self.info_text.pack(fill="x", pady=(4, 0))
        self.info_text.tag_config("ok", foreground=COLORS["success"])
        self.info_text.tag_config("warn", foreground=COLORS["warning"])
        self.info_text.tag_config("err", foreground=COLORS["accent"])
        self.info_text.tag_config("vr", foreground=COLORS["info"])
        
        # Progress
        self._sep(p)
        prog_frame = tk.Frame(p, bg=COLORS["panel"], pady=10)
        prog_frame.pack(fill="x")
        
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal",
                                        mode="determinate",
                                        style="red.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=12, pady=(0, 6))
        
        stat_row = tk.Frame(prog_frame, bg=COLORS["panel"])
        stat_row.pack(fill="x", padx=12)
        
        self.speed_lbl = tk.Label(stat_row, text="Speed: —", font=FONTS["main"],
                                  bg=COLORS["panel"], fg=COLORS["success"])
        self.speed_lbl.pack(side="left")
        
        self.eta_lbl = tk.Label(stat_row, text="ETA: —", font=FONTS["main"],
                               bg=COLORS["panel"], fg=COLORS["warning"])
        self.eta_lbl.pack(side="left", padx=16)
        
        self.got_lbl = tk.Label(stat_row, text="Got: —", font=FONTS["main"],
                               bg=COLORS["panel"], fg=COLORS["info"])
        self.got_lbl.pack(side="left")
        
        self.status_lbl = tk.Label(stat_row, text="IDLE", font=("Segoe UI", 10, "bold"),
                                  bg=COLORS["panel"], fg=COLORS["text_muted"])
        self.status_lbl.pack(side="right")
        
        # Buttons
        btn_row = tk.Frame(p, bg=COLORS["bg"])
        btn_row.pack(fill="x", pady=(10, 0))
        
        self.download_btn = self._btn(btn_row, "⬇  DOWNLOAD", COLORS["success"],
                                     "black", self._start_download,
                                     font=("Segoe UI", 12, "bold"))
        self.download_btn.pack(side="left", fill="x", expand=True, ipady=12)
        self.download_btn.config(state="disabled")
        
        self.queue_btn = self._btn(btn_row, "+ QUEUE", COLORS["border"],
                                  COLORS["text"], self._add_to_queue,
                                  font=("Segoe UI", 10, "bold"))
        self.queue_btn.pack(side="right", padx=(8, 0), ipady=12, ipadx=10)
        self.queue_btn.config(state="disabled")
        Tooltip(self.queue_btn, "Add to batch queue instead of downloading now")
    
    def _build_queue_tab(self):
        """Build queue management tab"""
        p = tk.Frame(self.tab_queue, bg=COLORS["bg"])
        p.pack(fill="both", expand=True, padx=20, pady=16)
        
        self._label(p, "DOWNLOAD QUEUE")
        tk.Label(p, text="Add items from the Download tab, then press Run All.",
                font=FONTS["code"], bg=COLORS["bg"],
                fg=COLORS["text_muted"]).pack(anchor="w", pady=(2, 8))
        
        # Queue listbox
        list_frame = tk.Frame(p, bg=COLORS["card"])
        list_frame.pack(fill="both", expand=True)
        
        self.queue_lb = tk.Listbox(list_frame, bg=COLORS["card"],
                                   fg=COLORS["text"], font=FONTS["code"],
                                   selectbackground=COLORS["border"],
                                   relief="flat", activestyle="none", bd=0)
        self.queue_lb.pack(side="left", fill="both", expand=True)
        
        sb = tk.Scrollbar(list_frame, bg=COLORS["card"], troughcolor=COLORS["card"])
        sb.pack(side="right", fill="y")
        self.queue_lb.config(yscrollcommand=sb.set)
        sb.config(command=self.queue_lb.yview)
        
        # Queue buttons
        qb_row = tk.Frame(p, bg=COLORS["bg"])
        qb_row.pack(fill="x", pady=(10, 0))
        
        self.run_queue_btn = self._btn(qb_row, "▶  RUN ALL", COLORS["success"],
                                      "black", self._run_queue,
                                      font=("Segoe UI", 11, "bold"))
        self.run_queue_btn.pack(side="left", ipadx=14, ipady=8)
        
        self._btn(qb_row, "✕  Remove", COLORS["border"], COLORS["text"],
                 self._remove_queue_item).pack(side="left", padx=(8, 0), ipadx=10, ipady=8)
        
        self._btn(qb_row, "Clear All", "#3a1a1a", COLORS["accent"],
                 self._clear_queue).pack(side="right", ipadx=10, ipady=8)
        
        # Queue progress
        self.queue_progress_lbl = tk.Label(p, text="", font=FONTS["code"],
                                          bg=COLORS["bg"], fg=COLORS["text_muted"])
        self.queue_progress_lbl.pack(anchor="w", pady=(8, 0))
        
        self.queue_bar = ttk.Progressbar(p, orient="horizontal",
                                        mode="determinate",
                                        style="green.Horizontal.TProgressbar")
        self.queue_bar.pack(fill="x", pady=(4, 0))
    
    def _build_history_tab(self):
        """Build history viewer tab"""
        p = tk.Frame(self.tab_history, bg=COLORS["bg"])
        p.pack(fill="both", expand=True, padx=20, pady=16)
        
        self._label(p, "DOWNLOAD HISTORY")
        
        cols = ("date", "title", "quality", "path")
        self.hist_tree = ttk.Treeview(p, columns=cols, show="headings")
        
        style = ttk.Style()
        style.configure("hist.Treeview",
                       background=COLORS["card"],
                       fieldbackground=COLORS["card"],
                       foreground=COLORS["text"],
                       font=FONTS["code"],
                       rowheight=24)
        style.configure("hist.Treeview.Heading",
                       background=COLORS["panel"],
                       foreground=COLORS["text"],
                       font=("Segoe UI", 9, "bold"))
        style.map("hist.Treeview",
                 background=[("selected", COLORS["border"])])
        
        self.hist_tree.configure(style="hist.Treeview")
        
        self.hist_tree.heading("date", text="Date")
        self.hist_tree.heading("title", text="Title")
        self.hist_tree.heading("quality", text="Quality")
        self.hist_tree.heading("path", text="Save Path")
        
        self.hist_tree.column("date", width=110, anchor="w")
        self.hist_tree.column("title", width=250, anchor="w")
        self.hist_tree.column("quality", width=70, anchor="center")
        self.hist_tree.column("path", width=150, anchor="w")
        
        sb = ttk.Scrollbar(p, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=sb.set)
        self.hist_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        btn_row = tk.Frame(self.tab_history, bg=COLORS["bg"])
        btn_row.pack(fill="x", padx=20, pady=(6, 12))
        self._btn(btn_row, "Clear History", "#3a1a1a", COLORS["accent"],
                 self._clear_history).pack(side="right", ipadx=10, ipady=6)
        
        self._refresh_history_tree()
    
    # ─────────────────────────────────────────────────────────────────────────
    #  UI HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    
    def _label(self, parent: tk.Widget, text: str, pack_side: Optional[str] = None) -> tk.Label:
        """Create a styled label"""
        lbl = tk.Label(parent, text=text, font=("Segoe UI", 8, "bold"),
                      bg=COLORS["bg"], fg=COLORS["text_muted"], pady=4)
        if pack_side:
            lbl.pack(side=pack_side, padx=(0, 8))
        else:
            lbl.pack(anchor="w")
        return lbl
    
    def _btn(self, parent: tk.Widget, text: str, bg: str, fg: str,
            cmd, width: Optional[int] = None,
            font=FONTS["header"]) -> tk.Button:
        """Create a styled button"""
        b = tk.Button(parent, text=text, bg=bg, fg=fg, font=font,
                     relief="solid", bd=1, cursor="hand2", command=cmd,
                     activebackground=bg, activeforeground=fg)
        if width:
            b.config(width=width)
        return b
    
    def _sep(self, parent: tk.Widget):
        """Create a separator line"""
        tk.Frame(parent, bg=COLORS["border"], height=1).pack(fill="x", pady=10)
    
    def _log(self, msg: str, tag: str = ""):
        """Log message to output"""
        self.info_text.insert(tk.END, msg + "\n", tag)
        self.info_text.see(tk.END)
    
    def _set_status(self, text: str, color: str = COLORS["text_muted"]):
        """Update status label"""
        self.status_lbl.config(text=text, fg=color)
    
    # ─────────────────────────────────────────────────────────────────────────
    #  EVENTS & HANDLERS
    # ─────────────────────────────────────────────────────────────────────────
    
    def _paste_url(self):
        """Paste URL from clipboard"""
        try:
            clip = self.root.clipboard_get().strip()
            self.url_var.set(clip)
            self._on_url_change()
        except Exception:
            pass
    
    def _on_url_change(self, *_):
        """Handle URL change"""
        self._reset_preview()
        if self._thumb_job:
            self.root.after_cancel(self._thumb_job)
        self._thumb_job = self.root.after(1200, lambda: None)
    
    def _reset_preview(self):
        """Reset thumbnail and info preview"""
        self.thumb_canvas.delete("all")
        self.thumb_canvas.create_text(80, 45, text="No Preview",
                                     fill=COLORS["text_muted"],
                                     font=("Segoe UI", 9),
                                     tags="placeholder")
        self.title_lbl.config(text="—")
        self.meta_lbl.config(text="")
        self.vr_badge.config(text="")
        self.quality_combo.set("Fetch Info First")
        self.download_btn.config(state="disabled")
        self.queue_btn.config(state="disabled")
        self.is_vr = False
        self.info_data = None
    
    def _on_audio_toggle(self, *_):
        """Handle audio toggle"""
        if self.audio_var.get():
            self.quality_combo.config(state="disabled")
            self.quality_var.set("Audio Only (MP3)")
        else:
            self.quality_combo.config(state="readonly")
            if self.info_data:
                self.quality_combo.current(0)
    
    def _browse_folder(self):
        """Browse for save folder"""
        folder = filedialog.askdirectory(initialdir=self.save_path.get())
        if folder:
            self.save_path.set(folder)
    
    # ─────────────────────────────────────────────────────────────────────────
    #  DEPENDENCY MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────
    
    def _check_and_install_dependencies(self, missing_tools: List[str],
                                       missing_packages: List[str]):
        """Check and install missing dependencies"""
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
    
    def _install_dependencies_thread(self, missing_tools: List[str],
                                    missing_packages: List[str]):
        """Install dependencies in background thread"""
        def install():
            success_count, failed_items = DependencyManager.install_dependencies(
                missing_tools, missing_packages)
            self.root.after(0, lambda: self._show_installation_result(success_count, failed_items))
        
        threading.Thread(target=install, daemon=True).start()
    
    def _show_installation_result(self, success_count: int, failed_items: List[str]):
        """Show installation result"""
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
            
            messagebox.showwarning("Installation Partial", msg)
    
    # ─────────────────────────────────────────────────────────────────────────
    #  VIDEO INFO FETCHING
    # ─────────────────────────────────────────────────────────────────────────
    
    def _fetch_info(self):
        """Fetch video information"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please enter a video URL first.")
            return
        
        self.info_text.delete("1.0", tk.END)
        self._log("@ Fetching info…")
        self.fetch_btn.config(state="disabled")
        self._set_status("FETCHING…", COLORS["warning"])
        threading.Thread(target=self._fetch_thread, args=(url,), daemon=True).start()
    
    def _fetch_thread(self, url: str):
        """Fetch video info in thread"""
        try:
            opts = {
                'quiet': True,
                'noplaylist': not self.playlist_var.get(),
                'nocheckcertificate': True,
                'extract_flat': self.playlist_var.get(),
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.root.after(0, lambda: self._process_fetched(info, url))
        except Exception as e:
            self.root.after(0, lambda: self._fetch_error(str(e)))
    
    def _process_fetched(self, info: Dict, url: str):
        """Process fetched video information"""
        self.info_data = info
        is_playlist = info.get("_type") == "playlist"
        self.is_playlist = is_playlist
        
        if is_playlist:
            self._handle_playlist(info)
        else:
            self._handle_single_video(info)
    
    def _handle_playlist(self, info: Dict):
        """Handle playlist info"""
        entries = info.get("entries", [])
        count = len(entries)
        self._log(f"PLAYLIST: {info.get('title', 'Unknown')}", "ok")
        self._log(f"{count} video(s) found.")
        self.title_lbl.config(text=f"📋  {info.get('title', 'Playlist')}")
        self.meta_lbl.config(text=f"{count} videos")
        self.quality_combo['values'] = ["Best Available", "1080p", "720p", "480p", "360p"]
        self.quality_combo.current(0)
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        self._set_status("READY", COLORS["success"])
        self.fetch_btn.config(state="normal")
    
    def _handle_single_video(self, info: Dict):
        """Handle single video info"""
        title = info.get("title", "Unknown")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "")
        view_cnt = info.get("view_count", 0)
        thumb_url = info.get("thumbnail", "")
        
        # VR/360 detection
        tags = info.get("tags") or []
        description = info.get("description") or ""
        projection = str(info.get("projection", "")).lower()
        spherical = info.get("spherical", False)
        formats = info.get("formats", [])
        
        is_vr = (
            spherical or
            projection in ("equirectangular", "360", "vr180") or
            any("360" in str(t).lower() or "vr" in str(t).lower() for t in tags) or
            "360" in title.lower() or
            any(str(f.get("format_note", "")).lower() in ("360", "vr", "equirectangular")
                for f in formats)
        )
        self.is_vr = is_vr
        
        # Build resolution list
        res_list = []
        size_dict = {}
        table_lines = [f"TITLE : {title}", "─" * 60]
        
        if is_vr:
            table_lines.append("⚠  VR / 360° video detected")
        
        for res in [4320, 2160, 1440, 1080, 720, 480, 360, 240]:
            matching = [f for f in formats if f.get("height") == res]
            if matching:
                res_list.append(f"{res}p")
                max_size = max(f.get("filesize") or 0 for f in matching)
                size_dict[f"{res}p"] = max_size
                size_str = format_file_size(max_size) if max_size > 0 else "size N/A"
                table_lines.append(f"  ✔  {res}p  —  {size_str}")
        
        self.size_dict = size_dict
        table_text = "\n".join(table_lines)
        
        dur_str = format_duration(duration)
        views_str = f"{view_cnt:,}" if view_cnt else "—"
        
        self._log(table_text, "vr" if is_vr else "")
        self.title_lbl.config(text=title)
        self.meta_lbl.config(text=f"⏱ {dur_str}   👁 {views_str} views   ↑ {uploader}")
        
        if is_vr:
            self.vr_badge.config(text="🔮  360° / VR Video")
        
        opts = ["Best Available"] + sorted(set(res_list),
                                          key=lambda x: int(x[:-1]), reverse=True)
        self.quality_combo['values'] = opts
        self.quality_combo.current(0)
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        self._set_status("READY", COLORS["success"])
        self.fetch_btn.config(state="normal")
        
        if thumb_url:
            threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()
    
    def _fetch_error(self, msg: str):
        """Handle fetch error"""
        self._log(f"ERROR: {msg}", "err")
        self._set_status("ERROR", COLORS["accent"])
        self.fetch_btn.config(state="normal")
    
    # ─────────────────────────────────────────────────────────────────────────
    #  THUMBNAIL HANDLING
    # ─────────────────────────────────────────────────────────────────────────
    
    def _load_thumbnail(self, url: str):
        """Load and display thumbnail"""
        try:
            from PIL import Image, ImageTk
            import io
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).resize(THUMBNAIL_SIZE, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, lambda: self._set_thumb(photo))
        except ImportError:
            self.root.after(0, lambda: self.thumb_canvas.create_text(
                80, 45, text="Install Pillow\nfor previews",
                fill=COLORS["text_muted"], font=("Segoe UI", 8),
                justify="center"))
        except Exception:
            pass
    
    def _set_thumb(self, photo):
        """Set thumbnail image"""
        self._thumb_photo = photo
        self.thumb_canvas.delete("all")
        self.thumb_canvas.create_image(0, 0, anchor="nw", image=photo)
    
    # ─────────────────────────────────────────────────────────────────────────
    #  DOWNLOAD FUNCTIONALITY
    # ─────────────────────────────────────────────────────────────────────────
    
    def _start_download(self):
        """Start video download"""
        url = self.url_var.get().strip()
        quality = self.quality_var.get()
        audio = self.audio_var.get()
        playlist = self.playlist_var.get()
        
        if not url:
            return
        
        self.download_btn.config(state="disabled")
        self.queue_btn.config(state="disabled")
        self._set_status("STARTING…", COLORS["warning"])
        threading.Thread(
            target=self._download_thread,
            args=(url, quality, audio, playlist, self.is_vr),
            daemon=True
        ).start()
    
    def _download_thread(self, url: str, quality: str, audio_only: bool,
                        playlist: bool, is_vr: bool):
        """Download in thread"""
        success, title = self._run_download(url, quality, audio_only, playlist, is_vr)
        if success:
            self.root.after(0, lambda: self._on_complete(url, quality if not audio_only else "MP3", title))
        else:
            self.root.after(0, lambda: self._on_failed())
    
    def _build_ydl_opts(self, quality: str, audio_only: bool, playlist: bool,
                       is_vr: bool, hook=None, post_hook=None) -> Dict:
        """Build yt-dlp options"""
        save = self.save_path.get()
        opts = {
            'outtmpl': (os.path.join(save, '%(playlist_index)s-%(title)s [%(height)sp].%(ext)s')
                       if playlist else
                       os.path.join(save, '%(title)s [%(height)sp].%(ext)s')),
            'merge_output_format': 'mp4',
            'nocolor': True,
            'nocheckcertificate': True,
            'noplaylist': not playlist,
        }
        
        if hook:
            opts['progress_hooks'] = [hook]
        if post_hook:
            opts['postprocessor_hooks'] = [post_hook]
        
        if audio_only:
            opts['format'] = 'bestaudio/best'
            opts['outtmpl'] = os.path.join(save, '%(title)s.%(ext)s')
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
            return opts
        
        h = "best" if quality == "Best Available" else quality.replace("p", "")
        
        if is_vr:
            if h == "best":
                opts['format'] = "bestvideo+bestaudio/best"
            else:
                opts['format'] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
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
    
    def _run_download(self, url: str, quality: str, audio_only: bool,
                     playlist: bool, is_vr: bool) -> Tuple[bool, str]:
        """Execute download"""
        title = "Unknown"
        opts = self._build_ydl_opts(quality, audio_only, playlist, is_vr,
                                   hook=self._progress_hook,
                                   post_hook=self._postprocess_hook)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url)
                if info:
                    title = info.get("title", url[:40])
            return True, title
        except Exception as e:
            self.root.after(0, lambda: self._log("⚠ Primary failed, trying fallback…", "warn"))
            h = "best" if quality == "Best Available" else quality.replace("p", "")
            fb_fmt = "best" if h == "best" else f"best[height<={h}][ext=mp4]/best"
            opts2 = self._build_ydl_opts(fb_fmt, audio_only, playlist, False)
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
    
    def _progress_hook(self, d: Dict):
        """Handle download progress"""
        if d['status'] == 'downloading':
            raw_p = strip_ansi(d.get('_percent_str', '0%')).replace('%', '').strip()
            speed = strip_ansi(d.get('_speed_str', '—'))
            eta = strip_ansi(d.get('_eta_str', '—'))
            got = strip_ansi(d.get('_downloaded_bytes_str', '—'))
            try:
                pct = float(raw_p)
                self.root.after(0, lambda: self.progress.config(value=pct))
                self.root.after(0, lambda: self.speed_lbl.config(text=f"Speed: {speed}"))
                self.root.after(0, lambda: self.eta_lbl.config(text=f"ETA: {eta}"))
                self.root.after(0, lambda: self.got_lbl.config(text=f"Got: {got}"))
                self.root.after(0, lambda: self._set_status(f"DOWNLOADING {pct:.0f}%", COLORS["warning"]))
            except Exception:
                pass
        elif d['status'] == 'finished':
            self.root.after(0, lambda: self._set_status("PROCESSING…", COLORS["info"]))
    
    def _postprocess_hook(self, d: Dict):
        """Handle post-processing"""
        if d['status'] == 'started':
            self.root.after(0, lambda: self._set_status("⚙  MERGING…", COLORS["info"]))
    
    def _on_complete(self, url: str, quality: str, title: str):
        """Handle download completion"""
        self._set_status("COMPLETE ✓", COLORS["success"])
        self.progress.config(value=100)
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        self._log(f"✔ Done: {title}", "ok")
        
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": title,
            "quality": quality,
            "path": self.save_path.get(),
            "url": url,
        }
        self.history.insert(0, entry)
        self.history = self.history[:MAX_HISTORY_ENTRIES]
        save_history(self.history)
        self._refresh_history_tree()
        
        if messagebox.askyesno("Done ✓", f"'{title}' downloaded!\n\nOpen folder?"):
            open_folder(self.save_path.get())
    
    def _on_failed(self):
        """Handle download failure"""
        self._set_status("FAILED", COLORS["accent"])
        self.download_btn.config(state="normal")
        self.queue_btn.config(state="normal")
        messagebox.showerror("Download Failed",
            "All attempts failed.\nCheck your internet connection and FFmpeg install.")
    
    # ─────────────────────────────────────────────────────────────────────────
    #  QUEUE MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────
    
    def _add_to_queue(self):
        """Add current video to download queue"""
        url = self.url_var.get().strip()
        quality = self.quality_var.get()
        audio = self.audio_var.get()
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
        """Refresh queue listbox"""
        self.queue_lb.delete(0, tk.END)
        for item in self.download_queue:
            self.queue_lb.insert(tk.END, str(item))
    
    def _remove_queue_item(self):
        """Remove selected queue item"""
        sel = self.queue_lb.curselection()
        if sel:
            del self.download_queue[sel[0]]
            self._refresh_queue_lb()
    
    def _clear_queue(self):
        """Clear entire queue"""
        if messagebox.askyesno("Clear Queue", "Remove all queued items?"):
            self.download_queue.clear()
            self._refresh_queue_lb()
    
    def _run_queue(self):
        """Run entire queue"""
        if not self.download_queue:
            messagebox.showinfo("Queue Empty", "Add items to the queue first.")
            return
        
        self.run_queue_btn.config(state="disabled")
        threading.Thread(target=self._queue_thread, daemon=True).start()
    
    def _queue_thread(self):
        """Process queue in thread"""
        total = len(self.download_queue)
        for idx, item in enumerate(self.download_queue):
            if item.status == "Done":
                continue
            
            item.status = "Working"
            self.root.after(0, self._refresh_queue_lb)
            self.root.after(0, lambda i=idx, t=total: self.queue_progress_lbl.config(
                text=f"Processing {i + 1} / {t}  —  {self.download_queue[i].title[:50]}"))
            self.root.after(0, lambda i=idx, t=total: self.queue_bar.config(value=(i / t) * 100))
            
            success, title = self._run_download(
                item.url, item.quality, item.audio_only, False, False)
            
            item.status = "Done" if success else "Failed"
            if success:
                entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "title": title,
                    "quality": item.quality if not item.audio_only else "MP3",
                    "path": self.save_path.get(),
                    "url": item.url,
                }
                self.history.insert(0, entry)
                save_history(self.history)
            
            self.root.after(0, self._refresh_queue_lb)
            self.root.after(0, self._refresh_history_tree)
        
        self.root.after(0, lambda: self.queue_bar.config(value=100))
        self.root.after(0, lambda: self.queue_progress_lbl.config(text="Queue complete ✓"))
        self.root.after(0, lambda: self.run_queue_btn.config(state="normal"))
        self.root.after(0, lambda: messagebox.showinfo("Queue Done", f"Finished {total} item(s)."))
    
    # ─────────────────────────────────────────────────────────────────────────
    #  HISTORY MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────
    
    def _refresh_history_tree(self):
        """Refresh history treeview"""
        self.hist_tree.delete(*self.hist_tree.get_children())
        for e in self.history:
            self.hist_tree.insert("", "end", values=(
                e.get("date", ""),
                e.get("title", "")[:55],
                e.get("quality", ""),
                e.get("path", ""),
            ))
    
    def _clear_history(self):
        """Clear download history"""
        if messagebox.askyesno("Clear History", "Delete all download history?"):
            self.history.clear()
            save_history(self.history)
            self._refresh_history_tree()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeDownloader(root)
    root.mainloop()
