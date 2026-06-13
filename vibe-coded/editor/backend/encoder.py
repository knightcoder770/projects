# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/encoder.py
# Video Encoding Engine
#
# Responsibilities:
#   - Take raw numpy frames from CaptureEngine
#   - Take WAV audio path from AudioEngine
#   - Encode to MP4 / MKV / GIF using FFmpeg
#   - Use NVENC (RTX 3050 GPU) for hardware-accelerated H.264/H.265
#   - Fall back to CPU encoding (libx264) if NVENC unavailable
#   - Mux video + audio into final output file
#   - Generate thumbnail for clip library
#   - Report encoding progress back to UI via callback
#
# DSA Used:
#   - Queue for frame pipeline (producer-consumer pattern)
#     → CaptureEngine produces frames
#     → Encoder consumes frames via subprocess pipe
#   - Subprocess pipe to FFmpeg stdin (streaming frames directly)
#     → Avoids writing all frames to disk before encoding
#     → Much faster and lower memory usage
#
# GPU:
#   - h264_nvenc: NVENC H.264 (best compatibility, RTX 3050 supported)
#   - hevc_nvenc: NVENC H.265 (better compression, same quality)
#   - Fallback: libx264 (CPU, slower but always works)
# ─────────────────────────────────────────────────────────────────

import subprocess          # Run FFmpeg as subprocess
import threading
import os
import platform
import tempfile
import time
import shutil              # Check if ffmpeg is in PATH
from typing import List, Optional, Callable
import numpy as np
import cv2                 # For thumbnail generation + frame writing


# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# Quality presets map to FFmpeg CRF values (lower = better quality)
# NVENC uses -cq (constant quality), libx264 uses -crf
QUALITY_PRESETS = {
    "low":      {"crf": 35, "cq": 35, "preset": "fast"},
    "medium":   {"crf": 28, "cq": 28, "preset": "medium"},
    "high":     {"crf": 20, "cq": 20, "preset": "slow"},
    "lossless": {"crf": 0,  "cq": 0,  "preset": "lossless"}
}

# Supported output formats
SUPPORTED_FORMATS = ["mp4", "mkv", "gif"]

# Thumbnail size for clip library preview
THUMBNAIL_WIDTH = 320
THUMBNAIL_HEIGHT = 180


# ─────────────────────────────────────────────────────────────────
# ENCODER ENGINE CLASS
# ─────────────────────────────────────────────────────────────────

