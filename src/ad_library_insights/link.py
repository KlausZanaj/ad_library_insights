"""Connect the program to Claude Code, from the page, on the user's own computer.

Three things are checked and, on request, done: Claude Code is installed, the MCP server of this
program is registered in the user's Claude Code configuration, and the skills and specialist
sub-agents of this program are in the user's Claude folder. Nothing here calls a model or sends
anything to a server: it runs the `claude` command the user already has, with an argument list and
no shell, and copies local files.
"""
from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

NAME = "ad-library-insights"
MCP_TIMEOUT = 8.0             # `claude mcp list` checks every server and can be slow
ADD_TIMEOUT = 60.0
SHOWN_SKILLS_FOLDER = "~/.claude/skills"    # what the page says; the real path is not shown


def default_skills_source() -> Path:
    """The skills folder shipped with the program (next to ``src`` in a source checkout)."""
    return Path(__file__).resolve().parents[2] / "skills"


def default_agents_source() -> Path:
    """The specialist sub-agents shipped with the program (``.claude/agents``)."""
    return Path(__file__).resolve().parents[2] / ".claude" / "agents"


@dataclass
class Settings:
    """Where things are. Tests replace these; the app uses the defaults."""

    skills_source: Path = field(default_factory=default_skills_source)
    skills_target: Path = field(default_factory=lambda: Path.home() / ".claude" / "skills")
    python: str = field(default_factory=lambda: sys.executable)
    mcp_timeout: float = MCP_TIMEOUT
    add_timeout: float = ADD_TIMEOUT
    agents_source: Path | None = None
    agents_target: Path | None = None
    claude_config: Path | None = None

    def __post_init__(self) -> None:
        if self.agents_source is None:
            if self.skills_source == default_skills_source():
                self.agents_source = default_agents_source()
            else:
                self.agents_source = self.skills_source.parent / ".claude" / "agents"
        if self.agents_target is None:
            self.agents_target = self.skills_target.parent / "agents"
        if self.claude_config is None:
            if self.skills_source == default_skills_source():
                self.claude_config = Path.home() / ".claude.json"
            else:
                self.claude_config = self.skills_target.parent / ".claude.json"


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
    options: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                     "text": True, "encoding": "utf-8", "errors": "replace",
                     "stdin": subprocess.DEVNULL, "shell": False}
    if sys.platform.startswith("win"):
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(args, **options)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        raise
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def _config_has_server(config_path: Path | None = None) -> bool:
    """Fallback check in ``.claude.json`` (user or project scope) when ``claude mcp list`` is unavailable."""
    path = config_path if config_path is not None else (Path.home() / ".claude.json")
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and NAME in servers:
        return True
    projects = data.get("projects")
    if isinstance(projects, dict):
        for proj in projects.values():
            if isinstance(proj, dict):
                proj_servers = proj.get("mcpServers")
                if isinstance(proj_servers, dict) and NAME in proj_servers:
                    return True
    return False


def mcp_state(claude: str, timeout: float = MCP_TIMEOUT, config_path: Path | None = None) -> str:
    """``connected`` (listed), ``missing`` (not listed) or ``unknown`` (the command failed or was slow)."""
    try:
        done = _run([claude, "mcp", "list"], timeout)
    except (OSError, subprocess.SubprocessError):
        return "connected" if _config_has_server(config_path) else "unknown"
    if done.returncode != 0:
        return "connected" if _config_has_server(config_path) else "unknown"
    listed = any(line.strip().startswith(f"{NAME}:") for line in done.stdout.splitlines())
    return "connected" if (listed or _config_has_server(config_path)) else "missing"


# --- skills and specialist sub-agents -------------------------------------------------------

def _skill_files(source: Path) -> list[Path]:
    """Every file of every skill, relative to the skills folder."""
    if not source or not source.is_dir():
        return []
    return sorted(path.relative_to(source) for path in source.rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts)


