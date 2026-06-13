# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/hotkeys.py
# Global Hotkey Manager
#
# Responsibilities:
#   - Listen for global keyboard shortcuts system-wide
#     (works even when SnapClip window is not focused)
#   - Trigger recording start / stop / pause / resume
#   - Support custom key bindings from UI settings
#   - Cross-platform: Windows (win32) + Linux (X11/Wayland via pynput)
#   - Non-blocking: runs in background thread
#   - Safe registration / unregistration without app restart
#
# DSA Used:
#   - Hash map (dict) for O(1) hotkey → callback lookup
#     Key: frozenset of keys currently held
#     Value: callback function to invoke
#   - Set for tracking currently pressed keys (for combo detection)
#     O(1) add/remove/lookup
#
# How combos work:
#   - We maintain a set of currently pressed keys
#   - On each key press, check if current set matches any registered combo
#   - frozenset used as dict key (sets are unhashable, frozensets are)
#
# Platform notes:
#   Windows: pynput uses Win32 API hooks (no extra setup needed)
#   Linux X11: pynput uses Xlib (works out of the box)
#   Linux Wayland: pynput has limited support — user may need to
#                  run app with: sudo or add user to 'input' group
# ─────────────────────────────────────────────────────────────────

import threading
import platform
import time
from typing import Callable, Dict, Optional, Set

# ── pynput for cross-platform global hotkeys ──
try:
    from pynput import keyboard as pynput_keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("[HotkeyManager] pynput not available — hotkeys disabled")
    print("  Install with: pip install pynput")


# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# Default hotkey bindings
# Format: "action" → "modifier+modifier+key"
DEFAULT_HOTKEYS = {
    "start_recording":  "ctrl+shift+r",     # Start capture
    "stop_recording":   "ctrl+shift+s",     # Stop capture
    "pause_recording":  "ctrl+shift+p",     # Pause/Resume toggle
    "screenshot":       "ctrl+shift+x",     # Take screenshot of region
    "open_editor":      "ctrl+shift+e",     # Bring editor window to front
    "cancel":           "ctrl+shift+c",     # Cancel current operation
}

# Modifier key names (normalized)
MODIFIER_KEYS = {"ctrl", "shift", "alt", "cmd", "super"}


# ─────────────────────────────────────────────────────────────────
# HOTKEY MANAGER CLASS
# ─────────────────────────────────────────────────────────────────

