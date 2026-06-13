# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/effects.py
# Effects & Filters Engine
#
# Responsibilities:
#   - Apply visual filters: brightness, contrast, saturation,
#     blur, sharpen, grayscale, sepia, vignette, flip, rotate
#   - Add text overlays with custom font, color, size, position
#   - Add image watermarks at any corner or custom position
#   - All effects are non-destructive (write to new file)
#   - GPU accelerated via OpenCV CUDA where possible
#   - FFmpeg used for effects that are faster via filter graphs
#
# DSA Used:
#   - Frame pipeline: read → process (GPU/CPU) → write
#     Uses OpenCV VideoCapture + VideoWriter as streaming pipeline
#     Avoids loading all frames into RAM at once (memory efficient)
#   - Filter registry: dict mapping filter names → handler functions
#     O(1) filter lookup by name
#
# GPU Strategy:
#   - Upload frame to GPU (GpuMat) → apply filter → download
#   - Supported GPU ops: resize, blur, color conversion
#   - Non-GPU ops (text, watermark) done on CPU after GPU processing
#   - Falls back to CPU if CUDA unavailable
# ─────────────────────────────────────────────────────────────────

import cv2
import numpy as np
import subprocess
import shutil
import os
import time
import platform
from typing import Optional, Tuple

# ── Pillow for advanced text rendering ──
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("[EffectsEngine] Pillow not available — text overlays use OpenCV fallback")


# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# FFmpeg path
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# Default font for text overlays (falls back to OpenCV font if not found)
DEFAULT_FONT_WINDOWS = "C:/Windows/Fonts/Arial.ttf"
DEFAULT_FONT_LINUX   = "/usr/share/fonts/TTF/DejaVuSans.ttf"

# Watermark position presets (anchor point label → alignment logic)
WATERMARK_POSITIONS = ["topleft", "topright", "bottomleft", "bottomright", "center"]

# Sepia transform matrix (applied to BGR channels)
# Converts image to warm brownish tone
SEPIA_KERNEL = np.array([
    [0.272, 0.534, 0.131],  # Blue channel output
    [0.349, 0.686, 0.168],  # Green channel output
    [0.393, 0.769, 0.189],  # Red channel output
], dtype=np.float32)


# ─────────────────────────────────────────────────────────────────
# EFFECTS ENGINE CLASS
# ─────────────────────────────────────────────────────────────────

