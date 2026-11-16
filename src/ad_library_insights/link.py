"""Connect the program to Claude Code, from the page, on the user's own computer.

Three things are checked and, on request, done: Claude Code is installed, the MCP server of this
program is registered in the user's Claude Code configuration, and the skills of this program are
in the user's skills folder. Nothing here calls a model or sends anything to a server: it runs the
`claude` command the user already has, with an argument list and no shell, and copies local files.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

NAME = "ad-library-insights"
MCP_TIMEOUT = 20.0            # `claude mcp list` checks every server and can be slow
ADD_TIMEOUT = 60.0
SHOWN_SKILLS_FOLDER = "~/.claude/skills"    # what the page says; the real path is not shown


def default_skills_source() -> Path:
    """The skills folder shipped with the program (next to ``src`` in a source checkout)."""
    return Path(__file__).resolve().parents[2] / "skills"


@dataclass
class Settings:
    """Where things are. Tests replace these; the app uses the defaults."""

    skills_source: Path = field(default_factory=default_skills_source)
    skills_target: Path = field(default_factory=lambda: Path.home() / ".claude" / "skills")
    python: str = field(default_factory=lambda: sys.executable)
    mcp_timeout: float = MCP_TIMEOUT
    add_timeout: float = ADD_TIMEOUT


def find_claude() -> str | None:
    return shutil.which("claude")


def add_arguments(claude: str, python: str) -> list[str]:
    """The exact command, as an argument list: nothing goes through a shell."""
    return [claude, "mcp", "add", NAME, "--scope", "user", "--", python, "-m", "ad_library_insights"]


def shown_command(settings: Settings) -> str:
    """The command as the user would type it, with quoting for spaces."""
    args = add_arguments("claude", settings.python)
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    options: dict = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace",
                     "timeout": timeout, "stdin": subprocess.DEVNULL, "shell": False}
    if sys.platform.startswith("win"):
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(args, **options)


def mcp_state(claude: str, timeout: float = MCP_TIMEOUT) -> str:
    """``connected`` (listed), ``missing`` (not listed) or ``unknown`` (the command failed or was slow)."""
    try:
        done = _run([claude, "mcp", "list"], timeout)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if done.returncode != 0:
        return "unknown"
    listed = any(line.strip().startswith(f"{NAME}:") for line in done.stdout.splitlines())
    return "connected" if listed else "missing"


# --- skills --------------------------------------------------------------------------------

def _skill_files(source: Path) -> list[Path]:
    """Every file of every skill, relative to the skills folder."""
    if not source.is_dir():
        return []
    return sorted(path.relative_to(source) for path in source.rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts)


def skills_state(source: Path, target: Path) -> dict:
    """How the skills stand in the user's folder: ``installed`` when none is missing."""
    files = _skill_files(source)
    missing = [f for f in files if not (target / f).is_file()]
    differing = [f for f in files if (target / f).is_file() and (target / f).read_bytes() != (source / f).read_bytes()]
    return {"available": bool(files), "total": len(files), "missing": len(missing),
            "modified": [f.as_posix() for f in differing],
            "installed": bool(files) and not missing}


def install_skills(source: Path, target: Path, overwrite: bool = False) -> dict:
    """Copy the skills. A file that already exists and differs is kept unless ``overwrite``."""
    copied, kept = 0, []
    for rel in _skill_files(source):
        destination = target / rel
        if destination.is_file():
            if destination.read_bytes() == (source / rel).read_bytes():
                continue
            if not overwrite:
                kept.append(rel.as_posix())
                continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, destination)
        copied += 1
    return {"copied": copied, "kept": kept}


# --- the whole connection --------------------------------------------------------------------

def status(settings: Settings) -> dict:
    """The quick part of the state: no command is run."""
    claude = find_claude()
    return {"claude": bool(claude), "skills": skills_state(settings.skills_source, settings.skills_target),
            "command": shown_command(settings), "skills_folder": SHOWN_SKILLS_FOLDER}


def mcp_status(settings: Settings) -> dict:
    """The slow part: asks Claude Code which servers it knows."""
    claude = find_claude()
    return {"state": mcp_state(claude, settings.mcp_timeout) if claude else "no_claude"}


def connect(settings: Settings, overwrite_skills: bool = False) -> dict:
    """Register the server and copy the skills. Safe to repeat: what is done is not done again."""
    claude = find_claude()
    if not claude:
        return {"ok": False, "error": "claude_missing"}
    if mcp_state(claude, settings.mcp_timeout) == "connected":
        server = "already"
    else:
        try:
            done = _run(add_arguments(claude, settings.python), settings.add_timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "command_failed", "detail": "timeout"}
        except OSError as exc:
            return {"ok": False, "error": "command_failed", "detail": type(exc).__name__}
        said = (done.stderr or done.stdout or "").strip()
        if done.returncode == 0:
            server = "added"
        elif "already exists" in said:
            server = "already"
        else:
            return {"ok": False, "error": "command_failed", "detail": said[-400:]}
    try:
        skills = install_skills(settings.skills_source, settings.skills_target, overwrite_skills)
    except OSError as exc:
        return {"ok": False, "error": "skills_failed", "detail": type(exc).__name__, "server": server}
    return {"ok": True, "server": server, "skills": skills,
            "skills_available": bool(_skill_files(settings.skills_source))}
