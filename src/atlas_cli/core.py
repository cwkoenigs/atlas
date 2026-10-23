"""atlas core: cards, checks, search, the generated pages. No terminal output here."""
import datetime as dt, html, json, os, pathlib, re, secrets, shutil, subprocess, sys

ROOT = pathlib.Path(os.environ.get("ATLAS_DIR", pathlib.Path.home() / "Developer" / "atlas")).expanduser()
CFG = json.loads((ROOT / "atlas.json").read_text())
STATE = ROOT / ".state" / "checks.json"
FOLDERS = {"inbox": "Draft", "cards": "Active", "retired": "Retired"}
FIELDS = ["id", "title", "kind", "host", "where", "what", "why", "source", "entry", "check",
          "links", "notes", "confidence", "confirmed"]
REQUIRED = ["title", "kind", "host", "where", "what", "why", "source", "check"]
TODAY = dt.date.today()
HOME = pathlib.Path.home()


def expand(p):
    return pathlib.Path(os.path.expanduser(p))


# ---------- cards: a small, strict frontmatter format (key: value, lists as [a, b]) ----------

def parse(path):
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        raise ValueError(f"{path}: no frontmatter")
    meta = {}
    for line in m.group(1).splitlines():
        line = line.split("  #", 1)[0].rstrip() if "  #" in line else line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            v = v.strip("'\"") if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v
        meta[k.strip()] = v
    for k in ("links", "notes"):
        meta.setdefault(k, [])
        if isinstance(meta[k], str):
            meta[k] = [meta[k]] if meta[k] else []
    meta["_body"] = m.group(2)
    meta["_path"] = path
    meta["_slug"] = path.stem
    meta["_personal"] = path.parent.name == "personal"
    meta["_folder"] = path.parent.parent.name if meta["_personal"] else path.parent.name
    return meta


def dump(card):
    def val(v):
        if isinstance(v, list):
            return "[" + ", ".join(f'"{x}"' if ("," in x or "[" in x) else x for x in v) + "]"
        v = str(v)
        return f'"{v}"' if (v.startswith(("[", "{", "'", '"')) or ": " in v or " #" in v) else v
    keys = FIELDS + [k for k in card if not k.startswith("_") and k not in FIELDS]
    head = "\n".join(f"{k}: {val(card[k])}".rstrip() for k in keys if k in card)
    return f"---\n{head}\n---\n{card.get('_body', '')}"


def load(folders=("inbox", "cards", "retired")):
    cards = []
    for f in folders:
        for p in sorted((ROOT / f).glob("*.md")) + sorted((ROOT / f / "personal").glob("*.md")):
            cards.append(parse(p))
    return cards


def ordered(cards):
    """Every card in map order: by place, then title; drafts after active cards. Numbers come from here."""
    hosts = list(CFG["hosts"])
    rank = lambda h: hosts.index(h) if h in hosts else len(hosts)
    return sorted([c for c in cards if c["_folder"] != "retired"],
                  key=lambda c: (rank(c.get("host", "")), c.get("host", ""), c["_folder"] == "inbox", c["title"].lower()))


def search(query, cards=None):
    """Cards matching a number from the map, an id or file name, or words in the title (then anywhere)."""
    cards = cards if cards is not None else load()
    q = query.strip().lower()
    if q.isdigit():
        lst = ordered(cards)
        n = int(q)
        return [lst[n - 1]] if 1 <= n <= len(lst) else []
    exact = [c for c in cards if q in (c.get("id", "").lower(), c["_slug"])]
    if exact:
        return exact
    words = q.split()
    title = [c for c in cards if all(w in (c["title"] + " " + c["_slug"]).lower() for w in words)]
    if title:
        return title
    return [c for c in cards if all(w in c["_path"].read_text().lower() for w in words)]


class NoMatch(Exception):
    pass


class Ambiguous(Exception):
    def __init__(self, query, hits):
        super().__init__(query)
        self.query, self.hits = query, hits


def numbers(cards):
    """slug -> number on the map."""
    return {c["_slug"]: i for i, c in enumerate(ordered(cards), 1)}


def find(ident, cards=None):
    """Exactly one card, or NoMatch / Ambiguous (with the candidates)."""
    cards = cards if cards is not None else load()
    hits = search(ident, cards)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise NoMatch(ident)
    num = numbers(cards)
    raise Ambiguous(ident, sorted(hits, key=lambda c: num.get(c["_slug"], 999)))


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


# ---------- checks ----------

