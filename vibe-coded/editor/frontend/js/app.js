// ═══════════════════════════════════════════════════════════════
// SnapClip - frontend/js/app.js
// Main Application JavaScript
//
// Fixes in this version:
//   - openCropOverlay: actually minimizes window, opens tkinter
//     overlay, then restores window after selection
//   - browseSavePath: opens real OS native Save File dialog
//   - browseExportPath: opens real OS native Save File dialog
// ═══════════════════════════════════════════════════════════════

'use strict';

// ─────────────────────────────────────────────────────────────
// APP STATE
// ─────────────────────────────────────────────────────────────
const AppState = {
  isRecording:      false,
  isPaused:         false,
  selectedRegion:   null,
  selectedClipPath: null,
  currentFormat:    'mp4',
  currentQuality:   'high',
  exportFormat:     'mp4',
  exportQuality:    'high',
  recStartTime:     null,
  recTimerInterval: null,
  statusInterval:   null,
  zoomLevel:        1,
  playbackSpeed:    1,
  isMuted:          false,
};


// ─────────────────────────────────────────────────────────────
// API — pywebview Bridge Wrapper
// ─────────────────────────────────────────────────────────────
const API = {

  waitForReady() {
    return new Promise((resolve) => {
      if (window.pywebview && window.pywebview.api) { resolve(); return; }
      const check = setInterval(() => {
        if (window.pywebview && window.pywebview.api) {
          clearInterval(check); resolve();
        }
      }, 100);
      setTimeout(() => {
        clearInterval(check);
        console.error('[API] pywebview not available after 10s');
        resolve();
      }, 10000);
    });
  },

  async call(method, ...args) {
    if (!window.pywebview || !window.pywebview.api) {
      console.warn('[API] pywebview not ready — skipping: ' + method);
      return { success: true, _mock: true };
    }
    try {
      const fn = window.pywebview.api[method];
      if (typeof fn !== 'function') throw new Error('Method not found: ' + method);
      const result = await fn(...args);
      console.log('[API] ' + method + '()', result);
      return result;
    } catch (err) {
      console.error('[API] Error calling ' + method + '():', err);
      UI.toast('Error: ' + (err.message || err), 'error');
      return { success: false, message: String(err) };
    }
  }
};


// ─────────────────────────────────────────────────────────────
// UI — DOM Utilities, Modals, Toasts, Tabs
// ─────────────────────────────────────────────────────────────
const UI = {

  openModal(id) {
    const el = document.getElementById(id);
    if (el) {
      el.classList.remove('hidden');
      const firstBtn = el.querySelector('button, input, select');
      if (firstBtn) firstBtn.focus();
    }
  },

  closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  },

  openSaveModal() {
    const defaultName = 'snapclip_' + Date.now() + '.' + AppState.currentFormat;
    document.getElementById('save-path-input').value = defaultName;
    this.openModal('modal-save');
  },

  openExportModal() {
    if (!AppState.selectedClipPath) {
      UI.toast('No clip selected to export', 'error'); return;
    }
    this.openModal('modal-export');
  },

  openTextModal() {
    if (!AppState.selectedClipPath) {
      UI.toast('Load a clip first to add text overlay', 'error'); return;
    }
    this.openModal('modal-text');
  },

  switchSidebarTab(tab) {
    document.querySelectorAll('.tab-content').forEach(el => { el.style.display = 'none'; });
    document.querySelectorAll('.sidebar-tab').forEach(el => { el.classList.remove('active'); });
    const tabContent = document.getElementById('tab-' + tab);
    if (tabContent) tabContent.style.display = 'flex';
    const tabBtn = document.querySelector('.sidebar-tab[data-tab="' + tab + '"]');
    if (tabBtn) tabBtn.classList.add('active');
  },

  toast(message, type, duration) {
    type     = type     || 'info';
    duration = duration || 3000;
    const container = document.getElementById('toast-container');
    if (!container) return;
    const icons = { success: '✓', error: '✕', info: 'ℹ' };
    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<span class="toast-icon">' + (icons[type] || 'ℹ') + '</span><span>' + message + '</span>';
    container.appendChild(toast);
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(function() { toast.remove(); }, 300);
    }, duration);
  },

  setStatus(text, type) {
    type = type || 'ok';
    const dot        = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    if (statusText) statusText.textContent = text;
    if (dot) {
      dot.className = 'status-dot';
      if (type === 'warn')  dot.classList.add('warn');
      if (type === 'error') dot.classList.add('error');
    }
  },

  setRecordingUI(recording) {
    const btnStart = document.getElementById('btn-start-record');
    const btnPause = document.getElementById('btn-pause-record');
    const btnStop  = document.getElementById('btn-stop-record');
    const recDot   = document.getElementById('rec-dot');
    const recTimer = document.getElementById('rec-timer');
    if (recording) {
      btnStart.classList.add('hidden');
      btnPause.classList.remove('hidden');
      btnStop.classList.remove('hidden');
      recDot.classList.add('visible');
      recTimer.classList.add('visible');
      UI.setStatus('Recording...', 'warn');
    } else {
      btnStart.classList.remove('hidden');
      btnPause.classList.add('hidden');
      btnStop.classList.add('hidden');
      recDot.classList.remove('visible');
      recTimer.classList.remove('visible');
      UI.setStatus('Ready');
    }
  },

  setPausedUI(paused) {
    const btnPause = document.getElementById('btn-pause-record');
    if (btnPause) btnPause.textContent = paused ? 'Resume' : 'Pause';
    UI.setStatus(paused ? 'Paused' : 'Recording...', paused ? 'ok' : 'warn');
  },

  updateBadges(width, height, fps) {
    const res      = document.getElementById('badge-resolution');
    const fpsBadge = document.getElementById('badge-fps');
    const topFps   = document.getElementById('fps-badge');
    if (res)      res.textContent      = width + 'x' + height;
    if (fpsBadge) fpsBadge.textContent = fps + ' fps';
    if (topFps)   topFps.textContent   = fps + ' FPS';
  }
};


// ─────────────────────────────────────────────────────────────
// SETTINGS
// ─────────────────────────────────────────────────────────────
const Settings = {

  defaults: {
    audioMode:        'system',   // Default: system audio only (no mic = no outside noise)
    noiseSuppression: false,
    monitor:          0,
    countdown:        true,
    highlightCursor:  false,
    hwAccel:          true,
  },

  load() {
    const saved  = JSON.parse(localStorage.getItem('snapclip_settings') || '{}');
    const merged = Object.assign({}, this.defaults, saved);
    const audioMode = document.getElementById('setting-audio-mode');
    if (audioMode) audioMode.value = merged.audioMode;
    const noiseSuppress = document.getElementById('setting-noise-suppress');
    if (noiseSuppress) noiseSuppress.checked = merged.noiseSuppression;
    const countdown = document.getElementById('setting-countdown');
    if (countdown) countdown.checked = merged.countdown;
    const hwAccel = document.getElementById('setting-hw-accel');
    if (hwAccel) hwAccel.checked = merged.hwAccel;
    return merged;
  },

  set(key, value) {
    const saved = JSON.parse(localStorage.getItem('snapclip_settings') || '{}');
    saved[key]  = value;
    localStorage.setItem('snapclip_settings', JSON.stringify(saved));
  },

  get(key) {
    const saved = JSON.parse(localStorage.getItem('snapclip_settings') || '{}');
    return key in saved ? saved[key] : this.defaults[key];
  },

  async resetHotkeys() {
    await API.call('register_hotkeys', {
      start_recording: 'ctrl+shift+r',
      stop_recording:  'ctrl+shift+s',
      pause_recording: 'ctrl+shift+p',
      screenshot:      'ctrl+shift+x',
      open_editor:     'ctrl+shift+e',
    });
    UI.toast('Hotkeys reset to defaults', 'success');
  }
};


