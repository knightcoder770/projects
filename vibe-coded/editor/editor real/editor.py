# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/editor.py
# Clip Editing Engine
#
# Responsibilities:
#   - Load video clips and extract metadata
#   - Trim clips to a start/end range
#   - Split a clip into two at a given timestamp
#   - Merge multiple clips into one
#   - Change playback speed (0.25x to 4x)
#   - Volume control, fade in/out
#   - Replace audio track entirely
#   - Add background music (BGM) mixed with existing audio
#   - All operations are non-destructive (output to new file)
#
# DSA Used:
#   - Linked list concept for timeline clip ordering
#     (Python list of clip dicts, supports insert/remove/reorder)
#   - Memoization for clip metadata (avoids re-reading same file)
#
# Tech:
#   - MoviePy for high-level editing (trim, merge, speed, audio)
#   - FFmpeg (subprocess) for operations MoviePy can't do well
#   - OpenCV for frame-level inspection and metadata extraction
#
# Non-destructive design:
#   - Every edit creates a NEW output file
#   - Original clip is NEVER modified
#   - This lets user undo by keeping original files
# ─────────────────────────────────────────────────────────────────

import os
import subprocess
import shutil
import platform
import tempfile
import time
from typing import Optional, List, Dict, Any

# ── MoviePy imports ──
# MoviePy uses FFmpeg under the hood for most operations
try:
    from moviepy.editor import (
        VideoFileClip,          # Load a video file
        concatenate_videoclips, # Merge multiple clips
        AudioFileClip,          # Load an audio file
        CompositeAudioClip,     # Mix multiple audio tracks
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("[EditorEngine] MoviePy not available — install with: pip install moviepy")

import cv2      # For metadata extraction and frame inspection


# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# Speed range limits
MIN_SPEED = 0.25    # Quarter speed (slow motion)
MAX_SPEED = 4.0     # 4x fast forward

# Volume range limits
MIN_VOLUME = 0.0    # Mute
MAX_VOLUME = 3.0    # 3x amplification (beyond this risks clipping)

# Supported input formats for loading clips
SUPPORTED_INPUT_FORMATS = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".gif"]


# ─────────────────────────────────────────────────────────────────
# EDITOR ENGINE CLASS
# ─────────────────────────────────────────────────────────────────