def state():
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def run_checks(cards, on_each=None):
    """Run each card's check; on_each(card, ok, out) after each one. Results go to .state/checks.json."""
    st = state()
    for c in cards:
        cmd = c.get("check", "")
        if not cmd:
            continue
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=CFG.get("check_timeout", 15), cwd=HOME)
            ok, out = r.returncode == 0, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            ok, out = False, f"timed out after {CFG.get('check_timeout', 15)}s"
        st[c["id"]] = {"ok": ok, "at": dt.datetime.now().isoformat(timespec="minutes"),
                       "out": out.splitlines()[-1][:200] if out else ""}
        if on_each:
            on_each(c, ok, st[c["id"]]["out"])
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1) + "\n")
    return st


def status(c, st):
    """(word, state) for display. state is ok | fail | none | draft | retired."""
    if c["_folder"] == "retired":
        return "Retired", "retired"
    s = st.get(c.get("id"))
    if c["_folder"] == "inbox":
        return "Draft", "draft"
    if not c.get("check"):
        return "No check", "none"
    if not s:
        return "Not checked", "none"
    return ("OK", "ok") if s["ok"] else ("Failing", "fail")


def stale(c):
    try:
        return (TODAY - dt.date.fromisoformat(c.get("confirmed", ""))).days > CFG.get("stale_days", 30)
    except ValueError:
        return True


def attention(cards, st):
    """Most urgent first: failing checks, drafts waiting, guesses, stale confirmations. One row per card."""
    rows = {}
    for c in cards:
        word, s = status(c, st)
        why, rank = [], 9
        res = st.get(c.get("id"))
        if res and not res["ok"]:
            why.append("not ok" + (f": {res['out']}" if res["out"] else ", its check fails")); rank = 0
        if s == "draft":
            why.append("new, not confirmed yet"); rank = min(rank, 1)
        elif s == "none":
            why.append("no passing check yet"); rank = min(rank, 2)
        if c["_folder"] == "cards" and c.get("confidence") == "guess":
            why.append("still a guess"); rank = min(rank, 3)
        elif c["_folder"] == "cards" and stale(c):
            why.append(f"not confirmed since {c.get('confirmed') or 'ever'}")
            rank = min(rank, 4)
        if why:
            rows[c["id"]] = (rank, c, "; ".join(why))
    return sorted(rows.values(), key=lambda x: (x[0], x[1]["title"]))


# ---------- build: ATLAS.md ----------

def host_name(h):
    return CFG["hosts"].get(h, h)


def linkname(c):
    return f"[[{c['_folder']}/{c['_slug']}|{c['title']}]]"


def build_md(cards, st):
    active = [c for c in cards if c["_folder"] != "retired"]
    counts = {k: sum(1 for c in active if status(c, st)[1] == k) for k in ("ok", "fail", "none", "draft")}
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = ["# Atlas", "",
         "What runs where, and why. One card per thing in `cards/`; this page is built from them.", "",
         f"_Updated {now} by `atlas check`. Edit the cards, not this file._", "",
         f"{len(active) - counts['draft']} cards: {counts['ok']} OK, {counts['fail']} failing, "
         f"{counts['none']} without a passing check. {counts['draft']} draft(s) in the inbox.", ""]
    att = attention(active, st)
    if att:
        L += ["## Needs a look", ""]
        L += [f"- [ ] **{linkname(c)}** `{c['id']}`: {why}" for _, c, why in att]
        L.append("")
    L += ["## By place", ""]
    by_host = {}
    for c in active:
        by_host.setdefault(c.get("host", ""), []).append(c)
    order = list(CFG["hosts"]) + sorted(h for h in by_host if h not in CFG["hosts"])
    for h in order:
        if h not in by_host:
            continue
        L += [f"### {host_name(h)}", ""]
        for c in sorted(by_host[h], key=lambda c: (c["_folder"] == "inbox", c["title"])):
            word, _ = status(c, st)
            L.append(f"- **{linkname(c)}** · {c.get('kind', '')} · {word} · `{c['id']}`")
            L.append(f"  {c.get('what', '')} Where: `{c.get('where', '')}`.")
            if c.get("why"):
                L.append(f"  Why: {c['why']}")
        L.append("")
    edges = [(c, l) for c in active for l in c.get("links", [])]
    if edges:
        idx = {x.get("id"): x for x in active} | {x["_slug"]: x for x in active}
        L += ["## Connections", "", "```mermaid", "flowchart LR"]
        for h in order:
            group = by_host.get(h)
            if group:
                L.append(f'  subgraph {re.sub(r"[^A-Za-z0-9]", "_", h)}["{host_name(h)}"]')
                L += [f'    {c["id"].replace("-", "_")}["{c["title"]}"]' for c in group]
                L.append("  end")
        for c, l in edges:
            if l in idx:
                L.append(f'  {c["id"].replace("-", "_")} --> {idx[l]["id"].replace("-", "_")}')
        L += ["```", ""]
    retired = [c for c in cards if c["_folder"] == "retired"]
    if retired:
        L += ["## Retired", ""] + [f"- {linkname(c)} `{c['id']}`: {c.get('retired_reason', '')}" for c in retired] + [""]
    (ROOT / "ATLAS.md").write_text("\n".join(L))


