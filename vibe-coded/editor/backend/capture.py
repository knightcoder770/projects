# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/capture.py
# Screen Capture Engine
#
# KEY FIX: Frames are written to a temp AVI file on DISK instead of
# kept in RAM. This allows unlimited recording length without
# freezing the system due to RAM exhaustion.
#
# Old approach: deque(maxlen=18000) in RAM → ~3GB for 5min at 60fps
# New approach: OpenCV VideoWriter to temp .avi → unlimited length
# ─────────────────────────────────────────────────────────────────

import threading
import time
import tempfile
import os
import platform

import mss
import numpy as np
import cv2


# FPS detection: sample this many frames at start
FPS_DETECTION_FRAMES = 60


class CaptureEngine:

    def __init__(self):
        self._os            = platform.system()
        self._is_capturing  = False
        self._is_paused     = False
        self._pause_event   = threading.Event()
        self._pause_event.set()
        self._capture_thread = None
        self._lock          = threading.Lock()

        # Video writer (disk-based)
        self._writer        = None
        self._temp_avi      = None   # Path to temp AVI file
        self._region        = {}
        self._target_fps    = 0

        # Metadata set after stop()
        self.detected_fps   = 30.0
        self.total_duration = 0.0
        self.frame_count    = 0

        # GPU (CUDA) acceleration
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                self._use_gpu = True
                print("[CaptureEngine] CUDA available")
            else:
                self._use_gpu = False
        except Exception:
            self._use_gpu = False

        print(f"[CaptureEngine] Initialized | GPU: {self._use_gpu} | OS: {self._os}")

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def start(self, region: dict, fps: int = 0):
        """
        Start screen capture.
        region: {left, top, width, height}  (pixel coords)
        fps:    target fps (0 = auto/max)
        """
        if self._is_capturing:
            return

        self._region       = {
            "left":   region.get("x", region.get("left", 0)),
            "top":    region.get("y", region.get("top",  0)),
            "width":  region.get("width",  1280),
            "height": region.get("height",  720),
        }
        self._target_fps   = fps
        self._is_capturing = True
        self._is_paused    = False
        self._pause_event.set()
        self.frame_count   = 0

        # Create temp AVI file on disk
        tmp = tempfile.NamedTemporaryFile(
            suffix=".avi", delete=False, prefix="snapclip_frames_"
        )
        self._temp_avi = tmp.name
        tmp.close()

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="SnapClip-Capture"
        )
        self._capture_thread.start()
        print(f"[CaptureEngine] Capture started | Region: {self._region} | FPS: {fps or 'auto'}")

    def stop(self):
        """Stop capture. Returns (temp_avi_path, fps, duration)."""
        self._is_capturing = False
        self._pause_event.set()   # Unblock if paused

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=5.0)

        # Release writer
        with self._lock:
            if self._writer:
                self._writer.release()
                self._writer = None

        print(f"[CaptureEngine] Stopped | Frames: {self.frame_count} | "
              f"FPS: {self.detected_fps:.2f} | Duration: {self.total_duration:.2f}s")

        return self._temp_avi, self.detected_fps, self.total_duration

    def pause(self):
        self._is_paused = True
        self._pause_event.clear()

    def resume(self):
        self._is_paused = False
        self._pause_event.set()

    def is_paused(self) -> bool:
        return self._is_paused

    def get_temp_avi(self) -> str:
        return self._temp_avi

    # ─────────────────────────────────────────────────────────────
    # CAPTURE LOOP
    # ─────────────────────────────────────────────────────────────

    def _capture_loop(self):
        """
        Capture frames from screen and write directly to AVI on disk.
        No RAM accumulation — can record for hours.
        """
        w = self._region["width"]
        h = self._region["height"]

        # Ensure even dimensions for codec compatibility
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1

        # ── FPS detection phase ──
        # Capture FPS_DETECTION_FRAMES to measure real capture speed
        detect_times = []
        detect_frames = []

        with mss.mss() as sct:
            # Detection phase
            for _ in range(FPS_DETECTION_FRAMES):
                if not self._is_capturing:
                    break
                t0    = time.perf_counter()
                shot  = sct.grab(self._region)
                frame = np.array(shot)[:, :, :3]   # Drop alpha
                frame = cv2.resize(frame, (w, h))
                detect_frames.append(frame)
                detect_times.append(t0)

            if len(detect_times) >= 2:
                elapsed = detect_times[-1] - detect_times[0]
                self.detected_fps = (len(detect_times) - 1) / elapsed if elapsed > 0 else 30.0
            else:
                self.detected_fps = 30.0

            fps = round(self.detected_fps, 3)
            print(f"[CaptureEngine] Auto-detected FPS: {fps}")

            # ── Open VideoWriter on disk ──
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            writer = cv2.VideoWriter(self._temp_avi, fourcc, fps, (w, h))

            if not writer.isOpened():
                # Fallback codec
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                writer = cv2.VideoWriter(self._temp_avi, fourcc, fps, (w, h))

            with self._lock:
                self._writer = writer

            # Write detection frames first
            for frame in detect_frames:
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, (w, h))
                writer.write(frame)
                self.frame_count += 1

            detect_frames.clear()

            # ── Main capture loop ──
            rec_start = time.perf_counter()
            interval  = 1.0 / fps if fps > 0 else 0

            while self._is_capturing:
                # Pause support
                self._pause_event.wait()

                t0   = time.perf_counter()
                shot = sct.grab(self._region)

                frame = np.array(shot)[:, :, :3]
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, (w, h))

                with self._lock:
                    if self._writer:
                        self._writer.write(frame)
                self.frame_count += 1

                # Sleep to maintain target FPS (avoid burning CPU)
                elapsed = time.perf_counter() - t0
                sleep   = interval - elapsed
                if sleep > 0.001:
                    time.sleep(sleep)

            # Calculate total duration
            self.total_duration = time.perf_counter() - rec_start
            print(f"[CaptureEngine] Capture loop exited | "
                  f"Frames written to disk: {self.frame_count}")

    # ─────────────────────────────────────────────────────────────
    # LEGACY: get_frames() — kept for backward compatibility
    # Returns empty list (frames are on disk now)
    # ─────────────────────────────────────────────────────────────

    def get_frames(self):
        """Legacy method — frames are now on disk, not in RAM."""
        return []
