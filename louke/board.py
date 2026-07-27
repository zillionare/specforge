"""IDE board generation commands."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from ._common import git_root
from .models import frontmatter_binding, resolve_model


SKIP = {"README.md", "ROSTER.md"}

# v0.6-009 FR-0030: passthrough allowlist (besides description / mode / model, which are handled separately).
# Source: OpenCode official frontmatter fields + permission.
PASSTHROUGH_KEYS = {
    "permission",  # v0.6-009 FR-0010/0060/0070 implementation
    "hidden",  # OpenCode supported
    "color",  # OpenCode supported
    "temperature",  # OpenCode supported
    "top_p",  # OpenCode supported
    "steps",  # OpenCode supported
    "disable",  # OpenCode supported
}

SKILL_PREFIX = "lk-"
AGENT_SKILL_REFERENCE_NAMES = {
    "inline-discussion": f"{SKILL_PREFIX}inline-discussion",
}


def register(parser):
    """Register board subcommands on the given parser."""
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    p = sub.add_parser("opencode", help="generate OpenCode agents")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--quiet",
        action="store_true",
        help="do not print per-step progress (only the final summary)",
    )
    p.add_argument(
        "--root",
        help="explicitly specify the project root directory (default: current git repo root)",
    )
    p = sub.add_parser("status", help="show board status")
    p.add_argument(
        "--root",
        default="",
        help="explicitly specify the project root directory (default: current git repo root)",
    )
    p = sub.add_parser("vscode", help="VS Code board is currently unsupported")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--root", default="")


def run(args):
    handlers = {"opencode": cmd_opencode, "status": cmd_status, "vscode": cmd_vscode}
    return handlers[args.command](args)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter into a dict.

    louke agent style: `---\\nkey: value\\n\\nbody...` (no closing `---`,
    ends at the first blank line). `---` in the body (a markdown horizontal rule)
    does not affect frontmatter detection.

    Nested structures supported:
    - `key: value` (string)
    - `key:` + indented `  - item` (list, used by legacy `models:`)
    - `key:` + indented `  subkey: value` (dict, used for `permission:`)
    """
    if not text.startswith("---\n"):
        return {}, text
    # louke agent style: the first blank line ends the frontmatter
    # (cannot rely on `\n---\n` because the body may contain markdown horizontal rules)
    lines = text[4:].splitlines()
    end_idx = 0
    while end_idx < len(lines) and lines[end_idx].strip():
        end_idx += 1
    raw = lines[:end_idx]
    body = "\n".join(lines[end_idx:]).lstrip("\n")

    data: dict = {}
    i = 0
    while i < len(raw):
        line = raw[i]
        if not line.strip():
            i += 1
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent != 0:
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = value
            i += 1
            continue
        # Container: collect children
        children: dict = {}
        child_list: list = []
        j = i + 1
        while j < len(raw):
            child_line = raw[j]
            if not child_line.strip():
                j += 1
                continue
            child_stripped = child_line.lstrip()
            child_indent = len(child_line) - len(child_stripped)
            if child_indent <= indent:
                break
            if child_stripped.startswith("- "):
                child_list.append(child_stripped[2:].strip())
            elif ":" in child_stripped:
                ck, cv = child_stripped.split(":", 1)
                children[ck.strip()] = cv.strip()
            j += 1
        if children:
            data[key] = children
        if child_list:
            data[key] = child_list
        i = j
    return data, body


def agent_source(root: Path | None = None) -> Path:
    """Return the canonical agent source directory (the installed louke package).

    Agents are part of the toolchain, not the project. They live inside the
    installed `louke` Python package and are immutable from a user's perspective:
    users must not (and cannot meaningfully) customize them. Customizing was
    tried and removed because it caused multi-source confusion (e.g. an output
    format got committed as a source on the `millionaire` project).

    `root` is accepted for backwards-compat with call sites but is ignored.
    """
    from ._common import package_root

    return package_root() / "agents"


def skill_source(root: Path) -> Path:
    return agent_source(root) / "_skills"


def prefixed_skill_name(name: str) -> str:
    text = str(name).strip()
    if not text:
        return text
    if text.startswith(SKILL_PREFIX):
        return text
    return f"{SKILL_PREFIX}{text}"


def _rewrite_agent_skill_references(text: str) -> str:
    out = text
    for old, new in AGENT_SKILL_REFERENCE_NAMES.items():
        out = re.sub(
            rf"(?<!{re.escape(SKILL_PREFIX)})`{re.escape(old)}`", f"`{new}`", out
        )
        out = re.sub(
            rf"(?<!{re.escape(SKILL_PREFIX)})\*\*{re.escape(old)}\*\*",
            f"**{new}**",
            out,
        )
        out = re.sub(
            rf"(?<!{re.escape(SKILL_PREFIX)}){re.escape(old)} skill",
            f"{new} skill",
            out,
        )
        out = out.replace(
            f"agents/_skills/{old}/SKILL.md", f".opencode/skill/{new}/SKILL.md"
        )
    return out