// ─────────────────────────────────────────────────────────────
// CAPTURE — Screen recording flow
// ─────────────────────────────────────────────────────────────
const Capture = {

  // ── Open region selector ──
  // Minimizes SnapClip, opens fullscreen Python tkinter overlay,
  // then restores window. Works over ANY app on screen.

  async openCropOverlay() {
    UI.setStatus('Opening region selector...');
    UI.toast('Minimizing — draw a region anywhere on your screen!', 'info', 2000);
    console.log('[Capture] Opening Python tkinter region selector');

    // Step 1: Minimize SnapClip window so screen is visible
    await API.call('minimize_window');

    // Wait for window to fully minimize before overlay appears
    await new Promise(function(r) { setTimeout(r, 800); });

    // Step 2: Open fullscreen transparent tkinter overlay
    // This BLOCKS until user draws a region or presses Escape
    var result = await API.call('open_region_selector');

    // Step 3: Restore SnapClip window
    await API.call('restore_window');

    // Step 4: Handle result
    if (result && result.success) {
      AppState.selectedRegion = {
        x:      result.x,
        y:      result.y,
        width:  result.width,
        height: result.height
      };
      UI.updateBadges(result.width, result.height, '--');
      UI.toast('Region selected: ' + result.width + 'x' + result.height, 'success', 4000);
      UI.setStatus('Region ' + result.width + 'x' + result.height + ' — Ready to record');
      console.log('[Capture] Region confirmed:', AppState.selectedRegion);
    } else {
      UI.setStatus('Ready');
      UI.toast('Selection cancelled', 'info');
    }
  },

  // Stubs kept for HTML button compatibility
  closeCropOverlay() { UI.setStatus('Ready'); },
  confirmRegion()    { UI.toast('Region confirmed!', 'success'); },
  _onDragStart()     {},
  _onDragMove()      {},
  _onDragEnd()       {},

  // ── Fullscreen capture ──

  async setFullscreen() {
    var monitorIdx = parseInt(Settings.get('monitor') || 0);
    var result = await API.call('get_screens');
    if (result && result[monitorIdx]) {
      var m = result[monitorIdx];
      AppState.selectedRegion = { x: m.x, y: m.y, width: m.width, height: m.height };
      UI.toast('Fullscreen: ' + m.width + 'x' + m.height, 'success');
      UI.updateBadges(m.width, m.height, '--');
      UI.setStatus('Fullscreen ' + m.width + 'x' + m.height + ' — Ready to record');
    } else {
      AppState.selectedRegion = { x: 0, y: 0, width: screen.width, height: screen.height };
      UI.toast('Fullscreen: ' + screen.width + 'x' + screen.height, 'success');
    }
  },

  // ── Start recording ──

  async startRecording() {
    if (AppState.isRecording) { UI.toast('Already recording!', 'error'); return; }

    if (!AppState.selectedRegion) {
      UI.toast('Select a screen region first!', 'error');
      Capture.openCropOverlay();
      return;
    }

    if (Settings.get('countdown')) {
      await Capture._showCountdown(3);
    }

    var audioMode = Settings.get('audioMode') || 'both';
    var result    = await API.call('start_recording', AppState.selectedRegion, 0, audioMode);

    if (result && result.success) {
      AppState.isRecording  = true;
      AppState.isPaused     = false;
      AppState.recStartTime = Date.now();
      Capture._startTimer();
      UI.setRecordingUI(true);
      UI.toast('Recording! Use the floating bar to Stop/Pause.', 'success', 4000);

      // Step 1: Minimize SnapClip FIRST so it does not appear in the recording
      await API.call('minimize_window');

      // Step 2: Small delay to ensure window is fully minimized
      await new Promise(function(r) { setTimeout(r, 500); });

      // Step 3: Show floating Stop/Pause bar on screen
      await API.call('show_record_overlay');
    } else {
      UI.toast('Failed to start: ' + (result && result.message ? result.message : 'Unknown error'), 'error');
    }
  },

  // ── Stop recording ──

  async stopRecording() {
    if (!AppState.isRecording) return;
    Capture._stopTimer();

    var result = await API.call('stop_recording');

    if (result && result.success) {
      AppState.isRecording = false;
      AppState.isPaused    = false;
      if (result.fps) {
        var topFps = document.getElementById('fps-badge');
        if (topFps) topFps.textContent = result.fps.toFixed(1) + ' FPS';
      }
      UI.setRecordingUI(false);
      UI.toast('Captured ' + result.frames_count + ' frames at ' + (result.fps ? result.fps.toFixed(1) : '--') + 'fps', 'success');
      UI.openSaveModal();
    } else {
      UI.toast('Stop failed: ' + (result && result.message ? result.message : 'Unknown error'), 'error');
      AppState.isRecording = false;
      UI.setRecordingUI(false);
    }
  },

  // ── Pause / Resume ──

  async togglePause() {
    if (!AppState.isRecording) return;
    if (AppState.isPaused) {
      await API.call('resume_recording');
      AppState.isPaused = false;
      Capture._resumeTimer();
      UI.setPausedUI(false);
      UI.toast('Resumed', 'info');
    } else {
      await API.call('pause_recording');
      AppState.isPaused = true;
      Capture._pauseTimer();
      UI.setPausedUI(true);
      UI.toast('Paused', 'info');
    }
  },

  // ── Timer ──

  _timerPausedAt:    0,
  _timerPausedTotal: 0,

  _startTimer() {
    Capture._timerPausedTotal = 0;
    AppState.recTimerInterval = setInterval(function() {
      if (AppState.isPaused) return;
      var elapsed = Date.now() - AppState.recStartTime - Capture._timerPausedTotal;
      var el = document.getElementById('rec-timer');
      if (el) el.textContent = Capture._formatTime(elapsed);
    }, 500);
  },

  _stopTimer() {
    clearInterval(AppState.recTimerInterval);
    AppState.recTimerInterval = null;
    var el = document.getElementById('rec-timer');
    if (el) el.textContent = '00:00:00';
  },

  _pauseTimer()  { Capture._timerPausedAt = Date.now(); },

  _resumeTimer() {
    if (Capture._timerPausedAt) {
      Capture._timerPausedTotal += Date.now() - Capture._timerPausedAt;
      Capture._timerPausedAt = 0;
    }
  },

  _formatTime(ms) {
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    return [h, m, s].map(function(n) { return String(n).padStart(2, '0'); }).join(':');
  },

  // ── Countdown ──

  _showCountdown(seconds) {
    return new Promise(function(resolve) {
      var el = document.createElement('div');
      el.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:500',
        'display:flex', 'align-items:center', 'justify-content:center',
        'background:rgba(0,0,0,0.5)', 'backdrop-filter:blur(4px)',
        'font-size:120px', 'font-weight:900', 'color:white', 'pointer-events:none'
      ].join(';');
      document.body.appendChild(el);
      var count = seconds;
      el.textContent = count;
      var interval = setInterval(function() {
        count--;
        if (count <= 0) {
          clearInterval(interval);
          el.remove();
          resolve();
        } else {
          el.textContent = count;
        }
      }, 1000);
    });
  }
};


