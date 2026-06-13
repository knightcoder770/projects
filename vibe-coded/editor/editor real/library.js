// ═══════════════════════════════════════════════════════════════
// SnapClip - frontend/js/library.js
// Clip Library Manager
//
// Responsibilities:
//   - Render clip cards in the sidebar library
//   - Handle clip selection → load into preview + timeline
//   - Add clips from file picker
//   - Remove clips from library
//   - Show thumbnails, duration, file size metadata
//   - Animate card entrance/exit
//   - Sync library state with backend clip list
//
// DSA Used:
//   - Map for O(1) clip lookup by path
//     Key: clip path string
//     Value: clip metadata object + DOM element reference
//   - Array for ordered clip list (preserves insertion order)
//
// Design:
//   Library is the source of truth for all saved clips.
//   Clicking a clip card: loads it into Player + adds to Timeline.
//   All clip metadata is kept in _clips Map for fast access.
// ═══════════════════════════════════════════════════════════════

'use strict';

const Library = {

  // ── Internal clip store ──
  // Map: clipPath → { meta, element }
  // O(1) lookup, update, delete by path
  _clips: new Map(),

  // ── DOM container ──
  get _container() {
    return document.getElementById('clip-library');
  },

  get _emptyState() {
    return document.getElementById('library-empty');
  },

  // ─────────────────────────────────────────────────────────────
  // ADD CLIP
  // Called after recording stops or from file picker
  // ─────────────────────────────────────────────────────────────

  /**
   * Add a clip to the library and render its card.
   *
   * @param {object} clipData - Clip metadata
   *   {
   *     path: string,          // Full file path (required)
   *     name: string,          // Display name (optional, derived from path)
   *     duration: number,      // Duration in seconds (optional)
   *     size_mb: number,       // File size in MB (optional)
   *     thumbnail: string,     // Path to thumbnail image (optional)
   *   }
   */
  addClip(clipData) {
    if (!clipData || !clipData.path) {
      console.warn('[Library] addClip: missing path');
      return;
    }

    // Skip if already in library (avoid duplicates)
    if (this._clips.has(clipData.path)) {
      console.log('[Library] Clip already in library:', clipData.path);
      return;
    }

    // Derive display name from path if not provided
    const name = clipData.name
      || clipData.path.split('/').pop()
      || clipData.path.split('\\').pop()
      || 'Untitled Clip';

    const meta = {
      path:      clipData.path,
      name:      name,
      duration:  clipData.duration  || 0,
      size_mb:   clipData.size_mb   || 0,
      thumbnail: clipData.thumbnail || null,
    };

    // Create DOM card
    const card = this._createCard(meta);

    // Store in Map: O(1) future access
    this._clips.set(meta.path, { meta, element: card });

    // Append to library container
    this._container.appendChild(card);

    // Hide empty state
    this._updateEmptyState();

    console.log(`[Library] Added clip: ${name} (${meta.size_mb}MB)`);
  },

  // ─────────────────────────────────────────────────────────────
  // CREATE CARD DOM ELEMENT
  // ─────────────────────────────────────────────────────────────

  /**
   * Build a clip card DOM element.
   *
   * @param {object} meta - Clip metadata
   * @returns {HTMLElement} The card element
   */
  _createCard(meta) {
    const card = document.createElement('div');
    card.className = 'clip-card';
    card.dataset.path = meta.path;     // Store path for easy retrieval

    // ── Format duration as M:SS ──
    const durStr = meta.duration > 0
      ? Library._formatDuration(meta.duration)
      : '--:--';

    // ── Format file size ──
    const sizeStr = meta.size_mb > 0
      ? `${meta.size_mb.toFixed(1)}MB`
      : '';

    // ── Thumbnail src ──
    // Use thumbnail if available, else show placeholder gradient
    const thumbStyle = meta.thumbnail
      ? `background-image: url('file://${meta.thumbnail}'); background-size: cover; background-position: center;`
      : `background: linear-gradient(135deg, rgba(124,58,237,0.3), rgba(6,182,212,0.2));`;

    card.innerHTML = `
      <!-- Thumbnail -->
      <div class="clip-thumb" style="${thumbStyle}"></div>

      <!-- Clip info -->
      <div class="clip-info">
        <div class="clip-name" title="${meta.name}">${meta.name}</div>
        <div class="clip-meta">
          ${durStr}
          ${sizeStr ? '· ' + sizeStr : ''}
        </div>
      </div>

      <!-- Action buttons (appear on hover) -->
      <div class="clip-actions">
        <button class="clip-action-btn add-to-timeline-btn" title="Add to Timeline">+</button>
        <button class="clip-action-btn delete remove-clip-btn" title="Remove from Library">✕</button>
      </div>
    `;

    // ── Attach button events using data-path (avoids backslash escaping) ──
    var addBtn = card.querySelector('.add-to-timeline-btn');
    var removeBtn = card.querySelector('.remove-clip-btn');

    addBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      Timeline.addClip(meta.path);
    });

    removeBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      Library.removeClip(meta.path);
    });

    // ── Click to load in preview ──
    card.addEventListener('click', () => {
      Library.selectClip(meta.path);
    });

    return card;
  },

  // ─────────────────────────────────────────────────────────────
  // SELECT CLIP
  // Load clip into preview player and update selection state
  // ─────────────────────────────────────────────────────────────

  async selectClip(clipPath) {
    // Update selected state in UI
    document.querySelectorAll('.clip-card').forEach(c => c.classList.remove('selected'));
    const entry = this._clips.get(clipPath);
    if (entry && entry.element) {
      entry.element.classList.add('selected');
    }

    // Load clip metadata from backend (updates cache)
    const meta = await API.call('load_clip_to_editor', clipPath);

    if (meta && meta.success) {
      // Load into player
      Player.loadClip(clipPath);

      // Update resolution badge
      UI.updateBadges(meta.width, meta.height, meta.fps?.toFixed(1) || '--');

      // Update timeline with this clip's duration info
      Timeline.setActiveDuration(meta.duration);

      UI.setStatus(`Loaded: ${clipPath.split('/').pop()}`);
      console.log(`[Library] Selected: ${clipPath}`);
    } else {
      // Still try to load even if metadata call failed
      Player.loadClip(clipPath);
    }
  },

  // ─────────────────────────────────────────────────────────────
  // REMOVE CLIP
  // Remove from library UI (does NOT delete the file)
  // ─────────────────────────────────────────────────────────────

  async removeClip(clipPath) {
    const entry = this._clips.get(clipPath);
    if (!entry) return;

    // Animate out
    const card = entry.element;
    card.style.opacity = '0';
    card.style.transform = 'translateX(-10px)';
    card.style.transition = 'all 0.2s ease';

    setTimeout(async () => {
      // Remove from DOM
      card.remove();

      // Remove from Map: O(1)
      this._clips.delete(clipPath);

      // Tell backend to remove from its library too
      await API.call('remove_clip_from_library', clipPath);

      // Show empty state if no clips left
      this._updateEmptyState();

      // If this was the selected clip, clear player
      if (AppState.selectedClipPath === clipPath) {
        AppState.selectedClipPath = null;
        const v = document.getElementById('preview-video');
        if (v) { v.src = ''; v.style.display = 'none'; }
        document.getElementById('preview-placeholder').style.display = 'flex';
      }

      console.log(`[Library] Removed: ${clipPath}`);
      UI.toast('Clip removed from library', 'info');
    }, 200);
  },

  // ─────────────────────────────────────────────────────────────
  // ADD FROM FILE PICKER
  // Let user browse for an existing video file
  // ─────────────────────────────────────────────────────────────

  async addClipFromFile() {
    // pywebview doesn't have a built-in file picker exposed directly to JS
    // We trigger it via the backend which uses tkinter or native dialog
    // For now, show a path input prompt
    const path = prompt('Enter video file path (e.g. /home/user/video.mp4):');
    if (!path || !path.trim()) return;

    const cleanPath = path.trim();

    // Load metadata to verify the file
    UI.setStatus('Loading file…');
    const meta = await API.call('load_clip_to_editor', cleanPath);

    if (meta && meta.success) {
      this.addClip({
        path:     cleanPath,
        duration: meta.duration,
        size_mb:  meta.file_size_mb,
      });
      UI.toast('Clip added to library!', 'success');
    } else {
      UI.toast(`Could not load file: ${meta?.message || 'Invalid path'}`, 'error');
    }

    UI.setStatus('Ready');
  },

  // ─────────────────────────────────────────────────────────────
  // REFRESH CLIP META
  // Update a clip's metadata in the library after an edit
  // ─────────────────────────────────────────────────────────────

  refreshClipMeta(newPath) {
    // After an effect is applied, a new file is created at newPath
    // Add it to the library as a new clip
    if (newPath && !this._clips.has(newPath)) {
      this.addClip({ path: newPath });
    }
  },

  // ─────────────────────────────────────────────────────────────
  // UTILITIES
  // ─────────────────────────────────────────────────────────────

  _updateEmptyState() {
    const empty = this._emptyState;
    if (!empty) return;
    empty.style.display = this._clips.size === 0 ? 'flex' : 'none';
  },

  _formatDuration(seconds) {
    // Format as M:SS or H:MM:SS
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
      return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }
    return `${m}:${String(s).padStart(2,'0')}`;
  },

  getClipCount() {
    return this._clips.size;
  },

  getAllPaths() {
    return Array.from(this._clips.keys());
  },

  getClipMeta(path) {
    return this._clips.get(path)?.meta || null;
  }
};
