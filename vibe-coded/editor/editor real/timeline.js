// ═══════════════════════════════════════════════════════════════
// SnapClip - frontend/js/timeline.js
// Timeline Manager
//
// Responsibilities:
//   - Render clip blocks on the timeline track
//   - Handle drag-to-reorder clips on timeline
//   - Sync playhead position with video currentTime
//   - In/Out point markers for trimming
//   - Zoom in/out (scales clip block widths)
//   - Click-to-seek on timeline
//   - Trim handle drag (left/right edges of clip blocks)
//   - Show/hide empty state
//   - Communicate clip order to Editor for merge
//
// DSA Used:
//   - Doubly-linked array for clip sequence (JS Array with
//     splice/indexOf for O(n) reorder — acceptable for typical
//     timeline lengths of <50 clips)
//   - Object map for clipPath → block element (O(1) lookup)
//
// Timeline coordinate system:
//   - Each second of video = PIXELS_PER_SECOND * zoomLevel pixels
//   - Clip block width = clip.duration * PIXELS_PER_SECOND * zoom
//   - Playhead left position = currentTime * PIXELS_PER_SECOND * zoom
// ═══════════════════════════════════════════════════════════════

'use strict';

// ── Constants ──
const PIXELS_PER_SECOND = 40;   // Base pixels per second at zoom 1x
const MIN_ZOOM          = 0.5;  // Minimum zoom level
const MAX_ZOOM          = 8.0;  // Maximum zoom level
const ZOOM_STEP         = 0.5;  // Zoom increment per click

