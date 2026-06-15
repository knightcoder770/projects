import sys
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
import config_manager

gitpush_bp = Blueprint("gitpush", __name__)


def get_gitpush_module():
    """Dynamically import git_ops from the configured GitPush path."""
    gitpush_path = config_manager.get("gitpush_path")
    if not gitpush_path:
        return None, "GitPush path not configured. Go to Settings."

    if gitpush_path not in sys.path:
        sys.path.insert(0, gitpush_path)

    try:
        import importlib
        import git_ops
        importlib.reload(git_ops)
        return git_ops, None
    except ImportError as e:
        return None, f"Could not import GitPush: {e}"


def get_cleanup_module():
    """Dynamically import cleanup from the configured GitPush path."""
    gitpush_path = config_manager.get("gitpush_path")
    if not gitpush_path:
        return None

    if gitpush_path not in sys.path:
        sys.path.insert(0, gitpush_path)

    try:
        import importlib
        import cleanup
        importlib.reload(cleanup)
        return cleanup
    except ImportError:
        return None


@gitpush_bp.route("/gitpush")
def gitpush():
    if not config_manager.is_setup_complete():
        return redirect(url_for("setup.setup"))

    cfg = config_manager.load_config()
    git_ops, error = get_gitpush_module()
    connected = git_ops is not None

    return render_template(
        "gitpush.html",
        cfg=cfg,
        connected=connected,
        error=error,
    )


@gitpush_bp.route("/api/gitpush/changed-files", methods=["POST"])
def changed_files():
    body = request.get_json()
    folder = body.get("folder", "").strip()

    if not folder or not Path(folder).exists():
        return jsonify({"ok": False, "error": "Folder not found"}), 400

    git_ops, error = get_gitpush_module()
    if not git_ops:
        return jsonify({"ok": False, "error": error}), 500

    files = git_ops.git_get_changed_files(folder)

    # Clean paths and filter out __pycache__ and .pyc
    cleaned = []
    for f in files:
        path = f["path"].strip().strip('"').strip("'")
        if "__pycache__" in path or path.endswith(".pyc") or path.endswith(".pyo"):
            continue
        cleaned.append({"status": f["status"], "path": path})

    return jsonify({"ok": True, "files": cleaned})


@gitpush_bp.route("/api/gitpush/preview-cleanup", methods=["POST"])
def preview_cleanup():
    body = request.get_json()
    folder = body.get("folder", "").strip()

    if not folder or not Path(folder).exists():
        return jsonify({"ok": False, "error": "Folder not found"}), 400

    cleanup = get_cleanup_module()
    if not cleanup:
        return jsonify({"ok": False, "error": "Cleanup module not found"}), 500

    preview = cleanup.preview_cleanup(folder)
    return jsonify({
        "ok": True,
        "junk_folders": len(preview["junk_folders"]),
        "junk_files": len(preview["junk_files"]),
        "sensitive_files": [str(p) for p in preview["sensitive_files"]],
    })


@gitpush_bp.route("/api/gitpush/push", methods=["POST"])
def push():
    body = request.get_json()
    folder = body.get("folder", "").strip()
    remote_url = body.get("remote_url", "").strip()
    commit_msg = body.get("commit_message", "Update via CodeLife").strip()
    branch = body.get("branch", "main").strip()
    specific_files_raw = body.get("specific_files", None)
    # Extract from wrapper object to avoid JSON array first-element corruption
    if specific_files_raw and isinstance(specific_files_raw, dict):
        specific_files = specific_files_raw.get("files", [])
    elif specific_files_raw and isinstance(specific_files_raw, list):
        specific_files = specific_files_raw
    else:
        specific_files = None
    if specific_files:
        specific_files = [f.strip() for f in specific_files if f and f.strip()]
    remove_junk = body.get("remove_junk", True)
    protect_sensitive = body.get("protect_sensitive", True)

    if not folder or not Path(folder).exists():
        return jsonify({"ok": False, "error": "Folder not found"}), 400
    if not remote_url:
        return jsonify({"ok": False, "error": "Remote URL required"}), 400

    git_ops, error = get_gitpush_module()
    if not git_ops:
        return jsonify({"ok": False, "error": error}), 500

    cleanup = get_cleanup_module()
    log = []

    # Cleanup phase
    if cleanup:
        cleanup_log = cleanup.run_cleanup(folder, remove_junk, protect_sensitive)
        log.extend(cleanup_log)

    # Log exact paths being staged for debugging
    if specific_files:
        log.append(f"📄 Staging paths received:")
        for f in specific_files:
            log.append(f"   [{repr(f)}]")

    # Git pipeline
    steps = git_ops.full_push_pipeline(
        folder_path=folder,
        remote_url=remote_url,
        commit_message=commit_msg,
        branch=branch,
        specific_files=specific_files if specific_files else None,
    )

    all_ok = True
    for step_name, success, output in steps:
        icon = "✅" if success else "❌"
        log.append(f"{icon} {step_name}")
        if output:
            for line in output.splitlines():
                log.append(f"   {line}")
        if not success:
            all_ok = False
            break

    return jsonify({"ok": all_ok, "log": log})


@gitpush_bp.route("/api/gitpush/detect-branch", methods=["POST"])
def detect_branch():
    body = request.get_json()
    folder = body.get("folder", "").strip()

    git_ops, error = get_gitpush_module()
    if not git_ops:
        return jsonify({"branch": "main"})

    try:
        branch = git_ops.git_get_current_branch(folder)
        return jsonify({"branch": branch})
    except Exception:
        return jsonify({"branch": "main"})
