import subprocess
from pathlib import Path


def run_command(command: list[str], cwd: str) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except FileNotFoundError:
        return False, f"Command not found: {command[0]}. Is git installed?"
    except Exception as e:
        return False, str(e)


def is_git_repo(folder_path: str) -> bool:
    """Check if folder is already a git repository."""
    return (Path(folder_path) / ".git").exists()


def git_init(folder_path: str) -> tuple[bool, str]:
    """Initialize a git repository in the given folder."""
    return run_command(["git", "init"], cwd=folder_path)


def git_set_remote(folder_path: str, remote_url: str) -> tuple[bool, str]:
    """Set or update the remote origin URL."""
    run_command(["git", "remote", "remove", "origin"], cwd=folder_path)
    return run_command(["git", "remote", "add", "origin", remote_url], cwd=folder_path)


def git_add_all(folder_path: str) -> tuple[bool, str]:
    """Stage all files."""
    return run_command(["git", "add", "."], cwd=folder_path)


def git_add_specific(folder_path: str, files: list[str]) -> tuple[bool, str]:
    """Stage only the given list of file paths."""
    if not files:
        return False, "No files provided to stage."
    return run_command(["git", "add", "--"] + files, cwd=folder_path)


def git_get_changed_files(folder_path: str) -> list[dict]:
    """
    Return list of changed/untracked files using git status --porcelain.
    Each item: {"status": "M"/"??"/etc, "path": "relative/path.py"}
    Returns empty list if not a git repo or no changes.
    """
    # Init repo silently first so status works even on fresh folders
    if not is_git_repo(folder_path):
        git_init(folder_path)
        git_set_user_config(folder_path)

    success, output = run_command(["git", "status", "--porcelain"], cwd=folder_path)
    if not success or not output:
        return []

    files = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        # git porcelain gives 2-char XY status codes (e.g. "MM", "??", " M", "AD")
        xy = line[:2]
        filepath = line[3:].strip()

        # Decode both X (index/staged) and Y (worktree) status chars
        char_map = {
            "?": "New",
            "M": "Modified",
            "A": "Added",
            "D": "Deleted",
            "R": "Renamed",
            "C": "Copied",
            "U": "Conflict",
            " ": "",
        }

        x_label = char_map.get(xy[0], xy[0])
        y_label = char_map.get(xy[1], xy[1])

        if xy == "??": 
            label = "New"
        elif x_label and y_label and x_label != y_label:
            label = f"{x_label}+{y_label}"
        else:
            label = x_label or y_label or xy

        files.append({"status": label, "path": filepath})

    return files


def git_commit(folder_path: str, message: str) -> tuple[bool, str]:
    """Commit staged files with the given message."""
    return run_command(["git", "commit", "-m", message], cwd=folder_path)


def git_push(folder_path: str, branch: str = "main") -> tuple[bool, str]:
    """Push to remote origin."""
    return run_command(["git", "push", "-u", "origin", branch], cwd=folder_path)


def git_get_current_branch(folder_path: str) -> str:
    """Detect the actual current branch name (master, main, etc)."""
    success, output = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=folder_path)
    if success and output and output != "HEAD":
        return output.strip()
    return "main"  # fallback


def git_pull(folder_path: str, branch: str = "main") -> tuple[bool, str]:
    """Pull latest from remote before pushing (handles existing repos)."""
    return run_command(
        ["git", "pull", "origin", branch, "--allow-unrelated-histories"],
        cwd=folder_path
    )


def git_set_user_config(folder_path: str) -> None:
    """Ensure git user config exists locally — avoids 'who are you?' errors."""
    run_command(["git", "config", "user.email", "gitpush@local.dev"], cwd=folder_path)
    run_command(["git", "config", "user.name", "GitPush"], cwd=folder_path)


def git_get_log(folder_path: str, count: int = 5) -> tuple[bool, str]:
    """Get last N commit messages."""
    return run_command(
        ["git", "log", f"-{count}", "--oneline"],
        cwd=folder_path
    )


def full_push_pipeline(
    folder_path: str,
    remote_url: str,
    commit_message: str,
    branch: str = "main",
    specific_files: list[str] | None = None,
) -> list[tuple[str, bool, str]]:
    """
    Run the full git pipeline. Returns list of (step_name, success, output).
    If specific_files is provided, only those files are staged instead of everything.
    Handles both fresh repos and repos that already exist on GitHub.
    """
    steps = []
    already_existed = is_git_repo(folder_path)

    # Step 1: Init if not already a repo
    if not already_existed:
        success, output = git_init(folder_path)
        steps.append(("git init", success, output))
        if not success:
            return steps
    else:
        steps.append(("git init", True, "Already a git repository — skipping init."))

    # Step 1.5: Ensure git user config exists
    git_set_user_config(folder_path)

    # Step 2: Set remote
    success, output = git_set_remote(folder_path, remote_url)
    steps.append(("set remote", success, output))
    if not success:
        return steps

    # Step 3: Stage files (all or specific)
    if specific_files:
        success, output = git_add_specific(folder_path, specific_files)
        steps.append((f"git add ({len(specific_files)} file(s))", success, output))
    else:
        success, output = git_add_all(folder_path)
        steps.append(("git add .", success, output))
    if not success:
        return steps

    # Step 4: Commit
    success, output = git_commit(folder_path, commit_message)
    nothing_to_commit = "nothing to commit" in output
    if not success and not nothing_to_commit:
        steps.append(("git commit", False, output))
        return steps
    steps.append(("git commit", True, output))

    # Step 5: Auto-detect real branch if user left it as default
    actual_branch = git_get_current_branch(folder_path)
    if branch in ("main", "master") and actual_branch not in ("main", "master"):
        # Repo uses a custom branch — trust git over the input field
        branch = actual_branch
    elif branch == "main" and actual_branch == "master":
        # Very common case: repo uses master, UI defaulted to main
        branch = "master"
    steps.append((f"branch detected", True, f"Using branch: {branch}"))

    # Step 6: Pull first if repo already existed on GitHub (prevents rejection)
    if already_existed:
        success, output = git_pull(folder_path, branch)
        # Pull failure (e.g. empty remote, wrong ref) must not block push
        steps.append(("git pull", True, output if output else "Pull complete."))

    # Step 7: Push
    success, output = git_push(folder_path, branch)
    steps.append(("git push", success, output))

    return steps