# ---------- build: HTML page in the dashboard-style system ----------

def build_html(cards, st):
    out, tpl = CFG.get("html_out"), CFG.get("template")
    if not out or not tpl or not expand(tpl).is_file():
        return None
    out, tpl = expand(out), expand(tpl).read_text()
    prefix = tpl[: tpl.index("<!-- @ds-mark end -->") + len("<!-- @ds-mark end -->")]
    prefix = re.sub(r"<title>.*?</title>", "<title>Atlas</title>", prefix, count=1)
    e = html.escape
    active = [c for c in cards if c["_folder"] != "retired"]
    counts = {k: sum(1 for c in active if status(c, st)[1] == k) for k in ("ok", "fail", "none", "draft")}
    rel = lambda p: os.path.relpath(p, out.parent)

    def code(s):  # `x` -> <code>x</code>
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", e(s))

    banners = "".join(
        f'<div class="banner" data-label="{"Failing" if rank == 0 else "Draft" if rank == 1 else "Check"}">'
        f'<span><strong>{e(c["title"])}</strong> <code>{e(c["id"])}</code>: {code(why)}</span></div>\n'
        for rank, c, why in attention(active, st) if rank <= 2)
    sections, n = [], 0
    by_host = {}
    for c in active:
        by_host.setdefault(c.get("host", ""), []).append(c)
    for h in list(CFG["hosts"]) + sorted(x for x in by_host if x not in CFG["hosts"]):
        if h not in by_host:
            continue
        n += 1
        tiles = []
        for c in sorted(by_host[h], key=lambda c: (c["_folder"] == "inbox", c["title"])):
            word, s = status(c, st)
            tiles.append(
                f'<a class="tile" data-freshness="{word}" data-state="{s}" href="{e(rel(c["_path"]))}">'
                f'<span class="idx">{e(c["id"])} · {e(c.get("kind", ""))}</span>'
                f'<span class="title">{e(c["title"])}</span>'
                f'<span class="desc">{code(c.get("what", ""))}</span>'
                f'<span class="desc"><strong>Why</strong> {code(c.get("why", ""))}</span>'
                f'<span class="meta">{e(c.get("where", ""))}</span></a>')
        sections.append(f'<h2><span class="idx">{n:02d}</span>{e(host_name(h))}</h2>\n'
                        f'<div class="tiles">\n' + "\n".join(tiles) + "\n</div>")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    stats = "".join(f"<div><dt>{a}</dt><dd>{b}<small>{s}</small></dd></div>" for a, b, s in [
        ("Cards", len(active) - counts["draft"], f"{len(by_host)} places"),
        ("OK", counts["ok"], "checks passing"),
        ("Failing", counts["fail"], "checks failing"),
        ("Inbox", counts["draft"], "drafts to promote")])
    page = prefix + f"""
    <a class="brand" href="index.html">Life admin</a><span class="crumb">/ atlas</span>
    <p class="refreshed" id="refreshed" data-live>Checked {now}</p>
  </div>
</header>
<section class="hero">
  <div class="wrap">
    <p class="eyebrow">{e(str(ROOT).replace(str(HOME), "~"))}</p>
    <h1>Atlas</h1>
    <p class="lead">What runs where, and why. Each card is a markdown file; run <code>atlas check</code> to re-check and rebuild.</p>
    <dl class="stats">{stats}</dl>
  </div>
</section>
<main class="wrap">
{banners}
{chr(10).join(sections)}
</main>
<footer class="site"><div class="wrap">Built from <code>{e(str(ROOT / "cards").replace(str(HOME), "~"))}</code> by <code>atlas check</code>. Edit the cards, not this page.</div></footer>
</body>
</html>
"""
    out.write_text(page)
    return out


