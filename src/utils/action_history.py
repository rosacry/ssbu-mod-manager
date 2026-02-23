"""Undo/Redo action history system."""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Action:
    description: str
    do: Callable
    undo: Callable
    page: str = ""


class ActionHistory:
    """Tracks user actions for undo/redo support."""

    def __init__(self, max_history: int = 50):
        self._undo_stack: list[Action] = []
        self._redo_stack: list[Action] = []
        self._max = max_history
        self._listeners: list[Callable] = []

    def execute(self, action: Action):
        """Execute an action and push it onto the undo stack."""
        action.do()
        # Only clear redo and push to undo AFTER do() succeeds; if
        # do() raises, the stacks remain untouched.
        self._undo_stack.append(action)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._max:
            self._undo_stack.pop(0)
        self._notify()

    def undo(self) -> Optional[str]:
        """Undo the last action. Returns description or None."""
        if not self._undo_stack:
            return None
        action = self._undo_stack.pop()
        action.undo()
        self._redo_stack.append(action)
        self._notify()
        return action.description

    def redo(self) -> Optional[str]:
        """Redo the last undone action. Returns description or None."""
        if not self._redo_stack:
            return None
        action = self._redo_stack.pop()
        action.do()
        self._undo_stack.append(action)
        self._notify()
        return action.description

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def get_undo_description(self) -> str:
        if self._undo_stack:
            return self._undo_stack[-1].description
        return ""

    def get_redo_description(self) -> str:
        if self._redo_stack:
            return self._redo_stack[-1].description
        return ""

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def _notify(self):
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                pass

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify()


# Singleton
action_history = ActionHistory()