class EncoderEngine:
    """
    Handles video encoding using FFmpeg with NVENC GPU acceleration.

    Pipeline:
    1. Receive frames list from CaptureEngine
    2. Open FFmpeg subprocess with stdin pipe
    3. Stream frames directly into FFmpeg stdin (no temp disk writes)
    4. FFmpeg encodes with NVENC (GPU) or libx264 (CPU fallback)
    5. Mux with audio WAV file
    6. Generate thumbnail from first frame
    7. Return result metadata
    """

    def __init__(self):
        # ── Check FFmpeg availability ──
        self._ffmpeg_path = self._find_ffmpeg()

        # ── Check NVENC availability (RTX 3050) ──
        self._nvenc_available = self._check_nvenc()

        # ── Check NVENC H.265 support ──
        self._hevc_nvenc_available = self._check_hevc_nvenc()

        # ── Progress tracking ──
        self._progress_callback: Optional[Callable] = None
        self._is_encoding = False

        print(f"[EncoderEngine] Initialized")
        print(f"[EncoderEngine] FFmpeg: {self._ffmpeg_path}")
        print(f"[EncoderEngine] NVENC H.264: {self._nvenc_available}")
        print(f"[EncoderEngine] NVENC H.265: {self._hevc_nvenc_available}")

    # ─────────────────────────────────────────────────────────────
    # FFMPEG DETECTION
    # ─────────────────────────────────────────────────────────────

    def _find_ffmpeg(self) -> str:
        """
        Find FFmpeg executable path.
        Checks system PATH first, then common install locations.

        Returns:
            str: Path to ffmpeg executable
        """
        # Check if ffmpeg is in system PATH
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            print(f"[EncoderEngine] FFmpeg found in PATH: {ffmpeg}")
            return ffmpeg

        # Common locations on Windows
        windows_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.join(os.environ.get("USERPROFILE", ""), "ffmpeg", "bin", "ffmpeg.exe")
        ]

        # Common locations on Linux
        linux_paths = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/ffmpeg/bin/ffmpeg"
        ]

        search_paths = windows_paths if platform.system() == "Windows" else linux_paths

        for path in search_paths:
            if os.path.exists(path):
                print(f"[EncoderEngine] FFmpeg found at: {path}")
                return path

        # FFmpeg not found — warn user
        print("[EncoderEngine] WARNING: FFmpeg not found! Install it:")
        print("  Windows: https://ffmpeg.org/download.html")
        print("  Arch Linux: sudo pacman -S ffmpeg")
        return "ffmpeg"     # Return "ffmpeg" and hope it's in PATH at runtime

    # ─────────────────────────────────────────────────────────────
    # NVENC DETECTION
    # ─────────────────────────────────────────────────────────────

    def _check_nvenc(self) -> bool:
        """
        Check if NVENC H.264 encoder is available via FFmpeg.
        RTX 3050 fully supports NVENC.

        Tests by running: ffmpeg -encoders | grep nvenc
        """
        try:
            result = subprocess.run(
                [self._ffmpeg_path, "-encoders", "-hide_banner"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "h264_nvenc" in result.stdout:
                print("[EncoderEngine] NVENC H.264 available ✓")
                return True
            else:
                print("[EncoderEngine] NVENC H.264 not available, will use libx264")
                return False
        except Exception as e:
            print(f"[EncoderEngine] NVENC check error: {e}")
            return False

    def _check_hevc_nvenc(self) -> bool:
        """Check if NVENC H.265 (HEVC) encoder is available"""
        try:
            result = subprocess.run(
                [self._ffmpeg_path, "-encoders", "-hide_banner"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return "hevc_nvenc" in result.stdout
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────
    # MAIN ENCODE FUNCTION
    # ─────────────────────────────────────────────────────────────

    def encode(self,
               frames: List[np.ndarray],
               audio_path: Optional[str],
               output_path: str,
               format: str = "mp4",
               quality: str = "high",
               fps: float = 30.0,
               progress_callback: Optional[Callable] = None,
               video_duration: float = 0.0) -> dict:
        # video_duration: exact recording duration from timestamps
        # Used to trim audio to EXACTLY match video length
        # This is the key fix for A/V sync
        """
        Encode frames + audio into a video file.

        Args:
            frames: List of numpy BGR frames from CaptureEngine
            audio_path: Path to WAV file from AudioEngine (None = no audio)
            output_path: Full path for output file (e.g. /home/user/clip.mp4)
            format: "mp4" | "mkv" | "gif"
            quality: "low" | "medium" | "high" | "lossless"
            fps: Frames per second (from CaptureEngine.detected_fps)
            progress_callback: Function(percent: int) called during encoding

        Returns:
            dict: {
                success: bool,
                file_path: str,
                size_mb: float,
                duration: float,
                thumbnail: str (path to thumbnail image)
            }
        """
        if not frames:
            return {"success": False, "message": "No frames to encode"}

        if format not in SUPPORTED_FORMATS:
            return {"success": False, "message": f"Unsupported format: {format}"}

        self._is_encoding = True
        self._progress_callback = progress_callback

        try:
            # ── Get frame dimensions from first frame ──
            height, width = frames[0].shape[:2]
            total_frames  = len(frames)

            # ── Calculate exact duration ──
            # Use video_duration from timestamps if available (most accurate)
            # Otherwise calculate from frame count / fps
            if video_duration and video_duration > 0:
                duration = video_duration
                # Recalculate fps from actual duration for perfect sync
                fps = (total_frames - 1) / video_duration if total_frames > 1 else fps
                print(f"[EncoderEngine] Using timestamp-based FPS: {fps:.4f} | Duration: {duration:.3f}s")
            else:
                duration = total_frames / fps if fps > 0 else 0

            # ── Trim audio to EXACTLY match video duration ──
            # This is the main A/V sync fix:
            # Audio WAV may be longer/shorter than video due to thread timing
            # We trim it to exact video duration before muxing
            if audio_path and os.path.exists(audio_path) and duration > 0:
                audio_path = self._trim_audio_to_duration(audio_path, duration)

            print(f"[EncoderEngine] Encoding {total_frames} frames | "
                  f"{width}x{height} @ {fps:.3f}fps | Format: {format} | Quality: {quality}")

            # ── Route to appropriate encoder ──
            if format == "gif":
                result_path = self._encode_gif(frames, output_path, fps, width, height)
            elif self._nvenc_available and quality != "lossless":
                result_path = self._encode_nvenc(
                    frames, audio_path, output_path, format,
                    quality, fps, width, height, total_frames
                )
            else:
                # CPU fallback
                result_path = self._encode_cpu(
                    frames, audio_path, output_path, format,
                    quality, fps, width, height, total_frames
                )

            if not result_path or not os.path.exists(result_path):
                return {"success": False, "message": "Encoding failed — output file not created"}

            # ── Generate thumbnail ──
            thumb_path = self._generate_thumbnail(frames[0], output_path)

            # ── File size ──
            size_bytes = os.path.getsize(result_path)
            size_mb = round(size_bytes / (1024 * 1024), 2)

            print(f"[EncoderEngine] Done | Output: {result_path} | "
                  f"Size: {size_mb}MB | Duration: {duration:.1f}s")

            return {
                "success": True,
                "file_path": result_path,
                "size_mb": size_mb,
                "duration": round(duration, 2),
                "thumbnail": thumb_path,
                "width": width,
                "height": height,
                "fps": fps
            }

        except Exception as e:
            print(f"[EncoderEngine] Encoding error: {e}")
            return {"success": False, "message": str(e)}

        finally:
            self._is_encoding = False

    # ─────────────────────────────────────────────────────────────
    # NVENC ENCODING (GPU - RTX 3050)
    # ─────────────────────────────────────────────────────────────

    def _encode_nvenc(self, frames, audio_path, output_path, format,
                      quality, fps, width, height, total_frames) -> str:
        """
        Encode using NVENC hardware encoder on RTX 3050.

        FFmpeg pipeline:
        stdin (raw BGR frames) → h264_nvenc → mux with audio → output file

        NVENC advantages over CPU:
        - 5-10x faster encoding
        - Frees CPU for capture and UI
        - RTX 3050 has dedicated NVENC engine (doesn't use CUDA cores)
        """
        q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])

        # ── Determine codec ──
        # Use H.265 for MKV (better compression), H.264 for MP4 (compatibility)
        if format == "mkv" and self._hevc_nvenc_available:
            video_codec = "hevc_nvenc"
        else:
            video_codec = "h264_nvenc"

        # ── Build FFmpeg command ──
        cmd = [
            self._ffmpeg_path,
            "-y",                           # Overwrite output without asking

            # ── Video input from stdin ──
            "-f", "rawvideo",               # Input format: raw video frames
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",            # OpenCV uses BGR24
            "-s", f"{width}x{height}",      # Frame dimensions
            "-r", str(fps),                 # Input FPS
            "-i", "pipe:0",                 # Read from stdin (pipe)

            # ── Audio input (if available) ──
            *(["-i", audio_path] if audio_path and os.path.exists(audio_path) else []),

            # ── NVENC video encoding ──
            "-c:v", video_codec,
            "-preset", "p4",                # NVENC preset: p1(fast)–p7(slow), p4=balanced
            "-cq", str(q["cq"]),            # Constant quality (NVENC equivalent of CRF)
            "-rc", "vbr",                   # Variable bitrate mode
            "-b:v", "0",                    # Let CQ control quality, no bitrate limit
            "-maxrate", "20M",              # Max bitrate cap (prevents huge files)
            "-bufsize", "40M",              # Buffer for rate control
            "-gpu", "0",                    # Use first GPU (RTX 3050)
            "-pix_fmt", "yuv420p",          # Output pixel format (broad compatibility)

            # ── Audio encoding + sync fix ──
            # aresample=async=1: fixes A/V sync by resampling audio
            # to match video timeline (handles drift from capture)
            *(["-c:a", "aac", "-b:a", "192k",
               "-af", "aresample=async=1:min_hard_comp=0.100000:first_pts=0",
               "-fps_mode", "cfr"]                 # Constant frame rate keeps sync
              if audio_path and os.path.exists(audio_path) else
              ["-fps_mode", "cfr"]),

            # ── Output ──
            output_path
        ]

        return self._run_ffmpeg(cmd, total_frames, frames)

    # ─────────────────────────────────────────────────────────────
    # CPU ENCODING (libx264 fallback)
    # ─────────────────────────────────────────────────────────────

    def _encode_cpu(self, frames, audio_path, output_path, format,
                    quality, fps, width, height, total_frames) -> str:
        """
        CPU encoding fallback using libx264 / libx265.
        Used when NVENC is not available or for lossless encoding.
        Slower than NVENC but produces identical quality output.
        """
        q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])

        # Choose codec based on format
        if format == "mkv":
            video_codec = "libx265"
            extra = ["-crf", str(q["crf"]), "-preset", q["preset"]]
        else:
            video_codec = "libx264"
            if quality == "lossless":
                extra = ["-qp", "0", "-preset", "ultrafast"]
            else:
                extra = ["-crf", str(q["crf"]), "-preset", q["preset"]]

        cmd = [
            self._ffmpeg_path,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "pipe:0",
            *(["-i", audio_path] if audio_path and os.path.exists(audio_path) else []),
            "-c:v", video_codec,
            *extra,
            "-pix_fmt", "yuv420p",
            "-fps_mode", "cfr",
            *(["-c:a", "aac", "-b:a", "192k",
               "-af", "aresample=async=1:min_hard_comp=0.100000:first_pts=0"]
              if audio_path and os.path.exists(audio_path) else []),
            output_path
        ]

        print(f"[EncoderEngine] Using CPU encoder: {video_codec}")
        return self._run_ffmpeg(cmd, total_frames, frames)

    # ─────────────────────────────────────────────────────────────
    # GIF ENCODING
    # ─────────────────────────────────────────────────────────────

    def _encode_gif(self, frames, output_path, fps, width, height) -> str:
        """
        Encode frames as an optimized GIF using FFmpeg palette trick.

        FFmpeg GIF pipeline (two-pass for best quality):
        Pass 1: Generate optimal color palette from all frames
        Pass 2: Encode GIF using that palette

        GIFs are capped at 15fps for reasonable file size.
        """
        gif_fps = min(fps, 15)      # GIF max fps cap

        # ── Pass 1: Generate palette ──
        # FFmpeg needs the video twice (stdin can't be rewound)
        # So we first write frames to a temp file, then encode

        temp_raw = tempfile.NamedTemporaryFile(suffix=".avi", delete=False)
        temp_raw_path = temp_raw.name
        temp_raw.close()

        palette_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name

        try:
            # Write frames to temp AVI (lossless, fast)
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            writer = cv2.VideoWriter(temp_raw_path, fourcc, gif_fps, (width, height))
            for frame in frames:
                writer.write(frame)
            writer.release()

            # Generate palette
            palette_cmd = [
                self._ffmpeg_path, "-y",
                "-i", temp_raw_path,
                "-vf", f"fps={gif_fps},scale={width}:{height}:flags=lanczos,palettegen",
                palette_path
            ]
            subprocess.run(palette_cmd, capture_output=True, timeout=60)

            # Encode GIF with palette
            gif_cmd = [
                self._ffmpeg_path, "-y",
                "-i", temp_raw_path,
                "-i", palette_path,
                "-lavfi", f"fps={gif_fps},scale={width}:{height}:flags=lanczos[x];[x][1:v]paletteuse",
                output_path
            ]
            subprocess.run(gif_cmd, capture_output=True, timeout=120)

        finally:
            # Clean up temp files
            for p in [temp_raw_path, palette_path]:
                if os.path.exists(p):
                    os.remove(p)

        print(f"[EncoderEngine] GIF encoded: {output_path}")
        return output_path

    # ─────────────────────────────────────────────────────────────
    # FFMPEG SUBPROCESS RUNNER
    # ─────────────────────────────────────────────────────────────

    def _run_ffmpeg(self, cmd: list, total_frames: int,
                    frames: List[np.ndarray]) -> str:
        """
        Run FFmpeg and write frames via stdin pipe.

        Fix for 'write to closed file':
        - Do NOT use process.communicate() — it closes stdin internally
        - Instead: write all frames first, close stdin, then wait for process
        - Use a large pipe buffer via bufsize=-1 (OS default, usually 64KB+)
        - Drain stderr in background thread to prevent deadlock

        Fix for blank screen / lag:
        - Encoding runs in background thread in main.py
        - This function just does the actual work synchronously
        """
        output_path = cmd[-1]

        try:
            # Start FFmpeg with large buffer size
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8      # Large buffer prevents pipe stalls
            )

            # ── Drain stderr in background to prevent deadlock ──
            # If stderr buffer fills, FFmpeg blocks, causing deadlock
            stderr_lines = []
            def drain_stderr():
                for line in process.stderr:
                    stderr_lines.append(line)
            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()

            # ── Write ALL frames to stdin ──
            # Do this synchronously — no separate thread needed
            # because stderr is being drained in background
            write_ok = True
            for i, frame in enumerate(frames):
                try:
                    # Check if FFmpeg died early
                    if process.poll() is not None:
                        print(f"[EncoderEngine] FFmpeg exited early at frame {i}")
                        write_ok = False
                        break

                    process.stdin.write(frame.tobytes())

                    # Flush every 30 frames to keep pipe moving
                    if i % 30 == 0:
                        process.stdin.flush()

                    # Progress callback
                    if self._progress_callback and total_frames > 0:
                        percent = int((i + 1) / total_frames * 100)
                        self._progress_callback(percent)

                except BrokenPipeError:
                    print(f"[EncoderEngine] Broken pipe at frame {i} — FFmpeg may have crashed")
                    write_ok = False
                    break
                except Exception as e:
                    print(f"[EncoderEngine] Frame write error at {i}: {e}")
                    write_ok = False
                    break

            # ── Signal end of input ──
            try:
                process.stdin.flush()
                process.stdin.close()
            except Exception:
                pass

            # ── Wait for FFmpeg to finish encoding ──
            try:
                process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                process.kill()
                print("[EncoderEngine] FFmpeg timed out")
                return None

            stderr_thread.join(timeout=5)

            # Check return code
            if process.returncode != 0:
                err = b"".join(stderr_lines).decode("utf-8", errors="replace")
                print(f"[EncoderEngine] FFmpeg error (code {process.returncode}):")
                print(err[-2000:])   # Print last 2000 chars of error
                return None

            if not write_ok:
                return None

            print(f"[EncoderEngine] FFmpeg finished OK → {output_path}")
            return output_path

        except Exception as e:
            print(f"[EncoderEngine] Subprocess error: {e}")
            return None


    # ─────────────────────────────────────────────────────────────
    # AUDIO TRIM — key A/V sync fix
    # ─────────────────────────────────────────────────────────────

    def _trim_audio_to_duration(self, audio_path: str, duration: float) -> str:
        """
        Trim WAV audio to exactly match video duration.

        Why this fixes sync:
        - Screen capture and audio capture start at slightly different times
        - Audio capture may have extra silence at start/end
        - Trimming audio to exact video duration keeps them aligned

        Args:
            audio_path: Path to WAV file
            duration:   Exact video duration in seconds

        Returns:
            str: Path to trimmed WAV (temp file)
        """
        import tempfile
        import wave

        try:
            # Read current audio duration
            with wave.open(audio_path, 'rb') as wf:
                frames     = wf.getnframes()
                rate       = wf.getframerate()
                channels   = wf.getnchannels()
                sampwidth  = wf.getsampwidth()
                audio_dur  = frames / rate

            print(f"[EncoderEngine] Audio duration: {audio_dur:.3f}s | Video duration: {duration:.3f}s")

            # If audio is already close enough (within 0.1s), skip trimming
            if abs(audio_dur - duration) < 0.1:
                print("[EncoderEngine] Audio/video durations match — no trim needed")
                return audio_path

            # Create trimmed audio temp file
            trimmed_path = audio_path.replace('.wav', '_trimmed.wav')

            # Use FFmpeg to trim audio to exact duration
            # -t duration: output exactly this many seconds
            # -af apad: pad with silence if audio is shorter than video
            cmd = [
                self._ffmpeg_path, "-y",
                "-i", audio_path,
                "-t", str(duration),          # Trim to exact video duration
                "-af", f"apad=whole_dur={duration}",  # Pad if too short
                trimmed_path
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=60)

            if result.returncode == 0 and os.path.exists(trimmed_path):
                print(f"[EncoderEngine] Audio trimmed to {duration:.3f}s")
                return trimmed_path
            else:
                print("[EncoderEngine] Audio trim failed, using original")
                return audio_path

        except Exception as e:
            print(f"[EncoderEngine] Audio trim error: {e}")
            return audio_path

    # ─────────────────────────────────────────────────────────────
    # THUMBNAIL GENERATION
    # ─────────────────────────────────────────────────────────────

    def _generate_thumbnail(self, first_frame: np.ndarray,
                             video_path: str) -> Optional[str]:
        """
        Generate a thumbnail image from the first frame of the recording.
        Saved as a JPEG next to the video file.
        Used by the clip library in the UI.

        Args:
            first_frame: First captured frame (numpy BGR)
            video_path: Path to the video (thumbnail saved alongside it)

        Returns:
            str: Path to thumbnail JPEG, or None if failed
        """
        try:
            # Derive thumbnail path from video path
            base = os.path.splitext(video_path)[0]
            thumb_path = base + "_thumb.jpg"

            # Resize to thumbnail dimensions
            thumb = cv2.resize(
                first_frame,
                (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT),
                interpolation=cv2.INTER_AREA    # Best quality for downscaling
            )

            # Save as JPEG (quality 85 = good balance of size vs quality)
            cv2.imwrite(thumb_path, thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
            print(f"[EncoderEngine] Thumbnail saved: {thumb_path}")
            return thumb_path

        except Exception as e:
            print(f"[EncoderEngine] Thumbnail error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────
    # EXPORT EXISTING CLIP (re-encode)
    # ─────────────────────────────────────────────────────────────

    def export_clip(self, input_path: str, output_path: str,
                    format: str = "mp4", quality: str = "high",
                    resolution: Optional[tuple] = None) -> dict:
        """
        Re-encode an existing video file to a different format/quality.
        Used by the editor's export button.

        Args:
            input_path: Source video file
            output_path: Destination file
            format: Target format
            quality: Target quality preset
            resolution: Optional (width, height) tuple to resize

        Returns:
            dict: {success, file_path, size_mb}
        """
        try:
            q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])

            # Build scale filter if resolution specified
            scale_filter = ""
            if resolution:
                w, h = resolution
                scale_filter = f"-vf scale={w}:{h}"

            # Choose encoder
            if self._nvenc_available:
                codec_args = ["-c:v", "h264_nvenc", "-cq", str(q["cq"])]
            else:
                codec_args = ["-c:v", "libx264", "-crf", str(q["crf"])]

            cmd = [
                self._ffmpeg_path, "-y",
                "-i", input_path,
                *codec_args,
                "-pix_fmt", "yuv420p",
                *(scale_filter.split() if scale_filter else []),
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]

            result = subprocess.run(
                cmd, capture_output=True,
                text=True, timeout=300
            )

            if result.returncode != 0:
                return {"success": False, "message": result.stderr}

            size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
            return {"success": True, "file_path": output_path, "size_mb": size_mb}

        except Exception as e:
            print(f"[EncoderEngine] Export error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────────────────────

    def is_encoding(self) -> bool:
        """Return True if currently encoding"""
        return self._is_encoding

    def get_supported_formats(self) -> list:
        """Return list of supported output formats"""
        return SUPPORTED_FORMATS

    def get_quality_presets(self) -> list:
        """Return list of quality preset names"""
        return list(QUALITY_PRESETS.keys())
