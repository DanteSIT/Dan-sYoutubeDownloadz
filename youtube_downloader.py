import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import yt_dlp
import threading
import os
import subprocess
import re
import shutil

class YouTubeDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader by Dante")
        self.root.geometry("850x950")
        self.root.configure(bg="#0f0f0f")

        # Theme Colors
        self.bg_color = "#0f0f0f"
        self.accent = "#ff0000"
        self.green = "#00ff00"
        self.text = "#ffffff"
        self.gray = "#aaaaaa"

        self.url_var = tk.StringVar()
        self.save_path = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.quality_var = tk.StringVar(value="Select Quality")

        self.setup_ui()
        self.check_system_tools()

    def check_system_tools(self):
        """Alerts user if FFmpeg is missing."""
        if not shutil.which("ffmpeg"):
            messagebox.showwarning("FFmpeg Missing",
                "FFmpeg not found! 1080p+ downloads will likely freeze or fail.\n"
                "Linux: 'sudo apt install ffmpeg'\n"
                "Windows: Download ffmpeg.exe and add to PATH.")

    def clean_ansi(self, text):
        """Removes terminal color codes like [0;32m."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg=self.accent, height=60)
        header.pack(fill="x")
        tk.Label(header, text="YouTube Downloader", font=("Arial", 18, "bold"), bg=self.accent, fg="white").pack(pady=15)

        main_frame = tk.Frame(self.root, bg=self.bg_color)
        main_frame.pack(fill="both", expand=True, padx=30, pady=20)

        # URL Input
        tk.Label(main_frame, text="Video URL", font=("Arial", 11, "bold"), bg=self.bg_color, fg=self.text).pack(anchor="w")
        tk.Entry(main_frame, textvariable=self.url_var, font=("Arial", 11), bg="#2a2a2a", fg="white", relief="flat").pack(fill="x", pady=(5, 15), ipady=8)

        # Path Selection
        path_frame = tk.Frame(main_frame, bg="#1f1f1f")
        path_frame.pack(fill="x", pady=(5, 15))
        tk.Entry(path_frame, textvariable=self.save_path, font=("Arial", 10), bg="#2a2a2a", fg="white", state="readonly", relief="flat").pack(side="left", fill="x", expand=True, padx=10, ipady=8)
        tk.Button(path_frame, text="Browse", bg="#444444", fg="white", relief="flat", command=self.browse_folder).pack(side="right", padx=5, pady=5)

        # Quality & Fetch Row
        row_frame = tk.Frame(main_frame, bg=self.bg_color)
        row_frame.pack(fill="x", pady=10)

        self.quality_combo = ttk.Combobox(row_frame, textvariable=self.quality_var, state="readonly", font=("Arial", 11), width=25)
        self.quality_combo.pack(side="left", pady=5)
        self.quality_combo.set("1. Fetch Info First")

        tk.Button(row_frame, text="🔍 FETCH INFO", font=("Arial", 11, "bold"), bg=self.accent, fg="white", relief="flat", command=self.fetch_info).pack(side="right", ipadx=20)

        # Info Box
        self.info_text = scrolledtext.ScrolledText(main_frame, height=10, font=("Consolas", 11), bg="#161616", fg="#00ffaa", relief="flat")
        self.info_text.pack(fill="x", pady=10)

        # Stats Dashboard
        self.progress_frame = tk.LabelFrame(main_frame, text=" Live Stats ", bg=self.bg_color, fg=self.gray)
        self.progress_frame.pack(fill="x", pady=10, ipady=10)

        self.progress = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate", length=700)
        self.progress.pack(fill="x", padx=15, pady=5)

        self.stats_label = tk.Label(self.progress_frame, text="Speed: -- | ETA: -- | Got: --", font=("Consolas", 10), bg=self.bg_color, fg=self.text)
        self.stats_label.pack()

        self.status_label = tk.Label(main_frame, text="IDLE", font=("Arial", 12, "bold"), bg=self.bg_color, fg=self.gray)
        self.status_label.pack(pady=5)

        # Download Button
        self.download_btn = tk.Button(main_frame, text="⬇️ START DOWNLOAD", font=("Arial", 16, "bold"), bg=self.green, fg="black", height=2, state="disabled", relief="flat", command=self.start_download)
        self.download_btn.pack(fill="x", pady=10)

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.save_path.get())
        if folder: self.save_path.set(folder)

    def fetch_info(self):
        url = self.url_var.get().strip()
        if not url: return
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, " ⚙ Probing YouTube... please wait.\n")

        def thread_target():
            try:
                ydl_opts = {'quiet': True, 'noplaylist': True, 'nocheckcertificate': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                formats = info.get('formats', [])
                res_list = []
                table = f"TITLE: {info.get('title')}\n" + "═"*65 + "\n"

                for res in [4320, 2160, 1440, 1080, 720, 480, 360]:
                    if any(f.get('height') == res for f in formats):
                        res_list.append(f"{res}p")
                        table += f"✔️ {res}p Available\n"

                self.root.after(0, lambda: self.finish_fetch(table, res_list))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Fetch failed: {e}"))

        threading.Thread(target=thread_target, daemon=True).start()

    def finish_fetch(self, text, res_list):
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, text)
        self.quality_combo['values'] = ["Best Available"] + sorted(list(set(res_list)), key=lambda x: int(x.replace('p','')), reverse=True)
        self.quality_combo.current(0)
        self.download_btn.config(state="normal")
        self.status_label.config(text="READY", fg=self.green)

    def start_download(self):
        url = self.url_var.get().strip()
        selected = self.quality_var.get()
        self.download_btn.config(state="disabled")

        def download_thread():
            h = "best" if selected == "Best Available" else selected.replace('p','')
            # Primary Attempt: High Quality Merge
            fmt = "bestvideo+bestaudio/best" if h == "best" else f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"

            success = self.run_ydl(url, fmt)

            # Fallback Attempt: Single File (fixes 1080p freeze if ffmpeg is missing)
            if not success:
                self.root.after(0, lambda: self.status_label.config(text="FALLBACK MODE...", fg="yellow"))
                fallback_fmt = f"best[height<={h}][ext=mp4]/best"
                success = self.run_ydl(url, fallback_fmt)

            if success:
                self.root.after(0, self.on_complete)
            else:
                self.root.after(0, lambda: messagebox.showerror("Error", "Download failed after fallback. Check FFmpeg."))

            self.root.after(0, lambda: self.download_btn.config(state="normal"))

        threading.Thread(target=download_thread, daemon=True).start()

    def run_ydl(self, url, fmt_string):
        opts = {
            'format': fmt_string,
            'outtmpl': os.path.join(self.save_path.get(), '%(title)s [%(height)sp].%(ext)s'),
            'merge_output_format': 'mp4',
            'nocolor': True,
            'progress_hooks': [self.update_progress],
            'postprocessor_hooks': [self.post_process_hook]
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return True
        except: return False

    def update_progress(self, d):
        if d['status'] == 'downloading':
            p_raw = d.get('_percent_str', '0%')
            p = self.clean_ansi(p_raw).replace('%','').strip()
            speed = self.clean_ansi(d.get('_speed_str', 'N/A'))
            eta = self.clean_ansi(d.get('_eta_str', 'N/A'))
            got = self.clean_ansi(d.get('_downloaded_bytes_str', '0MB'))

            try:
                self.root.after(0, lambda: self.progress.config(value=float(p)))
                self.root.after(0, lambda: self.stats_label.config(text=f"Speed: {speed} | ETA: {eta} | Got: {got}"))
                self.root.after(0, lambda: self.status_label.config(text=f"DOWNLOADING {p}%", fg="#ffaa00"))
            except: pass

    def post_process_hook(self, d):
        if d['status'] == 'started':
            self.root.after(0, lambda: self.status_label.config(text="⚙️ STITCHING VIDEO & AUDIO...", fg="#ff00ff"))

    def on_complete(self):
        self.status_label.config(text="COMPLETE!", fg=self.green)
        self.progress.config(value=100)
        if messagebox.askyesno("Done", "Download successful! Open folder?"):
            path = os.path.realpath(self.save_path.get())
            if os.name == 'nt': os.startfile(path)
            else: subprocess.Popen(['xdg-open', path])

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeDownloader(root)
    root.mainloop()
