// ─────────────────────────────────────────────────────────────────
// FIX 1: In app.js — Replace the openCropOverlay() function
// Find the line:  async openCropOverlay() {
// Replace the entire function with this:
// ─────────────────────────────────────────────────────────────────

  async openCropOverlay() {
    UI.setStatus('Opening region selector...');
    UI.toast('Minimizing — draw a region anywhere on your screen!', 'info', 2000);
    console.log('[Capture] Opening Python tkinter region selector');

    // Step 1: Minimize SnapClip window so screen is visible
    await API.call('minimize_window');

    // Delay so window finishes minimizing before overlay appears
    await new Promise(r => setTimeout(r, 400));

    // Step 2: Open fullscreen tkinter overlay (blocks until done)
    const result = await API.call('open_region_selector');

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
      UI.toast('Region: ' + result.width + 'x' + result.height + ' selected!', 'success', 4000);
      UI.setStatus('Region ' + result.width + 'x' + result.height + ' — Ready to record');
    } else {
      UI.setStatus('Ready');
      UI.toast('Selection cancelled', 'info');
    }
  },


// ─────────────────────────────────────────────────────────────────
// FIX 2: In app.js — Replace browseSavePath() inside Export object
// Find:  browseSavePath() {
// Replace the entire function with this:
// ─────────────────────────────────────────────────────────────────

  async browseSavePath() {
    // Get current format for default filename
    const fmt = this._selectedFormat || 'mp4';
    const defaultName = 'snapclip_' + Date.now() + '.' + fmt;

    // Call Python native OS save dialog
    const result = await API.call('open_save_dialog', defaultName);

    if (result && result.success && result.path) {
      // Fill the path input with chosen path
      const pathInput = document.getElementById('save-path-input');
      if (pathInput) {
        pathInput.value = result.path;
      }
      UI.toast('Save location set!', 'success');
    } else {
      UI.toast('No location selected', 'info');
    }
  },


// ─────────────────────────────────────────────────────────────────
// FIX 3: In app.js — Replace browseExportPath() inside Export object
// Find:  browseExportPath() {
// Replace with:
// ─────────────────────────────────────────────────────────────────

  async browseExportPath() {
    const fmt = this._exportFormat || 'mp4';
    const defaultName = 'exported_' + Date.now() + '.' + fmt;

    const result = await API.call('open_save_dialog', defaultName);

    if (result && result.success && result.path) {
      const pathInput = document.getElementById('export-path-input');
      if (pathInput) {
        pathInput.value = result.path;
      }
      UI.toast('Export location set!', 'success');
    } else {
      UI.toast('No location selected', 'info');
    }
  },
