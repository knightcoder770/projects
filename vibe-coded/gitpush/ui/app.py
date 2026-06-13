import string
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, Input, Label,
    Checkbox, Static, DirectoryTree, Log, Select
)
from textual import work

sys.path.insert(0, str(Path(__file__).parent.parent))

import config_manager
from cleanup import run_cleanup, preview_cleanup
from git_ops import full_push_pipeline, git_get_changed_files, git_get_current_branch


def get_available_drives() -> list[tuple[str, str]]:
    """
    Return list of (label, value) tuples for all available drives.
    Works on Windows (A-Z scan) and Linux/Mac (uses home + common mounts).
    """
    drives = []
    if sys.platform == "win32":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:\\"
                drives.append((drive, drive))
            bitmask >>= 1
    else:
        drives = [
            ("Home (~)", str(Path.home())),
            ("Root (/)", "/"),
        ]
        for mount_parent in [Path("/mnt"), Path("/media")]:
            if mount_parent.exists():
                for child in sorted(mount_parent.iterdir()):
                    if child.is_dir():
                        drives.append((str(child), str(child)))

    return drives if drives else [("Home", str(Path.home()))]


CSS = """
Screen {
    background: $surface;
}

#app-grid {
    layout: grid;
    grid-size: 2;
    grid-columns: 1fr 2fr;
    height: 100%;
}

#left-panel {
    border: solid $primary;
    padding: 1;
    height: 100%;
}

#right-panel {
    padding: 1;
    height: 100%;
}

#drive-label {
    color: $text-muted;
    margin-bottom: 0;
}

#drive-select {
    margin-bottom: 1;
    height: 3;
}

#folder-label {
    color: $text-muted;
    margin-bottom: 0;
}

#selected-folder {
    background: $surface-darken-1;
    color: $success;
    padding: 0 1;
    margin-bottom: 1;
    height: 3;
    border: solid $success;
    content-align: left middle;
}

DirectoryTree {
    height: 1fr;
    border: solid $primary-darken-2;
}

.section-title {
    color: $accent;
    text-style: bold;
    margin-top: 1;
    margin-bottom: 0;
}

.input-label {
    color: $text-muted;
    margin-top: 1;
}

Input {
    margin-bottom: 0;
}

#checkboxes {
    layout: horizontal;
    height: auto;
    margin-top: 1;
}

#checkboxes Checkbox {
    margin-right: 2;
}

#selective-section {
    height: auto;
    margin-top: 1;
}

#selective-header {
    layout: horizontal;
    height: auto;
    margin-bottom: 0;
}

#btn-load-files {
    margin-left: 1;
    min-width: 16;
    height: 3;
}

#file-list-container {
    height: 8;
    border: solid $primary-darken-2;
    background: $surface-darken-2;
    padding: 0 1;
    margin-top: 0;
    display: none;
}

#file-list-container.visible {
    display: block;
}

.file-row {
    height: 1;
    layout: horizontal;
}

.file-status {
    color: $warning;
    width: 12;
}

.file-checkbox {
    width: 1fr;
}

#action-buttons {
    layout: horizontal;
    height: auto;
    margin-top: 1;
}

#btn-preview {
    background: $warning-darken-2;
    border: solid $warning;
    margin-right: 1;
}

#btn-push {
    background: $success-darken-2;
    border: solid $success;
    margin-right: 1;
}

#btn-clear {
    background: $surface-darken-2;
    border: solid $primary-darken-2;
}

#log-title {
    color: $accent;
    text-style: bold;
    margin-top: 1;
}

#output-log {
    height: 1fr;
    border: solid $primary-darken-2;
    background: $surface-darken-2;
}

#status-bar {
    color: $text-muted;
    margin-top: 1;
    height: 1;
}
"""