// ─────────────────────────────────────────────────────────────
// PLAYER — Video playback controls
// ─────────────────────────────────────────────────────────────
const Player = {

  get video() { return document.getElementById('preview-video'); },

  togglePlayPause() {
    var v = this.video;
    if (!v || v.style.display === 'none') return;
    var btn = document.getElementById('btn-play-pause');
    if (v.paused) { v.play();  if (btn) btn.textContent = 'Pause'; }
    else          { v.pause(); if (btn) btn.textContent = 'Play';  }
  },

  stop() {
    var v = this.video;
    if (!v) return;
    v.pause(); v.currentTime = 0;
    var btn = document.getElementById('btn-play-pause');
    if (btn) btn.textContent = 'Play';
  },

  seekToClick(event) {
    var v = this.video;
    if (!v || !v.duration) return;
    var track = document.getElementById('progress-track');
    var rect  = track.getBoundingClientRect();
    var ratio = (event.clientX - rect.left) / rect.width;
    v.currentTime = ratio * v.duration;
  },

  updateProgress() {
    var v = this.video;
    if (!v || !v.duration) return;
    var ratio   = v.currentTime / v.duration;
    var pct     = ratio * 100;
    var fill    = document.getElementById('progress-fill');
    var thumb   = document.getElementById('progress-thumb');
    var display = document.getElementById('time-display');
    if (fill)    fill.style.width  = pct + '%';
    if (thumb)   thumb.style.left  = pct + '%';
    if (display) display.textContent = Player._fmtTime(v.currentTime) + ' / ' + Player._fmtTime(v.duration);
  },

  _fmtTime(sec) {
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return m + ':' + String(s).padStart(2, '0');
  },

  setVolume(val) {
    var v = this.video;
    if (v) v.volume = val / 100;
    var label = document.getElementById('val-volume');
    if (label) label.textContent = Math.round(val) + '%';
  },

  toggleMute() {
    var v = this.video;
    if (!v) return;
    AppState.isMuted = !AppState.isMuted;
    v.muted = AppState.isMuted;
    var btn = document.getElementById('btn-mute');
    if (btn) btn.textContent = AppState.isMuted ? 'Unmute' : 'Mute';
  },

  setSpeed(val) {
    var v = this.video;
    if (v) v.playbackRate = parseFloat(val);
    AppState.playbackSpeed = parseFloat(val);
  },

  skipToStart() { var v = this.video; if (v) v.currentTime = 0; },
  skipToEnd()   { var v = this.video; if (v && v.duration) v.currentTime = v.duration; },

  loadClip(clipPath) {
    var v           = this.video;
    var placeholder = document.getElementById('preview-placeholder');
    if (!v) return;
    v.style.display = 'block';
    if (placeholder) placeholder.style.display = 'none';
    // Build proper file URL for Windows paths
    var src = clipPath.replace(/\\/g, '/');
    if (!src.startsWith('file://')) src = 'file:///' + src;
    v.src = src;
    v.load();
    v.ontimeupdate = function() {
      Player.updateProgress();
      if (typeof Timeline !== 'undefined') Timeline.syncPlayhead(v.currentTime);
    };
    v.onloadedmetadata = function() {
      // Show clip in timeline
      if (typeof Timeline !== 'undefined') {
        Timeline._activeDuration = v.duration || 0;
        var name = clipPath.split('\\').pop().split('/').pop();
        // Add to timeline if not already there
        if (Timeline._clips && !Timeline._clips.find(function(c){ return c.path === clipPath; })) {
          Timeline.addClip({ path: clipPath, name: name, duration: v.duration || 0 });
        }
        if (Timeline._render) Timeline._render();
      }
    };
    AppState.selectedClipPath = clipPath;
    console.log('[Player] Loaded:', clipPath);
  }
};