const Timeline = {

  // ── State ──
  _clips:        [],        // Ordered array of clip objects: [{path, duration, element}]
  _clipElements: new Map(), // Map: clipPath → DOM element (O(1) lookup)
  _zoomLevel:    1,         // Current zoom multiplier
  _inPoint:      null,      // Trim in-point (seconds)
  _outPoint:     null,      // Trim out-point (seconds)
  _activeDuration: 0,       // Duration of currently active clip (for playhead bounds)
  _isDraggingClip: false,   // True when drag-reordering a clip
  _draggedClip:    null,    // The clip being dragged

  // ── DOM ──
  get _track() {
    return document.getElementById('timeline-track');
  },
  get _playhead() {
    return document.getElementById('timeline-playhead');
  },
  get _emptyState() {
    return document.getElementById('timeline-empty');
  },
  get _zoomLabel() {
    return document.getElementById('timeline-zoom');
  },

  // ─────────────────────────────────────────────────────────────
  // ADD CLIP TO TIMELINE
  // ─────────────────────────────────────────────────────────────

  /**
   * Add a clip to the timeline track.
   * Creates a visual block proportional to the clip's duration.
   *
   * @param {string} clipPath - Full path to video file
   */
  async addClip(clipPath) {
    // Avoid duplicate entries
    if (this._clipElements.has(clipPath)) {
      UI.toast('Clip already on timeline', 'info');
      return;
    }

    // Load metadata to get duration for block sizing
    const meta = await API.call('load_clip_to_editor', clipPath);

    const duration = (meta && meta.success)
      ? meta.duration
      : 5;    // Fallback duration if metadata unavailable

    const name = clipPath.split('/').pop() || clipPath.split('\\').pop() || 'Clip';

    // Create clip object
    const clip = { path: clipPath, duration, name, element: null };

    // Create DOM block
    const block = this._createClipBlock(clip);
    clip.element = block;

    // Add to ordered array and element map
    this._clips.push(clip);
    this._clipElements.set(clipPath, block);

    // Append to track (before the empty state element)
    this._track.insertBefore(block, this._emptyState);

    // Hide empty state
    this._updateEmptyState();

    // Also tell backend timeline about this clip
    await API.call('add_to_timeline', clipPath);

    console.log(`[Timeline] Added: ${name} (${duration.toFixed(2)}s)`);
    UI.toast(`${name} added to timeline`, 'success');
  },

  // ─────────────────────────────────────────────────────────────
  // CREATE CLIP BLOCK
  // ─────────────────────────────────────────────────────────────

  /**
   * Create a timeline clip block DOM element.
   * Width is proportional to clip duration × zoom × pixels/sec.
   *
   * @param {object} clip - {path, duration, name}
   * @returns {HTMLElement} The block element
   */
  _createClipBlock(clip) {
    const block = document.createElement('div');
    block.className = 'timeline-clip';
    block.dataset.path = clip.path;

    // ── Width based on duration ──
    // width = duration (sec) × pixels_per_sec × zoom
    const width = Math.max(60, clip.duration * PIXELS_PER_SECOND * this._zoomLevel);
    block.style.width = `${width}px`;

    block.innerHTML = `
      <!-- Waveform decoration (visual texture) -->
      <div class="clip-waveform"></div>

      <!-- Left trim handle -->
      <div class="trim-handle left"
           onmousedown="event.stopPropagation(); Timeline._startTrimDrag(event, '${clip.path}', 'left')">
      </div>

      <!-- Clip label -->
      <div class="timeline-clip-label" title="${clip.name}">
        ${clip.name}
      </div>

      <!-- Right trim handle -->
      <div class="trim-handle right"
           onmousedown="event.stopPropagation(); Timeline._startTrimDrag(event, '${clip.path}', 'right')">
      </div>
    `;

    // ── Click to select + load clip ──
    block.addEventListener('click', (e) => {
      // Ignore if clicking on trim handle
      if (e.target.classList.contains('trim-handle')) return;

      // Select this clip
      document.querySelectorAll('.timeline-clip').forEach(b => b.classList.remove('selected'));
      block.classList.add('selected');

      // Load into player
      Player.loadClip(clip.path);
      AppState.selectedClipPath = clip.path;

      // Sync library selection
      document.querySelectorAll('.clip-card').forEach(c => c.classList.remove('selected'));
      const libCard = document.querySelector(`.clip-card[data-path="${clip.path}"]`);
      if (libCard) libCard.classList.add('selected');
    });

    // ── Double click to set in/out points ──
    block.addEventListener('dblclick', (e) => {
      const rect = block.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      const time = ratio * clip.duration;
      Timeline.setInPoint(time);
      UI.toast(`In point set: ${time.toFixed(2)}s`, 'info');
    });

    // ── Drag to reorder ──
    block.addEventListener('mousedown', (e) => {
      // Only drag on the clip body, not handles
      if (e.target.classList.contains('trim-handle')) return;
      Timeline._startClipDrag(e, clip.path);
    });

    return block;
  },

  // ─────────────────────────────────────────────────────────────
  // DRAG TO REORDER CLIPS
  // ─────────────────────────────────────────────────────────────

  _dragOffsetX: 0,

  _startClipDrag(e, clipPath) {
    e.preventDefault();
    this._isDraggingClip = true;
    this._draggedClip = clipPath;

    const block = this._clipElements.get(clipPath);
    if (!block) return;

    this._dragOffsetX = e.clientX - block.getBoundingClientRect().left;

    // Visual feedback: semi-transparent while dragging
    block.style.opacity = '0.6';
    block.style.zIndex  = '10';

    // Bind move and up to document so drag works outside element
    document.addEventListener('mousemove', Timeline._onClipDragMove);
    document.addEventListener('mouseup',   Timeline._onClipDragEnd);
  },

  _onClipDragMove(e) {
    if (!Timeline._isDraggingClip) return;

    const block = Timeline._clipElements.get(Timeline._draggedClip);
    if (!block) return;

    const track     = Timeline._track;
    const trackRect = track.getBoundingClientRect();
    const newX      = e.clientX - trackRect.left - Timeline._dragOffsetX;

    // Constrain to track bounds
    const maxX = trackRect.width - block.offsetWidth;
    block.style.position = 'relative';
    block.style.left     = `${Math.max(0, Math.min(newX, maxX))}px`;

    // ── Detect drop position ──
    // Find which clip this should be inserted before/after
    // by checking horizontal overlap with other clip blocks
    const dragMidX = e.clientX;

    Timeline._clips.forEach(clip => {
      if (clip.path === Timeline._draggedClip) return;
      const el   = clip.element;
      const rect = el.getBoundingClientRect();
      const mid  = rect.left + rect.width / 2;

      // Highlight potential drop position
      if (dragMidX < mid) {
        el.style.borderLeft = '2px solid var(--accent-secondary)';
      } else {
        el.style.borderLeft = '';
        el.style.borderRight = '2px solid var(--accent-secondary)';
      }
    });
  },

  _onClipDragEnd(e) {
    if (!Timeline._isDraggingClip) return;

    const block = Timeline._clipElements.get(Timeline._draggedClip);

    // Reset visual feedback
    if (block) {
      block.style.opacity  = '1';
      block.style.zIndex   = '';
      block.style.position = '';
      block.style.left     = '';
    }

    // Clear drop highlights
    Timeline._clips.forEach(clip => {
      if (clip.element) {
        clip.element.style.borderLeft  = '';
        clip.element.style.borderRight = '';
      }
    });

    // ── Determine new order ──
    // Find the drop position based on final mouse X
    const trackRect = Timeline._track.getBoundingClientRect();
    const dropX     = e.clientX - trackRect.left;

    let insertBefore = null;
    let accX = 0;
    for (const clip of Timeline._clips) {
      if (clip.path === Timeline._draggedClip) continue;
      const w = clip.element?.offsetWidth || 80;
      if (dropX < accX + w / 2) {
        insertBefore = clip.path;
        break;
      }
      accX += w + 4; // 4px gap
    }

    // ── Reorder array ──
    const fromIdx = Timeline._clips.findIndex(c => c.path === Timeline._draggedClip);
    const toIdx   = insertBefore
      ? Timeline._clips.findIndex(c => c.path === insertBefore)
      : Timeline._clips.length - 1;

    if (fromIdx !== -1 && fromIdx !== toIdx) {
      // Splice and reinsert
      const [moved] = Timeline._clips.splice(fromIdx, 1);
      Timeline._clips.splice(toIdx, 0, moved);

      // Re-render all blocks in new order
      Timeline._rerenderBlocks();

      // Sync order with backend
      API.call('reorder_timeline', fromIdx, toIdx);
      console.log(`[Timeline] Reordered: ${fromIdx} → ${toIdx}`);
    }

    // Cleanup
    Timeline._isDraggingClip = false;
    Timeline._draggedClip    = null;
    document.removeEventListener('mousemove', Timeline._onClipDragMove);
    document.removeEventListener('mouseup',   Timeline._onClipDragEnd);
  },

  // Re-render all clip blocks in current _clips order
  _rerenderBlocks() {
    // Remove all clip blocks from track
    document.querySelectorAll('.timeline-clip').forEach(el => el.remove());

    // Re-append in new order
    this._clips.forEach(clip => {
      if (clip.element) {
        this._track.insertBefore(clip.element, this._emptyState);
      }
    });
  },

  // ─────────────────────────────────────────────────────────────
  // TRIM HANDLE DRAG
  // ─────────────────────────────────────────────────────────────

  _trimSide:       null,   // 'left' or 'right'
  _trimClipPath:   null,
  _trimStartX:     0,
  _trimStartWidth: 0,

  _startTrimDrag(e, clipPath, side) {
    e.preventDefault();

    this._trimSide     = side;
    this._trimClipPath = clipPath;
    this._trimStartX   = e.clientX;

    const block = this._clipElements.get(clipPath);
    this._trimStartWidth = block ? block.offsetWidth : 0;

    document.addEventListener('mousemove', Timeline._onTrimMove);
    document.addEventListener('mouseup',   Timeline._onTrimEnd);
  },

  _onTrimMove(e) {
    const block = Timeline._clipElements.get(Timeline._trimClipPath);
    if (!block) return;

    const delta = e.clientX - Timeline._trimStartX;
    const clip  = Timeline._clips.find(c => c.path === Timeline._trimClipPath);
    if (!clip) return;

    if (Timeline._trimSide === 'right') {
      // Dragging right handle: change width (= change out point)
      const newWidth = Math.max(40, Timeline._trimStartWidth + delta);
      block.style.width = `${newWidth}px`;

      // Calculate new out point from pixel width
      const newDuration = newWidth / (PIXELS_PER_SECOND * Timeline._zoomLevel);
      Timeline._outPoint = Math.min(newDuration, clip.duration);

      UI.setStatus(`Out: ${Timeline._outPoint.toFixed(2)}s`);

    } else {
      // Dragging left handle: shift start + shrink block
      const newWidth = Math.max(40, Timeline._trimStartWidth - delta);
      block.style.width    = `${newWidth}px`;
      block.style.marginLeft = `${delta}px`;

      const trimmedDuration = newWidth / (PIXELS_PER_SECOND * Timeline._zoomLevel);
      const inPoint = clip.duration - trimmedDuration;
      Timeline._inPoint = Math.max(0, inPoint);

      UI.setStatus(`In: ${Timeline._inPoint.toFixed(2)}s`);
    }
  },

  _onTrimEnd() {
    // Show trim confirmation hint
    UI.toast(
      `Trim set: ${(Timeline._inPoint || 0).toFixed(2)}s – ${(Timeline._outPoint || 0).toFixed(2)}s. Click "Trim to Selection" to apply.`,
      'info',
      4000
    );

    document.removeEventListener('mousemove', Timeline._onTrimMove);
    document.removeEventListener('mouseup',   Timeline._onTrimEnd);
  },

  // ─────────────────────────────────────────────────────────────
  // PLAYHEAD SYNC
  // Called by Player on video timeupdate event
  // ─────────────────────────────────────────────────────────────

  /**
   * Move the playhead to the current video time position.
   *
   * @param {number} currentTime - Video current time in seconds
   */
  syncPlayhead(currentTime) {
    const playhead = this._playhead;
    if (!playhead) return;

    // Convert time to pixel position
    // left = currentTime × pixels_per_sec × zoom
    const left = currentTime * PIXELS_PER_SECOND * this._zoomLevel;
    playhead.style.left = `${left}px`;
  },

  /**
   * Called when a video file is loaded into the player.
   * Sets the active duration for playhead bounds.
   *
   * @param {HTMLVideoElement} videoEl - The video element
   */
  onVideoLoaded(videoEl) {
    if (videoEl && videoEl.duration) {
      this._activeDuration = videoEl.duration;
      console.log(`[Timeline] Active duration: ${videoEl.duration.toFixed(2)}s`);
    }
  },

  setActiveDuration(duration) {
    this._activeDuration = duration;
  },

  // ─────────────────────────────────────────────────────────────
  // ZOOM
  // ─────────────────────────────────────────────────────────────

  /**
   * Zoom the timeline in or out.
   * Adjusts the width of all clip blocks proportionally.
   *
   * @param {number} direction - +1 to zoom in, -1 to zoom out
   */
  zoom(direction) {
    const newZoom = this._zoomLevel + direction * ZOOM_STEP;
    this._zoomLevel = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom));

    // Update zoom label
    const label = this._zoomLabel;
    if (label) label.textContent = `${this._zoomLevel.toFixed(1)}×`;

    // Resize all clip blocks
    this._clips.forEach(clip => {
      const block = clip.element;
      if (block) {
        const newWidth = Math.max(60, clip.duration * PIXELS_PER_SECOND * this._zoomLevel);
        block.style.width = `${newWidth}px`;
        block.style.transition = 'width 0.2s ease';
      }
    });

    // Re-sync playhead position to new zoom
    const v = document.getElementById('preview-video');
    if (v) this.syncPlayhead(v.currentTime);

    AppState.zoomLevel = this._zoomLevel;
    console.log(`[Timeline] Zoom: ${this._zoomLevel}×`);
  },

  // ─────────────────────────────────────────────────────────────
  // IN / OUT POINT MANAGEMENT
  // Used by Editor.trimSelected()
  // ─────────────────────────────────────────────────────────────

  setInPoint(time) {
    this._inPoint = time;
    if (time !== null && time !== undefined) {
      UI.setStatus('In: ' + time.toFixed(2) + 's — seek forward then click O Out');
    }
  },

  setOutPoint(time) {
    this._outPoint = time;
    if (time !== null && time !== undefined) {
      UI.setStatus('Out: ' + time.toFixed(2) + 's — click Trim to Selection');
    }
  },

  getInPoint()  { return this._inPoint;  },
  getOutPoint() { return this._outPoint; },

  // ─────────────────────────────────────────────────────────────
  // REMOVE CLIP FROM TIMELINE
  // ─────────────────────────────────────────────────────────────

  removeClip(clipPath) {
    const block = this._clipElements.get(clipPath);

    if (block) {
      // Animate out
      block.style.opacity   = '0';
      block.style.transform = 'scaleY(0)';
      block.style.transition = 'all 0.2s ease';
      setTimeout(() => block.remove(), 200);
    }

    // Remove from arrays/maps
    this._clipElements.delete(clipPath);
    this._clips = this._clips.filter(c => c.path !== clipPath);

    // Tell backend
    API.call('remove_from_timeline', this._clips.findIndex(c => c.path === clipPath));

    this._updateEmptyState();
    console.log(`[Timeline] Removed: ${clipPath}`);
  },

  // ─────────────────────────────────────────────────────────────
  // CLEAR TIMELINE
  // ─────────────────────────────────────────────────────────────

  clearTimeline() {
    // Animate all blocks out
    this._clips.forEach(clip => {
      if (clip.element) {
        clip.element.style.opacity   = '0';
        clip.element.style.transform = 'scaleY(0)';
        clip.element.style.transition = 'all 0.15s ease';
      }
    });

    setTimeout(() => {
      // Remove all clip blocks from DOM
      document.querySelectorAll('.timeline-clip').forEach(el => el.remove());

      // Clear state
      this._clips        = [];
      this._clipElements = new Map();
      this._inPoint      = null;
      this._outPoint     = null;

      // Tell backend
      API.call('clear_timeline');

      // Reset playhead
      if (this._playhead) this._playhead.style.left = '0px';

      this._updateEmptyState();
      UI.toast('Timeline cleared', 'info');
      console.log('[Timeline] Cleared');
    }, 200);
  },

  // ─────────────────────────────────────────────────────────────
  // CLICK TO SEEK ON TIMELINE TRACK
  // ─────────────────────────────────────────────────────────────

  seekToClick(e) {
    if (!this._activeDuration) return;

    const track    = this._track;
    const trackRect = track.getBoundingClientRect();
    const clickX   = e.clientX - trackRect.left;

    // Convert pixel position to time
    const time = clickX / (PIXELS_PER_SECOND * this._zoomLevel);
    const clampedTime = Math.max(0, Math.min(time, this._activeDuration));

    // Seek video to this time
    const v = document.getElementById('preview-video');
    if (v && v.duration) v.currentTime = clampedTime;

    // Move playhead immediately
    this.syncPlayhead(clampedTime);
  },

  // ─────────────────────────────────────────────────────────────
  // GET CLIP PATHS IN ORDER
  // Used by Editor.mergeSelected()
  // ─────────────────────────────────────────────────────────────

  getClipPaths() {
    return this._clips.map(c => c.path);
  },

  // ─────────────────────────────────────────────────────────────
  // UTILITIES
  // ─────────────────────────────────────────────────────────────

  _updateEmptyState() {
    const empty = this._emptyState;
    if (!empty) return;
    empty.style.display = this._clips.length === 0 ? 'flex' : 'none';
  },

  getClipCount() {
    return this._clips.length;
  }
};

