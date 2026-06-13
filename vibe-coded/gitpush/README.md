# GitPush 🚀

A terminal UI tool to push any folder to GitHub — with smart cleanup built in. No more typing `git init`, `git add .`, `git commit`, `git push` every time.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Textual](https://img.shields.io/badge/UI-Textual-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## Features

- 📁 **Visual folder browser** — navigate and select any folder from a directory tree
- 🧹 **Smart cleanup** — auto-removes `__pycache__`, `.pyc`, `.log`, `node_modules` and more
- 🔒 **Sensitive file protection** — detects `.env`, `*.key`, `secrets.json` and adds them to `.gitignore`
- 👁 **Preview mode** — see exactly what will be deleted before committing
- ✍️ **Commit message input** — type your message directly in the UI
- 🌿 **Branch selector** — push to any branch (default: `main`)
- 💾 **Config memory** — remembers your last remote URL, folder, and settings
- 📋 **Live log panel** — streams git output in real time

---

## Installation

```bash
git clone https://github.com/yourusername/gitpush.git
cd gitpush
pip install -r requirements.txt
python main.py
```

---

## Requirements

```
textual>=0.47.0
```

Git must be installed and available in your PATH.

---

## Usage

1. Run `python main.py`
2. Browse and click a folder in the left panel
3. Paste your GitHub remote URL
4. Type a commit message
5. Click **Preview Cleanup** to see what will be removed
6. Click **Push to GitHub** — done

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+P` | Preview cleanup |
| `Ctrl+G` | Push to GitHub |
| `Ctrl+Q` | Quit |

---

## Project Structure

```
gitpush/
├── main.py            # Entry point
├── git_ops.py         # Git command wrappers
├── cleanup.py         # Junk + sensitive file removal
├── config_manager.py  # Persistent settings (config.json)
├── ui/
│   └── app.py         # Textual UI
├── config.json        # Auto-generated on first run
├── requirements.txt
└── README.md
```

---

## What Gets Cleaned

### Junk (deleted)
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`
- `node_modules/`, `venv/`, `.venv/`, `env/`
- `*.pyc`, `*.pyo`, `*.log`, `*.tmp`, `*.bak`
- `.DS_Store`, `Thumbs.db`

### Sensitive (added to .gitignore, NOT deleted)
- `.env`, `.env.local`, `.env.production`
- `*.pem`, `*.key`, `secrets.json`, `credentials.json`
- `token.json`, `*.p12`, `*.pfx`

---

## Contributing

Contributions welcome! Here are some ideas:

- [ ] AI commit message generator (uses diff to suggest a message)
- [ ] Branch creator / switcher
- [ ] `.gitignore` template selector (Python, Node, etc.)
- [ ] Multi-folder batch push
- [ ] GitHub authentication via token (no password prompts)
- [ ] Commit history viewer
- [ ] Dark/light theme toggle

Open an issue or submit a PR!

---

## License

MIT