def _pairs(source: Path, target: Path, agents_source: Path | None = None,
           agents_target: Path | None = None) -> list[tuple[str, Path, Path]]:
    """All (display_name, source_file, target_file) triples for skills and optional agents."""
    items = [(f.as_posix(), source / f, target / f) for f in _skill_files(source)]
    if agents_source and agents_target and agents_source.is_dir():
        for f in _skill_files(agents_source):
            items.append((f"agents/{f.as_posix()}", agents_source / f, agents_target / f))
    return items


def skills_state(source: Path, target: Path, agents_source: Path | None = None,
                 agents_target: Path | None = None) -> dict:
    """How the skills (and specialist sub-agents) stand in the user's folder."""
    items = _pairs(source, target, agents_source, agents_target)
    missing = [name for name, src, dst in items if not dst.is_file()]
    differing = [name for name, src, dst in items if dst.is_file() and dst.read_bytes() != src.read_bytes()]
    return {"available": bool(items), "total": len(items), "missing": len(missing),
            "modified": differing, "installed": bool(items) and not missing}


def install_skills(source: Path, target: Path, overwrite: bool = False,
                   agents_source: Path | None = None, agents_target: Path | None = None) -> dict:
    """Copy the skills and specialist sub-agents. A modified file is kept unless ``overwrite``."""
    copied, kept = 0, []
    for name, src, destination in _pairs(source, target, agents_source, agents_target):
        if destination.is_file():
            if destination.read_bytes() == src.read_bytes():
                continue
            if not overwrite:
                kept.append(name)
                continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, destination)
        copied += 1
    return {"copied": copied, "kept": kept}


# --- the whole connection --------------------------------------------------------------------

def status(settings: Settings) -> dict:
    """The quick part of the state: no command is run."""
    claude = find_claude()
    return {"claude": bool(claude),
            "skills": skills_state(settings.skills_source, settings.skills_target,
                                   settings.agents_source, settings.agents_target),
            "command": shown_command(settings), "skills_folder": SHOWN_SKILLS_FOLDER,
            "codex_command": codex_shown_command(settings.python),
            "antigravity_entry": json.dumps(antigravity_mcp_entry(settings.python))}


def mcp_status(settings: Settings) -> dict:
    """The slow part: asks Claude Code which servers it knows."""
    claude = find_claude()
    return {"state": mcp_state(claude, settings.mcp_timeout, settings.claude_config) if claude else "no_claude"}


def connect(settings: Settings, overwrite_skills: bool = False) -> dict:
    """Register the server and copy the skills and specialist sub-agents. Safe to repeat."""
    claude = find_claude()
    if not claude:
        return {"ok": False, "error": "claude_missing"}
    if mcp_state(claude, settings.mcp_timeout, settings.claude_config) == "connected":
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
        skills = install_skills(settings.skills_source, settings.skills_target, overwrite_skills,
                                settings.agents_source, settings.agents_target)
    except OSError as exc:
        return {"ok": False, "error": "skills_failed", "detail": type(exc).__name__, "server": server}
    return {"ok": True, "server": server, "skills": skills,
            "skills_available": bool(_skill_files(settings.skills_source))}


# --- Google Antigravity and ChatGPT Codex CLI helpers ----------------------------------------

def codex_arguments(codex: str, python: str) -> list[str]:
    """The command to register the MCP server in ChatGPT Codex CLI."""
    return [codex, "mcp", "add", NAME, "--", python, "-m", "ad_library_insights"]


def codex_shown_command(python: str | None = None) -> str:
    """The Codex CLI registration command as the user would type it."""
    args = codex_arguments("codex", python or sys.executable)
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def antigravity_mcp_entry(python: str | None = None) -> dict:
    """The ``mcpServers`` entry for Google Antigravity (``~/.gemini/antigravity/mcp_config.json``)."""
    return {NAME: {"command": python or sys.executable, "args": ["-m", "ad_library_insights"]}}


def install_to_folder(source: Path | None = None, target: Path | None = None, overwrite: bool = False) -> dict:
    """Copy the program's skills to an assistant skills folder (e.g. Antigravity or Codex)."""
    src = source or default_skills_source()
    dst = target or (Path.home() / ".gemini" / "antigravity" / "skills")
    return install_skills(src, dst, overwrite=overwrite)

