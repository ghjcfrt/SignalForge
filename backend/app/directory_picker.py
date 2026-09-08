"""Native directory picker for the local FastAPI process.

The picker is intentionally isolated in a daemon thread: Tk requires a
desktop-capable thread and its modal dialog must not block FastAPI's event
loop. Requests are serialized so both output-directory controls can share the
same native picker without starting a new process for every click.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass


@dataclass
class _Request:
    done: threading.Event
    path: str | None = None


class DirectoryPicker:
    # 中文说明：函数「__init__」负责完成该步骤的输入处理、核心逻辑和结果返回。
    def __init__(self) -> None:
        self._requests: queue.Queue[_Request] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self._failed = False

    # 中文说明：函数「_ensure_started」负责完成该步骤的输入处理、核心逻辑和结果返回。
    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker,
                name="signalforge-directory-picker",
                daemon=True,
            )
            self._thread.start()

    # 中文说明：函数「_worker」负责完成该步骤的输入处理、核心逻辑和结果返回。
    def _worker(self) -> None:
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

    # 中文说明：函数「_fail_pending」负责完成该步骤的输入处理、核心逻辑和结果返回。
    def _fail_pending(self) -> None:
        while True:
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return
            request.path = None
            request.done.set()

    # 中文说明：函数「pick」负责完成该步骤的输入处理、核心逻辑和结果返回。
    def pick(self) -> str | None:
        self._ensure_started()
        request = _Request(done=threading.Event())
        if self._failed:
            return None
        self._requests.put(request)
        # The Tk thread can fail while this request is being enqueued (for
        # example on a headless server). Do not leave the HTTP request hanging.
        if self._failed:
            request.done.set()
        request.done.wait()
        return request.path


directory_picker = DirectoryPicker()
