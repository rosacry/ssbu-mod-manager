"""Debug logging system for developer mode."""
from collections import deque
from datetime import datetime


class AppLogger:
    """Simple in-memory logger. Singleton."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._logs = deque(maxlen=1000)
            cls._instance._enabled = False
            cls._instance._listeners = []
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
        """Add a log entry."""
        if not self._enabled:
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{timestamp}] [{level}] [{source}] {message}"
        self._logs.append(entry)
        for listener in self._listeners:
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

    def get_logs(self) -> list[str]:
        return list(self._logs)

    def clear(self):
        self._logs.clear()

    def add_listener(self, callback):
        self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)


# Global singleton
logger = AppLogger()