# ---------- operations (no printing; the CLI presents the results) ----------

def place(c, folder):
    """Where a card goes in `folder`, keeping it personal (out of git) if it was."""
    d = ROOT / folder / ("personal" if c["_personal"] else "")
    d.mkdir(exist_ok=True)
    return d / c["_path"].name


def new_card(title, kind, host, personal=False, confidence="believed", **fields):
    slug = slugify(title)
    if any(c["_slug"] == slug for c in load()):
        raise ValueError(f"a card named {slug} already exists")
    path = ROOT / "inbox" / ("personal" if personal else "") / f"{slug}.md"
    path.parent.mkdir(exist_ok=True)
    tpl = parse(ROOT / "templates" / "card.md")
    card = {k: tpl.get(k, "") for k in FIELDS}
    card.update(id="a-" + secrets.token_hex(3), title=title, kind=kind, host=host, confidence=confidence,
                confirmed="", links=fields.pop("links", []) or [], notes=[])
    card.update({k: v for k, v in fields.items() if v})
    card["_body"] = tpl["_body"]
    path.write_text(dump(card))
    return parse(path)


def promote(c, force=False):
    """inbox -> cards. Returns (dest, problem); problem is None on success."""
    if c["_folder"] != "inbox":
        return None, f"it is already in {c['_folder']}/"
    missing = [k for k in REQUIRED if not c.get(k)]
    st = run_checks([c]) if c.get("check") else state()
    if not force:
        if missing:
            return None, "fill these first: " + ", ".join(missing)
        if not st.get(c["id"], {}).get("ok"):
            return None, "its check does not pass yet"
    c["confirmed"] = TODAY.isoformat()
    if c.get("confidence") in ("", "guess") and not missing:
        c["confidence"] = "confirmed"
    dest = place(c, "cards")
    dest.write_text(dump(c))
    c["_path"].unlink()
    return dest, None


def confirm(c):
    c["confirmed"] = TODAY.isoformat()
    c["_path"].write_text(dump(c))


def retire(c, reason=""):
    c["retired"] = TODAY.isoformat()
    c["retired_reason"] = reason
    dest = place(c, "retired")
    dest.write_text(dump(c))
    c["_path"].unlink()
    return dest


def set_personal(c, want=True):
    if c["_personal"] == want:
        return None
    c["_personal"] = want
    dest = place(c, c["_folder"])
    c["_path"].rename(dest)
    return dest


def lint():
    cards, problems = load(), []
    ids = {c.get("id") for c in cards} | {c["_slug"] for c in cards}
    seen = {}
    for c in cards:
        where = c["_path"].relative_to(ROOT)
        if not re.fullmatch(r"a-[0-9a-f]{6}", c.get("id", "")):
            problems.append(f"{where}: id must look like a-1b2c3d")
        if c.get("id") in seen:
            problems.append(f"{where}: id {c['id']} also used by {seen[c['id']]}")
        seen[c.get("id")] = where
        if c["_folder"] == "cards":
            problems += [f"{where}: missing {k}" for k in REQUIRED if not c.get(k)]
        if c.get("host") and c["host"] not in CFG["hosts"]:
            problems.append(f"{where}: host {c['host']!r} is not in atlas.json")
        problems += [f"{where}: link {l!r} matches no card" for l in c.get("links", []) if l not in ids]
    return cards, problems


def short_version(c):
    m = re.search(r"## Short version\n(.*?)(?=\n## |\Z)", c["_body"], re.S)
    text = " ".join(m.group(1).split()) if m else ""
    text = text.replace("**", "").replace("`", "")
    return "" if text.startswith("Two or three lines") else text


def ago(iso):
    try:
        mins = int((dt.datetime.now() - dt.datetime.fromisoformat(iso)).total_seconds() // 60)
    except (TypeError, ValueError):
        return "never"
    return f"{mins} min ago" if mins < 90 else f"{mins // 60} h ago" if mins < 48 * 60 else f"{mins // 1440} days ago"


def last_checked(st):
    return max((v["at"] for v in st.values()), default=None)


def fresh(st, hours=6):
    last = last_checked(st)
    return bool(last) and (dt.datetime.now() - dt.datetime.fromisoformat(last)).total_seconds() < hours * 3600


def clip(text, n):
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def rebuild(cards=None, st=None):
    cards = cards if cards is not None else load()
    st = st if st is not None else state()
    build_md(cards, st)
    return build_html(cards, st)
