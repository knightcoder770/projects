# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/region_selector.py
# Fullscreen Transparent Region Selector
#
# Problem with in-browser crop overlay:
#   - pywebview window can't overlay other apps
#   - JS mouse events are confined to the app window
#
# Solution:
#   - Open a fullscreen transparent tkinter window on top of ALL apps
#   - User drags to select region anywhere on screen
#   - Returns {x, y, width, height} to the caller
#   - Works on Windows + Linux (X11)
#
# This runs in a separate thread so it doesn't block the main app
# ─────────────────────────────────────────────────────────────────

import tkinter as tk
import threading
import platform
from typing import Optional, Callable


class RegionSelector:
    """
    Fullscreen transparent overlay for selecting a screen region.
    Opens on top of all windows including browsers, video players etc.

    Usage:
        selector = RegionSelector()
        region = selector.select()  # Blocks until user selects
        # region = {x, y, width, height} or None if cancelled
    """

    def __init__(self):
        self._result: Optional[dict] = None
        self._done = threading.Event()  # Signals when selection is complete

    def select(self) -> Optional[dict]:
        """
        Open the fullscreen selector and wait for user to draw a region.

        Returns:
            dict: {x, y, width, height} in screen pixels
            None: if user cancelled (pressed Escape)
        """
        self._result = None
        self._done.clear()

        # ── Run tkinter in main thread (required on Windows) ──
        # If called from a non-main thread, schedule on main thread
        self._run_selector()

        return self._result

    def _run_selector(self):
        """Create and run the transparent fullscreen tkinter window"""

        # ── Root window ──
        root = tk.Tk()
        root.title("SnapClip Region Selector")

        # ── Make fullscreen and transparent ──
        root.attributes('-fullscreen', True)
        root.attributes('-topmost', True)       # Always on top of all windows
        root.attributes('-alpha', 0.25)         # Semi-transparent (25% opacity)
        root.configure(bg='black')
        root.lift()
        root.focus_force()

        # ── On Windows: additional transparency fix ──
        if platform.system() == "Windows":
            root.attributes('-transparentcolor', '')

        # ── Canvas fills entire screen ──
        canvas = tk.Canvas(
            root,
            cursor="crosshair",
            bg='black',
            highlightthickness=0
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        # ── State for drag ──
        state = {
            'start_x': 0, 'start_y': 0,
            'rect_id': None,
            'label_id': None,
            'instruction_id': None
        }

        # ── Instruction text ──
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()

        state['instruction_id'] = canvas.create_text(
            screen_w // 2, 40,
            text="🖱  Click and drag to select recording region  |  ESC to cancel",
            fill='#06b6d4',
            font=('Segoe UI', 14, 'bold'),
            anchor='center'
        )

        # ── Draw selection rectangle with cyan border ──
        def on_mouse_down(e):
            state['start_x'] = e.x
            state['start_y'] = e.y

            # Remove old rectangle
            if state['rect_id']:
                canvas.delete(state['rect_id'])
            if state['label_id']:
                canvas.delete(state['label_id'])

            # Create new rectangle
            state['rect_id'] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline='#06b6d4',      # Cyan border
                width=2,
                fill='#06b6d4',
                stipple='gray12'        # Slight fill texture
            )

        def on_mouse_drag(e):
            if state['rect_id'] is None:
                return

            # Update rectangle to current mouse position
            canvas.coords(state['rect_id'],
                          state['start_x'], state['start_y'], e.x, e.y)

            # Update dimension label
            w = abs(e.x - state['start_x'])
            h = abs(e.y - state['start_y'])

            if state['label_id']:
                canvas.delete(state['label_id'])

            # Show dimensions near the selection
            label_x = min(e.x, state['start_x']) + w // 2
            label_y = min(e.y, state['start_y']) - 20

            state['label_id'] = canvas.create_text(
                label_x, max(label_y, 20),
                text=f"{w} × {h}",
                fill='#06b6d4',
                font=('Segoe UI', 11, 'bold'),
                anchor='center'
            )

        def on_mouse_up(e):
            # Calculate final region
            x1 = min(state['start_x'], e.x)
            y1 = min(state['start_y'], e.y)
            x2 = max(state['start_x'], e.x)
            y2 = max(state['start_y'], e.y)

            w = x2 - x1
            h = y2 - y1

            # Minimum size check
            if w < 20 or h < 20:
                return  # Too small — let user try again

            # Store result
            self._result = {
                'x': int(x1),
                'y': int(y1),
                'width': int(w),
                'height': int(h)
            }

            # Close the overlay
            root.destroy()

        def on_escape(e):
            """Cancel selection"""
            self._result = None
            root.destroy()

        # ── Bind events ──
        canvas.bind('<ButtonPress-1>',   on_mouse_down)
        canvas.bind('<B1-Motion>',        on_mouse_drag)
        canvas.bind('<ButtonRelease-1>', on_mouse_up)
        root.bind('<Escape>',             on_escape)

        # ── Run tkinter event loop (blocks until window closes) ──
        root.mainloop()
