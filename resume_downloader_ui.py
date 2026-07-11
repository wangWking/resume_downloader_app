import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from resume_downloader_core import (
    DownloadOptions,
    download_resumes,
    get_runtime_app_dir,
    test_mail_connection,
)


PROVIDER_LABELS = {
    "飞书邮箱": "feishu",
    "腾讯企业邮箱": "tencent",
}

SHOW_TEST_BUTTON = False


class ResumeDownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("邮箱简历附件抓取工具")
        self.root.geometry("1080x680")
        self.root.minsize(980, 620)

        self.message_queue = queue.Queue()
        self.worker = None

        self.provider_var = tk.StringVar(value="飞书邮箱")
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.folder_var = tk.StringVar(value="简历库")
        self.output_var = tk.StringVar(value=r"D:\邮件简历库")
        self.download_all_var = tk.BooleanVar(value=False)

        self.configure_style()
        self.build_ui()
        self.root.after(100, self.process_queue)

    def configure_style(self):
        self.root.option_add("*Font", ("Microsoft YaHei UI", 11))
        style = ttk.Style()
        base_font = ("Microsoft YaHei UI", 11)
        style.configure(".", font=base_font)
        style.configure("TLabel", font=base_font)
        style.configure("TEntry", font=base_font)
        style.configure("TCombobox", font=base_font)
        style.configure("TCheckbutton", font=base_font)
        style.configure("TButton", font=base_font, padding=(8, 5))

    def build_ui(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        app_title = ttk.Label(
            self.root,
            text="邮箱简历附件抓取工具",
            font=("Microsoft YaHei UI", 20, "bold"),
            padding=(18, 16, 18, 4),
        )
        app_title.grid(row=0, column=0, columnspan=2, sticky="w")

        left = ttk.Frame(self.root, padding=(18, 10, 18, 18))
        left.grid(row=1, column=0, sticky="ns")

        right = ttk.Frame(self.root, padding=(0, 10, 18, 18))
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        title = ttk.Label(left, text="抓取设置", font=("Microsoft YaHei UI", 17, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        ttk.Label(left, text="邮箱类型").grid(row=1, column=0, sticky="w", pady=6)
        provider_combo = ttk.Combobox(
            left,
            textvariable=self.provider_var,
            values=list(PROVIDER_LABELS.keys()),
            state="readonly",
            width=24,
        )
        provider_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(left, text="邮箱账号").grid(row=2, column=0, sticky="w", pady=6)
        email_entry = ttk.Entry(left, textvariable=self.email_var, width=30)
        email_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(left, text="客户端专用密码").grid(row=3, column=0, sticky="w", pady=6)
        password_entry = ttk.Entry(left, textvariable=self.password_var, show="*", width=30)
        password_entry.grid(row=3, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(left, text="目标文件夹").grid(row=4, column=0, sticky="w", pady=6)
        folder_entry = ttk.Entry(left, textvariable=self.folder_var, width=30)
        folder_entry.grid(row=4, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(left, text="保存目录").grid(row=5, column=0, sticky="w", pady=6)
        output_entry = ttk.Entry(left, textvariable=self.output_var, width=30)
        output_entry.grid(row=5, column=1, sticky="ew", pady=6)
        browse_button = ttk.Button(left, text="选择", command=self.choose_output_dir)
        browse_button.grid(row=5, column=2, sticky="e", padx=(8, 0), pady=6)

        all_check = ttk.Checkbutton(
            left,
            text="重新抓取全部历史附件",
            variable=self.download_all_var,
        )
        all_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 4))

        self.test_button = None
        if SHOW_TEST_BUTTON:
            self.test_button = ttk.Button(left, text="测试连接", command=self.start_test_connection)
            self.test_button.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(18, 4))
            start_row = 8
            note_row = 9
            start_pady = (8, 4)
        else:
            start_row = 7
            note_row = 8
            start_pady = (18, 4)

        self.start_button = ttk.Button(left, text="开始抓取", command=self.start_download)
        self.start_button.grid(row=start_row, column=0, columnspan=3, sticky="ew", pady=start_pady)

        note = ttk.Label(
            left,
            text="密码仅在本次打开窗口期间保存在内存中，关闭后不会保存。",
            wraplength=300,
            foreground="#555555",
        )
        note.grid(row=note_row, column=0, columnspan=3, sticky="w", pady=(12, 0))

        left.columnconfigure(1, weight=1)

        log_title = ttk.Label(right, text="运行日志", font=("Microsoft YaHei UI", 17, "bold"))
        log_title.grid(row=0, column=0, sticky="w", pady=(0, 10))

        log_frame = ttk.Frame(right)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            height=20,
            font=("Consolas", 12),
            state="disabled",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def choose_output_dir(self):
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or r"D:\\")
        if selected:
            self.output_var.set(selected)

    def show_dialog(self, title: str, message: str, kind: str = "info"):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        symbols = {
            "info": "i",
            "warning": "!",
            "error": "x",
        }

        frame = ttk.Frame(dialog, padding=22)
        frame.grid(row=0, column=0, sticky="nsew")

        symbol = ttk.Label(
            frame,
            text=symbols.get(kind, "i"),
            font=("Microsoft YaHei UI", 22, "bold"),
            width=2,
            anchor="center",
        )
        symbol.grid(row=0, column=0, sticky="n", padx=(0, 14))

        message_label = ttk.Label(
            frame,
            text=message,
            font=("Microsoft YaHei UI", 12),
            wraplength=460,
            justify="left",
        )
        message_label.grid(row=0, column=1, sticky="w")

        ok_button = ttk.Button(dialog, text="确定", command=dialog.destroy)
        ok_button.grid(row=1, column=0, pady=(0, 18))

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        ok_button.focus_set()
        self.root.wait_window(dialog)

    def append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def validate_inputs(self) -> bool:
        if not self.provider_var.get():
            self.show_dialog("缺少信息", "请选择邮箱类型。", "warning")
            return False
        email_address = self.email_var.get().strip()
        if not email_address:
            self.show_dialog("缺少信息", "请输入邮箱账号。", "warning")
            return False
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_address):
            self.show_dialog("邮箱格式不正确", "请输入完整邮箱账号，例如 name@example.com。", "warning")
            return False
        if not self.password_var.get():
            self.show_dialog("缺少信息", "请输入客户端专用密码。", "warning")
            return False
        if not self.folder_var.get().strip():
            self.show_dialog("缺少信息", "请输入目标文件夹。", "warning")
            return False
        if not self.output_var.get().strip():
            self.show_dialog("缺少信息", "请选择保存目录。", "warning")
            return False
        return True

    def build_options(self) -> DownloadOptions:
        provider = PROVIDER_LABELS[self.provider_var.get()]
        app_dir = get_runtime_app_dir()
        return DownloadOptions(
            provider=provider,
            email_address=self.email_var.get().strip(),
            credential=self.password_var.get(),
            folder=self.folder_var.get().strip(),
            output_dir=Path(self.output_var.get().strip()),
            download_all=self.download_all_var.get(),
            app_dir=app_dir,
        )

    def set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.start_button.configure(state=state)
        if self.test_button is not None:
            self.test_button.configure(state=state)

    def start_test_connection(self):
        if self.worker and self.worker.is_alive():
            return

        if not self.validate_inputs():
            return

        options = self.build_options()
        self.set_busy(True)
        self.append_log("")
        self.append_log("准备测试连接...")

        self.worker = threading.Thread(
            target=self.run_test_connection,
            args=(options,),
            daemon=True,
        )
        self.worker.start()

    def start_download(self):
        if self.worker and self.worker.is_alive():
            return

        if not self.validate_inputs():
            return

        options = self.build_options()
        self.set_busy(True)
        self.append_log("")
        self.append_log("准备开始抓取...")

        self.worker = threading.Thread(
            target=self.run_download,
            args=(options,),
            daemon=True,
        )
        self.worker.start()

    def run_test_connection(self, options: DownloadOptions):
        try:
            test_mail_connection(options, log_callback=self.message_queue.put)
            self.message_queue.put(("TEST_DONE", None))
        except Exception as exc:
            self.message_queue.put(("ERROR", str(exc)))

    def run_download(self, options: DownloadOptions):
        try:
            download_resumes(options, log_callback=self.message_queue.put)
            self.message_queue.put(("DONE", None))
        except Exception as exc:
            self.message_queue.put(("ERROR", str(exc)))

    def process_queue(self):
        try:
            while True:
                item = self.message_queue.get_nowait()
                if isinstance(item, tuple):
                    kind, payload = item
                    if kind == "DONE":
                        self.set_busy(False)
                        self.show_dialog("完成", "抓取完成。", "info")
                    elif kind == "TEST_DONE":
                        self.set_busy(False)
                        self.show_dialog("测试成功", "测试连接成功，可以开始抓取。", "info")
                    elif kind == "ERROR":
                        self.set_busy(False)
                        self.append_log("")
                        self.append_log(f"操作失败：{payload}")
                        self.show_dialog("操作失败", payload, "error")
                else:
                    self.append_log(str(item))
        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)


def main():
    root = tk.Tk()
    ResumeDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
