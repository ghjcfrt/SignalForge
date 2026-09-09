"""本地 FastAPI 进程使用的原生目录选择器。

选择器运行在守护线程中，因为 Tk 要求图形线程且模态对话框不能阻塞
FastAPI 事件循环。请求按顺序处理，使两个输出目录控件可以复用同一个
选择器，而不必每次点击都创建新进程。
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass


@dataclass
class _Request:
    """目录选择队列中的单个请求，包含结果容器和完成事件。"""
    done: threading.Event
    path: str | None = None


class DirectoryPicker:
    """通过后台 Tk 线程提供跨平台目录选择能力。"""
    def __init__(self) -> None:
        """内部辅助函数“__init__”：初始化服务对象及其依赖。
返回：None。"""
        self._requests: queue.Queue[_Request] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self._failed = False

    def _ensure_started(self) -> None:
        """内部辅助函数“_ensure_started”：确保目录选择器的后台 Tk 线程已经启动。
返回：None。"""
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker,
                name="signalforge-directory-picker",
                daemon=True,
            )
            self._thread.start()

    def _worker(self) -> None:
        """内部辅助函数“_worker”：在后台线程中处理目录选择请求。
返回：None。"""
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            self._failed = True
            self._fail_pending()
            return

        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            while True:
                request = self._requests.get()
                try:
                    request.path = filedialog.askdirectory(
                        parent=root,
                        title="选择 SignalForge 产物输出目录",
                        mustexist=False,
                    ) or None
                except Exception:
                    request.path = None
                finally:
                    request.done.set()
        except Exception:
            self._failed = True
            self._fail_pending()

    def _fail_pending(self) -> None:
        """内部辅助函数“_fail_pending”：将队列中等待的目录选择请求统一标记为失败。
返回：None。"""
        while True:
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return
            request.path = None
            request.done.set()

    def pick(self) -> str | None:
        """函数“pick”：请求用户选择一个目录，并返回所选路径。
返回：str | None。"""
        self._ensure_started()
        request = _Request(done=threading.Event())
        if self._failed:
            return None
        self._requests.put(request)
        # 请求排队期间 Tk 界面线程可能失败（例如服务器没有图形桌面）。
        # 此时必须立即结束请求，不能让 HTTP 调用无限等待。
        if self._failed:
            request.done.set()
        request.done.wait()
        return request.path


directory_picker = DirectoryPicker()
