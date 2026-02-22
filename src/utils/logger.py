"""Debug logging system for developer mode."""
import threading
import traceback
from collections import deque
from datetime import datetime


class AppLogger:
    """Simple in-memory logger. Singleton.

    Behaviour:
    - ERROR and WARN are *always* stored, regardless of enabled state.
    - INFO is always stored (important for seeing app activity).
    - DEBUG is only stored when developer mode is enabled.
    - Listeners are always notified for stored entries.
    - Thread-safe: all access to logs and listeners is locked.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._logs = deque(maxlen=2000)
            cls._instance._enabled = False
            cls._instance._listeners = []
            cls._instance._lock = threading.Lock()
        return cls._instance

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value
        if value:
            self.info("Logger", "Developer mode enabled")

    def log(self, source: str, message: str, level: str = "INFO"):
        """Add a log entry. Only DEBUG requires enabled state. Thread-safe."""
        if level == "DEBUG" and not self._enabled:
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{timestamp}] [{level}] [{source}] {message}"
        with self._lock:
            self._logs.append(entry)
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(entry)
            except Exception:
                pass

    def debug(self, source: str, message: str):
        self.log(source, message, "DEBUG")

    def info(self, source: str, message: str):
        self.log(source, message, "INFO")

    def warn(self, source: str, message: str):
        self.log(source, message, "WARN")

    def error(self, source: str, message: str):
        self.log(source, message, "ERROR")

    def exception(self, source: str, message: str):
        """Log an error with the current exception traceback."""
        tb = traceback.format_exc()
        self.log(source, f"{message}\n{tb}", "ERROR")

    @property
    def entries(self):
        """Thread-safe access to log entries. Returns a snapshot list."""
        with self._lock:
            return list(self._logs)

    def get_logs(self) -> list[str]:
        with self._lock:
            return list(self._logs)

    def clear(self):
        with self._lock:
            self._logs.clear()

    def add_listener(self, callback):
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)


# Global singleton
logger = AppLogger()