// ── Attach click-to-seek on timeline track ──
// Done after DOM is ready to avoid null reference
document.addEventListener('DOMContentLoaded', () => {
  const track = document.getElementById('timeline-track');
  if (track) {
    track.addEventListener('click', (e) => {
      // Only seek if clicking directly on track (not on a clip block)
      if (e.target === track || e.target.id === 'timeline-track') {
        Timeline.seekToClick(e);
      }
    });
  }
});

// ─────────────────────────────────────────────────────────────
// IN / OUT POINT UI
// Keyboard shortcuts + right-click context menu on timeline
// ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {

  // ── Keyboard shortcuts ──
  // I = set in point, O = set out point
  // Works even when video element has focus
  function handleKeyboard(e) {
    // Don't fire if user is typing in a text field
    var tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.target.isContentEditable) return;

    var v = document.getElementById('preview-video');
    var t = v ? (v.currentTime || 0) : 0;

    // I = Set In point (works even without video loaded)
    if (e.key === 'i' || e.key === 'I') {
      e.preventDefault();
      if (typeof Editor !== 'undefined') Editor.addSegmentIn(t);
      Timeline.setInPoint(t);
      Timeline._drawInOutMarkers();
      return;
    }

    // O = Set Out point
    if (e.key === 'o' || e.key === 'O') {
      e.preventDefault();
      if (typeof Editor !== 'undefined') Editor.addSegmentOut(t);
      Timeline.setOutPoint(t);
      Timeline._drawInOutMarkers();
      // DO NOT reset _inPoint here — trim needs it
      return;
    }

    // Space = play/pause
    if (e.key === ' ') {
      e.preventDefault();
      if (typeof Player !== 'undefined') Player.togglePlayPause();
      return;
    }

    // Need video for seek shortcuts
    if (!v) return;

    if (e.shiftKey && e.key === 'ArrowLeft') {
      e.preventDefault();
      v.currentTime = Math.max(0, t - 5);
    } else if (e.shiftKey && e.key === 'ArrowRight') {
      e.preventDefault();
      v.currentTime = Math.min(v.duration || 999, t + 5);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      v.currentTime = Math.max(0, t - 0.033);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      v.currentTime = Math.min(v.duration || 999, t + 0.033);
    }
  });

  // ── Right-click context menu on timeline track ──
  var track = document.getElementById('timeline-track');
  if (track) {
    track.addEventListener('contextmenu', function(e) {
      e.preventDefault();
      Timeline._showContextMenu(e.clientX, e.clientY);
    });
  }

  // ── Right-click on preview video ──
  var video = document.getElementById('preview-video');
  if (video) {
    video.addEventListener('contextmenu', function(e) {
      e.preventDefault();
      Timeline._showContextMenu(e.clientX, e.clientY);
    });
  }

  // ── Click anywhere to close context menu ──
  document.addEventListener('click', function() {
    var menu = document.getElementById('timeline-context-menu');
    if (menu) menu.remove();
  });

  // ── FIX: Video element steals keyboard focus ──
  // Rebroadcast keydown from video to our handleKeyboard function
  var vid = document.getElementById('preview-video');
  if (vid) {
    vid.addEventListener('keydown', function(e) {
      handleKeyboard(e);
    });
  }

  // Use capture=true so our handler fires BEFORE browser defaults
  document.removeEventListener('keydown', handleKeyboard);
  document.addEventListener('keydown', handleKeyboard, true);

  // Also listen on window level for pywebview
  window.removeEventListener('keydown', handleKeyboard);
  window.addEventListener('keydown', handleKeyboard, true);

  // Make body focusable and give it focus so keys work immediately
  document.body.tabIndex = 0;
  document.body.focus();

  // Re-focus body when clicking preview area (pywebview steals focus)
  var preview = document.getElementById('preview-container');
  if (preview) {
    preview.addEventListener('click', function() {
      setTimeout(function() { document.body.focus(); }, 50);
    });
  }

  // Also add inline I/O buttons to timeline bar for easier access
  var tlHeader = document.querySelector('.timeline-header');
  if (tlHeader) {
    var ioDiv = document.createElement('div');
    ioDiv.style.cssText = 'display:flex;gap:6px;align-items:center;margin-left:8px;';
    ioDiv.innerHTML =
      '<button onclick="var v=document.getElementById('preview-video');if(v)Editor.addSegmentIn(v.currentTime||0);" ' +
      'class="btn btn-ghost btn-sm" style="font-size:11px;padding:3px 10px;color:#10b981;" title="Set In Point">' +
      'I In</button>' +
      '<button onclick="var v=document.getElementById('preview-video');if(v)Editor.addSegmentOut(v.currentTime||0);" ' +
      'class="btn btn-ghost btn-sm" style="font-size:11px;padding:3px 10px;color:#ef4444;" title="Set Out Point">' +
      'O Out</button>';
    var firstChild = tlHeader.querySelector('.timeline-title');
    if (firstChild && firstChild.nextSibling) {
      tlHeader.insertBefore(ioDiv, firstChild.nextSibling);
    } else {
      tlHeader.appendChild(ioDiv);
    }
  }

});

