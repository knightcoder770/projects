# ─────────────────────────────────────────────────────────────────
# SnapClip - backend/__init__.py
# Backend package initializer
#
# Makes the backend/ directory a Python package so modules
# can be imported as: from backend.capture import CaptureEngine
# ─────────────────────────────────────────────────────────────────

# ── Version info ──
__version__ = "1.0.0"
__app_name__ = "SnapClip"

# ── Expose main engines for convenience imports ──
# This lets main.py do: from backend import CaptureEngine
# instead of: from backend.capture import CaptureEngine
from backend.capture  import CaptureEngine
from backend.audio    import AudioEngine
from backend.encoder  import EncoderEngine
from backend.editor   import EditorEngine
from backend.effects  import EffectsEngine
from backend.hotkeys  import HotkeyManager

__all__ = [
    "CaptureEngine",
    "AudioEngine",
    "EncoderEngine",
    "EditorEngine",
    "EffectsEngine",
    "HotkeyManager",
]