class GitPushApp(App):
    """GitPush — push any folder to GitHub without touching the terminal."""

    CSS = CSS
    TITLE = "GitPush"
    SUB_TITLE = "Smart Git Pusher"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+p", "preview", "Preview Cleanup"),
        ("ctrl+g", "push", "Push to GitHub"),
    ]

    def __init__(self):
        super().__init__()
        self.selected_folder: str = ""
        self.config = config_manager.load_config()
        self.drives = get_available_drives()
        # Tracks file checkboxes: {filepath: Checkbox widget}
        self._file_checkboxes: dict[str, Checkbox] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="app-grid"):

            # LEFT — drive switcher + folder browser
            with Vertical(id="left-panel"):
                yield Label("💾 Drive", id="drive-label")
                yield Select(
                    options=self.drives,
                    value=self.drives[0][1],
                    id="drive-select",
                    allow_blank=False,
                )
                yield Label("📁 Selected Folder", id="folder-label")
                yield Static(
                    self.config.get("last_folder") or "Click a folder in the tree",
                    id="selected-folder"
                )
                yield DirectoryTree(self.drives[0][1], id="dir-tree")

            # RIGHT — settings + log
            with Vertical(id="right-panel"):
                yield Static("⚙️  Settings", classes="section-title")

                yield Label("GitHub Remote URL", classes="input-label")
                yield Input(
                    placeholder="https://github.com/username/repo.git",
                    value=self.config.get("last_remote_url", ""),
                    id="remote-url",
                )

                yield Label("Commit Message", classes="input-label")
                yield Input(
                    placeholder="Update via GitPush",
                    id="commit-msg",
                )

                yield Label("Branch", classes="input-label")
                yield Input(
                    placeholder="main",
                    value=self.config.get("default_branch", "main"),
                    id="branch",
                )

                with Horizontal(id="checkboxes"):
                    yield Checkbox(
                        "Remove __pycache__ & junk",
                        value=self.config.get("remove_junk", True),
                        id="chk-junk"
                    )
                    yield Checkbox(
                        "Protect sensitive files (.env etc)",
                        value=self.config.get("protect_sensitive", True),
                        id="chk-sensitive"
                    )

                # Selective file staging section
                with Vertical(id="selective-section"):
                    with Horizontal(id="selective-header"):
                        yield Checkbox(
                            "Stage specific files only",
                            value=False,
                            id="chk-selective"
                        )
                        yield Button("🔄 Load changed files", id="btn-load-files")

                    with ScrollableContainer(id="file-list-container"):
                        yield Static(
                            "Click 'Load changed files' to see what's changed.",
                            id="file-list-placeholder"
                        )

                with Horizontal(id="action-buttons"):
                    yield Button("👁  Preview Cleanup", id="btn-preview", variant="warning")
                    yield Button("🚀 Push to GitHub", id="btn-push", variant="success")
                    yield Button("🧹 Clear Log", id="btn-clear")

                yield Static("📋  Output Log", id="log-title")
                yield Log(id="output-log", auto_scroll=True)
                yield Static("Ready. Select a drive then pick a folder.", id="status-bar")

        yield Footer()

    # ── Event Handlers ──────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        """User switched drive — reload the directory tree."""
        if event.select.id == "drive-select" and event.value:
            drive_path = str(event.value)
            tree = self.query_one("#dir-tree", DirectoryTree)
            tree.path = Path(drive_path)
            self.selected_folder = ""
            self._file_checkboxes.clear()
            self.query_one("#selected-folder", Static).update("Click a folder in the tree")
            self.query_one("#status-bar", Static).update(f"Browsing: {drive_path}")

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """User clicked a folder — update selection and auto-detect branch if it is a git repo."""
        self.selected_folder = str(event.path)
        self._file_checkboxes.clear()
        self.query_one("#selected-folder", Static).update(self.selected_folder)
        config_manager.update_config(last_folder=self.selected_folder)

        # Auto-detect branch for existing git repos and update the branch input
        from git_ops import is_git_repo
        if is_git_repo(self.selected_folder):
            detected = git_get_current_branch(self.selected_folder)
            self.query_one("#branch", Input).value = detected
            self.query_one("#status-bar", Static).update(
                f"Selected: {self.selected_folder}  |  branch: {detected}"
            )
        else:
            self.query_one("#status-bar", Static).update(f"Selected: {self.selected_folder}")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Show/hide file list when selective mode toggled."""
        if event.checkbox.id == "chk-selective":
            container = self.query_one("#file-list-container")
            if event.value:
                container.add_class("visible")
            else:
                container.remove_class("visible")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Save remote URL and branch to config on change."""
        if event.input.id == "remote-url":
            config_manager.update_config(last_remote_url=event.value)
        elif event.input.id == "branch":
            config_manager.update_config(default_branch=event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-load-files":
            self._load_changed_files()
        elif event.button.id == "btn-preview":
            self.action_preview()
        elif event.button.id == "btn-push":
            self.action_push()
        elif event.button.id == "btn-clear":
            self.query_one("#output-log", Log).clear()

    # ── Actions ─────────────────────────────────────────────────

    def action_preview(self) -> None:
        if not self.selected_folder:
            self._log("⚠️  No folder selected. Pick one from the tree.")
            return
        self._run_preview()

    def action_push(self) -> None:
        if not self._validate_inputs():
            return
        self._run_push()

    # ── File List Loader ─────────────────────────────────────────

    @work(thread=True)
    def _load_changed_files(self) -> None:
        """Fetch changed files from git and populate the checkbox list."""
        if not self.selected_folder:
            self._log("⚠️  Select a folder first before loading files.")
            return

        self._set_status("Loading changed files...")
        files = git_get_changed_files(self.selected_folder)

        # Update UI on main thread
        self.call_from_thread(self._populate_file_list, files)

    def _populate_file_list(self, files: list[dict]) -> None:
        """Rebuild the file checklist in the UI (runs on main thread via call_from_thread)."""
        container = self.query_one("#file-list-container", ScrollableContainer)
        self._file_checkboxes.clear()

        # Remove old widgets
        container.remove_children()

        if not files:
            container.mount(Static("✓  No changed files detected. All clean!"))
            self._write_status("No changes found.")
            return

        # Mount a checkbox per file
        for item in files:
            filepath = item["path"]
            status = item["status"]
            cb = Checkbox(f"[{status}]  {filepath}", value=True)
            self._file_checkboxes[filepath] = cb
            container.mount(cb)

        # Make sure the container is visible
        self.query_one("#chk-selective", Checkbox).value = True
        self._write_status(f"Found {len(files)} changed file(s). Uncheck to exclude.")

    def _get_selected_files(self) -> list[str] | None:
        """
        Return list of checked filepaths, or None if selective mode is off.
        None means 'stage everything'.
        """
        selective_mode = self.query_one("#chk-selective", Checkbox).value
        if not selective_mode:
            return None

        selected = [
            filepath
            for filepath, cb in self._file_checkboxes.items()
            if cb.value
        ]
        return selected

    # ── Workers ──────────────────────────────────────────────────

    @work(thread=True)
    def _run_preview(self) -> None:
        self._log("─" * 50)
        self._log(f"🔍 Previewing cleanup for: {self.selected_folder}")
        preview = preview_cleanup(self.selected_folder)

        junk_folders = preview["junk_folders"]
        junk_files = preview["junk_files"]
        sensitive = preview["sensitive_files"]

        if junk_folders:
            self._log(f"\n🗑  Junk folders ({len(junk_folders)}):")
            for p in junk_folders:
                self._log(f"   {p}")
        else:
            self._log("✓  No junk folders found.")

        if junk_files:
            self._log(f"\n🗑  Junk files ({len(junk_files)}):")
            for p in junk_files:
                self._log(f"   {p}")
        else:
            self._log("✓  No junk files found.")

        if sensitive:
            self._log(f"\n🔒 Sensitive files ({len(sensitive)}) — will be added to .gitignore:")
            for p in sensitive:
                self._log(f"   {p}")
        else:
            self._log("✓  No sensitive files found.")

        self._log("\nRun 'Push to GitHub' to apply cleanup + push.")
        self._set_status("Preview complete.")

    @work(thread=True)
    def _run_push(self) -> None:
        folder = self.selected_folder
        remote_url = self.query_one("#remote-url", Input).value.strip()
        commit_msg = self.query_one("#commit-msg", Input).value.strip() or "Update via GitPush"
        branch = self.query_one("#branch", Input).value.strip() or "main"
        remove_junk = self.query_one("#chk-junk", Checkbox).value
        protect_sensitive = self.query_one("#chk-sensitive", Checkbox).value
        specific_files = self._get_selected_files()

        self._log("─" * 50)
        self._log(f"📁 Folder   : {folder}")
        self._log(f"🔗 Remote   : {remote_url}")
        self._log(f"📝 Message  : {commit_msg}")
        self._log(f"🌿 Branch   : {branch}")

        if specific_files is not None:
            self._log(f"📄 Staging  : {len(specific_files)} selected file(s)")
            for f in specific_files:
                self._log(f"   {f}")
        else:
            self._log("📄 Staging  : all files")

        self._log("")

        # Guard: if selective mode but nothing checked
        if specific_files is not None and len(specific_files) == 0:
            self._log("⚠️  No files selected. Check at least one file to stage.")
            self._set_status("⚠️  No files checked.")
            return

        # Cleanup phase
        self._log("🧹 Running cleanup...")
        cleanup_log = run_cleanup(folder, remove_junk, protect_sensitive)
        for line in cleanup_log:
            self._log(line)

        self._log("")

        # Git pipeline
        self._log("🚀 Starting git pipeline...")
        steps = full_push_pipeline(
            folder_path=folder,
            remote_url=remote_url,
            commit_message=commit_msg,
            branch=branch,
            specific_files=specific_files,
        )

        all_ok = True
        for step_name, success, output in steps:
            icon = "✅" if success else "❌"
            self._log(f"\n{icon} {step_name}")
            if output:
                for line in output.splitlines():
                    self._log(f"   {line}")
            if not success:
                all_ok = False
                break

        self._log("")
        if all_ok:
            self._log("🎉 Successfully pushed to GitHub!")
            self._set_status("✅ Push complete!")
        else:
            self._log("❌ Push failed. Check the log above for details.")
            self._set_status("❌ Push failed. See log.")

    # ── Helpers ──────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        """Thread-safe log write."""
        self.call_from_thread(self._write_log, message)

    def _write_log(self, message: str) -> None:
        self.query_one("#output-log", Log).write_line(message)

    def _set_status(self, message: str) -> None:
        self.call_from_thread(self._write_status, message)

    def _write_status(self, message: str) -> None:
        self.query_one("#status-bar", Static).update(message)

    def _validate_inputs(self) -> bool:
        if not self.selected_folder:
            self._log("⚠️  No folder selected. Pick one from the tree on the left.")
            return False

        remote_url = self.query_one("#remote-url", Input).value.strip()
        if not remote_url:
            self._log("⚠️  GitHub remote URL is required.")
            return False

        if not remote_url.startswith("https://") and not remote_url.startswith("git@"):
            self._log("⚠️  Remote URL should start with https:// or git@")
            return False

        return True