// ── Draw IN / OUT markers on timeline ──
Timeline._drawInOutMarkers = function() {
  // Remove old markers
  var old = document.querySelectorAll('.inout-marker');
  old.forEach(function(m) { m.remove(); });

  var track = document.getElementById('timeline-track');
  if (!track) return;

  var pps = 40 * Timeline._zoomLevel;   // pixels per second

  // IN marker — green
  if (Timeline._inPoint !== null) {
    var inMarker = document.createElement('div');
    inMarker.className = 'inout-marker in-marker';
    inMarker.style.cssText = [
      'position:absolute',
      'top:0', 'bottom:0',
      'width:2px',
      'background:#10b981',
      'box-shadow:0 0 6px #10b981',
      'pointer-events:none',
      'z-index:4',
      'left:' + (Timeline._inPoint * pps) + 'px'
    ].join(';');

    // Label
    var inLabel = document.createElement('div');
    inLabel.style.cssText = 'position:absolute;top:2px;left:3px;font-size:9px;color:#10b981;font-weight:700;white-space:nowrap;';
    inLabel.textContent = 'IN ' + Timeline._inPoint.toFixed(2) + 's';
    inMarker.appendChild(inLabel);
    track.appendChild(inMarker);
  }

  // OUT marker — red
  if (Timeline._outPoint !== null) {
    var outMarker = document.createElement('div');
    outMarker.className = 'inout-marker out-marker';
    outMarker.style.cssText = [
      'position:absolute',
      'top:0', 'bottom:0',
      'width:2px',
      'background:#ef4444',
      'box-shadow:0 0 6px #ef4444',
      'pointer-events:none',
      'z-index:4',
      'left:' + (Timeline._outPoint * pps) + 'px'
    ].join(';');

    var outLabel = document.createElement('div');
    outLabel.style.cssText = 'position:absolute;top:2px;left:3px;font-size:9px;color:#ef4444;font-weight:700;white-space:nowrap;';
    outLabel.textContent = 'OUT ' + Timeline._outPoint.toFixed(2) + 's';
    outMarker.appendChild(outLabel);
    track.appendChild(outMarker);
  }

  // Shade the selected region between IN and OUT
  if (Timeline._inPoint !== null && Timeline._outPoint !== null && Timeline._outPoint > Timeline._inPoint) {
    var shade = document.createElement('div');
    shade.className = 'inout-marker inout-shade';
    var left  = Timeline._inPoint  * pps;
    var width = (Timeline._outPoint - Timeline._inPoint) * pps;
    shade.style.cssText = [
      'position:absolute',
      'top:0', 'bottom:0',
      'background:rgba(16,185,129,0.12)',
      'border-top:1px solid rgba(16,185,129,0.3)',
      'border-bottom:1px solid rgba(16,185,129,0.3)',
      'pointer-events:none',
      'z-index:3',
      'left:' + left + 'px',
      'width:' + width + 'px'
    ].join(';');
    track.appendChild(shade);
  }
};