def _rewrite_skill_frontmatter_name(text: str, new_name: str) -> str:
    return re.sub(r"(?m)^name:\s*.+$", f"name: {new_name}", text, count=1)


def _render_passthrough_block(fm: dict, exclude: set[str]) -> str:
    """Render passthrough keys as YAML lines.

    `exclude` should contain `description` / `mode` / `model` (handled separately).
    The returned string ends with a newline, e.g. 'hidden: true\ncolor: blue\n'.
    """
    lines = []
    for key in PASSTHROUGH_KEYS:
        if key in exclude:
            continue
        if key not in fm:
            continue
        value = fm[key]
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + ("\n" if lines else "")


def _require_project_root(args, command: str):
    """Resolve and validate the project root.

    Priority: --root arg > git_root() > error.
    Errors out (exit 1) if neither is available, with a hint about lk init.
    """
    from ._color import red, cyan

    explicit = getattr(args, "root", None)
    if explicit:
        root = Path(explicit).resolve()
    else:
        root = git_root()
    if root is None:
        print(
            f"{red('error:')} {command} requires a git repo (or explicit --root).",
            file=sys.stderr,
        )
        print(
            f"  {cyan('hint:')} run from the louke project root (the one with .git/), or pass --root <path>",
            file=sys.stderr,
        )
        return None
    return Path(root)


def cmd_opencode(args):
    root = _require_project_root(args, "lk board opencode")
    if root is None:
        return 1
    quiet = getattr(args, "quiet", False)
    dry_run = getattr(args, "dry_run", False)
    src = agent_source(root)
    skill_src = skill_source(root)
    dest_dir = root / ".opencode/agents"
    skill_dest_dir = root / ".opencode/skill"

    from ._color import (
        cyan,
        dim,
        green as g,
        warn,
        info,
        Spinner,
    )

    if not quiet:
        print(f"{cyan('[1/6]')} reading source agents + skills: {src}", flush=True)

    # 1. Collect source agents
    source_files = []
    for fp in sorted(src.glob("*.md")):
        if fp.name in SKIP:
            continue
        source_files.append(fp)
    source_skills = [fp for fp in sorted(skill_src.glob("*/SKILL.md")) if fp.is_file()]
    if not quiet:
        print(f"      found {len(source_files)} agent prompts", flush=True)
        print(f"      found {len(source_skills)} skills", flush=True)

    # 2. Parse frontmatter, collect all abstract model names
    from .models import opencode_models, auth_providers, model_costs

    parsed = []  # [(fp, fm, body)]
    abstract_models = set()
    for fp in source_files:
        text = fp.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        parsed.append((fp, fm, body))
        binding = frontmatter_binding(fm)
        if binding and "/" not in binding:
            abstract_models.add(binding)

    if not quiet:
        print(
            f"{cyan('[2/6]')} querying opencode models + resolving provider/model bindings",
            flush=True,
        )
    if not quiet:
        alias_user = Path.home() / ".louke/models.json"
        alias_proj = root / ".louke/models.json"
        print(f"      user-level aliases: {alias_user}", flush=True)
        print(f"      project-level aliases: {alias_proj}", flush=True)
    # opencode models (subprocess, may be slow) -> spinner
    available: list[str] = []
    if abstract_models:
        if not quiet:
            print(
                f"      calling opencode models (N={len(abstract_models)} abstract names)...",
                flush=True,
            )
        with Spinner("querying opencode models"):
            try:
                available = opencode_models()
            except Exception as e:
                if not quiet:
                    print(f"      {warn(f'opencode models failed: {e}')}", flush=True)
        if not quiet:
            print(f"      opencode models returned {len(available)} models", flush=True)
    # auth providers + model costs
    if not quiet:
        print(f"{cyan('[3/6]')} reading auth providers + cost index", flush=True)
    with Spinner("reading auth.json + cost index"):
        auth = auth_providers()
        costs = model_costs()
    if not quiet:
        sample = sorted(auth)[:3]
        more = "..." if len(auth) > 3 else ""
        print(f"      auth providers: {len(auth)} ({sample}{more})", flush=True)
        free_count = sum(1 for v in costs.values() if v == (0, 0))
        print(
            f"      model costs: {len(costs)}, of which {free_count} are free",
            flush=True,
        )

    # 4. Resolve each source's model and write the file
    if not quiet:
        print(
            f"{cyan('[4/6]')} resolving model bindings + writing .opencode/agents/",
            flush=True,
        )
    generated = []
    unbound_abstracts: list[tuple[str, str]] = []  # (agent_name, abstract)
    for fp, fm, body in parsed:
        name = str(fm.get("name") or fp.stem).lower()
        description = fm.get("description") or fp.stem
        mode = fm.get("mode") or "all"
        binding = frontmatter_binding(fm)
        model = (
            resolve_model(binding, root=root, models=available, auth=auth, costs=costs)
            if binding
            else ""
        )
        # Detect unbound: no '/' in the name (still abstract) + no alias
        if model and "/" not in model and not quiet:
            unbound_abstracts.append((name, model))
        passthrough = _render_passthrough_block(
            fm, exclude={"description", "mode", "model"}
        )
        body = _rewrite_agent_skill_references(body)

        unknown_keys = (
            set(fm.keys())
            - {
                "name",
                "description",
                "mode",
                "model",
                "models",
                "intelligence_quotation",
            }
            - PASSTHROUGH_KEYS
        )
        if unknown_keys and dry_run:
            for k in sorted(unknown_keys):
                print(
                    f"{warn(f'dropped unknown frontmatter key {k!r} from {fp.name}')}",
                    flush=True,
                )

        head = f"---\ndescription: {description}\nmode: {mode}\nmodel: {model}\n"
        if passthrough:
            out = head + passthrough + "---\n" + body
        else:
            out = head + "---\n" + body

        dest = dest_dir / f"{name}.md"
        generated.append(dest)
        if dry_run:
            if not quiet:
                marker = cyan("+")
                print(
                    f"      {marker} {name:<12} {mode:<10} {dim('->')} {model}",
                    flush=True,
                )
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(out, encoding="utf-8")
            if not quiet:
                marker = g("✓")
                print(
                    f"      {marker} {name:<12} {mode:<10} {dim('->')} {model}",
                    flush=True,
                )

    if not quiet:
        print(
            f"{cyan('[5/6]')} installing bundled skills into .opencode/skill/",
            flush=True,
        )
    generated_skills = []
    for fp in source_skills:
        skill_text = fp.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(skill_text)
        raw_name = str(fm.get("name") or fp.parent.name).strip() or fp.parent.name
        skill_name = prefixed_skill_name(raw_name)
        out = _rewrite_skill_frontmatter_name(skill_text, skill_name)
        # OpenCode expects `.opencode/skill/<name>/SKILL.md` (a directory) and
        # supports companion files (templates, references, scripts). Copy the
        # full skill folder, not just the SKILL.md — flattening to `<name>.md`
        # would drop any multi-file skills.
        src_dir = fp.parent
        dest = skill_dest_dir / skill_name
        generated_skills.append(dest)
        if dry_run:
            if not quiet:
                marker = cyan("+")
                print(f"      {marker} {skill_name}/", flush=True)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(out, encoding="utf-8")
            for sibling in sorted(src_dir.iterdir()):
                if sibling.name == "SKILL.md":
                    continue
                if sibling.is_file():
                    shutil.copy2(sibling, dest / sibling.name)
                elif sibling.is_dir():
                    shutil.copytree(sibling, dest / sibling.name, dirs_exist_ok=True)
            if not quiet:
                marker = g("✓")
                print(f"      {marker} {skill_name}/", flush=True)

    if not dry_run and not quiet:
        print(
            f"{cyan('[6/6]')} done: generated {len(generated)} OpenCode agents -> {dest_dir}; "
            f"installed {len(generated_skills)} skills -> {skill_dest_dir}",
            flush=True,
        )
    # Unbound hint
    if unbound_abstracts and not quiet:
        print(
            f"\n{warn(f'{len(unbound_abstracts)} abstract(s) unbound (output model has no provider prefix; OpenCode cannot use it):')}"
        )
        for n, a in unbound_abstracts:
            print(f"  {dim('-')} {n}: {a}")
        print(
            f"\n{info('fix:')} {cyan('lk models bind <abstract> <provider>/<model>')} "
            f"or {cyan('lk models bind <abstract>')} (interactive)"
        )
        # Suggest the interactive mode
        if available:
            print(
                f"      interactive mode will list {len(available)} opencode models to choose from"
            )
    return 0