// ─────────────────────────────────────────────────────────────
// EFFECTS — Filters, text, watermark
// ─────────────────────────────────────────────────────────────
const Effects = {

  _sliderValues: { brightness: 0, contrast: 1, saturation: 1 },

  async applyFilter(filterName) {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    UI.setStatus('Applying ' + filterName + '...');
    var result = await API.call('apply_filter', AppState.selectedClipPath, filterName, 1.0);
    if (result && result.success) {
      UI.toast(filterName + ' applied!', 'success');
      Player.loadClip(result.output_path);
      Library.refreshClipMeta(result.output_path);
    } else {
      UI.toast('Filter failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  updateSlider(param, value) {
    this._sliderValues[param] = parseFloat(value);
    var label = document.getElementById('val-' + param);
    if (label) label.textContent = parseFloat(value).toFixed(2);
    clearTimeout(this['_' + param + 'Timeout']);
    var self = this;
    this['_' + param + 'Timeout'] = setTimeout(function() {
      self._applyEqFilter(param, parseFloat(value));
    }, 600);
  },

  async _applyEqFilter(param, value) {
    if (!AppState.selectedClipPath) return;
    UI.setStatus('Adjusting ' + param + '...');
    var result = await API.call('apply_filter', AppState.selectedClipPath, param, value);
    if (result && result.success) Player.loadClip(result.output_path);
    UI.setStatus('Ready');
  },

  resetFilters() {
    var defaults = { brightness: 0, contrast: 1, saturation: 1 };
    for (var key in defaults) {
      var label = document.getElementById('val-' + key);
      if (label) label.textContent = defaults[key];
    }
    UI.toast('Filters reset', 'info');
  },

  async applyTextOverlay() {
    var text      = document.getElementById('text-overlay-input') && document.getElementById('text-overlay-input').value.trim();
    var position  = document.getElementById('text-position') && document.getElementById('text-position').value;
    var fontSize  = parseInt((document.getElementById('text-font-size') && document.getElementById('text-font-size').value) || 32);
    var color     = (document.getElementById('text-color') && document.getElementById('text-color').value) || '#ffffff';
    var startTime = parseFloat((document.getElementById('text-start-time') && document.getElementById('text-start-time').value) || 0);
    var endTimeEl = document.getElementById('text-end-time') && document.getElementById('text-end-time').value;
    var endTime   = endTimeEl ? parseFloat(endTimeEl) : null;

    if (!text) { UI.toast('Enter some text first', 'error'); return; }
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }

    UI.closeModal('modal-text');
    UI.setStatus('Adding text overlay...');
    var result = await API.call('add_text_overlay', AppState.selectedClipPath,
                                text, { align: position }, fontSize, color, startTime, endTime);
    if (result && result.success) {
      UI.toast('Text overlay added!', 'success');
      Player.loadClip(result.output_path);
    } else {
      UI.toast('Text overlay failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  async addWatermark()   { UI.toast('Select a watermark image in the file dialog', 'info'); },
  async cropSelected()   { UI.toast('Crop frame — coming in next update', 'info'); },
  async stackHorizontal(){ UI.toast('Select two clips from the library', 'info'); },
  async stackVertical()  { UI.toast('Select two clips from the library', 'info'); }
};


// ─────────────────────────────────────────────────────────────
// AUDIO EDIT — Volume, fade, replace, BGM mixer
// ─────────────────────────────────────────────────────────────
const AudioEdit = {

  // Mixer state
  _mixVideoVol:  1.0,
  _mixBGMVol:    0.3,
  _mixBGMStart:  0.0,
  _mixBGMPath:   null,

  // ── Preview volume (doesn't affect file) ──
  setVolume(val) {
    var label = document.getElementById('val-volume');
    if (label) label.textContent = parseFloat(val).toFixed(2) + 'x';
    clearTimeout(this._volTimeout);
    this._volTimeout = setTimeout(async function() {
      if (!AppState.selectedClipPath) return;
      var result = await API.call('set_volume', AppState.selectedClipPath, parseFloat(val));
      if (result && result.success) {
        Player.loadClip(result.output_path);
        AppState.selectedClipPath = result.output_path;
        Library.addClip({ path: result.output_path });
        UI.toast('Volume set to ' + parseFloat(val).toFixed(2) + 'x', 'success');
      }
    }, 700);
  },

  setFadeIn(val) {
    var label = document.getElementById('val-fadein');
    if (label) label.textContent = parseFloat(val).toFixed(1) + 's';
    this._pendingFadeIn = parseFloat(val);
  },

  setFadeOut(val) {
    var label = document.getElementById('val-fadeout');
    if (label) label.textContent = parseFloat(val).toFixed(1) + 's';
    this._pendingFadeOut = parseFloat(val);
    clearTimeout(this._fadeTimeout);
    this._fadeTimeout = setTimeout(async function() {
      if (!AppState.selectedClipPath) return;
      var fadeIn  = AudioEdit._pendingFadeIn  || 0;
      var fadeOut = AudioEdit._pendingFadeOut || 0;
      if (fadeIn === 0 && fadeOut === 0) return;
      var result = await API.call('fade_audio', AppState.selectedClipPath, fadeIn, fadeOut);
      if (result && result.success) {
        Player.loadClip(result.output_path);
        AppState.selectedClipPath = result.output_path;
        Library.addClip({ path: result.output_path });
        UI.toast('Fade applied', 'success');
      }
    }, 800);
  },

  // ── Replace audio track ──
  async replacAudio() {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    var result = await API.call('open_file_dialog', 'Audio');
    if (!result || !result.success) { UI.toast('No file selected', 'info'); return; }
    UI.setStatus('Replacing audio...');
    var res = await API.call('replace_audio', AppState.selectedClipPath, result.path);
    if (res && res.success) {
      UI.toast('Audio replaced!', 'success');
      Player.loadClip(res.output_path);
      AppState.selectedClipPath = res.output_path;
      Library.addClip({ path: res.output_path });
    } else {
      UI.toast('Replace audio failed: ' + (res && res.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // ── Add BGM (quick mix at 30% volume) ──
  async addBGM() {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    var result = await API.call('open_file_dialog', 'Audio');
    if (!result || !result.success) { UI.toast('No file selected', 'info'); return; }
    UI.setStatus('Adding BGM...');
    var res = await API.call('add_background_music', AppState.selectedClipPath, result.path, 0.3);
    if (res && res.success) {
      UI.toast('BGM added!', 'success');
      Player.loadClip(res.output_path);
      AppState.selectedClipPath = res.output_path;
      Library.addClip({ path: res.output_path });
    } else {
      UI.toast('BGM failed: ' + (res && res.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // ── Audio Mixer controls ──
  setMixVideoVol(val) {
    this._mixVideoVol = parseFloat(val);
    var label = document.getElementById('val-vid-vol');
    if (label) label.textContent = parseFloat(val).toFixed(2) + 'x';
  },

  setMixBGMVol(val) {
    this._mixBGMVol = parseFloat(val);
    var label = document.getElementById('val-bgm-vol');
    if (label) label.textContent = parseFloat(val).toFixed(2) + 'x';
  },

  setMixBGMStart(val) {
    this._mixBGMStart = parseFloat(val);
    var label = document.getElementById('val-bgm-start');
    if (label) label.textContent = parseFloat(val).toFixed(1) + 's';
  },

  async pickBGMForMixer() {
    var result = await API.call('open_file_dialog', 'Audio');
    if (!result || !result.success) { UI.toast('No file selected', 'info'); return; }
    this._mixBGMPath = result.path;
    var name = result.path.split('\\').pop().split('/').pop();
    var label = document.getElementById('mix-bgm-name');
    if (label) label.textContent = '🎵 ' + name;
    UI.toast('BGM selected: ' + name, 'success');
  },

  async applyMix() {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }

    UI.setStatus('Mixing audio...');
    UI.toast('Applying audio mix...', 'info', 2000);

    var result = await API.call(
      'mix_audio_levels',
      AppState.selectedClipPath,
      this._mixVideoVol,
      this._mixBGMPath,   // null if not selected
      this._mixBGMVol,
      this._mixBGMStart
    );

    if (result && result.success) {
      var msg = 'Mix applied! Video: ' + this._mixVideoVol.toFixed(1) + 'x';
      if (this._mixBGMPath) msg += ' | BGM: ' + this._mixBGMVol.toFixed(1) + 'x';
      UI.toast(msg, 'success', 4000);
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Mix failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  }
};

// ─────────────────────────────────────────────────────────────
// EDITOR — Trim, split, merge, speed
// ─────────────────────────────────────────────────────────────
const Editor = {

  // ── Multi-segment tracking ──
  // Stores multiple I/O point pairs from the same source clip
  _segments: [],        // [{in, out}, {in, out}, ...]
  _pendingIn: null,     // Last I key press time

  // Called when I is pressed — adds pending in-point
  addSegmentIn(time) {
    this._pendingIn = time;
    UI.toast('✂ In: ' + time.toFixed(2) + 's — now click O Out', 'info', 2000);
    Editor._updateBadge();
  },

  addSegmentOut(time) {
    if (this._pendingIn === null) {
      UI.toast('Click ⬤ I first to set start point', 'error'); return;
    }
    if (time <= this._pendingIn) {
      UI.toast('Out point must be after In point!', 'error'); return;
    }
    this._segments.push({ in: this._pendingIn, out: time });
    this._pendingIn = null;
    Editor._updateBadge();
    UI.toast('✅ Segment ' + this._segments.length + ' saved: ' +
             this._segments[this._segments.length-1].in.toFixed(2) +
             's → ' + time.toFixed(2) + 's', 'success', 3000);
  },

  _updateBadge() {
    var b1 = document.getElementById('segment-count');
    var b2 = document.getElementById('segment-badge');
    var txt = this._segments.length + ' seg' + (this._segments.length !== 1 ? 's' : '');
    if (b1) b1.textContent = this._segments.length + ' segment(s)';
    if (b2) {
      b2.textContent = txt;
      b2.style.color = this._segments.length > 0 ? '#10b981' : 'var(--text-muted)';
    }
  },

  clearSegments() {
    this._segments = [];
    this._pendingIn = null;
    Editor._updateBadge();
    UI.toast('Segments cleared', 'info');
  },

  async trimSelected() {
    if (!AppState.selectedClipPath) {
      UI.toast('No clip selected', 'error'); return;
    }

    // ── Multi-segment mode ──
    if (this._segments.length > 1) {
      UI.toast('Trimming ' + this._segments.length + ' segments and merging...', 'info', 3000);
      UI.setStatus('Multi-trim: cutting ' + this._segments.length + ' segments...');

      var trimPaths = [];
      for (var i = 0; i < this._segments.length; i++) {
        var seg = this._segments[i];
        var res = await API.call('trim_clip', AppState.selectedClipPath, seg.in, seg.out);
        if (res && res.success) {
          trimPaths.push(res.output_path);
          UI.setStatus('Trimmed segment ' + (i+1) + '/' + this._segments.length);
        } else {
          UI.toast('Segment ' + (i+1) + ' trim failed', 'error');
        }
      }

      if (trimPaths.length === 0) {
        UI.toast('No segments trimmed', 'error'); return;
      }

      if (trimPaths.length === 1) {
        // Only one succeeded — load it
        Player.loadClip(trimPaths[0]);
        AppState.selectedClipPath = trimPaths[0];
        Library.addClip({ path: trimPaths[0] });
        UI.toast('1 segment trimmed!', 'success');
      } else {
        // Merge all segments into one
        UI.setStatus('Merging ' + trimPaths.length + ' segments...');
        var mergeOut = AppState.selectedClipPath.replace(/\.\w+$/, '_multitrim_' + Date.now() + '.mp4');
        var mergeRes = await API.call('merge_clips', trimPaths, mergeOut);
        if (mergeRes && mergeRes.success) {
          UI.toast(trimPaths.length + ' segments merged into one clip!', 'success', 4000);
          Player.loadClip(mergeRes.output_path);
          AppState.selectedClipPath = mergeRes.output_path;
          Library.addClip({ path: mergeRes.output_path });
        } else {
          UI.toast('Merge failed — segments saved individually', 'info');
          trimPaths.forEach(function(p) { Library.addClip({ path: p }); });
        }
      }

      // Clear segments after trim
      this.clearSegments();

    } else {
      // ── Single trim — read from global _snapIn/_snapOut ──
      var inPoint  = null;
      var outPoint = null;

      // Check segments first, then globals, then Timeline
      if (this._segments.length === 1) {
        inPoint  = this._segments[0].in;
        outPoint = this._segments[0].out;
      } else {
        inPoint  = (typeof _snapIn  !== 'undefined') ? _snapIn  : Timeline.getInPoint();
        outPoint = (typeof _snapOut !== 'undefined') ? _snapOut : Timeline.getOutPoint();
      }

      if (inPoint === null || inPoint === undefined) {
        UI.toast('Click I In button in the player bar, then O Out', 'error'); return;
      }
      if (outPoint === null || outPoint === undefined) {
        UI.toast('Click O Out button after setting In point', 'error'); return;
      }
      if (outPoint <= inPoint) {
        UI.toast('Out must be after In point', 'error'); return;
      }

      UI.setStatus('Trimming...');
      var result = await API.call('trim_clip', AppState.selectedClipPath, inPoint, outPoint);

      if (result && result.success) {
        UI.toast('Trimmed! ' + inPoint.toFixed(2) + 's → ' + outPoint.toFixed(2) + 's', 'success');
        Player.loadClip(result.output_path);
        AppState.selectedClipPath = result.output_path;
        Library.addClip({ path: result.output_path, duration: result.duration });
        _snapIn  = null;
        _snapOut = null;
        Timeline.setInPoint(null);
        Timeline.setOutPoint(null);
        this.clearSegments();
        if (Timeline._drawInOutMarkers) Timeline._drawInOutMarkers();
        var b = document.getElementById('segment-badge');
        if (b) { b.textContent = '0 seg'; b.style.color = 'var(--text-muted)'; }
      } else {
        UI.toast('Trim failed: ' + (result && result.message), 'error');
      }
    }
    UI.setStatus('Ready');
  },

    async splitAtPlayhead() {
    if (!AppState.selectedClipPath) { UI.toast('No clip selected', 'error'); return; }
    var v      = document.getElementById('preview-video');
    var atTime = v ? v.currentTime : 0;
    if (atTime <= 0) { UI.toast('Move the playhead to the split point', 'error'); return; }
    UI.setStatus('Splitting...');
    var result = await API.call('split_clip', AppState.selectedClipPath, atTime);
    if (result && result.success) {
      UI.toast('Split into Part A and Part B!', 'success');
      Library.addClip({ path: result.part_a_path });
      Library.addClip({ path: result.part_b_path });
    } else {
      UI.toast('Split failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  async mergeSelected() {
    var clips = Timeline.getClipPaths();
    if (clips.length < 2) { UI.toast('Add at least 2 clips to the timeline', 'error'); return; }
    var outputPath = 'merged_' + Date.now() + '.mp4';
    UI.setStatus('Merging ' + clips.length + ' clips...');
    var result = await API.call('merge_clips', clips, outputPath);
    if (result && result.success) {
      UI.toast('Merged ' + clips.length + ' clips!', 'success');
      Player.loadClip(result.output_path);
      Library.addClip({ path: result.output_path, duration: result.total_duration });
    } else {
      UI.toast('Merge failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  async setSpeed(val) {
    if (!AppState.selectedClipPath) { UI.toast('No clip selected', 'error'); return; }
    var speed = parseFloat(val);
    UI.setStatus('Setting speed to ' + speed + 'x...');
    var result = await API.call('set_clip_speed', AppState.selectedClipPath, speed);
    if (result && result.success) {
      UI.toast('Speed set to ' + speed + 'x', 'success');
      Player.loadClip(result.output_path);
    } else {
      UI.toast('Speed change failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  }
};


// ─────────────────────────────────────────────────────────────
// EXPORT — Save and export modals
// ─────────────────────────────────────────────────────────────
const Export = {

  _selectedFormat:  'mp4',
  _selectedQuality: 'high',
  _exportFormat:    'mp4',
  _exportQuality:   'high',

  selectFormat(fmt, el) {
    this._selectedFormat   = fmt;
    AppState.currentFormat = fmt;
    document.querySelectorAll('#format-options .format-option').forEach(function(opt) { opt.classList.remove('selected'); });
    if (el) el.classList.add('selected');
    var pathInput = document.getElementById('save-path-input');
    if (pathInput && pathInput.value) pathInput.value = pathInput.value.replace(/\.\w+$/, '.' + fmt);
  },

  selectQuality(q, el) {
    this._selectedQuality   = q;
    AppState.currentQuality = q;
    document.querySelectorAll('#quality-options .quality-option').forEach(function(opt) { opt.classList.remove('selected'); });
    if (el) el.classList.add('selected');
  },

  selectExportFormat(fmt, el) {
    this._exportFormat = fmt;
    document.querySelectorAll('#export-format-options .format-option').forEach(function(opt) { opt.classList.remove('selected'); });
    if (el) el.classList.add('selected');
  },

  selectExportQuality(q, el) {
    this._exportQuality = q;
    document.querySelectorAll('#export-format-options .quality-option').forEach(function(opt) { opt.classList.remove('selected'); });
    if (el) el.classList.add('selected');
  },

  // ── Browse Save Path — Opens real OS native Save dialog ──
  async browseSavePath() {
    var fmt         = this._selectedFormat || 'mp4';
    var defaultName = 'snapclip_' + Date.now() + '.' + fmt;
    var result      = await API.call('open_save_dialog', defaultName);
    if (result && result.success && result.path) {
      var pathInput = document.getElementById('save-path-input');
      if (pathInput) pathInput.value = result.path;
      UI.toast('Save location set!', 'success');
    } else {
      UI.toast('No location selected', 'info');
    }
  },

  // ── Browse Export Path — Opens real OS native Save dialog ──
  async browseExportPath() {
    var fmt         = this._exportFormat || 'mp4';
    var defaultName = 'exported_' + Date.now() + '.' + fmt;
    var result      = await API.call('open_save_dialog', defaultName);
    if (result && result.success && result.path) {
      var pathInput = document.getElementById('export-path-input');
      if (pathInput) pathInput.value = result.path;
      UI.toast('Export location set!', 'success');
    } else {
      UI.toast('No location selected', 'info');
    }
  },

  async saveRecording() {
    var savePath = document.getElementById('save-path-input') && document.getElementById('save-path-input').value.trim();
    if (!savePath) { UI.toast('Choose a save location first', 'error'); return; }

    UI.closeModal('modal-save');
    UI.openModal('modal-encoding');

    var progress = 0;
    var progressInterval = setInterval(function() {
      progress = Math.min(progress + 2, 95);
      Export._updateEncodingProgress(progress);
    }, 200);

    var result = await API.call('save_clip', savePath, this._selectedFormat, this._selectedQuality);

    clearInterval(progressInterval);
    Export._updateEncodingProgress(100);

    setTimeout(function() {
      UI.closeModal('modal-encoding');
      if (result && result.success) {
        UI.toast('Saved! ' + result.size_mb + 'MB at ' + savePath, 'success', 5000);
        Library.addClip({
          path:      result.file_path,
          name:      savePath.split('/').pop() || savePath.split('\\').pop(),
          duration:  result.duration,
          size_mb:   result.size_mb,
          thumbnail: result.thumbnail
        });
      } else {
        UI.toast('Save failed: ' + (result && result.message), 'error');
      }
      // Always reset UI state after save attempt
      UI.setRecordingUI(false);
    }, 500);
  },

  async exportClip() {
    var outputPath = document.getElementById('export-path-input') && document.getElementById('export-path-input').value.trim();
    if (!outputPath) { UI.toast('Choose an output path', 'error'); return; }
    if (!AppState.selectedClipPath) { UI.toast('No clip selected', 'error'); return; }

    UI.closeModal('modal-export');
    UI.openModal('modal-encoding');

    var resSel     = document.getElementById('export-resolution') && document.getElementById('export-resolution').value;
    var resolution = null;
    if (resSel && resSel !== 'original' && resSel !== 'custom') {
      var parts = resSel.split('x').map(Number);
      if (parts.length === 2 && parts[0] > 0 && parts[1] > 0) {
        resolution = parts;
      }
    }

    var result = await API.call('export_clip', AppState.selectedClipPath,
                                outputPath, this._exportFormat, this._exportQuality, resolution);
    UI.closeModal('modal-encoding');
    if (result && result.success) {
      UI.toast('Exported: ' + result.size_mb + 'MB', 'success');
    } else {
      UI.toast('Export failed: ' + (result && result.message), 'error');
    }
  },

  async exportGif() {
    if (!AppState.selectedClipPath) { UI.toast('No clip selected', 'error'); return; }
    var outputPath = AppState.selectedClipPath.replace(/\.\w+$/, '.gif');
    UI.setStatus('Exporting GIF...');
    var result = await API.call('export_clip', AppState.selectedClipPath, outputPath, 'gif', 'medium', null);
    if (result && result.success) {
      UI.toast('GIF exported: ' + result.size_mb + 'MB', 'success');
    } else {
      UI.toast('GIF export failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  _updateEncodingProgress(pct) {
    var bar     = document.getElementById('encoding-progress');
    var percent = document.getElementById('encoding-percent');
    var detail  = document.getElementById('encoding-detail');
    if (bar)     bar.style.width       = pct + '%';
    if (percent) percent.textContent   = Math.round(pct) + '%';
    if (detail)  detail.textContent    = pct < 100 ? 'Encoding... ' + Math.round(pct) + '%' : 'Done!';
  }
};


// ─────────────────────────────────────────────────────────────
// STATUS BAR
// ─────────────────────────────────────────────────────────────
const StatusBar = {

  start() {
    AppState.statusInterval = setInterval(StatusBar.update, 3000);
    StatusBar.update();
  },

  async update() {
    var info = await API.call('get_system_info');
    if (!info || info._mock) return;
    var cpu      = document.getElementById('stat-cpu');
    var ram      = document.getElementById('stat-ram');
    var gpu      = document.getElementById('stat-gpu');
    var platform = document.getElementById('stat-platform');
    if (cpu)      cpu.textContent      = info.cpu_percent + '%';
    if (ram)      ram.textContent      = info.ram_used_gb + '/' + info.ram_total_gb + 'GB';
    if (gpu)      gpu.textContent      = info.gpu || 'GPU';
    if (platform) platform.textContent = info.platform || '--';
    var gpuStatus  = document.getElementById('gpu-status');
    var cudaStatus = document.getElementById('cuda-status');
    if (gpuStatus)  gpuStatus.textContent  = 'NVENC';
    if (cudaStatus) cudaStatus.textContent = 'Available';
  }
};


// ─────────────────────────────────────────────────────────────
// ASPECT RATIO — crop video to standard ratios
// ─────────────────────────────────────────────────────────────
const AspectRatio = {

  _selectedRatio: null,
  _selectedRes:   null,

  apply(ratio, res) {
    // Update UI selection
    document.querySelectorAll('.ratio-btn').forEach(function(b) {
      b.classList.remove('active');
    });
    // Find and activate the clicked button
    var btns = document.querySelectorAll('.ratio-btn');
    btns.forEach(function(b) {
      if (b.getAttribute('onclick') && b.getAttribute('onclick').indexOf("'" + ratio + "'") > -1) {
        b.classList.add('active');
      }
    });

    this._selectedRatio = ratio;
    this._selectedRes   = res;

    var badge = document.getElementById('current-ratio-badge');
    if (badge) badge.textContent = ratio + ' (' + res + ')';

    UI.toast('Ratio selected: ' + ratio + ' — click Apply Crop to render', 'info', 2000);
  },

  async applyCrop() {
    if (!AppState.selectedClipPath) {
      UI.toast('Load a clip first', 'error'); return;
    }
    if (!this._selectedRatio) {
      UI.toast('Select an aspect ratio first', 'error'); return;
    }

    UI.setStatus('Cropping to ' + this._selectedRatio + '...');
    var result = await API.call('apply_aspect_ratio',
                                AppState.selectedClipPath,
                                this._selectedRatio);

    if (result && result.success) {
      UI.toast('Cropped to ' + this._selectedRatio + '!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Crop failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  reset() {
    this._selectedRatio = null;
    this._selectedRes   = null;
    document.querySelectorAll('.ratio-btn').forEach(function(b) {
      b.classList.remove('active');
    });
    var badge = document.getElementById('current-ratio-badge');
    if (badge) badge.textContent = 'Original';
    UI.toast('Ratio reset', 'info');
  }
};


// ─────────────────────────────────────────────────────────────
// COLOR GRADE — LUT presets + manual color controls
// ─────────────────────────────────────────────────────────────
const ColorGrade = {

  _activeLut: null,

  // Pending slider values
  _vals: {
    brightness: 0.0,
    contrast:   1.0,
    saturation: 1.0,
    gamma:      1.0,
    hue:        0.0,
    shadows:    0.0,
    highlights: 0.0,
  },

  async applyLut(lutName) {
    if (!AppState.selectedClipPath) {
      UI.toast('Load a clip first', 'error'); return;
    }

    // Update active LUT chip UI
    document.querySelectorAll('.lut-chip').forEach(function(c) {
      c.classList.remove('active');
    });
    var chips = document.querySelectorAll('.lut-chip');
    chips.forEach(function(c) {
      if (c.getAttribute('onclick') && c.getAttribute('onclick').indexOf("'" + lutName + "'") > -1) {
        c.classList.add('active');
      }
    });

    this._activeLut = lutName;
    UI.setStatus('Applying ' + lutName + ' LUT...');

    var result = await API.call('apply_lut', AppState.selectedClipPath, lutName);

    if (result && result.success) {
      UI.toast(lutName + ' LUT applied!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('LUT failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  updateSlider(param, value) {
    var val = parseFloat(value);
    this._vals[param] = val;

    // Update label
    var label = document.getElementById('val-' + param);
    if (label) {
      if (param === 'hue') {
        label.textContent = Math.round(val) + '°';
      } else {
        label.textContent = val.toFixed(2);
      }
    }

    // Debounce apply
    clearTimeout(this['_timeout_' + param]);
    this['_timeout_' + param] = setTimeout(function() {
      // Don't auto-apply on slider — wait for Apply button
      // Just update the label for now
    }, 300);
  },

  async applyAll() {
    if (!AppState.selectedClipPath) {
      UI.toast('Load a clip first', 'error'); return;
    }

    UI.setStatus('Applying color grade...');

    var result = await API.call(
      'apply_color_grade',
      AppState.selectedClipPath,
      this._vals.brightness,
      this._vals.contrast,
      this._vals.saturation,
      this._vals.gamma,
      this._vals.hue,
      this._vals.shadows,
      this._vals.highlights
    );

    if (result && result.success) {
      UI.toast('Color grade applied!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Color grade failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  reset() {
    // Reset all sliders to default
    var defaults = {
      brightness: 0, contrast: 1, saturation: 1,
      gamma: 1, hue: 0, shadows: 0, highlights: 0
    };

    for (var key in defaults) {
      this._vals[key] = defaults[key];
      var label = document.getElementById('val-' + key);
      if (label) label.textContent = key === 'hue' ? '0°' : defaults[key].toFixed ? defaults[key].toFixed(1) : defaults[key];
    }

    // Reset slider DOM elements
    var inputs = document.querySelectorAll('input[type="range"]');
    inputs.forEach(function(input) {
      var param = input.getAttribute('oninput');
      if (param && param.indexOf('ColorGrade') > -1) {
        if (param.indexOf('brightness') > -1) input.value = 0;
        if (param.indexOf('contrast') > -1)   input.value = 1;
        if (param.indexOf('saturation') > -1) input.value = 1;
        if (param.indexOf('gamma') > -1)       input.value = 1;
        if (param.indexOf('hue') > -1)         input.value = 0;
        if (param.indexOf('shadows') > -1)     input.value = 0;
        if (param.indexOf('highlights') > -1)  input.value = 0;
      }
    });

    // Clear active LUT
    this._activeLut = null;
    document.querySelectorAll('.lut-chip').forEach(function(c) {
      c.classList.remove('active');
    });

    UI.toast('Color grade reset', 'info');
  }
};



// ─────────────────────────────────────────────────────────────
// VFX — Modern Shorts/Reels Effects
// ─────────────────────────────────────────────────────────────
const VFX = {

  _zoomPunchTime: 1.0,   // Zoom punch timestamp

  _fadeDuration: 1.5,

  setFadeDuration(val) {
    this._fadeDuration = parseFloat(val);
    var label = document.getElementById('val-fade-duration');
    if (label) label.textContent = parseFloat(val).toFixed(1);
  },

  // Fade to black/white at end of clip
  async fadeOut(color) {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    UI.setStatus('Fading out...');
    UI.toast('Fading out to ' + color + '...', 'info', 2000);

    var result = await API.call('apply_vfx', 'fade_out', AppState.selectedClipPath, {
      fade_duration: this._fadeDuration,
      color: color
    });

    if (result && result.success) {
      UI.toast('Fade out applied! (' + this._fadeDuration + 's)', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Fade out failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // Fade in from black/white at start of clip
  async fadeIn(color) {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    UI.setStatus('Fading in...');

    var result = await API.call('apply_vfx', 'fade_in', AppState.selectedClipPath, {
      fade_duration: this._fadeDuration,
      color: color
    });

    if (result && result.success) {
      UI.toast('Fade in applied! (' + this._fadeDuration + 's)', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Fade in failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // Fade in at start AND fade out at end — both in one pass
  async fadeInOut(color) {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    UI.setStatus('Applying fade in + out...');

    var result = await API.call('apply_vfx', 'fade_in_out', AppState.selectedClipPath, {
      fade_in_duration:  this._fadeDuration,
      fade_out_duration: this._fadeDuration,
      color: color
    });

    if (result && result.success) {
      UI.toast('Fade in + out applied!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Fade in/out failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // Crossfade between 2 clips on timeline
  async crossfade() {
    var clips = Timeline.getClipPaths();
    if (clips.length < 2) {
      UI.toast('Add 2 clips to the timeline for crossfade', 'error');
      return;
    }

    var clipA = clips[clips.length - 2];
    var clipB = clips[clips.length - 1];
    var color = document.getElementById('fade-color-picker') ?
                document.getElementById('fade-color-picker').value : '#000000';

    UI.setStatus('Crossfading clips...');
    UI.toast('Crossfading: clip A fades out, clip B fades in...', 'info', 3000);

    var result = await API.call('apply_transition', 'crossfade_transition', clipA, clipB, {
      fade_duration: this._fadeDuration,
      color: color
    });

    if (result && result.success) {
      UI.toast('Crossfade done! Past fades → Present appears.', 'success', 4000);
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Crossfade failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // Custom color fade from the color picker
  async fadeOutCustom() {
    var picker = document.getElementById('fade-color-picker');
    var color = picker ? picker.value : '#000000';
    await this.fadeOut(color);
  },

  setZoomTime(val) {
    this._zoomPunchTime = parseFloat(val);
    var label = document.getElementById('val-zoompunch');
    if (label) label.textContent = parseFloat(val).toFixed(1);
  },

  // Apply a single-clip VFX effect
  async apply(effectName, extraArgs) {
    if (!AppState.selectedClipPath) {
      UI.toast('Load a clip first', 'error'); return;
    }
    UI.setStatus('Applying ' + effectName + '...');
    UI.toast(effectName + ' processing...', 'info', 2000);

    var args = Object.assign({ clip_path: AppState.selectedClipPath }, extraArgs || {});
    var result = await API.call('apply_vfx', effectName, AppState.selectedClipPath, extraArgs || {});

    if (result && result.success) {
      UI.toast(effectName + ' applied!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('VFX failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // Apply transition between two clips (needs 2 clips on timeline)
  async transition(effectName) {
    var clips = Timeline.getClipPaths();
    if (clips.length < 2) {
      UI.toast('Add 2 clips to the timeline first for a transition', 'error');
      return;
    }

    var clipA = clips[clips.length - 2];  // second-to-last
    var clipB = clips[clips.length - 1];  // last clip

    UI.setStatus('Applying ' + effectName + '...');
    UI.toast(effectName + ' processing... (this takes a moment)', 'info', 3000);

    var result = await API.call('apply_transition', effectName, clipA, clipB, {});

    if (result && result.success) {
      UI.toast('Transition applied! New merged clip created.', 'success', 4000);
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Transition failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  // Light leak with color choice
  async applyLightLeak(color) {
    await this.apply('light_leak', { color: color, intensity: 0.4 });
  },

  // Lens flare at top-right (most cinematic position)
  async applyLensFlare() {
    await this.apply('lens_flare', { flare_x: 0.8, flare_y: 0.08 });
  },

  // Zoom punch at user-defined timestamp
  async applyZoomPunch() {
    await this.apply('zoom_punch', {
      at_time: this._zoomPunchTime,
      zoom_scale: 1.3,
      duration: 0.15
    });
  },

  // Animated text effects
  async animText(effectName, extraArgs) {
    if (!AppState.selectedClipPath) {
      UI.toast('Load a clip first', 'error'); return;
    }

    var textInput = document.getElementById('vfx-text-input');
    var text = textInput && textInput.value.trim();

    if (!text) {
      UI.toast('Enter text in the VFX text box first!', 'error');
      if (textInput) textInput.focus();
      return;
    }

    UI.setStatus('Adding animated text...');
    UI.toast('Rendering animated text...', 'info', 2000);

    var args = Object.assign({
      text: text,
      font_size: 38,
      color: 'white',
      at_time: 0.5,
      start_time: 0.5
    }, extraArgs || {});

    var result = await API.call('apply_vfx', effectName, AppState.selectedClipPath, args);

    if (result && result.success) {
      UI.toast('Animated text added!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Text animation failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  }
};


// ─────────────────────────────────────────────────────────────
// PRO TOOLS — Premiere Pro level features
// ─────────────────────────────────────────────────────────────
const ProTools = {

  _freezeAt:  1.0,
  _freezeDur: 2.0,

  setFreezeAt(val) {
    this._freezeAt = parseFloat(val);
    var l = document.getElementById('val-freeze-at');
    if (l) l.textContent = parseFloat(val).toFixed(1);
  },

  setFreezeDur(val) {
    this._freezeDur = parseFloat(val);
    var l = document.getElementById('val-freeze-dur');
    if (l) l.textContent = parseFloat(val).toFixed(1) + 's';
  },

  async _run(method, args, label) {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    UI.setStatus(label + '...');
    UI.toast(label + ' processing...', 'info', 2000);
    var result = await API.call(method, AppState.selectedClipPath, ...(args || []));
    if (result && result.success) {
      UI.toast(label + ' done!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast(label + ' failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  stabilize()      { this._run('stabilize_clip',   [10],                'Stabilizing'); },
  denoise()        { this._run('denoise_clip',      [5],                 'Denoising'); },
  sharpen()        { this._run('sharpen_clip',      [1.5],               'Sharpening'); },
  reverse()        { this._run('reverse_clip',      [],                  'Reversing'); },
  normalizeAudio() { this._run('normalize_audio',   [-16.0],             'Normalizing audio'); },
  noiseGate()      { this._run('noise_gate',        [0.02],              'Noise gate'); },
  autocut()        { this._run('auto_cut_silence',  [-35.0, 0.5],        'Auto cutting silence'); },

  freezeFrame() {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    this._run('freeze_frame', [this._freezeAt, this._freezeDur], 'Freeze frame');
  },

  async chromaKey(color) {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    UI.setStatus('Chroma key (' + color + ')...');
    UI.toast('Removing ' + color + ' screen...', 'info', 3000);
    var result = await API.call('chroma_key', AppState.selectedClipPath, color, 0.3, 0.1);
    if (result && result.success) {
      UI.toast('Chroma key done! Output: ' + result.output_path.split('\\').pop(), 'success', 5000);
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('Chroma key failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  },

  async pip() {
    if (!AppState.selectedClipPath) { UI.toast('Load a clip first', 'error'); return; }
    // Pick the overlay clip
    var overlay = await API.call('open_file_dialog', 'Video');
    if (!overlay || !overlay.success) { UI.toast('No overlay clip selected', 'info'); return; }
    var pos = document.getElementById('pip-position');
    var position = pos ? pos.value : 'topright';
    UI.setStatus('Creating PiP...');
    var result = await API.call('picture_in_picture',
                                AppState.selectedClipPath,
                                overlay.path, position, 0.25);
    if (result && result.success) {
      UI.toast('Picture-in-Picture created!', 'success');
      Player.loadClip(result.output_path);
      AppState.selectedClipPath = result.output_path;
      Library.addClip({ path: result.output_path });
    } else {
      UI.toast('PiP failed: ' + (result && result.message), 'error');
    }
    UI.setStatus('Ready');
  }
};

// ─────────────────────────────────────────────────────────────
// SNAPCLIP GLOBALS — I/O point setters (used by HTML buttons)
// Simple: just store times, trim reads them back
// ─────────────────────────────────────────────────────────────
var _snapIn  = null;   // In point time (seconds)
var _snapOut = null;   // Out point time (seconds)

const SnapClip = {
  setIn() {
    var v = document.getElementById('preview-video');
    _snapIn = v ? (v.currentTime || 0) : 0;
    _snapOut = null;  // Reset out when new in is set

    // Visual marker
    Timeline.setInPoint(_snapIn);
    Timeline.setOutPoint(null);
    if (Timeline._drawInOutMarkers) Timeline._drawInOutMarkers();

    // Update badge
    var b = document.getElementById('segment-badge');
    if (b) { b.textContent = 'IN: ' + _snapIn.toFixed(2) + 's'; b.style.color = '#10b981'; }

    UI.setStatus('In: ' + _snapIn.toFixed(2) + 's — seek to end then click O Out');
    UI.toast('In set: ' + _snapIn.toFixed(2) + 's', 'info', 1500);
  },

  setOut() {
    var v  = document.getElementById('preview-video');
    var t  = v ? (v.currentTime || 0) : 0;

    if (_snapIn === null) {
      UI.toast('Click I In first!', 'error'); return;
    }
    if (t <= _snapIn) {
      UI.toast('Out must be after In (' + _snapIn.toFixed(2) + 's)', 'error'); return;
    }

    _snapOut = t;
    Timeline.setOutPoint(_snapOut);
    if (Timeline._drawInOutMarkers) Timeline._drawInOutMarkers();

    // Also store in segments list for multi-trim
    Editor._segments.push({ in: _snapIn, out: _snapOut });
    var b = document.getElementById('segment-badge');
    if (b) {
      b.textContent = Editor._segments.length + ' seg(s) ready';
      b.style.color = '#f59e0b';
    }

    UI.setStatus(_snapIn.toFixed(2) + 's → ' + _snapOut.toFixed(2) + 's — click Trim!');
    UI.toast('Segment: ' + _snapIn.toFixed(2) + 's → ' + _snapOut.toFixed(2) +
             's | Click Trim ✂', 'success', 3000);

    // Reset in-point so next I starts fresh segment
    _snapIn = null;
  },

  getIn()  { return _snapIn;  },
  getOut() { return _snapOut; }
};

// ─────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────
async function initApp() {
  console.log('[SnapClip] Initializing...');

  await API.waitForReady();
  console.log('[SnapClip] pywebview ready');

  Settings.load();

  var screens = await API.call('get_screens');
  if (screens && !screens._mock && screens.length > 1) {
    var monitorSel = document.getElementById('setting-monitor');
    if (monitorSel) {
      monitorSel.innerHTML = screens.map(function(s, i) {
        return '<option value="' + i + '">Monitor ' + (i+1) + ' (' + s.width + 'x' + s.height + ')</option>';
      }).join('');
    }
  }

  await API.call('register_hotkeys', {
    start_recording: 'ctrl+shift+r',
    stop_recording:  'ctrl+shift+s',
    pause_recording: 'ctrl+shift+p',
    screenshot:      'ctrl+shift+x',
    open_editor:     'ctrl+shift+e',
  });

  StatusBar.start();

  var libClips = await API.call('get_clips_library');
  if (libClips && Array.isArray(libClips)) {
    libClips.forEach(function(clip) { Library.addClip(clip); });
  }

  UI.setStatus('Ready');
  UI.toast('SnapClip ready! Select a region to start recording.', 'success', 4000);
  console.log('[SnapClip] Init complete');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
