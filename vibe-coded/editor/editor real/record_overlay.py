# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/record_overlay.py
# Floating Record/Stop/Pause bar during recording
#
# Root cause of Tcl_AsyncDelete:
#   tkinter.StringVar / IntVar / BooleanVar are linked to the Tcl
#   interpreter. When they are garbage-collected from a thread that
#   is NOT the thread that created them, Tcl crashes with
#   "Tcl_AsyncDelete: async handler deleted by the wrong thread".
#
# Fix:
#   - Zero tkinter Variable objects (no StringVar, no IntVar)
#   - Update labels via label.config(text=...) called with after()
#   - after() schedules work on the tkinter thread safely
#   - Callbacks fire in plain daemon threads, never touching tkinter
# ─────────────────────────────────────────────────────────────────

import threading
import time
from typing import Callable, Optional


class RecordOverlay:
    """
    Floating Stop/Pause control bar.
    No StringVar/IntVar — pure config() + after() updates only.
    """

    def __init__(self, on_stop: Callable, on_pause: Callable):
        self._on_stop   = on_stop
        self._on_pause  = on_pause
        self._is_paused = False
        self._seconds   = 0
        self._running   = False
        self._root      = None

        # Labels updated via after() — kept as instance vars
        self._timer_lbl = None
        self._pause_lbl = None
        self._dot_lbl   = None

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def show(self):
        """Launch overlay in a dedicated daemon thread"""
        self._running = True
        t = threading.Thread(
            target=self._run,
            daemon=True,
            name="SnapClip-Overlay"
        )
        t.start()

    def hide(self):
        """Signal overlay to close — safe from any thread"""
        self._running = False
        if self._root:
            try:
                # Schedule destroy on tkinter thread
                self._root.after(0, self._destroy_root)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────
    # OVERLAY THREAD
    # ─────────────────────────────────────────────────────────────

    def _run(self):
        """All tkinter code lives and dies in this thread"""
        import tkinter as tk

        BG    = '#111827'
        RED   = '#ef4444'
        AMBER = '#f59e0b'
        WHITE = '#ffffff'
        GRAY  = '#374151'

        try:
            root = tk.Tk()
            self._root = root

            root.title("SnapClip")
            root.overrideredirect(True)
            root.attributes('-topmost', True)
            root.attributes('-alpha', 0.94)
            root.configure(bg=GRAY)     # GRAY = border color

            # ── Size + position ──
            W, H = 300, 54
            sw   = root.winfo_screenwidth()
            sh   = root.winfo_screenheight()
            root.geometry(f"{W}x{H}+{(sw-W)//2}+{sh-115}")

            # ── Inner frame ──
            inner = tk.Frame(root, bg=BG, padx=0, pady=0)
            inner.place(x=1, y=1, width=W-2, height=H-2)

            # ── Dot ──
            dot = tk.Label(inner, text='●', fg=RED, bg=BG,
                           font=('Segoe UI', 13, 'bold'))
            dot.place(x=8, y=14)
            self._dot_lbl = dot

            # ── Timer ──
            timer = tk.Label(inner, text='00:00:00',
                             fg=WHITE, bg=BG,
                             font=('Courier New', 12, 'bold'))
            timer.place(x=28, y=15)
            self._timer_lbl = timer

            # ── Separator ──
            sep = tk.Frame(inner, bg=GRAY, width=1, height=36)
            sep.place(x=130, y=9)

            # ── Pause button ──
            pause_btn = tk.Button(
                inner,
                text=' ⏸ Pause ',
                fg=AMBER, bg=BG,
                activeforeground=WHITE,
                activebackground=GRAY,
                font=('Segoe UI', 10, 'bold'),
                bd=0, relief='flat',
                cursor='hand2',
                command=self._click_pause
            )
            pause_btn.place(x=138, y=13)
            self._pause_lbl = pause_btn

            # ── Stop button ──
            stop_btn = tk.Button(
                inner,
                text=' ■ Stop ',
                fg=WHITE, bg=RED,
                activeforeground=WHITE,
                activebackground='#b91c1c',
                font=('Segoe UI', 10, 'bold'),
                bd=0, relief='flat',
                cursor='hand2',
                command=self._click_stop
            )
            stop_btn.place(x=220, y=12)

            # ── Drag support ──
            self._dx = self._dy = 0
            for w in [root, inner, dot, timer]:
                w.bind('<ButtonPress-1>',  self._drag_press)
                w.bind('<B1-Motion>',      self._drag_move)

            # ── Start recurring updates via after() ──
            # after() is thread-safe — always runs on tkinter thread
            root.after(1000, self._tick)
            root.after(500,  self._blink)

            root.mainloop()

        except Exception as e:
            print(f"[RecordOverlay] Error: {e}")
        finally:
            self._root      = None
            self._timer_lbl = None
            self._pause_lbl = None
            self._dot_lbl   = None
            print("[RecordOverlay] Closed cleanly")

    # ─────────────────────────────────────────────────────────────
    # AFTER() CALLBACKS — run on tkinter thread, safe
    # ─────────────────────────────────────────────────────────────

    def _tick(self):
        """Update timer every second — scheduled via after()"""
        if not self._running or not self._root:
            return
        if not self._is_paused:
            self._seconds += 1
        h = self._seconds // 3600
        m = (self._seconds % 3600) // 60
        s = self._seconds % 60
        try:
            self._timer_lbl.config(text=f'{h:02d}:{m:02d}:{s:02d}')
            self._root.after(1000, self._tick)
        except Exception:
            pass

    def _blink(self):
        """Blink the recording dot — scheduled via after()"""
        if not self._running or not self._root:
            return
        try:
            RED = '#ef4444'
            BG  = '#111827'
            cur = self._dot_lbl.cget('fg')
            self._dot_lbl.config(fg=BG if cur == RED else RED)
            self._root.after(500, self._blink)
        except Exception:
            pass

    def _destroy_root(self):
        """Destroy tkinter root — must run on tkinter thread via after()"""
        try:
            if self._root:
                self._root.destroy()
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    # BUTTON CLICKS — update UI then fire callback in new thread
    # ─────────────────────────────────────────────────────────────

    def _click_stop(self):
        """Stop button clicked — destroy overlay, fire callback"""
        self._running = False
        # Destroy cleanly from tkinter thread
        try:
            self._root.destroy()
        except Exception:
            pass
        # Fire callback in separate thread — never block tkinter
        threading.Thread(
            target=self._on_stop,
            daemon=True,
            name="SnapClip-StopCallback"
        ).start()

    def _click_pause(self):
        """Pause/Resume button clicked"""
        self._is_paused = not self._is_paused
        try:
            if self._is_paused:
                self._pause_lbl.config(text=' ▶ Resume', fg='#10b981')
            else:
                self._pause_lbl.config(text=' ⏸ Pause ', fg='#f59e0b')
        except Exception:
            pass
        # Fire callback in separate thread
        threading.Thread(
            target=self._on_pause,
            daemon=True,
            name="SnapClip-PauseCallback"
        ).start()

    # ─────────────────────────────────────────────────────────────
    # DRAG
    # ─────────────────────────────────────────────────────────────

    def _drag_press(self, e):
        if self._root:
            self._dx = e.x_root - self._root.winfo_x()
            self._dy = e.y_root - self._root.winfo_y()

    def _drag_move(self, e):
        if self._root:
            try:
                self._root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")
            except Exception:
                pass