class EditorEngine:
    """
    Non-destructive clip editor.

    All methods take an input file path and write to a new output file.
    Original clips are never modified, enabling undo by keeping originals.

    Timeline management:
    - Uses a Python list as a linked-list-style timeline
    - Each entry is a dict with clip path + in/out points
    - Supports insert, remove, reorder operations
    """

    def __init__(self):
        # ── FFmpeg path (reuse from encoder if possible) ──
        self._ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"

        # ── Metadata cache (memoization) ──
        # Avoids re-reading the same file multiple times
        # Key: file path, Value: metadata dict
        self._metadata_cache: Dict[str, dict] = {}

        # ── Timeline ──
        # List of clip dicts: [{path, in_point, out_point, speed, volume}, ...]
        # This represents the current editing timeline
        self._timeline: List[Dict[str, Any]] = []

        print(f"[EditorEngine] Initialized | MoviePy: {MOVIEPY_AVAILABLE}")
        print(f"[EditorEngine] FFmpeg: {self._ffmpeg_path}")

    # ─────────────────────────────────────────────────────────────
    # LOAD CLIP
    # ─────────────────────────────────────────────────────────────

    def load_clip(self, clip_path: str) -> dict:
        """
        Load a video clip and extract its metadata.
        Metadata is cached to avoid repeated file reads (memoization).

        Args:
            clip_path (str): Full path to video file

        Returns:
            dict: {
                success, path, duration, fps,
                width, height, has_audio, file_size_mb
            }
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": f"File not found: {clip_path}"}

        # ── Check cache first (memoization) ──
        if clip_path in self._metadata_cache:
            print(f"[EditorEngine] Metadata from cache: {clip_path}")
            return {**self._metadata_cache[clip_path], "success": True}

        ext = os.path.splitext(clip_path)[1].lower()
        if ext not in SUPPORTED_INPUT_FORMATS:
            return {"success": False, "message": f"Unsupported format: {ext}"}

        try:
            # ── Read metadata via OpenCV ──
            cap = cv2.VideoCapture(clip_path)

            if not cap.isOpened():
                return {"success": False, "message": "Could not open video file"}

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            cap.release()

            # ── Check for audio track via FFmpeg ──
            has_audio = self._check_has_audio(clip_path)

            # ── File size ──
            size_mb = round(os.path.getsize(clip_path) / (1024 * 1024), 2)

            metadata = {
                "path": clip_path,
                "duration": round(duration, 3),
                "fps": round(fps, 2),
                "width": width,
                "height": height,
                "has_audio": has_audio,
                "file_size_mb": size_mb,
                "frame_count": frame_count
            }

            # ── Store in cache ──
            self._metadata_cache[clip_path] = metadata

            print(f"[EditorEngine] Loaded: {os.path.basename(clip_path)} | "
                  f"{width}x{height} @ {fps}fps | {duration:.1f}s | Audio: {has_audio}")

            return {**metadata, "success": True}

        except Exception as e:
            print(f"[EditorEngine] Load error: {e}")
            return {"success": False, "message": str(e)}

    def _check_has_audio(self, clip_path: str) -> bool:
        """
        Check if a video file has an audio track using FFmpeg.

        Args:
            clip_path: Path to video file

        Returns:
            bool: True if audio track exists
        """
        try:
            result = subprocess.run(
                [
                    self._ffmpeg_path, "-i", clip_path,
                    "-hide_banner"
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            # FFmpeg prints stream info to stderr
            # Audio streams show as "Stream #X:X: Audio:"
            return "Audio:" in result.stderr
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────
    # TRIM
    # ─────────────────────────────────────────────────────────────

    def trim(self, clip_path: str, start: float, end: float,
             output_path: Optional[str] = None) -> dict:
        """
        Trim a clip to the given start–end time range (in seconds).
        Uses FFmpeg stream copy for speed (no re-encoding needed for trim).

        Args:
            clip_path: Source video file
            start: Start time in seconds
            end: End time in seconds
            output_path: Optional output path, auto-generated if None

        Returns:
            dict: {success, output_path, duration}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source file not found"}

        if start < 0 or end <= start:
            return {"success": False, "message": f"Invalid range: {start}–{end}"}

        # Auto-generate output path if not provided
        if not output_path:
            output_path = self._make_output_path(clip_path, f"trim_{int(start)}_{int(end)}")

        try:
            duration = end - start

            # ── FFmpeg stream copy trim ──
            # -ss before -i = fast seek (key-frame accurate)
            # -t = duration to keep
            # -c copy = no re-encoding (instant, lossless)
            cmd = [
                self._ffmpeg_path, "-y",
                "-ss", str(start),          # Seek to start time
                "-i", clip_path,
                "-t", str(duration),        # Duration to keep
                "-c", "copy",               # Stream copy (no re-encode)
                "-avoid_negative_ts", "make_zero",  # Fix timestamps
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                print(f"[EditorEngine] Trim FFmpeg error: {result.stderr}")
                return {"success": False, "message": "Trim failed"}

            # Invalidate cache for output path
            self._metadata_cache.pop(output_path, None)

            print(f"[EditorEngine] Trimmed: {start}s–{end}s → {output_path}")
            return {
                "success": True,
                "output_path": output_path,
                "duration": round(duration, 3)
            }

        except Exception as e:
            print(f"[EditorEngine] Trim error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # SPLIT
    # ─────────────────────────────────────────────────────────────

    def split(self, clip_path: str, at_time: float) -> dict:
        """
        Split a clip into two parts at the given timestamp.
        Part A: 0 → at_time
        Part B: at_time → end

        Args:
            clip_path: Source video file
            at_time: Split point in seconds

        Returns:
            dict: {success, part_a_path, part_b_path}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source file not found"}

        # Get duration to validate split point
        meta = self.load_clip(clip_path)
        if not meta.get("success"):
            return {"success": False, "message": "Could not read clip metadata"}

        total_duration = meta["duration"]

        if at_time <= 0 or at_time >= total_duration:
            return {
                "success": False,
                "message": f"Split point {at_time}s out of range (0–{total_duration}s)"
            }

        # Generate output paths for both parts
        part_a_path = self._make_output_path(clip_path, "split_A")
        part_b_path = self._make_output_path(clip_path, "split_B")

        try:
            # ── Part A: 0 → at_time ──
            result_a = self.trim(clip_path, 0, at_time, part_a_path)
            if not result_a["success"]:
                return {"success": False, "message": "Split Part A failed"}

            # ── Part B: at_time → end ──
            result_b = self.trim(clip_path, at_time, total_duration, part_b_path)
            if not result_b["success"]:
                return {"success": False, "message": "Split Part B failed"}

            print(f"[EditorEngine] Split at {at_time}s → A: {part_a_path} | B: {part_b_path}")
            return {
                "success": True,
                "part_a_path": part_a_path,
                "part_b_path": part_b_path,
                "split_at": at_time
            }

        except Exception as e:
            print(f"[EditorEngine] Split error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # MERGE
    # ─────────────────────────────────────────────────────────────

    def merge(self, clip_paths: List[str], output_path: str) -> dict:
        """
        Merge multiple clips in order into a single output file.
        Uses FFmpeg concat demuxer for fast stream-copy merging.

        Args:
            clip_paths: List of video file paths in order
            output_path: Output file path

        Returns:
            dict: {success, output_path, total_duration}
        """
        if not clip_paths:
            return {"success": False, "message": "No clips provided"}

        if len(clip_paths) == 1:
            # Nothing to merge — just copy
            shutil.copy2(clip_paths[0], output_path)
            return {"success": True, "output_path": output_path}

        # Verify all files exist
        for path in clip_paths:
            if not os.path.exists(path):
                return {"success": False, "message": f"File not found: {path}"}

        try:
            # ── Create FFmpeg concat list file ──
            # FFmpeg concat demuxer requires a text file listing all clips
            # Format:
            #   file '/path/to/clip1.mp4'
            #   file '/path/to/clip2.mp4'
            concat_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt',
                delete=False, prefix='snapclip_concat_'
            )

            for path in clip_paths:
                # Escape single quotes in path (FFmpeg concat format)
                safe_path = path.replace("'", "'\\''")
                concat_file.write(f"file '{safe_path}'\n")
            concat_file.close()

            # ── FFmpeg concat ──
            cmd = [
                self._ffmpeg_path, "-y",
                "-f", "concat",             # Use concat demuxer
                "-safe", "0",               # Allow absolute paths
                "-i", concat_file.name,
                "-c", "copy",               # Stream copy (no re-encode)
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            # Clean up concat file
            os.remove(concat_file.name)

            if result.returncode != 0:
                print(f"[EditorEngine] Merge error: {result.stderr}")
                return {"success": False, "message": "Merge failed"}

            # Calculate total duration
            total_duration = sum(
                self.load_clip(p).get("duration", 0) for p in clip_paths
            )

            print(f"[EditorEngine] Merged {len(clip_paths)} clips → {output_path}")
            return {
                "success": True,
                "output_path": output_path,
                "total_duration": round(total_duration, 3),
                "clip_count": len(clip_paths)
            }

        except Exception as e:
            print(f"[EditorEngine] Merge error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # SPEED CONTROL
    # ─────────────────────────────────────────────────────────────

    def set_speed(self, clip_path: str, speed: float,
                  output_path: Optional[str] = None) -> dict:
        """
        Change the playback speed of a clip.
        Adjusts both video and audio to match.

        Args:
            clip_path: Source video file
            speed: Speed multiplier (0.25 = slow-mo, 4.0 = fast-forward)
            output_path: Optional output path

        FFmpeg filters used:
        - Video: setpts (presentation timestamp scaling)
          setpts=0.5*PTS → 2x speed (half the timestamps = twice as fast)
        - Audio: atempo (audio tempo change, range 0.5–2.0)
          For speed > 2x or < 0.5x, chain multiple atempo filters

        Returns:
            dict: {success, output_path, new_duration}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Source file not found"}

        # Clamp speed to valid range
        speed = max(MIN_SPEED, min(MAX_SPEED, speed))

        if not output_path:
            output_path = self._make_output_path(clip_path, f"speed_{speed}x")

        try:
            # ── Video filter: setpts ──
            # PTS = presentation timestamp
            # setpts = (1/speed) * PTS scales timestamps by inverse of speed
            video_pts = f"setpts={1.0/speed}*PTS"

            # ── Audio filter: atempo ──
            # atempo range is 0.5–2.0 only
            # For speeds outside this range, chain multiple atempo filters
            audio_filter = self._build_atempo_filter(speed)

            meta = self.load_clip(clip_path)
            has_audio = meta.get("has_audio", False)

            cmd = [
                self._ffmpeg_path, "-y",
                "-i", clip_path,
                "-filter:v", video_pts,
                # Only apply audio filter if clip has audio
                *([ "-filter:a", audio_filter] if has_audio else ["-an"]),
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"[EditorEngine] Speed error: {result.stderr}")
                return {"success": False, "message": "Speed change failed"}

            original_duration = meta.get("duration", 0)
            new_duration = original_duration / speed

            print(f"[EditorEngine] Speed {speed}x applied → {output_path}")
            return {
                "success": True,
                "output_path": output_path,
                "speed": speed,
                "new_duration": round(new_duration, 3)
            }

        except Exception as e:
            print(f"[EditorEngine] Speed error: {e}")
            return {"success": False, "message": str(e)}

    def _build_atempo_filter(self, speed: float) -> str:
        """
        Build an FFmpeg atempo filter chain for any speed value.

        atempo only works in range 0.5–2.0, so for values outside
        this range we chain multiple atempo filters.

        Examples:
        - speed=2.0 → "atempo=2.0"
        - speed=4.0 → "atempo=2.0,atempo=2.0"
        - speed=0.25 → "atempo=0.5,atempo=0.5"
        - speed=1.5 → "atempo=1.5"

        Args:
            speed: Target speed multiplier

        Returns:
            str: FFmpeg audio filter string
        """
        filters = []
        remaining = speed

        if speed > 1.0:
            # Fast forward: chain atempo=2.0 until remaining ≤ 2.0
            while remaining > 2.0:
                filters.append("atempo=2.0")
                remaining /= 2.0
            filters.append(f"atempo={remaining:.4f}")
        else:
            # Slow motion: chain atempo=0.5 until remaining ≥ 0.5
            while remaining < 0.5:
                filters.append("atempo=0.5")
                remaining /= 0.5
            filters.append(f"atempo={remaining:.4f}")

        return ",".join(filters)

    # ─────────────────────────────────────────────────────────────
    # VOLUME CONTROL
    # ─────────────────────────────────────────────────────────────

    def set_volume(self, clip_path: str, volume: float,
                   output_path: Optional[str] = None) -> dict:
        """
        Adjust the volume of a clip's audio track.

        Args:
            clip_path: Source video file
            volume: Volume multiplier (0.0=mute, 1.0=original, 2.0=double)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        volume = max(MIN_VOLUME, min(MAX_VOLUME, volume))

        if not output_path:
            output_path = self._make_output_path(clip_path, f"vol_{volume}")

        try:
            cmd = [
                self._ffmpeg_path, "-y",
                "-i", clip_path,
                "-c:v", "copy",             # Don't re-encode video
                "-filter:a", f"volume={volume}",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                return {"success": False, "message": "Volume adjustment failed"}

            print(f"[EditorEngine] Volume set to {volume}x → {output_path}")
            return {"success": True, "output_path": output_path, "volume": volume}

        except Exception as e:
            print(f"[EditorEngine] Volume error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # FADE AUDIO
    # ─────────────────────────────────────────────────────────────

    def fade_audio(self, clip_path: str, fade_in: float = 0.0,
                   fade_out: float = 0.0, output_path: Optional[str] = None) -> dict:
        """
        Apply fade-in and/or fade-out to audio.

        Args:
            clip_path: Source video
            fade_in: Duration of fade-in in seconds (0 = no fade in)
            fade_out: Duration of fade-out in seconds (0 = no fade out)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if not output_path:
            output_path = self._make_output_path(clip_path, "fade_audio")

        try:
            meta = self.load_clip(clip_path)
            duration = meta.get("duration", 0)

            # ── Build audio filter chain ──
            filters = []
            if fade_in > 0:
                # afade=t=in: type=in, st=start_time, d=duration
                filters.append(f"afade=t=in:st=0:d={fade_in}")
            if fade_out > 0:
                # Fade out starts at (total_duration - fade_out_duration)
                fade_out_start = max(0, duration - fade_out)
                filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")

            if not filters:
                return {"success": False, "message": "No fade specified"}

            audio_filter = ",".join(filters)

            cmd = [
                self._ffmpeg_path, "-y",
                "-i", clip_path,
                "-c:v", "copy",
                "-filter:a", audio_filter,
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                return {"success": False, "message": "Audio fade failed"}

            print(f"[EditorEngine] Audio fade applied (in:{fade_in}s out:{fade_out}s)")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            print(f"[EditorEngine] Fade error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # REPLACE AUDIO
    # ─────────────────────────────────────────────────────────────

    def replace_audio(self, clip_path: str, audio_path: str,
                      output_path: Optional[str] = None) -> dict:
        """
        Replace the audio track of a video with a new audio file.
        The video track is kept unchanged (stream copy).

        Args:
            clip_path: Source video file
            audio_path: New audio file (WAV, MP3, AAC, etc.)
            output_path: Optional output path

        Returns:
            dict: {success, output_path}
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Video file not found"}
        if not os.path.exists(audio_path):
            return {"success": False, "message": "Audio file not found"}

        if not output_path:
            output_path = self._make_output_path(clip_path, "replaced_audio")

        try:
            cmd = [
                self._ffmpeg_path, "-y",
                "-i", clip_path,            # Video source
                "-i", audio_path,           # New audio source
                "-c:v", "copy",             # Keep video unchanged
                "-c:a", "aac",              # Re-encode audio to AAC
                "-map", "0:v:0",            # Use video from first input
                "-map", "1:a:0",            # Use audio from second input
                "-shortest",                # End at shorter stream
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                return {"success": False, "message": "Audio replace failed"}

            print(f"[EditorEngine] Audio replaced → {output_path}")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            print(f"[EditorEngine] Replace audio error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # ADD BACKGROUND MUSIC
    # ─────────────────────────────────────────────────────────────

    def add_bgm(self, clip_path: str, music_path: str,
                volume: float = 0.3,
                video_volume: float = 1.0,
                bgm_start: float = 0.0,
                output_path: Optional[str] = None) -> dict:
        """
        Mix BGM into clip with independent volume control for both tracks.

        Args:
            clip_path:    Source video
            music_path:   BGM file (MP3, WAV, AAC, OGG, FLAC all work)
            volume:       BGM volume multiplier (0.0=silent, 0.3=30%, 1.0=full)
            video_volume: Video audio volume (1.0=original, 0.5=half, 0=mute)
            bgm_start:    Start BGM from this many seconds into the music file
            output_path:  Optional output path
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "Video file not found"}
        if not os.path.exists(music_path):
            return {"success": False, "message": "Music file not found"}

        if not output_path:
            output_path = self._make_output_path(clip_path, "with_bgm")

        try:
            audio_filter = (
                f"[0:a]volume={video_volume}[va];"
                f"[1:a]atrim=start={bgm_start},asetpts=PTS-STARTPTS,"
                f"volume={volume}[bgm];"
                f"[va][bgm]amix=inputs=2:duration=first:dropout_transition=1[aout]"
            )

            cmd = [
                self._ffmpeg_path, "-y",
                "-i", clip_path,
                "-i", music_path,
                "-c:v", "copy",
                "-filter_complex", audio_filter,
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"[EditorEngine] BGM error: {result.stderr[-300:]}")
                return {"success": False, "message": "BGM add failed"}

            print(f"[EditorEngine] BGM | video:{video_volume}x bgm:{volume}x "
                  f"bgm_start:{bgm_start}s → {output_path}")
            return {"success": True, "output_path": output_path}

        except Exception as e:
            print(f"[EditorEngine] BGM error: {e}")
            return {"success": False, "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # TIMELINE MANAGEMENT
    # ─────────────────────────────────────────────────────────────

    def add_to_timeline(self, clip_path: str, position: int = -1) -> dict:
        """
        Add a clip to the editing timeline at a given position.
        Default: append to end (-1).

        Timeline is a Python list acting as an ordered linked sequence.

        Args:
            clip_path: Path to video file
            position: Insert position (-1 = append to end)

        Returns:
            dict: {success, timeline_length}
        """
        meta = self.load_clip(clip_path)
        if not meta.get("success"):
            return {"success": False, "message": "Could not load clip"}

        entry = {
            "path": clip_path,
            "in_point": 0,                      # Start of clip
            "out_point": meta["duration"],       # End of clip
            "speed": 1.0,
            "volume": 1.0,
            "duration": meta["duration"]
        }

        if position == -1 or position >= len(self._timeline):
            self._timeline.append(entry)
        else:
            self._timeline.insert(max(0, position), entry)

        print(f"[EditorEngine] Timeline: added {os.path.basename(clip_path)} "
              f"at position {position} | Total: {len(self._timeline)}")

        return {"success": True, "timeline_length": len(self._timeline)}

    def remove_from_timeline(self, index: int) -> dict:
        """Remove a clip from the timeline by index"""
        if 0 <= index < len(self._timeline):
            removed = self._timeline.pop(index)
            print(f"[EditorEngine] Timeline: removed index {index}")
            return {"success": True, "removed": removed["path"]}
        return {"success": False, "message": "Invalid index"}

    def reorder_timeline(self, from_index: int, to_index: int) -> dict:
        """
        Move a clip from one timeline position to another.
        Supports drag-and-drop reordering from the UI.
        """
        if not (0 <= from_index < len(self._timeline)):
            return {"success": False, "message": "Invalid from_index"}
        if not (0 <= to_index < len(self._timeline)):
            return {"success": False, "message": "Invalid to_index"}

        # Remove from current position and insert at new position
        clip = self._timeline.pop(from_index)
        self._timeline.insert(to_index, clip)

        print(f"[EditorEngine] Timeline: moved {from_index} → {to_index}")
        return {"success": True}

    def get_timeline(self) -> list:
        """Return current timeline state for the UI"""
        return self._timeline

    def clear_timeline(self) -> dict:
        """Clear all clips from the timeline"""
        self._timeline.clear()
        return {"success": True}

    # ─────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────

    def _make_output_path(self, source_path: str, suffix: str) -> str:
        """
        Generate an output file path based on source path + suffix.
        Output is saved in the same directory as the source.

        Example:
            source: /clips/recording.mp4
            suffix: trim_5_15
            output: /clips/recording_trim_5_15.mp4
        """
        dir_name = os.path.dirname(source_path)
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        ext = os.path.splitext(source_path)[1]
        timestamp = int(time.time())    # Prevent overwriting on multiple edits
        return os.path.join(dir_name, f"{base_name}_{suffix}_{timestamp}{ext}")

    def clear_metadata_cache(self):
        """Clear the metadata memoization cache"""
        self._metadata_cache.clear()


    # ─────────────────────────────────────────────────────────────
    # STABILIZATION
    # ─────────────────────────────────────────────────────────────
    def stabilize(self, clip_path: str, smoothing: int = 10,
                  output_path: str = None) -> dict:
        """
        Video stabilization.
        Tries vidstab (2-pass, best quality) first.
        Falls back to deshake filter if vidstab not available.
        """
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "stabilized")
        import tempfile

        # ── Try vidstab first (best quality) ──
        trf = tempfile.mktemp(suffix='.trf')
        r1 = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-vf", f"vidstabdetect=stepsize=6:shakiness=8:accuracy=9:result={trf}",
            "-f", "null", "-"
        ], capture_output=True, timeout=300)

        if r1.returncode == 0:
            # vidstab pass 1 worked, do pass 2
            r2 = subprocess.run([
                self._ffmpeg_path, "-y", "-i", clip_path,
                "-vf", (f"vidstabtransform=input={trf}:smoothing={smoothing}:crop=black,"
                        f"scale=trunc(iw/2)*2:trunc(ih/2)*2"),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "copy", "-pix_fmt", "yuv420p", out
            ], capture_output=True, timeout=600)
            try: os.remove(trf)
            except: pass
            if r2.returncode == 0:
                print(f"[EditorEngine] Stabilized (vidstab) → {out}")
                return {"success": True, "output_path": out}

        # ── Fallback: deshake filter (built into all FFmpeg builds) ──
        try: os.remove(trf)
        except: pass

        print("[EditorEngine] vidstab not available, using deshake fallback")
        r3 = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-vf", (f"deshake=x=-1:y=-1:w=-1:h=-1:rx=16:ry=16:edge=mirror,"
                    f"scale=trunc(iw/2)*2:trunc(ih/2)*2"),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p", out
        ], capture_output=True, timeout=600)

        if r3.returncode == 0:
            print(f"[EditorEngine] Stabilized (deshake) → {out}")
            return {"success": True, "output_path": out,
                    "note": "Used deshake (basic). For better stabilization install FFmpeg with vidstab."}

        err = r3.stderr.decode('utf-8', errors='replace')
        return {"success": False, "message": f"Stabilize failed: {err[-200:]}"}

    # ─────────────────────────────────────────────────────────────
    # DENOISE
    # ─────────────────────────────────────────────────────────────
    def denoise(self, clip_path: str, strength: int = 5,
                output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "denoised")
        s = max(1, min(20, strength))
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-vf", f"pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2,hqdn3d={s}:{s}:{s*2}:{s*2},scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p", out
        ], capture_output=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": r.stderr.decode('utf-8', errors='replace')[-200:]}

    # ─────────────────────────────────────────────────────────────
    # SHARPEN
    # ─────────────────────────────────────────────────────────────
    def sharpen(self, clip_path: str, strength: float = 1.5,
                output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "sharp")
        s = max(0.1, min(5.0, strength))
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-vf", f"pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2,unsharp=5:5:{s}:5:5:{s*0.5}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p", out
        ], capture_output=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": "Sharpen failed"}

    # ─────────────────────────────────────────────────────────────
    # REVERSE
    # ─────────────────────────────────────────────────────────────
    def reverse_clip(self, clip_path: str, output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "reversed")
        has_audio = self._check_has_audio(clip_path)
        cmd = [self._ffmpeg_path, "-y", "-i", clip_path,
               "-vf", "reverse"]
        if has_audio:
            cmd += ["-af", "areverse",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", "yuv420p"]
        cmd.append(out)
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": r.stderr.decode('utf-8', errors='replace')[-200:]}

    # ─────────────────────────────────────────────────────────────
    # FREEZE FRAME
    # ─────────────────────────────────────────────────────────────
    def freeze_frame(self, clip_path: str,
                     at_time: float = 1.0,
                     freeze_duration: float = 2.0,
                     output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "freeze")
        import tempfile

        # Get fps
        meta = self.load_clip(clip_path)
        fps = meta.get("fps", 30.0) if meta else 30.0
        fps_str = f"{fps:.3f}"

        # Extract freeze frame
        freeze_img = tempfile.mktemp(suffix='.png')
        subprocess.run([
            self._ffmpeg_path, "-y", "-ss", str(at_time),
            "-i", clip_path, "-vframes", "1", freeze_img
        ], capture_output=True, timeout=30)

        if not os.path.exists(freeze_img):
            return {"success": False, "message": "Could not extract frame"}

        # Create parts
        before = tempfile.mktemp(suffix='.mp4')
        after  = tempfile.mktemp(suffix='.mp4')
        still  = tempfile.mktemp(suffix='.mp4')

        subprocess.run([self._ffmpeg_path, "-y", "-i", clip_path,
                        "-t", str(at_time), "-c", "copy", before],
                       capture_output=True, timeout=60)

        subprocess.run([self._ffmpeg_path, "-y", "-ss", str(at_time),
                        "-i", clip_path, "-c", "copy", after],
                       capture_output=True, timeout=60)

        subprocess.run([self._ffmpeg_path, "-y",
                        "-loop", "1", "-i", freeze_img,
                        "-t", str(freeze_duration),
                        "-vf", f"fps={fps_str},scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-an", still],
                       capture_output=True, timeout=60)

        # Concat
        concat_f = tempfile.mktemp(suffix='.txt')
        with open(concat_f, 'w') as f:
            f.write("file '" + before.replace("\\", "/") + "'\n")
            f.write("file '" + still.replace("\\", "/") + "'\n")
            f.write("file '" + after.replace("\\", "/") + "'\n")

        r = subprocess.run([
            self._ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_f,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-pix_fmt", "yuv420p", out
        ], capture_output=True, timeout=300)

        for f in [freeze_img, before, after, still, concat_f]:
            try:
                if os.path.exists(f): os.remove(f)
            except: pass

        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": r.stderr.decode('utf-8', errors='replace')[-200:]}

    # ─────────────────────────────────────────────────────────────
    # NOISE GATE
    # ─────────────────────────────────────────────────────────────
    def noise_gate(self, clip_path: str, threshold: float = 0.02,
                   output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "gated")
        t = max(0.001, min(0.5, threshold))
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-c:v", "copy",
            "-af", f"silenceremove=stop_periods=-1:stop_duration=0.1:stop_threshold={t}",
            "-c:a", "aac", "-b:a", "192k", out
        ], capture_output=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": "Noise gate failed"}

    # ─────────────────────────────────────────────────────────────
    # NORMALIZE AUDIO (EBU R128)
    # ─────────────────────────────────────────────────────────────
    def normalize_audio(self, clip_path: str, target_lufs: float = -16.0,
                        output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "normalized")
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-c:v", "copy",
            "-af", f"loudnorm=I={target_lufs}:LRA=7:TP=-2",
            "-c:a", "aac", "-b:a", "192k", out
        ], capture_output=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": "Normalize failed"}

    # ─────────────────────────────────────────────────────────────
    # CHROMA KEY
    # ─────────────────────────────────────────────────────────────
    def chroma_key(self, clip_path: str,
                   color: str = "green",
                   similarity: float = 0.3,
                   blend: float = 0.1,
                   output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, f"chromakey_{color}")
        color_val = "0x00FF00" if color == "green" else "0x0000FF"

        # Composite onto black background (most compatible)
        # filter_complex: chromakey → merge with black bg
        filter_complex = (
            f"[0:v]chromakey={color_val}:{similarity:.2f}:{blend:.2f},"
            f"pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2[ck];"
            f"color=c=black:s=ceil(iw/2)*2x ceil(ih/2)*2:rate=25[bg];"
            f"[bg][ck]overlay=shortest=1"
        )

        # Simpler approach: just apply chromakey as vf then fill with black
        vf = (
            f"chromakey={color_val}:{similarity:.2f}:{blend:.2f},"
            f"pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2"
        )
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p", out
        ], capture_output=True, timeout=600)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": r.stderr.decode('utf-8', errors='replace')[-300:]}

    # ─────────────────────────────────────────────────────────────
    # PICTURE IN PICTURE
    # ─────────────────────────────────────────────────────────────
    def picture_in_picture(self, main_clip: str,
                            overlay_clip: str,
                            position: str = "topright",
                            scale: float = 0.25,
                            output_path: str = None) -> dict:
        for p in [main_clip, overlay_clip]:
            if not os.path.exists(p):
                return {"success": False, "message": f"File not found: {p}"}
        out = output_path or self._make_output_path(main_clip, "pip")
        sc  = max(0.1, min(0.5, scale))
        pad = 20
        pos_map = {
            "topright":    f"W-w-{pad}:{pad}",
            "topleft":     f"{pad}:{pad}",
            "bottomright": f"W-w-{pad}:H-h-{pad}",
            "bottomleft":  f"{pad}:H-h-{pad}",
            "center":      "(W-w)/2:(H-h)/2",
        }
        overlay_pos = pos_map.get(position, pos_map["topright"])
        filter_complex = (
            f"[1:v]scale=iw*{sc}:-2,setsar=1[pip];"
            f"[0:v][pip]overlay={overlay_pos}"
        )
        r = subprocess.run([
            self._ffmpeg_path, "-y",
            "-i", main_clip, "-i", overlay_clip,
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p",
            "-shortest", out
        ], capture_output=True, timeout=600)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": r.stderr.decode('utf-8', errors='replace')[-300:]}

    # ─────────────────────────────────────────────────────────────
    # AUTO CUT SILENCE
    # ─────────────────────────────────────────────────────────────
    def auto_cut_silence(self, clip_path: str,
                          silence_thresh: float = -35.0,
                          min_silence: float = 0.5,
                          output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "autocut")
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-af", (f"silenceremove=start_periods=1:"
                    f"start_threshold={silence_thresh}dB:"
                    f"stop_periods=-1:"
                    f"stop_threshold={silence_thresh}dB:"
                    f"stop_duration={min_silence}"),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", out
        ], capture_output=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": r.stderr.decode('utf-8', errors='replace')[-200:]}

    # ─────────────────────────────────────────────────────────────
    # CROP REGION
    # ─────────────────────────────────────────────────────────────
    def crop_region(self, clip_path: str,
                    x: int, y: int, w: int, h: int,
                    output_path: str = None) -> dict:
        if not os.path.exists(clip_path):
            return {"success": False, "message": "File not found"}
        out = output_path or self._make_output_path(clip_path, "crop")
        w2 = w if w % 2 == 0 else w - 1
        h2 = h if h % 2 == 0 else h - 1
        r = subprocess.run([
            self._ffmpeg_path, "-y", "-i", clip_path,
            "-vf", f"crop={w2}:{h2}:{x}:{y}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p", out
        ], capture_output=True, timeout=300)
        if r.returncode == 0:
            return {"success": True, "output_path": out}
        return {"success": False, "message": "Crop failed"}