class EffectsEngine:
    """
    GPU-accelerated video effects and filters engine.

    All methods process video frame-by-frame using a streaming
    pipeline to avoid loading the entire video into RAM.

    Filter registry maps filter names to handler functions for
    O(1) dispatch — easy to add new filters by registering them.
    """

    def __init__(self):
        # ── GPU check ──
        self._use_gpu = self._check_gpu()

        # ── Filter registry (dict for O(1) lookup) ──
        # Maps filter name → (method, uses_ffmpeg)
        # uses_ffmpeg=True: handled by FFmpeg filter graph (faster for these)
        # uses_ffmpeg=False: handled by OpenCV frame pipeline
        self._filter_registry = {
            # OpenCV / NumPy filters (frame-level processing)
            "grayscale":    (self._filter_grayscale,    False),
            "sepia":        (self._filter_sepia,        False),
            "blur":         (self._filter_blur,         False),
            "sharpen":      (self._filter_sharpen,      False),
            "flip_h":       (self._filter_flip_h,       False),
            "flip_v":       (self._filter_flip_v,       False),
            "film_grain":   (self._filter_film_grain,   False),
            "mirror":       (self._filter_mirror,       False),

            # FFmpeg filter graph (better for these)
            "brightness":   ("eq=brightness={v}",                True),
            "contrast":     ("eq=contrast={v}",                  True),
            "saturation":   ("eq=saturation={v}",                True),
            "vignette":     ("vignette=angle=PI/4",              True),
            "rotate":       ("rotate={v}*PI/180",                True),
            "glow":         ("split[a][b];[b]gblur=sigma=12[g];[a][g]blend=all_mode=screen:all_opacity=0.5", True),
            "pixelate":     ("scale=iw/8:ih/8,scale=iw*8:ih*8:flags=neighbor", True),
            "edge_detect":  ("edgedetect=low=0.1:high=0.4",      True),
        }

        # ── LUT color grade definitions ──
        # Each LUT is an FFmpeg eq/curves filter string
        # No external files needed — pure FFmpeg math
        self._lut_registry = {
            "cinematic":   "eq=contrast=1.2:brightness=-0.05:saturation=0.85,"
                           "curves=r='0/0 0.3/0.25 1/0.9':g='0/0 0.5/0.48 1/0.95':b='0/0.05 0.5/0.5 1/1'",
            "warm":        "eq=contrast=1.1:brightness=0.05:saturation=1.3,"
                           "curves=r='0/0 0.5/0.6 1/1':g='0/0 0.5/0.5 1/0.95':b='0/0 0.5/0.4 1/0.85'",
            "cool":        "eq=contrast=1.05:brightness=0:saturation=0.9,"
                           "curves=r='0/0 0.5/0.45 1/0.9':g='0/0 0.5/0.5 1/0.95':b='0/0.05 0.5/0.55 1/1'",
            "vintage":     "eq=contrast=0.9:brightness=0.05:saturation=0.7,"
                           "curves=r='0/0.1 0.5/0.6 1/0.95':g='0/0.05 0.5/0.5 1/0.85':b='0/0 0.5/0.4 1/0.75',"
                           "vignette=angle=PI/5",
            "noir":        "hue=s=0,"
                           "eq=contrast=1.4:brightness=-0.1,"
                           "curves=all='0/0 0.3/0.2 0.7/0.8 1/1'",
            "matrix":      "hue=s=0,"
                           "curves=r='0/0 1/0':g='0/0 0.5/0.6 1/1':b='0/0 1/0'",
            "sunset":      "eq=contrast=1.15:brightness=0.05:saturation=1.4,"
                           "curves=r='0/0 0.5/0.65 1/1':g='0/0 0.5/0.48 1/0.9':b='0/0 0.5/0.35 1/0.75'",
            "teal_orange": "eq=contrast=1.1:saturation=1.2,"
                           "curves=r='0/0 0.3/0.35 0.7/0.75 1/1':g='0/0 0.5/0.48 1/0.92':b='0/0.05 0.4/0.55 0.7/0.5 1/0.8'",
        }

        # ── Default font path ──
        if platform.system() == "Windows":
            self._font_path = DEFAULT_FONT_WINDOWS
        else:
            self._font_path = DEFAULT_FONT_LINUX

        # Fallback: scan common font locations
        if not os.path.exists(self._font_path):
            self._font_path = self._find_font()

        print(f"[EffectsEngine] Initialized | GPU: {self._use_gpu} | "
              f"Pillow: {PILLOW_AVAILABLE} | Font: {self._font_path}")

    # ─────────────────────────────────────────────────────────────
    # GPU CHECK
    # ─────────────────────────────────────────────────────────────

    def _check_gpu(self) -> bool:
        """Check OpenCV CUDA availability for RTX 3050"""
        try:
            return cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────
    # MAIN APPLY FILTER ENTRY POINT
    # ─────────────────────────────────────────────────────────────

    def apply(self, clip_path: str, filter_name: str,
              intensity: float = 1.0,
              output_path: Optional[str] = None) -> dict:
        """
        Apply a named filter to a video clip.

        Dispatches to FFmpeg filter graph or OpenCV pipeline
        based on the filter registry.

        Args:
            clip_path: Source video file
            filter_name: Filter name (see _filter_registry keys)
            intensity: Filter intensity/value (meaning varies by filter)
                - brightness: -1.0 to 1.0 (0 = original)
                - contrast: 0.0 to 3.0 (1.0 = original)
                - saturation: 0.0 to 3.0 (1.0 = original)
                - blur: 1–20 (kernel size)
                - sharpen: 0.5–3.0
                - rotate: degrees (0–360)
                - flip_h/flip_v/grayscale/sepia/vignette: intensity ignored
            output_path: Optional output path

        Returns:
            dict: {success, output_path, filter_applied}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source file not found"}

        if filter_name not in self._filter_registry:
            available = list(self._filter_registry.keys())
            return {"success": False,
                    "message": f"Unknown filter: {filter_name}. Available: {available}"}

        if not output_path:
            output_path = self._make_output_path(clip_path, f"fx_{filter_name}")

        handler, uses_ffmpeg = self._filter_registry[filter_name]

        try:
            if uses_ffmpeg:
                # ── FFmpeg filter graph path ──
                # Replace {v} placeholder with intensity value
                vf = handler.replace("{v}", str(intensity))
                result = self._apply_ffmpeg_filter(clip_path, output_path, vf)
            else:
                # ── OpenCV frame pipeline path ──
                result = self._apply_opencv_filter(
                    clip_path, output_path, handler, intensity
                )

            if result:
                print(f"[EffectsEngine] Filter '{filter_name}' applied → {output_path}")
                return {
                    "success": True,
                    "output_path": output_path,
                    "filter_applied": filter_name,
                    "intensity": intensity
                }
            else:
                return {"success": False, "message": f"Filter '{filter_name}' failed"}

        except Exception as e:
            print(f"[EffectsEngine] Filter error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # FFMPEG FILTER GRAPH PIPELINE
    # ─────────────────────────────────────────────────────────────

    def _apply_ffmpeg_filter(self, clip_path: str, output_path: str,
                              vf_filter: str) -> bool:
        """
        Apply a filter using FFmpeg -vf filter graph.
        Faster than OpenCV for simple EQ adjustments.

        Args:
            clip_path: Input video
            output_path: Output video
            vf_filter: FFmpeg -vf filter string

        Returns:
            bool: True if successful
        """
        cmd = [
            FFMPEG, "-y",
            "-i", clip_path,
            "-vf", vf_filter,
            "-c:a", "copy",         # Keep audio unchanged
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            print(f"[EffectsEngine] FFmpeg filter error: {result.stderr[:500]}")
            return False
        return True

    # ─────────────────────────────────────────────────────────────
    # OPENCV FRAME PIPELINE
    # ─────────────────────────────────────────────────────────────

    def _apply_opencv_filter(self, clip_path: str, output_path: str,
                              filter_fn, intensity: float) -> bool:
        """
        Apply a filter frame-by-frame using OpenCV.

        Streaming pipeline (memory efficient):
        VideoCapture → read frame → GPU upload (optional)
        → apply filter → GPU download → VideoWriter

        Args:
            clip_path: Input video
            output_path: Output video
            filter_fn: Function(frame, intensity) → processed_frame
            intensity: Filter intensity value

        Returns:
            bool: True if successful
        """
        cap = cv2.VideoCapture(clip_path)
        if not cap.isOpened():
            print(f"[EffectsEngine] Cannot open: {clip_path}")
            return False

        # ── Get video properties ──
        fps    = cap.get(cv2.CAP_PROP_FPS)
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # ── Write to temp AVI first (XVID works on all platforms) ──
        # mp4v on Windows produces black output — AVI+XVID is reliable
        import tempfile
        temp_avi = tempfile.NamedTemporaryFile(suffix='.avi', delete=False).name

        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        writer = cv2.VideoWriter(temp_avi, fourcc, fps, (width, height))

        if not writer.isOpened():
            # Fallback to MJPG
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            writer = cv2.VideoWriter(temp_avi, fourcc, fps, (width, height))
            if not writer.isOpened():
                cap.release()
                print("[EffectsEngine] VideoWriter failed to open with both XVID and MJPG")
                return False

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # ── GPU acceleration ──
            if self._use_gpu:
                try:
                    gpu_frame = cv2.cuda_GpuMat()
                    gpu_frame.upload(frame)
                    processed = filter_fn(frame, intensity, gpu_frame=gpu_frame)
                except Exception:
                    processed = filter_fn(frame, intensity)
            else:
                processed = filter_fn(frame, intensity)

            writer.write(processed)
            frame_idx += 1

            if frame_idx % 100 == 0:
                progress = int(frame_idx / total * 100) if total > 0 else 0
                print(f"[EffectsEngine] Processing: {progress}% ({frame_idx}/{total})")

        cap.release()
        writer.release()

        # ── Convert AVI → MP4 via FFmpeg and remux audio ──
        # This gives us proper MP4 with audio in one step
        cmd = [
            FFMPEG, "-y",
            "-i", temp_avi,         # Processed video (no audio)
            "-i", clip_path,        # Original (has audio)
            "-c:v", "libx264",      # Re-encode to H.264 for compatibility
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-map", "0:v:0",        # Video from processed
            "-map", "1:a:0",        # Audio from original
            "-shortest",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)

        # Clean up temp AVI
        try:
            os.remove(temp_avi)
        except Exception:
            pass

        if result.returncode != 0:
            err = result.stderr.decode('utf-8', errors='replace')
            print(f"[EffectsEngine] FFmpeg convert error: {err[-500:]}")
            return False

        return True

    def _remux_audio(self, original_path: str, video_path: str):
        """
        Re-add audio from original clip to the processed video.
        OpenCV VideoWriter doesn't preserve audio, so we need this step.

        Creates a temp file, muxes video+audio, then replaces output.
        """
        temp_path = video_path + "_audio_temp.mp4"
        try:
            cmd = [
                FFMPEG, "-y",
                "-i", video_path,       # Processed video (no audio)
                "-i", original_path,    # Original (has audio)
                "-c:v", "copy",
                "-c:a", "copy",
                "-map", "0:v:0",        # Video from processed
                "-map", "1:a:0",        # Audio from original
                "-shortest",
                temp_path
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)

            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, video_path)   # Atomic replace
            else:
                # Audio remux failed — keep video without audio
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                print("[EffectsEngine] Audio remux failed — output has no audio")

        except Exception as e:
            print(f"[EffectsEngine] Audio remux error: {e}")

    # ─────────────────────────────────────────────────────────────
    # FILTER IMPLEMENTATIONS (OpenCV)
    # ─────────────────────────────────────────────────────────────

    def _filter_grayscale(self, frame: np.ndarray, intensity: float,
                           gpu_frame=None) -> np.ndarray:
        """
        Convert frame to grayscale then back to BGR.
        intensity is ignored (grayscale is binary).

        GPU: cv2.cuda.cvtColor (if available)
        CPU: cv2.cvtColor
        """
        if gpu_frame is not None:
            try:
                # GPU grayscale
                gray_gpu = cv2.cuda.cvtColor(gpu_frame, cv2.COLOR_BGR2GRAY)
                # Convert back to BGR for VideoWriter (needs 3 channels)
                bgr_gpu = cv2.cuda.cvtColor(gray_gpu, cv2.COLOR_GRAY2BGR)
                return bgr_gpu.download()
            except Exception:
                pass

        # CPU fallback
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def _filter_sepia(self, frame: np.ndarray, intensity: float,
                      gpu_frame=None) -> np.ndarray:
        """
        Apply sepia tone using a 3x3 color matrix transform.

        Sepia = warm brownish vintage look.
        intensity blends between original and full sepia (0–1).
        """
        # Apply sepia matrix to float32 frame
        frame_f = frame.astype(np.float32) / 255.0
        sepia_frame = cv2.transform(frame_f, SEPIA_KERNEL)
        sepia_frame = np.clip(sepia_frame, 0, 1)
        sepia_u8 = (sepia_frame * 255).astype(np.uint8)

        # Blend original and sepia based on intensity
        intensity = max(0.0, min(1.0, intensity))
        blended = cv2.addWeighted(frame, 1.0 - intensity, sepia_u8, intensity, 0)
        return blended

    def _filter_blur(self, frame: np.ndarray, intensity: float,
                     gpu_frame=None) -> np.ndarray:
        """
        Apply Gaussian blur.
        intensity = blur kernel size (1–20, must be odd).

        GPU: cv2.cuda.GaussianBlur (if available)
        CPU: cv2.GaussianBlur
        """
        # Kernel size must be positive odd integer
        ksize = max(1, int(intensity))
        if ksize % 2 == 0:
            ksize += 1  # Make it odd

        if gpu_frame is not None:
            try:
                blurred = cv2.cuda.GaussianBlur(gpu_frame, (ksize, ksize), 0)
                return blurred.download()
            except Exception:
                pass

        # CPU fallback
        return cv2.GaussianBlur(frame, (ksize, ksize), 0)

    def _filter_sharpen(self, frame: np.ndarray, intensity: float,
                        gpu_frame=None) -> np.ndarray:
        """
        Sharpen frame using unsharp mask technique.
        intensity = sharpening strength (0.5–3.0).

        Unsharp mask: sharp = original + intensity * (original - blurred)
        This enhances edges while preserving overall structure.
        """
        intensity = max(0.5, min(3.0, intensity))

        # Create blurred version (the "unsharp" mask source)
        blurred = cv2.GaussianBlur(frame, (0, 0), 3)

        # Blend: original + intensity * (original - blurred)
        # cv2.addWeighted: dst = src1*alpha + src2*beta + gamma
        sharpened = cv2.addWeighted(frame, 1 + intensity, blurred, -intensity, 0)
        return sharpened

    def _filter_flip_h(self, frame: np.ndarray, intensity: float,
                       gpu_frame=None) -> np.ndarray:
        """Flip frame horizontally (mirror effect). intensity ignored."""
        if gpu_frame is not None:
            try:
                flipped = cv2.cuda.flip(gpu_frame, 1)   # 1 = horizontal
                return flipped.download()
            except Exception:
                pass
        return cv2.flip(frame, 1)

    def _filter_flip_v(self, frame: np.ndarray, intensity: float,
                       gpu_frame=None) -> np.ndarray:
        """Flip frame vertically. intensity ignored."""
        if gpu_frame is not None:
            try:
                flipped = cv2.cuda.flip(gpu_frame, 0)   # 0 = vertical
                return flipped.download()
            except Exception:
                pass
        return cv2.flip(frame, 0)

    # ─────────────────────────────────────────────────────────────
    # TEXT OVERLAY
    # ─────────────────────────────────────────────────────────────

    def add_text(self, clip_path: str, text: str,
                 position: dict,
                 font_size: int = 32,
                 color: str = "#ffffff",
                 start_time: float = 0,
                 end_time: Optional[float] = None,
                 output_path: Optional[str] = None) -> dict:
        """
        Add a text overlay to a video clip.

        Uses FFmpeg drawtext filter for efficiency — no need to
        process frames individually for text.

        Args:
            clip_path: Source video
            text: Text string to display
            position: {x, y} in pixels OR {align: "center"|"topleft" etc}
            font_size: Font size in pixels
            color: Hex color string e.g. "#ffffff"
            start_time: When text appears (seconds from start)
            end_time: When text disappears (None = until end)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source file not found"}

        if not output_path:
            output_path = self._make_output_path(clip_path, "text")

        try:
            # ── Convert hex color to FFmpeg format ──
            # FFmpeg uses 0xRRGGBB or color name
            ffmpeg_color = self._hex_to_ffmpeg_color(color)

            # ── Resolve position ──
            x, y = self._resolve_text_position(position, clip_path)

            # ── Escape text for FFmpeg ──
            # FFmpeg drawtext has special chars: : ' \ need escaping
            safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")

            # ── Font path for FFmpeg ──
            font_arg = ""
            if self._font_path and os.path.exists(self._font_path):
                # Escape backslashes in Windows paths
                safe_font = self._font_path.replace("\\", "/")
                font_arg = f"fontfile={safe_font}:"

            # ── Time enable expression ──
            # FFmpeg enable= controls when filter is active
            if end_time is not None:
                enable = f"enable='between(t,{start_time},{end_time})'"
            else:
                enable = f"enable='gte(t,{start_time})'"

            # ── Build drawtext filter ──
            drawtext = (
                f"drawtext="
                f"{font_arg}"
                f"text='{safe_text}':"
                f"fontcolor={ffmpeg_color}:"
                f"fontsize={font_size}:"
                f"x={x}:y={y}:"
                f"box=1:boxcolor=black@0.4:boxborderw=5:"  # Semi-transparent bg box
                f"{enable}"
            )

            cmd = [
                FFMPEG, "-y",
                "-i", clip_path,
                "-vf", drawtext,
                "-c:a", "copy",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"[EffectsEngine] Text overlay error: {result.stderr[:500]}")
                return {"success": False, "message": "Text overlay failed"}

            print(f"[EffectsEngine] Text overlay added → {output_path}")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            print(f"[EffectsEngine] Text error: {e}")
            return {"success": False, "message": str(e)}

    def _resolve_text_position(self, position: dict,
                                clip_path: str) -> Tuple[str, str]:
        """
        Convert position dict to FFmpeg x,y expressions.

        Supports:
        - Pixel positions: {x: 100, y: 50}
        - Named positions: {align: "center"|"topleft"|"topright"|etc}
        - FFmpeg expressions: "w/2-text_w/2" for center

        Returns:
            tuple: (x_expression, y_expression) as strings
        """
        align = position.get("align", "")

        if align == "center":
            return "(w-text_w)/2", "(h-text_h)/2"
        elif align == "topleft":
            return "10", "10"
        elif align == "topright":
            return "w-text_w-10", "10"
        elif align == "bottomleft":
            return "10", "h-text_h-10"
        elif align == "bottomright":
            return "w-text_w-10", "h-text_h-10"
        elif align == "topcenter":
            return "(w-text_w)/2", "10"
        elif align == "bottomcenter":
            return "(w-text_w)/2", "h-text_h-10"
        else:
            # Pixel coordinates from position dict
            x = position.get("x", 10)
            y = position.get("y", 10)
            return str(x), str(y)

    # ─────────────────────────────────────────────────────────────
    # WATERMARK
    # ─────────────────────────────────────────────────────────────

    def add_watermark(self, clip_path: str, watermark_path: str,
                      position: str = "bottomright",
                      opacity: float = 0.7,
                      scale: float = 0.15,
                      output_path: Optional[str] = None) -> dict:
        """
        Add an image watermark overlay to a video clip.

        Uses FFmpeg overlay filter — very fast, no frame-by-frame needed.

        Args:
            clip_path: Source video
            watermark_path: Path to watermark image (PNG with transparency works best)
            position: "topleft"|"topright"|"bottomleft"|"bottomright"|"center"
            opacity: Watermark opacity 0.0–1.0
            scale: Watermark size as fraction of video width (0.15 = 15% of width)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Video file not found"}
        if not os.path.exists(watermark_path):
            return {"success": False, "message": "Watermark image not found"}

        if not output_path:
            output_path = self._make_output_path(clip_path, "watermark")

        try:
            # ── Position expressions for FFmpeg overlay filter ──
            # main_w/main_h = video dimensions
            # overlay_w/overlay_h = watermark dimensions
            position_map = {
                "topleft":     "10:10",
                "topright":    "main_w-overlay_w-10:10",
                "bottomleft":  "10:main_h-overlay_h-10",
                "bottomright": "main_w-overlay_w-10:main_h-overlay_h-10",
                "center":      "(main_w-overlay_w)/2:(main_h-overlay_h)/2"
            }
            overlay_pos = position_map.get(position, position_map["bottomright"])

            # ── Build filter complex ──
            # 1. Scale watermark to % of video width
            # 2. Apply opacity via colorchannelmixer or format+alpha
            # 3. Overlay at position
            filter_complex = (
                f"[1:v]scale=iw*{scale}:-1,"        # Scale watermark
                f"format=rgba,"                       # Ensure RGBA for alpha
                f"colorchannelmixer=aa={opacity}"     # Set opacity
                f"[wm];"                             # Label as [wm]
                f"[0:v][wm]overlay={overlay_pos}"    # Overlay on video
            )

            cmd = [
                FFMPEG, "-y",
                "-i", clip_path,
                "-i", watermark_path,
                "-filter_complex", filter_complex,
                "-c:a", "copy",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"[EffectsEngine] Watermark error: {result.stderr[:500]}")
                return {"success": False, "message": "Watermark failed"}

            print(f"[EffectsEngine] Watermark added ({position}) → {output_path}")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            print(f"[EffectsEngine] Watermark error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # CROP FILTER
    # ─────────────────────────────────────────────────────────────

    def crop(self, clip_path: str,
             x: int, y: int, width: int, height: int,
             output_path: Optional[str] = None) -> dict:
        """
        Crop a video to a specific rectangle.
        Useful for removing borders or focusing on a region.

        Args:
            clip_path: Source video
            x, y: Top-left corner of crop region (pixels)
            width, height: Crop dimensions (pixels)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if not output_path:
            output_path = self._make_output_path(clip_path, "crop")

        try:
            cmd = [
                FFMPEG, "-y",
                "-i", clip_path,
                "-vf", f"crop={width}:{height}:{x}:{y}",
                "-c:a", "copy",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                return {"success": False, "message": "Crop failed"}

            print(f"[EffectsEngine] Cropped to {width}x{height} at ({x},{y})")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # STACK / SIDE BY SIDE
    # ─────────────────────────────────────────────────────────────

    def stack_clips(self, clip_a: str, clip_b: str,
                    direction: str = "horizontal",
                    output_path: Optional[str] = None) -> dict:
        """
        Stack two clips side by side or top/bottom.
        Great for comparison or reaction-style videos.

        Args:
            clip_a: First video
            clip_b: Second video
            direction: "horizontal" (side by side) | "vertical" (top/bottom)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if not output_path:
            output_path = self._make_output_path(clip_a, f"stack_{direction}")

        try:
            if direction == "horizontal":
                # hstack: puts clips side by side horizontally
                filter_complex = "[0:v][1:v]hstack=inputs=2[v]"
            else:
                # vstack: puts clips top and bottom vertically
                filter_complex = "[0:v][1:v]vstack=inputs=2[v]"

            cmd = [
                FFMPEG, "-y",
                "-i", clip_a,
                "-i", clip_b,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-c:a", "copy",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                return {"success": False, "message": "Stack failed"}

            print(f"[EffectsEngine] Clips stacked ({direction}) → {output_path}")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _hex_to_ffmpeg_color(self, hex_color: str) -> str:
        """
        Convert hex color (#RRGGBB) to FFmpeg color format (0xRRGGBB).

        Args:
            hex_color: "#ffffff" or "ffffff"

        Returns:
            str: "0xffffff" for FFmpeg
        """
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            return f"0x{hex_color.upper()}"
        return "0xFFFFFF"   # Default white

    def _find_font(self) -> Optional[str]:
        """
        Scan common font directories to find a usable TTF font.
        Used as fallback when default font paths don't exist.
        """
        search_paths = [
            # Linux common font paths
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/OTF/Helvetica.otf",
            # Windows paths
            "C:/Windows/Fonts/Arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

        for path in search_paths:
            if os.path.exists(path):
                print(f"[EffectsEngine] Font found: {path}")
                return path

        print("[EffectsEngine] No TTF font found — text overlays use default FFmpeg font")
        return None

    def _make_output_path(self, source_path: str, suffix: str) -> str:
        """Generate output file path with suffix and timestamp"""
        dir_name  = os.path.dirname(source_path)
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        ext       = os.path.splitext(source_path)[1]
        timestamp = int(time.time())
        return os.path.join(dir_name, f"{base_name}_{suffix}_{timestamp}{ext}")

    # ─────────────────────────────────────────────────────────────
    # NEW FILTER IMPLEMENTATIONS
    # ─────────────────────────────────────────────────────────────

    def _filter_film_grain(self, frame: np.ndarray, intensity: float,
                            gpu_frame=None) -> np.ndarray:
        """Add realistic film grain noise to frame"""
        intensity = max(0.01, min(0.15, float(intensity) * 0.05))
        noise = np.random.normal(0, intensity * 255, frame.shape).astype(np.int16)
        grained = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        return grained

    def _filter_mirror(self, frame: np.ndarray, intensity: float,
                       gpu_frame=None) -> np.ndarray:
        """Mirror left half onto right half"""
        h, w = frame.shape[:2]
        left_half = frame[:, :w//2]
        mirrored  = cv2.flip(left_half, 1)
        result    = frame.copy()
        result[:, w//2:w//2 + mirrored.shape[1]] = mirrored
        return result

    # ─────────────────────────────────────────────────────────────
    # COLOR GRADING — LUT presets via FFmpeg curves
    # ─────────────────────────────────────────────────────────────

    def apply_lut(self, clip_path: str, lut_name: str,
                  output_path: Optional[str] = None) -> dict:
        """
        Apply a color grade LUT preset using FFmpeg curves/eq filters.
        No external .cube files needed — pure FFmpeg math.

        Args:
            clip_path: Source video
            lut_name:  LUT preset name from _lut_registry
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if lut_name not in self._lut_registry:
            return {"success": False,
                    "message": f"Unknown LUT: {lut_name}. Available: {list(self._lut_registry.keys())}"}

        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source file not found"}

        if not output_path:
            output_path = self._make_output_path(clip_path, f"lut_{lut_name}")

        vf_filter = self._lut_registry[lut_name]

        result = self._apply_ffmpeg_filter(clip_path, output_path, vf_filter)
        if result:
            print(f"[EffectsEngine] LUT '{lut_name}' applied → {output_path}")
            return {"success": True, "output_path": output_path, "lut": lut_name}
        return {"success": False, "message": f"LUT '{lut_name}' failed"}

    def apply_color_grade(self, clip_path: str,
                           brightness: float = 0.0,
                           contrast:   float = 1.0,
                           saturation: float = 1.0,
                           gamma:      float = 1.0,
                           hue:        float = 0.0,
                           shadows:    float = 0.0,
                           highlights: float = 0.0,
                           output_path: Optional[str] = None) -> dict:
        """
        Apply combined color grading in a single FFmpeg pass.
        All adjustments applied together = no quality loss from multiple passes.

        Args:
            brightness: -1.0 to 1.0 (0 = original)
            contrast:   0.0 to 3.0 (1.0 = original)
            saturation: 0.0 to 3.0 (1.0 = original)
            gamma:      0.1 to 3.0 (1.0 = original)
            hue:        -180 to 180 degrees
            shadows:    -0.5 to 0.5 (lift shadows)
            highlights: -0.5 to 0.5 (pull highlights)
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source not found"}

        if not output_path:
            output_path = self._make_output_path(clip_path, "colorgrade")

        # ── Build FFmpeg filter chain ──
        filters = []

        # Base EQ (brightness, contrast, saturation, gamma)
        eq_parts = []
        if brightness != 0.0:
            eq_parts.append(f"brightness={brightness:.3f}")
        if contrast != 1.0:
            eq_parts.append(f"contrast={contrast:.3f}")
        if saturation != 1.0:
            eq_parts.append(f"saturation={saturation:.3f}")
        if gamma != 1.0:
            eq_parts.append(f"gamma={gamma:.3f}")
        if eq_parts:
            filters.append("eq=" + ":".join(eq_parts))

        # Hue shift
        if hue != 0.0:
            filters.append(f"hue=h={hue:.1f}")

        # Shadows and highlights via curves
        if shadows != 0.0 or highlights != 0.0:
            # Shadow lift: raise the black point
            # Highlight pull: lower the white point
            s = max(0.0, min(0.3, shadows + 0.3)) if shadows > 0 else 0.0
            h_val = max(0.7, min(1.0, 1.0 + highlights)) if highlights < 0 else 1.0
            filters.append(f"curves=all='0/{s:.3f} 0.5/0.5 1/{h_val:.3f}'")

        if not filters:
            return {"success": False, "message": "No adjustments specified"}

        vf = ",".join(filters)
        print(f"[EffectsEngine] Color grade filter: {vf}")

        result = self._apply_ffmpeg_filter(clip_path, output_path, vf)
        if result:
            return {"success": True, "output_path": output_path}
        return {"success": False, "message": "Color grade failed"}

    # ─────────────────────────────────────────────────────────────
    # ASPECT RATIO CROP
    # ─────────────────────────────────────────────────────────────

    def apply_aspect_ratio(self, clip_path: str, ratio: str,
                            output_path: Optional[str] = None) -> dict:
        """
        Crop video to a specific aspect ratio.
        Centers the crop on the original frame.

        Args:
            clip_path: Source video
            ratio:     "16:9" | "9:16" | "1:1" | "4:5" | "4:3" | "21:9"
            output_path: Optional output path

        Returns:
            dict: {success, output_path, width, height}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source not found"}

        if not output_path:
            safe_ratio = ratio.replace(":", "x")
            output_path = self._make_output_path(clip_path, f"ratio_{safe_ratio}")

        # ── Build crop filter ──
        # FFmpeg crop=w:h:x:y where x,y = center offset
        # Using iw/ih (input width/height) as variables for dynamic calc

        ratio_map = {
            "16:9":  "iw:iw*9/16",           # Wide — crop top/bottom
            "9:16":  "ih*9/16:ih",            # Tall — crop left/right
            "1:1":   "iw:iw",                 # Square (will be padded)
            "4:5":   "ih*4/5:ih",             # Instagram portrait
            "4:3":   "ih*4/3:ih",             # Classic
            "21:9":  "iw:iw*9/21",            # Ultrawide
        }

        if ratio not in ratio_map:
            return {"success": False, "message": f"Unknown ratio: {ratio}"}

        w_expr, h_expr = ratio_map[ratio].split(":")

        # Center the crop
        crop_filter = (
            f"crop={w_expr}:{h_expr}:"
            f"(iw-{w_expr})/2:(ih-{h_expr})/2"
        )

        print(f"[EffectsEngine] Aspect ratio {ratio} → crop filter: {crop_filter}")
        result = self._apply_ffmpeg_filter(clip_path, output_path, crop_filter)

        if result:
            return {"success": True, "output_path": output_path, "ratio": ratio}
        return {"success": False, "message": f"Aspect ratio crop failed for {ratio}"}

    def get_available_filters(self) -> list:
        """Return list of all available filter names for the UI"""
        return list(self._filter_registry.keys())