def _default_agent_status(root: Path) -> str:
    project = root / "opencode.json"
    if project.exists():
        try:
            if (
                json.loads(project.read_text(encoding="utf-8")).get("default_agent")
                == "maestro"
            ):
                return "maestro (project opencode.json)"
        except json.JSONDecodeError:
            pass
    global_cfg = Path.home() / ".config/opencode/opencode.json"
    if global_cfg.exists():
        try:
            if (
                json.loads(global_cfg.read_text(encoding="utf-8")).get("default_agent")
                == "maestro"
            ):
                return "maestro (global opencode.json)"
        except json.JSONDecodeError:
            pass
    return "(not set)"


def cmd_status(args):
    root = _require_project_root(args, "lk board status")
    if root is None:
        return 1
    files = (
        list((root / ".opencode/agents").glob("*.md"))
        if (root / ".opencode/agents").exists()
        else []
    )
    skills = (
        list((root / ".opencode/skill").glob("*.md"))
        if (root / ".opencode/skill").exists()
        else []
    )
    ok = any(
        "model:" in f.read_text(encoding="utf-8", errors="replace").split("---", 2)[1]
        for f in files
        if f.exists()
    )
    mark = "✓" if ok else "-"
    print(
        f"opencode    {mark}  (.opencode/agents/ — {len(files)} agents; .opencode/skill/ — {len(skills)} skills)"
    )
    print(f"default_agent: {_default_agent_status(root)}")
    return 0


def cmd_vscode(args):
    print("lk board vscode is not supported in this release", flush=True)
    return 1
