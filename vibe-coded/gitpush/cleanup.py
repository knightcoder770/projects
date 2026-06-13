import shutil
from pathlib import Path


# Folders to delete entirely
JUNK_FOLDERS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".tox",
    "dist",
    "build",
    "*.egg-info",
    ".eggs",
    "venv",
    ".venv",
    "env",
}

# File patterns to delete
JUNK_FILES = {
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.log",
    "*.tmp",
    "*.bak",
    "*.swp",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

# Sensitive files — moved to .gitignore instead of deleted
SENSITIVE_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "*.pem",
    "*.key",
    "secrets.json",
    "credentials.json",
    "token.json",
    "*.p12",
    "*.pfx",
}


def find_junk_folders(root: Path) -> list[Path]:
    """Find all junk folders recursively."""
    found = []
    for folder in JUNK_FOLDERS:
        found.extend(root.rglob(folder))
    return [p for p in found if p.is_dir()]


def find_junk_files(root: Path) -> list[Path]:
    """Find all junk files recursively."""
    found = []
    for pattern in JUNK_FILES:
        found.extend(root.rglob(pattern))
    return [p for p in found if p.is_file()]


def find_sensitive_files(root: Path) -> list[Path]:
    """Find all sensitive files recursively."""
    found = []
    for pattern in SENSITIVE_FILES:
        found.extend(root.rglob(pattern))
    return [p for p in found if p.is_file()]


def preview_cleanup(folder_path: str) -> dict:
    """
    Return a preview of what will be cleaned — no deletion happens here.
    Returns dict with keys: junk_folders, junk_files, sensitive_files.
    """
    root = Path(folder_path)
    return {
        "junk_folders": find_junk_folders(root),
        "junk_files": find_junk_files(root),
        "sensitive_files": find_sensitive_files(root),
    }


def delete_junk_folders(root: Path) -> list[str]:
    """Delete all junk folders. Returns list of deleted paths."""
    deleted = []
    for folder in find_junk_folders(root):
        try:
            shutil.rmtree(folder)
            deleted.append(str(folder))
        except Exception as e:
            deleted.append(f"FAILED: {folder} — {e}")
    return deleted


def delete_junk_files(root: Path) -> list[str]:
    """Delete all junk files. Returns list of deleted paths."""
    deleted = []
    for file in find_junk_files(root):
        try:
            file.unlink()
            deleted.append(str(file))
        except Exception as e:
            deleted.append(f"FAILED: {file} — {e}")
    return deleted


def add_to_gitignore(root: Path, entries: list[str]) -> str:
    """Add sensitive file patterns to .gitignore."""
    gitignore_path = root / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.exists() else ""

    new_entries = [e for e in entries if e not in existing]
    if not new_entries:
        return "All sensitive patterns already in .gitignore."

    with open(gitignore_path, "a") as f:
        f.write("\n# Added by GitPush — sensitive files\n")
        for entry in new_entries:
            f.write(f"{entry}\n")

    return f"Added {len(new_entries)} entries to .gitignore."


def run_cleanup(folder_path: str, remove_junk: bool = True, protect_sensitive: bool = True) -> list[str]:
    """
    Run the full cleanup pipeline.
    Returns a list of log messages describing what was done.
    """
    root = Path(folder_path)
    log = []

    if remove_junk:
        deleted_folders = delete_junk_folders(root)
        deleted_files = delete_junk_files(root)

        if deleted_folders:
            log.append(f"🗑  Deleted {len(deleted_folders)} junk folder(s):")
            log.extend([f"   {p}" for p in deleted_folders])
        else:
            log.append("✓  No junk folders found.")

        if deleted_files:
            log.append(f"🗑  Deleted {len(deleted_files)} junk file(s):")
            log.extend([f"   {p}" for p in deleted_files])
        else:
            log.append("✓  No junk files found.")

    if protect_sensitive:
        sensitive = find_sensitive_files(root)
        patterns = list(SENSITIVE_FILES)
        result = add_to_gitignore(root, patterns)
        log.append(f"🔒 {result}")
        if sensitive:
            log.append(f"⚠️  Found {len(sensitive)} sensitive file(s) — added to .gitignore but NOT deleted:")
            log.extend([f"   {p}" for p in sensitive])

    return log