class HotkeyManager:
    """
    Global hotkey manager using pynput.

    Registers keyboard combos that fire callbacks even when
    the SnapClip window is not in focus.

    Uses a hash map of frozenset → callback for O(1) lookup
    on every key press event.
    """

    def __init__(self):
        # ── OS detection ──
        self._os = platform.system()    # "Windows" or "Linux"

        # ── Hotkey registry ──
        # Maps frozenset(keys) → (action_name, callback)
        # frozenset used because sets are unhashable (can't be dict keys)
        self._hotkey_map: Dict[frozenset, tuple] = {}

        # ── Action → hotkey string mapping (for UI display) ──
        self._action_bindings: Dict[str, str] = {}

        # ── Currently pressed keys (set for O(1) ops) ──
        self._pressed_keys: Set = set()

        # ── Listener thread ──
        self._listener: Optional[object] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._is_running = False

        # ── Cooldown tracking ──
        # Prevents same hotkey firing multiple times rapidly
        self._last_fired: Dict[str, float] = {}
        self._cooldown_seconds = 0.5    # 500ms between same hotkey fires

        # ── Callback registry for actions ──
        # Filled by register() calls from main.py
        self._callbacks: Dict[str, Callable] = {}

        print(f"[HotkeyManager] Initialized | OS: {self._os} | "
              f"pynput: {PYNPUT_AVAILABLE}")

        # Auto-start listener if pynput available
        if PYNPUT_AVAILABLE:
            self._start_listener()

    # ─────────────────────────────────────────────────────────────
    # REGISTER HOTKEYS
    # ─────────────────────────────────────────────────────────────

    def register(self, hotkey_map: dict) -> dict:
        """
        Register hotkey bindings from UI settings.

        Args:
            hotkey_map (dict): {action_name: key_combo_string}
                Example: {
                    "start_recording": "ctrl+shift+r",
                    "stop_recording":  "ctrl+shift+s"
                }

        Returns:
            dict: {success, registered: list, failed: list}
        """
        registered = []
        failed = []

        for action, combo_str in hotkey_map.items():
            try:
                # Parse combo string → frozenset of normalized key names
                key_set = self._parse_combo(combo_str)

                if not key_set:
                    failed.append({"action": action, "reason": "Invalid combo"})
                    continue

                # Remove any existing binding for this action
                self._unregister_action(action)

                # Register in hash map: frozenset → (action, callback)
                self._hotkey_map[key_set] = (action, self._dispatch_action)
                self._action_bindings[action] = combo_str

                registered.append({"action": action, "combo": combo_str})
                print(f"[HotkeyManager] Registered: {action} → {combo_str}")

            except Exception as e:
                failed.append({"action": action, "reason": str(e)})
                print(f"[HotkeyManager] Failed to register {action}: {e}")

        return {
            "success": len(registered) > 0,
            "registered": registered,
            "failed": failed
        }

    def register_callback(self, action: str, callback: Callable):
        """
        Register a Python callback for a named action.

        Args:
            action: Action name (e.g. "start_recording")
            callback: Function to call when hotkey fires
        """
        self._callbacks[action] = callback
        print(f"[HotkeyManager] Callback registered for: {action}")

    def register_defaults(self, callbacks: dict):
        """
        Register default hotkeys + their callbacks in one call.

        Args:
            callbacks: {action_name: callable}

        Example:
            hotkeys.register_defaults({
                "start_recording": api.start_recording,
                "stop_recording":  api.stop_recording,
            })
        """
        # Register default key bindings
        self.register(DEFAULT_HOTKEYS)

        # Register callbacks
        for action, cb in callbacks.items():
            self.register_callback(action, cb)

    # ─────────────────────────────────────────────────────────────
    # UNREGISTER
    # ─────────────────────────────────────────────────────────────

    def _unregister_action(self, action: str):
        """
        Remove an existing hotkey binding for an action.
        Used before re-registering with a new combo.

        Args:
            action: Action name to remove
        """
        # Find and remove the frozenset key for this action
        keys_to_remove = [
            key_set for key_set, (act, _) in self._hotkey_map.items()
            if act == action
        ]
        for key_set in keys_to_remove:
            del self._hotkey_map[key_set]
            print(f"[HotkeyManager] Unregistered: {action}")

    def unregister_all(self):
        """Clear all hotkey registrations"""
        self._hotkey_map.clear()
        self._action_bindings.clear()
        print("[HotkeyManager] All hotkeys cleared")

    # ─────────────────────────────────────────────────────────────
    # KEY PARSING
    # ─────────────────────────────────────────────────────────────

    def _parse_combo(self, combo_str: str) -> Optional[frozenset]:
        """
        Parse a combo string like "ctrl+shift+r" into a frozenset
        of normalized pynput key representations.

        This frozenset is used as the O(1) hash map key.

        Normalization:
        - "ctrl" → pynput_keyboard.Key.ctrl_l (left ctrl)
        - "shift" → pynput_keyboard.Key.shift
        - "alt" → pynput_keyboard.Key.alt_l
        - "r" → KeyCode(char='r')

        Args:
            combo_str: "ctrl+shift+r" style string

        Returns:
            frozenset of pynput key objects, or None if invalid
        """
        if not PYNPUT_AVAILABLE:
            return None

        parts = [p.strip().lower() for p in combo_str.split("+")]
        key_set = set()

        for part in parts:
            pynput_key = self._str_to_pynput_key(part)
            if pynput_key is None:
                print(f"[HotkeyManager] Unknown key: '{part}'")
                return None
            key_set.add(pynput_key)

        return frozenset(key_set) if key_set else None

    def _str_to_pynput_key(self, key_str: str):
        """
        Convert a key name string to a pynput key object.

        Modifier keys map to pynput.keyboard.Key enum values.
        Regular keys map to pynput.keyboard.KeyCode objects.

        Args:
            key_str: Lowercase key name ("ctrl", "shift", "r", "f1", etc.)

        Returns:
            pynput Key or KeyCode object, or None if unrecognized
        """
        if not PYNPUT_AVAILABLE:
            return None

        Key = pynput_keyboard.Key
        KeyCode = pynput_keyboard.KeyCode

        # ── Modifier key mapping ──
        modifier_map = {
            "ctrl":     Key.ctrl_l,
            "ctrl_l":   Key.ctrl_l,
            "ctrl_r":   Key.ctrl_r,
            "shift":    Key.shift,
            "shift_l":  Key.shift_l,
            "shift_r":  Key.shift_r,
            "alt":      Key.alt_l,
            "alt_l":    Key.alt_l,
            "alt_r":    Key.alt_r,
            "cmd":      Key.cmd,
            "super":    Key.cmd,        # Linux Super key = cmd in pynput
            "win":      Key.cmd,
        }

        # ── Special key mapping ──
        special_map = {
            "space":    Key.space,
            "enter":    Key.enter,
            "return":   Key.enter,
            "tab":      Key.tab,
            "esc":      Key.esc,
            "escape":   Key.esc,
            "backspace": Key.backspace,
            "delete":   Key.delete,
            "home":     Key.home,
            "end":      Key.end,
            "pageup":   Key.page_up,
            "pagedown": Key.page_down,
            "up":       Key.up,
            "down":     Key.down,
            "left":     Key.left,
            "right":    Key.right,
            **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)},  # F1–F12
        }

        if key_str in modifier_map:
            return modifier_map[key_str]
        elif key_str in special_map:
            return special_map[key_str]
        elif len(key_str) == 1:
            # Single character key
            return KeyCode.from_char(key_str)
        else:
            return None

    # ─────────────────────────────────────────────────────────────
    # PYNPUT LISTENER
    # ─────────────────────────────────────────────────────────────

    def _start_listener(self):
        """
        Start the pynput global keyboard listener in a daemon thread.
        The listener fires on_press and on_release for every key event
        system-wide, regardless of which window is focused.
        """
        if self._is_running:
            return

        self._is_running = True

        def run_listener():
            """Inner function that runs in background thread"""
            try:
                with pynput_keyboard.Listener(
                    on_press=self._on_key_press,
                    on_release=self._on_key_release
                ) as listener:
                    self._listener = listener
                    print("[HotkeyManager] Global listener started")
                    listener.join()     # Block until listener stops
            except Exception as e:
                print(f"[HotkeyManager] Listener error: {e}")
                if self._os == "Linux":
                    print("[HotkeyManager] On Wayland, try: DISPLAY=:0 python main.py")
                    print("[HotkeyManager] Or add user to 'input' group: sudo usermod -aG input $USER")
            finally:
                self._is_running = False
                print("[HotkeyManager] Listener stopped")

        self._listener_thread = threading.Thread(
            target=run_listener,
            daemon=True,
            name="SnapClip-HotkeyThread"
        )
        self._listener_thread.start()

    # ─────────────────────────────────────────────────────────────
    # KEY EVENT HANDLERS
    # ─────────────────────────────────────────────────────────────

    def _on_key_press(self, key):
        """
        Called by pynput on every key press (system-wide).

        1. Normalize the key to match our registration format
        2. Add to _pressed_keys set
        3. Check if current pressed set matches any registered combo
        4. If match found: dispatch the action

        Args:
            key: pynput Key or KeyCode object
        """
        try:
            # Normalize key for consistent comparison
            normalized = self._normalize_key(key)
            if normalized is None:
                return

            # ── Add to currently pressed set (O(1)) ──
            self._pressed_keys.add(normalized)

            # ── Check for combo match (O(1) hash lookup) ──
            current_combo = frozenset(self._pressed_keys)
            if current_combo in self._hotkey_map:
                action, dispatch_fn = self._hotkey_map[current_combo]
                dispatch_fn(action)

        except Exception as e:
            # Silently ignore key processing errors to keep listener alive
            pass

    def _on_key_release(self, key):
        """
        Called by pynput on every key release.
        Removes key from _pressed_keys set.

        Args:
            key: pynput Key or KeyCode object
        """
        try:
            normalized = self._normalize_key(key)
            if normalized is not None:
                # Discard (no error if key not in set)
                self._pressed_keys.discard(normalized)
        except Exception:
            pass

    def _normalize_key(self, key):
        """
        Normalize a pynput key object to match our registration format.

        Problem: pynput sends ctrl_l OR ctrl_r but we register ctrl_l.
        We normalize right-side modifiers to left-side for matching.

        Args:
            key: pynput Key or KeyCode

        Returns:
            Normalized pynput key object
        """
        if not PYNPUT_AVAILABLE:
            return None

        Key = pynput_keyboard.Key

        # ── Normalize right-side modifiers to left-side ──
        # This lets "ctrl+r" work whether left or right ctrl is pressed
        normalization_map = {
            Key.ctrl_r:  Key.ctrl_l,
            Key.shift_r: Key.shift,
            Key.alt_r:   Key.alt_l,
        }

        return normalization_map.get(key, key)

    # ─────────────────────────────────────────────────────────────
    # ACTION DISPATCH
    # ─────────────────────────────────────────────────────────────

    def _dispatch_action(self, action: str):
        """
        Dispatch a hotkey action to its registered callback.

        Includes cooldown check to prevent rapid re-firing.
        Runs callback in a new thread to avoid blocking the listener.

        Args:
            action: Action name (e.g. "start_recording")
        """
        # ── Cooldown check ──
        now = time.time()
        last = self._last_fired.get(action, 0)
        if now - last < self._cooldown_seconds:
            return  # Too soon — ignore

        self._last_fired[action] = now

        # ── Get callback ──
        callback = self._callbacks.get(action)
        if callback is None:
            print(f"[HotkeyManager] No callback for action: {action}")
            return

        # ── Run in thread so listener isn't blocked ──
        def run_callback():
            try:
                print(f"[HotkeyManager] Firing: {action}")
                callback()
            except Exception as e:
                print(f"[HotkeyManager] Callback error for {action}: {e}")

        t = threading.Thread(target=run_callback, daemon=True,
                             name=f"SnapClip-HotkeyAction-{action}")
        t.start()

    # ─────────────────────────────────────────────────────────────
    # PUBLIC UTILITIES
    # ─────────────────────────────────────────────────────────────

    def get_bindings(self) -> dict:
        """
        Return current hotkey bindings for display in UI settings.

        Returns:
            dict: {action: combo_string}
            Example: {"start_recording": "ctrl+shift+r", ...}
        """
        return dict(self._action_bindings)

    def get_defaults(self) -> dict:
        """Return the default hotkey bindings dict"""
        return dict(DEFAULT_HOTKEYS)

    def reset_to_defaults(self) -> dict:
        """Reset all hotkeys to their default bindings"""
        self.unregister_all()
        return self.register(DEFAULT_HOTKEYS)

    def is_running(self) -> bool:
        """Return True if the global listener is active"""
        return self._is_running

    def stop(self):
        """
        Stop the global hotkey listener.
        Call this when the app is closing to clean up resources.
        """
        self._is_running = False

        if self._listener:
            try:
                self._listener.stop()
                print("[HotkeyManager] Listener stopped")
            except Exception as e:
                print(f"[HotkeyManager] Stop error: {e}")

        # Clear pressed keys on stop
        self._pressed_keys.clear()

    def set_cooldown(self, seconds: float):
        """
        Set the cooldown period between same-hotkey fires.

        Args:
            seconds: Minimum seconds between same hotkey triggers
        """
        self._cooldown_seconds = max(0.1, seconds)
        print(f"[HotkeyManager] Cooldown set to {self._cooldown_seconds}s")

    def simulate_action(self, action: str):
        """
        Manually trigger an action as if its hotkey was pressed.
        Useful for testing callbacks without pressing actual keys.

        Args:
            action: Action name to trigger
        """
        print(f"[HotkeyManager] Simulating action: {action}")
        self._dispatch_action(action)
