"""atlas scan: find what is in a folder and draft a card for each thing that has none.

It reads; it never changes the folder or anything in it. For every direct subfolder it collects
facts (git remote and state, what the README or package says it is, how it deploys, what on this Mac
uses it, other clones of the same repo) and, when no card mentions that path, writes a draft card to
the inbox with `where`, `what`, a check, and those facts. `why` stays empty: only Clark knows it.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess

from . import core as A

HOME = pathlib.Path.home()
AGENT_SKILL_DIRS = {"Hermes": HOME / ".hermes/skills", "Claude": HOME / ".claude/skills", "Codex": HOME / ".codex/skills"}
CLONE_ROOTS = [HOME / "Developer", HOME / "code", HOME / "Documents", HOME]


def tilde(p) -> str:
    p = pathlib.Path(p)
    try:
        return "~/" + str(p.relative_to(HOME))
    except ValueError:
        return str(p)


def git(path, *args) -> str:
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 else ""


def norm_remote(url: str) -> str:
    """github.com/owner/repo for https and ssh forms alike."""
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?/?$", url or "")
    return f"github.com/{m.group(1)}" if m else (url or "")


# ── what is it ───────────────────────────────────────────────────────────────

def describe(path: pathlib.Path) -> str:
    """One line: the package description, else the first plain sentence of the README."""
    for name, rx in (("pyproject.toml", r'^description\s*=\s*"([^"]+)"'), ("package.json", None)):
        f = path / name
        if f.is_file():
            try:
                if rx:
                    m = re.search(rx, f.read_text(errors="replace"), re.M)
                    if m and m.group(1).strip():
                        return m.group(1).strip()
                else:
                    d = json.loads(f.read_text(errors="replace")).get("description", "").strip()
                    if d:
                        return d
            except (ValueError, OSError):
                pass
    for name in ("README.md", "readme.md", "README.txt", "README"):
        f = path / name
        if f.is_file():
            for line in f.read_text(errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith(("#", "!", "[!", "<", "|", "```", "---", ">", "-", "*")) or len(s) < 20:
                    continue
                s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s).replace("**", "").replace("`", "")
                first = re.split(r"(?<=[.!?])\s", s)[0]
                return first if len(first) <= 160 else first[:157].rsplit(" ", 1)[0] + "…"
    return ""


def stack(path: pathlib.Path) -> list[str]:
    out = []
    pkg = path / "package.json"
    if pkg.is_file():
        try:
            deps = json.loads(pkg.read_text(errors="replace"))
            deps = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
            out.append("Next.js" if "next" in deps else "Node")
        except ValueError:
            out.append("Node")
    if (path / "pyproject.toml").is_file() or (path / "setup.py").is_file():
        out.append("Python")
    if (path / "pixi.toml").is_file():
        out.append("pixi")
    for f, label in (("Cargo.toml", "Rust"), ("go.mod", "Go"), ("Dockerfile", "Docker"), ("Makefile", "Makefile"),
                     ("snowflake.yml", "Snowflake"), ("app.yml", "app.yml")):
        if (path / f).is_file():
            out.append(label)
    return out


def deploys(path: pathlib.Path) -> list[str]:
    out = []
    link = path / ".vercel" / "project.json"
    if link.is_file():
        try:
            out.append(f"linked to Vercel project {json.loads(link.read_text()).get('projectName', '?')} (.vercel/project.json)")
        except ValueError:
            out.append("has a .vercel link")
    vj = path / "vercel.json"
    if vj.is_file():
        try:
            crons = json.loads(vj.read_text()).get("crons", [])
        except ValueError:
            crons = []
        out.append("vercel.json" + (f" with {len(crons)} cron(s): " + ", ".join(f"{c.get('path')} at {c.get('schedule')}" for c in crons) if crons else ""))
    for f, label in (("fly.toml", "Fly.io (fly.toml)"), ("netlify.toml", "Netlify (netlify.toml)"),
                     ("wrangler.toml", "Cloudflare (wrangler.toml)"), (".github/workflows", "GitHub Actions workflows")):
        if (path / f).exists():
            out.append(label)
    return out


# ── what uses it ─────────────────────────────────────────────────────────────

class Users:
    """Everything on this Mac that points into a folder: launchd jobs, Hermes cron, agent skills, uv tools."""

    def __init__(self):
        self.launchd = {}
        for p in (HOME / "Library/LaunchAgents").glob("*.plist"):
            try:
                self.launchd[p.stem] = p.read_text(errors="replace")
            except OSError:
                pass
        self.cron = []
        jf = HOME / ".hermes/cron/jobs.json"
        if jf.is_file():
            try:
                d = json.loads(jf.read_text())
                jobs = d.get("jobs", d) if isinstance(d, dict) else d
                self.cron = list(jobs.values()) if isinstance(jobs, dict) else list(jobs)
            except ValueError:
                pass
        self.skills = []
        for agent, base in AGENT_SKILL_DIRS.items():
            if base.is_dir():
                for e in base.iterdir():
                    if e.is_symlink():
                        self.skills.append((agent, e.name, e.resolve()))
        self.tools = {}
        for r in (HOME / ".local/share/uv/tools").glob("*/uv-receipt.toml"):
            self.tools[r.parent.name] = r.read_text(errors="replace")

    def of(self, path: pathlib.Path) -> list[str]:
        p, out = str(path), []
        out += [f"launchd job {label}" for label, text in self.launchd.items() if p in text]
        for j in self.cron:
            blob = json.dumps(j)
            if p in blob or tilde(path) in blob:
                out.append(f"Hermes cron job \"{j.get('name', j.get('id'))}\" ({j.get('schedule_display') or j.get('schedule')})")
        by_skill = {}
        for agent, name, real in self.skills:
            if str(real).startswith(p + "/"):
                by_skill.setdefault(name, []).append(agent)
        out += [f"skill {name} (in {', '.join(agents)})" for name, agents in sorted(by_skill.items())]
        out += [f"uv tool {name} (installed from here)" for name, text in self.tools.items() if f'"{p}"' in text]
        return out


def other_clones(path: pathlib.Path, remote: str) -> list[str]:
    if not remote:
        return []
    out = []
    for root in CLONE_ROOTS:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if d == path or not (d / ".git").exists():
                continue
            if norm_remote(git(d, "remote", "get-url", "origin")) == remote:
                head = git(d, "log", "-1", "--format=%h %cd", "--date=short")
                out.append(f"{tilde(d)} is another clone of the same repo (at {head})")
    return out


# ── one folder ───────────────────────────────────────────────────────────────

def inspect(path: pathlib.Path, users: Users) -> dict:
    is_git = (path / ".git").exists()
    facts, gotchas = [], []
    remote = norm_remote(git(path, "remote", "get-url", "origin")) if is_git else ""
    what = describe(path)
    if is_git:
        branch = git(path, "branch", "--show-current") or "detached"
        last = git(path, "log", "-1", "--format=%h %cd %s", "--date=short")
        count = git(path, "rev-list", "--count", "HEAD") or "0"
        dirty = len([l for l in git(path, "status", "--porcelain").splitlines() if l.strip()])
        ahead = git(path, "rev-list", "--count", "@{u}..HEAD") if remote else ""
        facts.append(f"git repo on `{branch}`, {count} commits, last: {last or 'none'}")
        facts.append(f"remote: {remote}" if remote else "no remote: it exists only on this Mac")
        if not remote:
            gotchas.append("No remote, so this folder is its only copy.")
        if dirty:
            gotchas.append(f"{dirty} uncommitted change(s).")
        if ahead and ahead != "0":
            gotchas.append(f"{ahead} commit(s) not pushed.")
        if remote and not remote.startswith("github.com/cwkoenigs/"):
            facts.append("someone else's repo (a clone, not Clark's project)")
    else:
        files = [f for f in path.rglob("*") if f.is_file() and ".git" not in f.parts][:5000]
        newest = max((f.stat().st_mtime for f in files), default=path.stat().st_mtime)
        kinds = {}
        for f in files:
            kinds[f.suffix or f.name] = kinds.get(f.suffix or f.name, 0) + 1
        top = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])[:4])
        facts.append(f"not a git repo: {len(files)} files ({top}), newest changed {dt.date.fromtimestamp(newest)}")
        gotchas.append("Not in git, so this folder is its only copy.")
    st = stack(path)
    if st:
        facts.append("stack: " + ", ".join(st))
    dep = deploys(path)
    facts += [f"deploys: {d}" for d in dep]
    used = users.of(path)
    facts += [f"used by: {u}" for u in used] or ["used by: nothing found on this Mac (launchd, Hermes cron, agent skills, uv tools)"]
    facts += other_clones(path, remote)
    kind = "repo" if is_git else "folder"
    if dep and any("Vercel" in d for d in dep):
        kind = "app"
    if not what:
        what = ("No README or description." if is_git else "A folder of files, no README.")
    # ~ does not expand inside quotes, so a path with a space is written "$HOME/..."
    q = (f'"$HOME/{path.relative_to(HOME)}"' if str(path).startswith(str(HOME)) else f'"{path}"') if " " in str(path) else tilde(path)
    return {
        "path": path, "name": path.name, "kind": kind, "remote": remote, "what": what,
        "where": tilde(path) + (f" ({remote})" if remote else ""),
        "source": remote or tilde(path),
        "entry": f"cd {q}",
        "check": f"git -C {q} rev-parse --git-dir >/dev/null" if is_git else f"test -d {q}",
        "facts": facts, "gotchas": gotchas, "used": used,
    }


def covered(path: pathlib.Path, cards) -> dict | None:
    """The card that already describes this folder: one whose where/source/entry/check names its path."""
    p, t = str(path), tilde(path)
    pat = re.compile(rf"(?:{re.escape(p)}|{re.escape(t)})(?![\w.-])")
    exact = re.compile(rf"(?:{re.escape(p)}|{re.escape(t)})(?![\w./-])")
    best, best_score = None, 0
    for c in cards:
        blob = " ".join(str(c.get(k, "")) for k in ("where", "source", "entry", "check"))
        if not pat.search(blob):
            continue
        # prefer the card about the folder itself over one about something inside it
        score = 1 + (2 if exact.search(str(c.get("where", ""))) else 0) + (1 if c.get("kind") in ("repo", "folder") else 0)
        if score > best_score:
            best, best_score = c, score
    return best


def body(f: dict) -> str:
    today = A.TODAY.isoformat()
    lines = ["", "## Short version", "",
             f"Found by `atlas scan` on {today}. Fill in why it exists, then promote it, or retire it if it is not needed.",
             "", "## Untangled", "", f"Seen by `atlas scan` on {today}:", ""]
    lines += [f"- {x}" for x in f["facts"]]
    lines += ["", "## To change it", "", f"Work in `{tilde(f['path'])}`" + (f"; push to {f['remote']}." if f["remote"] else "."),
              "", "## Gotchas", ""]
    lines += [f"- {g}" for g in f["gotchas"]]
    return "\n".join(lines) + "\n"


def scan(folder: pathlib.Path):
    """Yield (finding, existing_card_or_None) for each direct subfolder, in name order."""
    cards = A.load()
    users = Users()
    for d in sorted((p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.name.lower()):
        yield inspect(d, users), covered(d, cards)


def loose_files(folder: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))


def draft(f: dict, personal: bool = True) -> dict:
    return A.new_card(f["name"], f["kind"], "this-mac", personal=personal, confidence="guess", body=body(f),
                      by="scan", summary="drafted by atlas scan", where=f["where"], what=f["what"],
                      source=f["source"], entry=f["entry"], check=f["check"])
