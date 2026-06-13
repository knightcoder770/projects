# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/audio.py
# Audio Capture Engine — Simple & Reliable
#
# Strategy:
#   1. Try soundcard WASAPI loopback (system audio, no mic noise)
#   2. If that fails, scan PyAudio devices for Stereo Mix / loopback
#   3. If that fails, use the default mic (at least record something)
#
# Key fixes for correct audio playback:
#   - Detect device's actual native sample rate
#   - Write WAV header with the ACTUAL rate used (not assumed 44100)
#   - Use mono (1 channel) — works on all devices
#   - This prevents fast/chipmunk audio caused by rate mismatch
# ─────────────────────────────────────────────────────────────────

import os
import wave
import threading
import tempfile
import platform
from typing import Optional

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    pyaudio = None

try:
    import soundcard as sc
    import numpy as np
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    sc  = None
    np  = None

# ── Default constants (may be overridden by device detection) ──
DEFAULT_RATE   = 44100
CHUNK_SIZE     = 1024
FORMAT_WIDTH   = 2      # 16-bit = 2 bytes


class AudioEngine:

    def __init__(self):
        self._os          = platform.system()
        self._pa          = None
        self._thread      = None
        self._is_running  = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start unpaused
        self._lock        = threading.Lock()
        self._chunks      = []       # Raw audio bytes captured
        self._wav_path    = None

        # Actual values discovered at stream-open time
        self._rate     = DEFAULT_RATE
        self._channels = 1

        # Init PyAudio
        if PYAUDIO_AVAILABLE:
            try:
                self._pa = pyaudio.PyAudio()
            except Exception as e:
                print(f"[AudioEngine] PyAudio init error: {e}")

        print(f"[AudioEngine] Initialized | OS: {self._os} | "
              f"soundcard: {SOUNDCARD_AVAILABLE} | pyaudio: {PYAUDIO_AVAILABLE}")

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def start(self, mode: str = "system"):
        """Start audio capture. mode: system | mic | both | none"""
        if self._is_running:
            return

        self._mode       = mode
        self._is_running = True
        self._chunks.clear()
        self._pause_event.set()

        # Create temp WAV path
        tmp = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, prefix="snapclip_audio_"
        )
        self._wav_path = tmp.name
        tmp.close()

        if mode == "none":
            return

        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="SnapClip-Audio"
        )
        self._thread.start()
        print(f"[AudioEngine] Started | Mode: {mode}")

    def stop(self) -> Optional[str]:
        """Stop capture and write WAV. Returns WAV path."""
        self._is_running = False
        self._pause_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        if self._mode == "none":
            return None

        self._write_wav()
        return self._wav_path

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def get_audio_path(self) -> Optional[str]:
        return self._wav_path

    # ─────────────────────────────────────────────────────────────
    # CAPTURE LOOP — runs in background thread
    # ─────────────────────────────────────────────────────────────

    def _capture_loop(self):
        """
        Try audio sources in order until one works.
        Priority: soundcard loopback → PyAudio loopback → default mic
        """
        captured = False

        # ── 1. Try soundcard WASAPI loopback ──
        if SOUNDCARD_AVAILABLE and self._os == "Windows" and self._mode in ("system", "both"):
            captured = self._try_soundcard_loopback()

        # ── 2. Try PyAudio Stereo Mix / loopback ──
        if not captured and PYAUDIO_AVAILABLE and self._os == "Windows" and self._mode in ("system", "both"):
            captured = self._try_pyaudio_loopback()

        # ── 3. Fallback: default mic ──
        # ONLY use mic if mode explicitly includes mic
        # In "system" mode — if loopback fails, record SILENCE not mic
        # This prevents fan/vehicle noise from appearing in system-only recordings
        if not captured:
            if self._mode in ("mic", "both"):
                # User wants mic — capture it
                captured = self._try_default_mic()
            elif self._mode == "system":
                # System audio failed — warn user but don't use mic
                print("[AudioEngine] ⚠ System audio (loopback) not available!")
                print("[AudioEngine] Recording video without audio.")
                print("[AudioEngine] To fix: Enable 'Stereo Mix' in Windows:")
                print("[AudioEngine]   Right-click speaker → Sound Settings")
                print("[AudioEngine]   → More sound settings → Recording tab")
                print("[AudioEngine]   → Right-click empty area → Show Disabled Devices")
                print("[AudioEngine]   → Right-click Stereo Mix → Enable → Set as Default")

        if not captured:
            print("[AudioEngine] No audio captured")

    # ─────────────────────────────────────────────────────────────
    # METHOD 1: soundcard WASAPI loopback
    # ─────────────────────────────────────────────────────────────

    def _try_soundcard_loopback(self) -> bool:
        """
        Try soundcard WASAPI loopback.
        The 'fromstring' error in older soundcard versions is caught per-chunk.
        Uses frombuffer instead which is the correct numpy API.
        """
        try:
            # Get ALL loopback devices and pick the best one
            # When Bluetooth is active, the loopback device changes
            # so we try ALL available loopbacks, not just default speaker
            loopback = None
            all_loopbacks = []

            try:
                mics = sc.all_microphones(include_loopback=True)
                for m in mics:
                    if hasattr(m, 'isloopback') and m.isloopback:
                        all_loopbacks.append(m)
                        print(f"[AudioEngine] Loopback found: {m.name}")
            except Exception as e:
                print(f"[AudioEngine] sc.all_microphones error: {e}")

            if all_loopbacks:
                # Try to match current default speaker (works for BT too)
                try:
                    default_spk = sc.default_speaker()
                    print(f"[AudioEngine] Default speaker: {default_spk.name}")
                    for lb in all_loopbacks:
                        if lb.name == default_spk.name or                            default_spk.name in lb.name or                            lb.name in default_spk.name:
                            loopback = lb
                            print(f"[AudioEngine] Matched loopback to default: {lb.name}")
                            break
                except Exception:
                    pass
                # If no match, just use the first available loopback
                if not loopback:
                    loopback = all_loopbacks[0]
                    print(f"[AudioEngine] Using first loopback: {loopback.name}")

            # Last attempt: get_microphone with default speaker id
            if not loopback:
                try:
                    default_spk = sc.default_speaker()
                    loopback = sc.get_microphone(
                        default_spk.id, include_loopback=True
                    )
                    print(f"[AudioEngine] Got loopback by ID: {loopback.name}")
                except Exception as e:
                    print(f"[AudioEngine] get_microphone failed: {e}")

            if not loopback:
                print("[AudioEngine] No soundcard loopback found")
                return False

            # Try recording a test chunk first to validate the device
            rate = 48000   # Use 48000 — most WASAPI devices prefer this
            try:
                with loopback.recorder(
                    samplerate=rate, channels=1, blocksize=CHUNK_SIZE
                ) as rec:
                    test = rec.record(numframes=CHUNK_SIZE)
                    # If we get here without error, device works
            except Exception as e:
                print(f"[AudioEngine] soundcard test failed: {e}")
                # Try 44100
                try:
                    rate = 44100
                    with loopback.recorder(
                        samplerate=rate, channels=1, blocksize=CHUNK_SIZE
                    ) as rec:
                        test = rec.record(numframes=CHUNK_SIZE)
                except Exception as e2:
                    print(f"[AudioEngine] soundcard 44100 also failed: {e2}")
                    return False

            # Main capture loop
            self._rate     = rate
            self._channels = 1
            print(f"[AudioEngine] soundcard loopback capturing @ {rate}Hz")

            with loopback.recorder(
                samplerate=rate, channels=1, blocksize=CHUNK_SIZE
            ) as rec:
                while self._is_running:
                    self._pause_event.wait()
                    try:
                        chunk = rec.record(numframes=CHUNK_SIZE)
                        # Handle both 1D and 2D arrays
                        if hasattr(chunk, 'ndim'):
                            if chunk.ndim > 1:
                                chunk = chunk[:, 0]
                            chunk = np.clip(chunk, -1.0, 1.0)
                            data  = (chunk * 32767).astype(np.int16).tobytes()
                        else:
                            # Already bytes
                            data = bytes(chunk)
                        with self._lock:
                            self._chunks.append(data)
                    except Exception as chunk_err:
                        print(f"[AudioEngine] chunk error: {chunk_err}")
                        break   # Stop on chunk error, don't silently fail

            captured = len(self._chunks) > 0
            print(f"[AudioEngine] soundcard captured {len(self._chunks)} chunks")
            return captured

        except Exception as e:
            print(f"[AudioEngine] soundcard loopback failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # METHOD 2: PyAudio Stereo Mix / loopback device
    # ─────────────────────────────────────────────────────────────

    def _try_pyaudio_loopback(self) -> bool:
        """Scan PyAudio devices for Stereo Mix or loopback. Returns True if captured."""
        if not self._pa:
            return False

        LOOPBACK_NAMES = [
            "stereo mix", "what u hear", "loopback",
            "wave out mix", "mix", "output",
            "bluetooth",   # BT loopback devices on some systems
            "realtek",     # Realtek with Stereo Mix enabled
        ]

        print("[AudioEngine] Scanning PyAudio devices for loopback...")
        loopback_idx  = None
        loopback_info = None
        count = self._pa.get_device_count()

        for i in range(count):
            try:
                info = self._pa.get_device_info_by_index(i)
                name = info.get("name", "").lower()
                ch   = int(info.get("maxInputChannels", 0))
                print(f"[AudioEngine]   [{i}] {info.get('name')} | inputs:{ch}")
                if ch > 0 and any(kw in name for kw in LOOPBACK_NAMES):
                    # Test at multiple rates
                    for test_rate in [48000, 44100]:
                        try:
                            test = self._pa.open(
                                format=pyaudio.paInt16,
                                channels=1,
                                rate=test_rate,
                                input=True,
                                input_device_index=i,
                                frames_per_buffer=CHUNK_SIZE
                            )
                            test.close()
                            loopback_idx  = i
                            loopback_info = info
                            print(f"[AudioEngine] Loopback OK: [{i}] {info.get('name')} @ {test_rate}Hz")
                            break
                        except Exception:
                            continue
                if loopback_idx is not None:
                    break
            except Exception:
                continue

        if loopback_idx is None:
            print("[AudioEngine] No working loopback device found")
            print("[AudioEngine] To enable system audio recording:")
            print("[AudioEngine]   1. Right-click speaker → Sound Settings")
            print("[AudioEngine]   2. More sound settings → Recording tab")
            print("[AudioEngine]   3. Right-click → Show Disabled Devices")
            print("[AudioEngine]   4. Right-click 'Stereo Mix' → Enable → Set as Default")
            return False

        # Open and capture
        return self._capture_pyaudio(loopback_idx, loopback_info)

    # ─────────────────────────────────────────────────────────────
    # METHOD 3: Default microphone
    # ─────────────────────────────────────────────────────────────

    def _try_default_mic(self) -> bool:
        """Use default system microphone. Returns True if captured."""
        if not self._pa:
            return False

        print("[AudioEngine] Using default mic (no system loopback available)")

        # Find default input device
        try:
            default_info = self._pa.get_default_input_device_info()
            dev_idx      = int(default_info.get('index', 0))
        except Exception:
            dev_idx = None

        if dev_idx is None:
            # Find first available input
            for i in range(self._pa.get_device_count()):
                info = self._pa.get_device_info_by_index(i)
                if info.get('maxInputChannels', 0) > 0:
                    dev_idx = i
                    break

        if dev_idx is None:
            print("[AudioEngine] No input device found")
            return False

        info = self._pa.get_device_info_by_index(dev_idx)
        print(f"[AudioEngine] Default mic: [{dev_idx}] {info.get('name')}")

        return self._capture_pyaudio(dev_idx, info)

    # ─────────────────────────────────────────────────────────────
    # PyAudio capture helper
    # ─────────────────────────────────────────────────────────────

    def _capture_pyaudio(self, dev_idx: int, dev_info: dict) -> bool:
        """
        Open PyAudio stream and capture.
        Tries device native rate first to avoid pitch/speed issues.
        Returns True if data was captured.
        """
        if not self._pa:
            return False

        # Try rates in priority order — native rate first
        native_rate = int(dev_info.get('defaultSampleRate', DEFAULT_RATE))
        rates_to_try = list(dict.fromkeys([native_rate, 48000, 44100, 16000]))

        stream    = None
        used_rate = native_rate

        for rate in rates_to_try:
            try:
                stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,           # Always mono — most compatible
                    rate=rate,
                    input=True,
                    input_device_index=dev_idx,
                    frames_per_buffer=CHUNK_SIZE
                )
                used_rate = rate
                print(f"[AudioEngine] Stream open: {rate}Hz mono | device [{dev_idx}]")
                break
            except Exception as e:
                print(f"[AudioEngine] Rate {rate}Hz failed: {e}")
                continue

        if not stream:
            print(f"[AudioEngine] Could not open stream on device [{dev_idx}]")
            return False

        # Store actual values for WAV header
        self._rate     = used_rate
        self._channels = 1

        # Capture loop
        while self._is_running:
            self._pause_event.wait()
            try:
                chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                with self._lock:
                    self._chunks.append(chunk)
            except Exception:
                continue

        stream.stop_stream()
        stream.close()

        return len(self._chunks) > 0

    # ─────────────────────────────────────────────────────────────
    # WAV WRITER
    # ─────────────────────────────────────────────────────────────

    def _write_wav(self):
        """Write captured audio chunks to WAV file."""
        with self._lock:
            chunks = list(self._chunks)

        if not chunks:
            print("[AudioEngine] No audio data captured")
            # Write a silent WAV so encoder doesn't crash
            self._write_silent_wav()
            return

        try:
            with wave.open(self._wav_path, 'wb') as wf:
                wf.setnchannels(self._channels)
                wf.setsampwidth(FORMAT_WIDTH)
                wf.setframerate(self._rate)
                for chunk in chunks:
                    wf.writeframes(chunk)

            size_kb = os.path.getsize(self._wav_path) / 1024
            print(f"[AudioEngine] WAV saved: {size_kb:.0f}KB | "
                  f"{len(chunks)} chunks | {self._rate}Hz {self._channels}ch")
            print(f"[AudioEngine] Path: {self._wav_path}")

        except Exception as e:
            print(f"[AudioEngine] WAV write error: {e}")
            self._write_silent_wav()

    def _write_silent_wav(self):
        """Write a 1-second silent WAV as fallback so encoder can proceed."""
        try:
            samples = DEFAULT_RATE  # 1 second of silence
            silence = b'\x00' * samples * FORMAT_WIDTH
            with wave.open(self._wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(FORMAT_WIDTH)
                wf.setframerate(DEFAULT_RATE)
                wf.writeframes(silence)
            print("[AudioEngine] Silent WAV written as fallback")
        except Exception as e:
            print(f"[AudioEngine] Silent WAV error: {e}")

    # ─────────────────────────────────────────────────────────────
    # LINUX AUDIO (PulseAudio monitor)
    # ─────────────────────────────────────────────────────────────

    def _try_linux_monitor(self) -> bool:
        """Linux PulseAudio monitor source for system audio."""
        if not self._pa:
            return False
        try:
            # Find monitor device
            monitor_idx = None
            for i in range(self._pa.get_device_count()):
                info = self._pa.get_device_info_by_index(i)
                name = info.get("name", "").lower()
                if "monitor" in name and info.get("maxInputChannels", 0) > 0:
                    monitor_idx = i
                    break

            if monitor_idx is None:
                return False

            info = self._pa.get_device_info_by_index(monitor_idx)
            return self._capture_pyaudio(monitor_idx, info)

        except Exception as e:
            print(f"[AudioEngine] Linux monitor error: {e}")
            return False