// ── Context menu ──
Timeline._showContextMenu = function(x, y) {
  // Remove any existing menu
  var existing = document.getElementById('timeline-context-menu');
  if (existing) existing.remove();

  var v = document.getElementById('preview-video');
  var currentTime = v ? v.currentTime : 0;

  var menu = document.createElement('div');
  menu.id = 'timeline-context-menu';
  menu.style.cssText = [
    'position:fixed',
    'left:' + x + 'px',
    'top:' + y + 'px',
    'background:#1a1a2e',
    'border:1px solid rgba(255,255,255,0.12)',
    'border-radius:10px',
    'padding:6px',
    'z-index:1000',
    'box-shadow:0 8px 32px rgba(0,0,0,0.5)',
    'min-width:200px',
    'backdrop-filter:blur(20px)'
  ].join(';');

  var items = [
    {
      label: 'Set In Point here  [I]',
      color: '#10b981',
      action: function() {
        Timeline.setInPoint(currentTime);
        Timeline._drawInOutMarkers();
        UI.toast('In: ' + currentTime.toFixed(2) + 's', 'success', 1500);
      }
    },
    {
      label: 'Set Out Point here  [O]',
      color: '#ef4444',
      action: function() {
        Timeline.setOutPoint(currentTime);
        Timeline._drawInOutMarkers();
        UI.toast('Out: ' + currentTime.toFixed(2) + 's', 'success', 1500);
      }
    },
    { label: '──────────────', color: 'rgba(255,255,255,0.1)', action: null },
    {
      label: 'Trim to In/Out',
      color: '#a78bfa',
      action: function() { Editor.trimSelected(); }
    },
    {
      label: 'Split at Playhead',
      color: '#06b6d4',
      action: function() { Editor.splitAtPlayhead(); }
    },
    { label: '──────────────', color: 'rgba(255,255,255,0.1)', action: null },
    {
      label: 'Clear In/Out Points',
      color: '#9ca3af',
      action: function() {
        Timeline._inPoint  = null;
        Timeline._outPoint = null;
        Timeline._drawInOutMarkers();
        UI.toast('In/Out points cleared', 'info', 1500);
      }
    }
  ];

  items.forEach(function(item) {
    var el = document.createElement('div');
    if (!item.action) {
      // Separator
      el.style.cssText = 'height:1px;background:rgba(255,255,255,0.08);margin:4px 0;';
    } else {
      el.style.cssText = [
        'padding:8px 14px',
        'border-radius:6px',
        'cursor:pointer',
        'font-size:12px',
        'color:' + item.color,
        'transition:background 0.15s',
        'display:flex',
        'align-items:center',
        'gap:8px'
      ].join(';');
      el.textContent = item.label;
      el.addEventListener('mouseenter', function() {
        el.style.background = 'rgba(255,255,255,0.07)';
      });
      el.addEventListener('mouseleave', function() {
        el.style.background = 'transparent';
      });
      el.addEventListener('click', function(e) {
        e.stopPropagation();
        item.action();
        menu.remove();
      });
    }
    menu.appendChild(el);
  });

  document.body.appendChild(menu);

  // Auto close if menu goes off screen
  var rect = menu.getBoundingClientRect();
  if (rect.right > window.innerWidth) {
    menu.style.left = (x - rect.width) + 'px';
  }
  if (rect.bottom > window.innerHeight) {
    menu.style.top = (y - rect.height) + 'px';
  }
};
