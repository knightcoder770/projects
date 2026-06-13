# ─────────────────────────────────────────────────────────────────
# SnapClip - main.py
# Entry point
#
# Fixes:
#   - Encoding: checks FFmpeg exists, validates frames before encode
#   - Record overlay: floating Stop/Pause buttons on screen
#   - Region selector: minimize/restore window
#   - Browse: native OS save dialog
# ─────────────────────────────────────────────────────────────────

import webview
import sys
import os
import platform
import shutil
import tempfile
from urllib.parse import quote

from backend.capture  import CaptureEngine
from backend.vfx      import VFXEngine
from backend.audio    import AudioEngine
from backend.encoder  import EncoderEngine
from backend.editor   import EditorEngine
from backend.effects  import EffectsEngine
from backend.hotkeys  import HotkeyManager


# ─────────────────────────────────────────────────────────────────
# SNAPCLIP API
# ─────────────────────────────────────────────────────────────────
class SnapClipAPI:

    def __init__(self):
        self.capture  = CaptureEngine()
        self.audio    = AudioEngine()
        self.encoder  = EncoderEngine()
        self.editor   = EditorEngine()
        self.effects  = EffectsEngine()
        self.vfx      = VFXEngine()
        self.hotkeys  = HotkeyManager()

        self.is_recording   = False
        self.clips_library  = []
        self._record_overlay = None     # Floating record control bar

        print(f"[SnapClip] OS: {platform.system()} {platform.release()}")
        print(f"[SnapClip] FFmpeg: {shutil.which('ffmpeg') or 'NOT FOUND'}")

    # ─────────────────────────────────────────────────────────────
    # RECORDING
    # ─────────────────────────────────────────────────────────────

    def start_recording(self, region: dict, fps: int = 0, audio_mode: str = "both"):
        # Force reset stale state — prevents "already recording" after crashes
        if self.is_recording:
            # Check if capture is actually still running
            if not self.capture._is_capturing:
                print("[SnapClip] Stale recording flag detected — resetting")
                self.is_recording = False
            else:
                return {"success": False, "message": "Already recording"}
        try:
            self.capture.start(region=region, fps=fps)
            self.audio.start(mode=audio_mode)
            self.is_recording = True
            print(f"[SnapClip] Recording started | Region: {region} | Audio: {audio_mode}")
            return {"success": True, "message": "Recording started"}
        except Exception as e:
            print(f"[SnapClip] Start error: {e}")
            return {"success": False, "message": str(e)}

    def stop_recording(self):
        if not self.is_recording and not self.capture._is_capturing:
            return {"success": False, "message": "Not recording"}
        try:
            avi_path, fps, duration = self.capture.stop()
            audio_path = self.audio.stop()

            if self._record_overlay:
                try:
                    self._record_overlay.hide()
                except Exception:
                    pass
                self._record_overlay = None

            fc = self.capture.frame_count
            print(f"[SnapClip] Stopped | Frames: {fc} | FPS: {fps:.2f} | "
                  f"Duration: {duration:.2f}s | AVI: {avi_path}")
            return {
                "success":      True,
                "frames_count": fc,
                "fps":          fps,
                "duration":     duration,
                "avi_path":     avi_path,
                "audio_path":   audio_path
            }
        except Exception as e:
            print(f"[SnapClip] Stop error: {e}")
            return {"success": False, "message": str(e)}
        finally:
            # Always reset — no matter what
            self.is_recording = False
            print("[SnapClip] is_recording reset to False")

    def pause_recording(self):
        self.capture.pause()
        self.audio.pause()
        return {"success": True}

    def resume_recording(self):
        self.capture.resume()
        self.audio.resume()
        return {"success": True}

    # ─────────────────────────────────────────────────────────────
    # FLOATING RECORD OVERLAY
    # Shows Stop/Pause buttons on screen so user doesn't need app
    # ─────────────────────────────────────────────────────────────

    def show_record_overlay(self):
        """
        Show the floating record control bar on screen.
        Called after recording starts — user can control recording
        without switching back to the SnapClip window.
        """
        try:
            from backend.record_overlay import RecordOverlay

            def on_stop():
                """Called when user clicks Stop on the overlay"""
                import time
                print("[SnapClip] Overlay: Stop clicked")
                # Step 1: Stop recording (capture + audio)
                self.stop_recording()
                time.sleep(0.3)

                # Step 2: Restore window ONLY to show save modal
                # (window was minimized during recording so it doesn't appear in clip)
                try:
                    import ctypes
                    SW_RESTORE = 9
                    hwnd = ctypes.windll.user32.FindWindowW(None, "SnapClip")
                    if hwnd:
                        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        print("[SnapClip] Window restored via Win32")
                    else:
                        for win in webview.windows:
                            win.restore()
                except Exception as e:
                    print(f"[SnapClip] Win32 restore error: {e}")

                # Step 3: Trigger save modal in JS
                time.sleep(0.6)
                try:
                    for win in webview.windows:
                        win.evaluate_js("UI.openSaveModal(); UI.setRecordingUI(false);")
                    print("[SnapClip] Save modal triggered")
                except Exception as e:
                    print(f"[SnapClip] JS eval error: {e}")

            def on_pause():
                """Called when user clicks Pause on the overlay"""
                print("[SnapClip] Overlay: Pause clicked")
                if self.is_recording:
                    if self.capture.is_paused():
                        self.resume_recording()
                        try:
                            for win in webview.windows:
                                win.evaluate_js("UI.setPausedUI(false);")
                        except Exception:
                            pass
                    else:
                        self.pause_recording()
                        try:
                            for win in webview.windows:
                                win.evaluate_js("UI.setPausedUI(true);")
                        except Exception:
                            pass

            self._record_overlay = RecordOverlay(on_stop=on_stop, on_pause=on_pause)
            self._record_overlay.show()
            return {"success": True}

        except Exception as e:
            print(f"[SnapClip] Overlay error: {e}")
            return {"success": False, "message": str(e)}

    def hide_record_overlay(self):
        """Hide the floating record overlay"""
        if self._record_overlay:
            try:
                self._record_overlay.hide()
            except Exception:
                pass
            self._record_overlay = None
        return {"success": True}

    # ─────────────────────────────────────────────────────────────
    # SAVE / ENCODE
    # ─────────────────────────────────────────────────────────────

    def save_clip(self, save_path: str, format: str = "mp4", quality: str = "high"):
        """
        Encode captured frames to video file.
        Validates frames exist and FFmpeg is available before encoding.
        """
        try:
            # ── Validate FFmpeg ──
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                # Try common Windows locations
                common = [
                    r"C:\ffmpeg\bin\ffmpeg.exe",
                    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                    os.path.join(os.environ.get("USERPROFILE",""), "ffmpeg","bin","ffmpeg.exe")
                ]
                for p in common:
                    if os.path.exists(p):
                        ffmpeg_path = p
                        break

                if not ffmpeg_path:
                    return {
                        "success": False,
                        "message": "FFmpeg not found! Install it:\n"
                                   "1. Download from https://ffmpeg.org/download.html\n"
                                   "2. Extract to C:\\ffmpeg\n"
                                   "3. Add C:\\ffmpeg\\bin to System PATH\n"
                                   "4. Restart SnapClip"
                    }

            # ── Use AVI file from disk (no RAM frames) ──
            avi_path = self.capture.get_temp_avi()
            if not avi_path or not os.path.exists(avi_path):
                return {"success": False, "message": "No recording found. Record first!"}
            if os.path.getsize(avi_path) < 1000:
                return {"success": False, "message": "Recording is empty. Try again."}

            # ── Validate save path ──
            save_dir = os.path.dirname(os.path.abspath(save_path))
            if not os.path.exists(save_dir):
                try:
                    os.makedirs(save_dir, exist_ok=True)
                except Exception as e:
                    return {"success": False, "message": f"Cannot create directory: {e}"}

            fps      = self.capture.detected_fps or 30.0
            duration = self.capture.total_duration or 0
            fc       = self.capture.frame_count

            print(f"[SnapClip] Encoding {fc} frames @ {fps:.2f}fps → {save_path}")

            # ── Validate audio WAV ──
            audio_path = self.audio.get_audio_path()
            if audio_path and os.path.exists(audio_path):
                if os.path.getsize(audio_path) < 100:
                    print("[SnapClip] Audio WAV empty — video only")
                    audio_path = None
                else:
                    print(f"[SnapClip] Audio: {os.path.getsize(audio_path)/1024:.0f}KB")
            else:
                audio_path = None

            # ── Encode AVI + Audio → final MP4 in background ──
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.encoder.encode_from_avi,
                    avi_path,
                    audio_path,
                    save_path,
                    format,
                    quality,
                    fps,
                    duration
                )
                result = future.result(timeout=3600)  # Up to 1hr for long recordings

            if result and result.get("success"):
                self.clips_library.append({
                    "path":      save_path,
                    "name":      os.path.basename(save_path),
                    "duration":  result.get("duration"),
                    "size_mb":   result.get("size_mb"),
                    "thumbnail": result.get("thumbnail")
                })
                print(f"[SnapClip] Saved: {save_path} ({result.get('size_mb')}MB)")

            return result

        except Exception as e:
            print(f"[SnapClip] Save error: {e}")
            return {"success": False, "message": str(e)}

        finally:
            # ── Always reset recording state ──
            # Even if encoding fails, user must be able to record again
            self.is_recording = False
            print("[SnapClip] Recording state reset")

    def export_clip(self, input_path, output_path,
                    format="mp4", quality="high", resolution=None):
        return self.encoder.export_clip(input_path, output_path, format, quality, resolution)

    # ─────────────────────────────────────────────────────────────
    # LIBRARY
    # ─────────────────────────────────────────────────────────────

    def get_clips_library(self):
        return self.clips_library

    def load_clip_to_editor(self, clip_path: str):
        return self.editor.load_clip(clip_path)

    def remove_clip_from_library(self, clip_path: str):
        self.clips_library = [c for c in self.clips_library if c["path"] != clip_path]
        return {"success": True}

    # ─────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────

    def trim_clip(self, clip_path, start, end):
        return self.editor.trim(clip_path, start, end)

    def split_clip(self, clip_path, at_time):
        return self.editor.split(clip_path, at_time)

    def merge_clips(self, clip_paths, output_path):
        return self.editor.merge(clip_paths, output_path)

    def set_clip_speed(self, clip_path, speed):
        return self.editor.set_speed(clip_path, speed)

    def set_volume(self, clip_path, volume):
        return self.editor.set_volume(clip_path, volume)

    def add_background_music(self, clip_path, music_path, volume=0.3):
        return self.editor.add_bgm(clip_path, music_path, volume)

    def mix_audio_levels(self, clip_path: str,
                          video_volume: float = 1.0,
                          bgm_path: str = None,
                          bgm_volume: float = 0.3,
                          bgm_start: float = 0.0) -> dict:
        """
        Advanced audio mixing — control video audio and BGM volumes
        independently, with optional BGM start time offset.

        Args:
            clip_path:    Source video
            video_volume: Original audio volume (0.0-2.0, 1.0=original)
            bgm_path:     Path to BGM file (None = just adjust video volume)
            bgm_volume:   BGM volume (0.0-1.0)
            bgm_start:    When BGM starts in seconds (0 = from beginning)
        """
        import shutil as sh
        ffmpeg = sh.which("ffmpeg") or "ffmpeg"
        import subprocess, os, time

        out = os.path.splitext(clip_path)[0] + f"_mix_{int(time.time())}.mp4"

        try:
            if bgm_path and os.path.exists(bgm_path):
                # Mix video audio + BGM with independent volume controls
                # adelay: delay BGM start by bgm_start seconds
                delay_ms = int(bgm_start * 1000)
                # Scale each stream volume independently
                # then mix using amix with normalize=0
                filter_complex = (
                    f"[0:a]volume={video_volume:.3f}[va];"
                    f"[1:a]volume={bgm_volume:.3f},"
                    f"adelay={delay_ms}|{delay_ms},"
                    f"apad=whole_dur=1[bgma];"
                    f"[va][bgma]amix=inputs=2:duration=first:"
                    f"dropout_transition=2:normalize=0[outa]"
                )
                cmd = [
                    ffmpeg, "-y",
                    "-i", clip_path,
                    "-i", bgm_path,
                    "-filter_complex", filter_complex,
                    "-map", "0:v:0",
                    "-map", "[outa]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    out
                ]
            else:
                # Just adjust video volume
                cmd = [
                    ffmpeg, "-y",
                    "-i", clip_path,
                    "-af", f"volume={video_volume}",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    out
                ]

            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode == 0:
                print(f"[SnapClip] Audio mix → {out}")
                return {"success": True, "output_path": out}
            else:
                err = result.stderr.decode('utf-8', errors='replace')
                return {"success": False, "message": err[-400:]}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def replace_audio(self, clip_path, audio_path):
        return self.editor.replace_audio(clip_path, audio_path)

    def fade_audio(self, clip_path, fade_in=0.0, fade_out=0.0):
        return self.editor.fade_audio(clip_path, fade_in, fade_out)

    # ─────────────────────────────────────────────────────────────
    # EFFECTS
    # ─────────────────────────────────────────────────────────────

    def apply_filter(self, clip_path, filter_name, intensity=1.0):
        return self.effects.apply(clip_path, filter_name, intensity)

    def add_text_overlay(self, clip_path, text, position,
                          font_size=32, color="#ffffff",
                          start_time=0, end_time=None):
        return self.effects.add_text(clip_path, text, position,
                                     font_size, color, start_time, end_time)

    def add_watermark(self, clip_path, watermark_path, position="bottomright"):
        return self.effects.add_watermark(clip_path, watermark_path, position)

    def apply_lut(self, clip_path: str, lut_name: str):
        """Apply a color grade LUT preset"""
        return self.effects.apply_lut(clip_path, lut_name)

    def apply_color_grade(self, clip_path: str, brightness=0.0, contrast=1.0,
                           saturation=1.0, gamma=1.0, hue=0.0,
                           shadows=0.0, highlights=0.0):
        """Apply combined color grade in single FFmpeg pass"""
        return self.effects.apply_color_grade(
            clip_path, brightness, contrast, saturation,
            gamma, hue, shadows, highlights
        )

    def apply_aspect_ratio(self, clip_path: str, ratio: str):
        """Crop video to aspect ratio (16:9, 9:16, 1:1, 4:5, 4:3, 21:9)"""
        return self.effects.apply_aspect_ratio(clip_path, ratio)

    # ─────────────────────────────────────────────────────────────
    # TIMELINE
    # ─────────────────────────────────────────────────────────────


    # ── VFX ────────────────────────────────────────────────────────
    def apply_vfx(self, effect: str, clip_path: str, kwargs: dict = None):
        """Dispatch VFX effect by name. kwargs as dict for pywebview."""
        fn = getattr(self.vfx, effect, None)
        if fn is None:
            return {"success": False, "message": f"Unknown VFX: {effect}"}
        try:
            kw = dict(kwargs) if kwargs else {}
            kw.pop('clip_path', None)
            print(f"[VFX] {effect}({clip_path}, {kw})")
            return fn(clip_path, **kw)
        except Exception as e:
            print(f"[VFX] Error in {effect}: {e}")
            return {"success": False, "message": str(e)}

    def apply_transition(self, effect: str, clip_a: str, clip_b: str, kwargs: dict = None):
        """Apply VFX transition between two clips."""
        fn = getattr(self.vfx, effect, None)
        if fn is None:
            return {"success": False, "message": f"Unknown transition: {effect}"}
        try:
            kw = dict(kwargs) if kwargs else {}
            print(f"[VFX] {effect}({clip_a}, {clip_b}, {kw})")
            return fn(clip_a, clip_b, **kw)
        except Exception as e:
            print(f"[VFX] Transition error: {e}")
            return {"success": False, "message": str(e)}

    def get_vfx_list(self):
        """Return all available VFX effects."""
        return self.vfx.get_available_effects()

    # ── New Premiere Pro features ──────────────────────────────────
    def stabilize_clip(self, clip_path, smoothing=10):
        return self.editor.stabilize(clip_path, smoothing)

    def denoise_clip(self, clip_path, strength=5):
        return self.editor.denoise(clip_path, strength)

    def sharpen_clip(self, clip_path, strength=1.5):
        return self.editor.sharpen(clip_path, strength)

    def reverse_clip(self, clip_path):
        return self.editor.reverse_clip(clip_path)

    def freeze_frame(self, clip_path, at_time=1.0, freeze_duration=2.0):
        return self.editor.freeze_frame(clip_path, at_time, freeze_duration)

    def noise_gate(self, clip_path, threshold=0.02):
        return self.editor.noise_gate(clip_path, threshold)

    def normalize_audio(self, clip_path, target_lufs=-16.0):
        return self.editor.normalize_audio(clip_path, target_lufs)

    def chroma_key(self, clip_path, color="green", similarity=0.3, blend=0.1):
        return self.editor.chroma_key(clip_path, color, similarity, blend)

    def picture_in_picture(self, main_clip, overlay_clip,
                            position="topright", scale=0.25):
        return self.editor.picture_in_picture(
            main_clip, overlay_clip, position, scale)

    def crop_region(self, clip_path, x, y, w, h):
        return self.editor.crop_region(clip_path, x, y, w, h)

    def auto_cut_silence(self, clip_path, silence_thresh=-35.0, min_silence=0.5):
        return self.editor.auto_cut_silence(clip_path, silence_thresh, min_silence)

    def add_to_timeline(self, clip_path):
        return self.editor.add_to_timeline(clip_path)

    def remove_from_timeline(self, index):
        return self.editor.remove_from_timeline(index)

    def reorder_timeline(self, from_index, to_index):
        return self.editor.reorder_timeline(from_index, to_index)

    def clear_timeline(self):
        return self.editor.clear_timeline()

    # ─────────────────────────────────────────────────────────────
    # SYSTEM
    # ─────────────────────────────────────────────────────────────

    def get_system_info(self):
        import psutil
        return {
            "cpu_percent":  psutil.cpu_percent(),
            "ram_used_gb":  round(psutil.virtual_memory().used  / (1024**3), 2),
            "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "platform":     platform.system(),
            "gpu":          "RTX 3050 (NVENC)"
        }

    def get_screens(self):
        from screeninfo import get_monitors
        return [
            {"index": i, "width": m.width, "height": m.height,
             "x": m.x, "y": m.y, "name": m.name or f"Monitor {i+1}"}
            for i, m in enumerate(get_monitors())
        ]

    def register_hotkeys(self, hotkey_map: dict):
        return self.hotkeys.register(hotkey_map)

    # ─────────────────────────────────────────────────────────────
    # WINDOW CONTROLS
    # ─────────────────────────────────────────────────────────────

    def minimize_window(self):
        """Minimize using pywebview + Win32 fallback"""
        import time
        try:
            # Try pywebview first
            for win in webview.windows:
                win.minimize()
            time.sleep(0.1)
        except Exception:
            pass

        # Win32 fallback for Windows — more reliable
        try:
            import ctypes
            import ctypes.wintypes as wt
            SW_MINIMIZE = 6
            hwnd = ctypes.windll.user32.FindWindowW(None, "SnapClip")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
        except Exception as e:
            print(f"[SnapClip] Win32 minimize error: {e}")

        return {"success": True}

    def restore_window(self):
        """Restore using pywebview + Win32 fallback"""
        import time
        try:
            for win in webview.windows:
                win.restore()
            time.sleep(0.1)
        except Exception:
            pass

        # Win32 fallback
        try:
            import ctypes
            SW_RESTORE = 9
            hwnd = ctypes.windll.user32.FindWindowW(None, "SnapClip")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"[SnapClip] Win32 restore error: {e}")

        return {"success": True}

    # ─────────────────────────────────────────────────────────────
    # REGION SELECTOR
    # ─────────────────────────────────────────────────────────────

    def open_region_selector(self):
        """Open fullscreen tkinter overlay for region selection"""
        try:
            from backend.region_selector import RegionSelector
            selector = RegionSelector()
            region   = selector.select()
            if region:
                print(f"[SnapClip] Region: {region}")
                return {"success": True, **region}
            else:
                return {"success": False, "message": "Cancelled"}
        except Exception as e:
            print(f"[SnapClip] Region selector error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # NATIVE FILE DIALOGS
    # ─────────────────────────────────────────────────────────────

    def open_file_dialog(self, file_types_label: str = "Audio") -> dict:
        """
        Open OS native file picker dialog.
        Used for selecting BGM, audio files, watermark images etc.
        """
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            if file_types_label == "Audio":
                ftypes = [
                    ("Audio Files", "*.mp3 *.wav *.aac *.ogg *.flac *.m4a"),
                    ("MP3", "*.mp3"),
                    ("WAV", "*.wav"),
                    ("All Files", "*.*"),
                ]
            elif file_types_label == "Image":
                ftypes = [
                    ("Image Files", "*.png *.jpg *.jpeg *.webp"),
                    ("All Files", "*.*"),
                ]
            elif file_types_label == "Video":
                ftypes = [
                    ("Video Files", "*.mp4 *.mkv *.avi *.mov *.webm"),
                    ("All Files", "*.*"),
                ]
            else:
                ftypes = [("All Files", "*.*")]

            path = filedialog.askopenfilename(
                title=f"Select {file_types_label} File",
                filetypes=ftypes
            )
            root.destroy()

            if path:
                return {"success": True, "path": path}
            return {"success": False, "message": "Cancelled"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def open_save_dialog(self, default_name: str = "snapclip.mp4") -> dict:
        """Open OS native Save File dialog"""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            # Determine file type from extension
            ext = os.path.splitext(default_name)[1].lower() or ".mp4"
            file_types = [
                ("MP4 Video",  "*.mp4"),
                ("MKV Video",  "*.mkv"),
                ("GIF Image",  "*.gif"),
                ("All Files",  "*.*"),
            ]

            # Default to Videos folder
            initial_dir = os.path.join(os.path.expanduser("~"), "Videos")
            if not os.path.exists(initial_dir):
                initial_dir = os.path.expanduser("~")

            save_path = filedialog.asksaveasfilename(
                title            = "Save SnapClip Recording",
                defaultextension = ext,
                initialfile      = default_name,
                initialdir       = initial_dir,
                filetypes        = file_types,
            )

            root.destroy()

            if save_path:
                print(f"[SnapClip] Save path: {save_path}")
                return {"success": True, "path": save_path}
            else:
                return {"success": False, "message": "Cancelled"}

        except Exception as e:
            print(f"[SnapClip] Save dialog error: {e}")
            return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # -- Check FFmpeg on startup --
    ffmpeg = shutil.which("ffmpeg")

    # Check common install locations even if not in PATH
    if not ffmpeg:
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.join(os.environ.get("USERPROFILE", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        ]
        for p in common_paths:
            if os.path.exists(p):
                ffmpeg = p
                bin_dir = os.path.dirname(p)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                print(f"[SnapClip] FFmpeg found at: {p}")
                break

    if not ffmpeg:
        print("=" * 60)
        print("FFmpeg NOT FOUND — please install it:")
        print("1. Download ffmpeg-master-latest-win64-gpl.zip from:")
        print("   https://github.com/BtbN/FFmpeg-Builds/releases")
        print("2. Extract and rename folder to ffmpeg")
        print("3. Move to C:\ffmpeg")
        print("4. Add C:\ffmpeg\bin to Windows PATH")
        print("5. Restart terminal and run: python main.py")
        print("=" * 60)

    # ── Resolve HTML path ──
    base_dir  = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "frontend", "index.html")

    if not os.path.exists(html_path):
        print(f"[SnapClip] ERROR: index.html not found at {html_path}")
        sys.exit(1)

    # ── Build file:// URL (handle Windows spaces in path) ──
    html_fwd = html_path.replace("\\", "/")
    encoded  = quote(html_fwd, safe=":/#")
    file_url = f"file:///{encoded}"

    print(f"[SnapClip] URL: {file_url}")

    # ── Create API + window ──
    api = SnapClipAPI()

    window = webview.create_window(
        title            = "SnapClip",
        url              = file_url,
        js_api           = api,
        width            = 1280,
        height           = 780,
        min_size         = (900, 600),
        resizable        = True,
        background_color = "#0a0a0f",
    )

    def on_loaded():
        """Inject keyboard shortcuts after page loads"""
        import time
        time.sleep(1.5)  # Wait for JS modules to initialize
        for win in webview.windows:
            try:
                win.evaluate_js("""
(function() {
    // Remove any existing listener first
    if (window._snapclipKeyHandler) {
        window.removeEventListener('keydown', window._snapclipKeyHandler, true);
    }

    window._snapclipKeyHandler = function(e) {
        // Skip if typing in input
        var tag = document.activeElement ? document.activeElement.tagName : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

        if (e.key === 'i' || e.key === 'I') {
            e.preventDefault();
            e.stopPropagation();
            if (typeof SnapClip !== 'undefined') SnapClip.setIn();
            return false;
        }
        if (e.key === 'o' || e.key === 'O') {
            e.preventDefault();
            e.stopPropagation();
            if (typeof SnapClip !== 'undefined') SnapClip.setOut();
            return false;
        }
        if (e.key === ' ') {
            e.preventDefault();
            if (typeof Player !== 'undefined') Player.togglePlayPause();
            return false;
        }
        if (e.key === 'ArrowLeft' && !e.shiftKey) {
            e.preventDefault();
            var v = document.getElementById('preview-video');
            if (v) v.currentTime = Math.max(0, v.currentTime - 0.033);
        }
        if (e.key === 'ArrowRight' && !e.shiftKey) {
            e.preventDefault();
            var v = document.getElementById('preview-video');
            if (v) v.currentTime = Math.min(v.duration||999, v.currentTime + 0.033);
        }
        if (e.key === 'ArrowLeft' && e.shiftKey) {
            e.preventDefault();
            var v = document.getElementById('preview-video');
            if (v) v.currentTime = Math.max(0, v.currentTime - 5);
        }
        if (e.key === 'ArrowRight' && e.shiftKey) {
            e.preventDefault();
            var v = document.getElementById('preview-video');
            if (v) v.currentTime = Math.min(v.duration||999, v.currentTime + 5);
        }
    };

    // capture=true fires BEFORE browser handles the event
    window.addEventListener('keydown', window._snapclipKeyHandler, true);
    document.addEventListener('keydown', window._snapclipKeyHandler, true);
    console.log('[SnapClip] Keyboard shortcuts injected');
})();
""")
                print("[SnapClip] Keyboard shortcuts injected")
            except Exception as e:
                print(f"[SnapClip] Keyboard inject error: {e}")

    import threading
    t = threading.Thread(target=on_loaded, daemon=True)
    t.start()

    print("[SnapClip] Starting...")
    webview.start(debug=True)
