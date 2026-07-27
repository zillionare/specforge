"""Model alias commands."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from ._common import git_root

SCHEMA = "louke://models-config"
INTELLIGENCE_QUOTATIONS = frozenset({"S", "A", "B"})


def register(parser):
    """Register models subcommands on the given parser."""
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    sub.add_parser("list", help="list model resolution results")
    p = sub.add_parser(
        "doctor", help="check model resolution (auth + match + optional probe)"
    )
    p.add_argument(
        "--fix-auto",
        action="store_true",
        help="write auth + strong-match results to ~/.louke/models.json automatically (prefer free)",
    )
    p.add_argument("--ide", default="opencode")
    p.add_argument(
        "--probe",
        action="store_true",
        help="probe ✓ candidates with a minimal opencode run request (slow, consumes tokens)",
    )
    p.add_argument(
        "--quiet", action="store_true", help="do not print per-step progress"
    )
    p = sub.add_parser(
        "bind",
        help="bind an abstract name (enters interactive mode when no <full> is given)",
    )
    p.add_argument(
        "abstract",
        nargs="?",
        help="abstract model name (omit and pass --all-unresolved to batch)",
    )
    p.add_argument("full", nargs="?", help="full model id (provider/model)")
    p.add_argument("--project", action="store_true")
    p.add_argument(
        "--all-unresolved",
        action="store_true",
        help="interactively bind each unresolved abstract one by one",
    )
    p = sub.add_parser("unbind", help="unbind an abstract name")
    p.add_argument("abstract")
    p.add_argument("--project", action="store_true")


def run(args):
    return {
        "list": cmd_list,
        "doctor": cmd_doctor,
        "bind": cmd_bind,
        "unbind": cmd_unbind,
    }[args.command](args)


def config_path(project: bool = False, root=None) -> Path:
    if project:
        root = root or git_root() or Path.cwd()
        return root / ".louke/models.json"
    louke_home = os.environ.get("LOUKE_HOME", "").strip()
    return (Path(louke_home) if louke_home else Path.home() / ".louke") / "models.json"


def load_config(path: Path) -> dict:
    if not path.exists():
        return {"$schema": SCHEMA, "version": 1, "aliases": {}, "assignments": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    data.setdefault("$schema", SCHEMA)
    data.setdefault("version", 1)
    data.setdefault("aliases", {})
    data.setdefault("assignments", {})
    return data


def save_config(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    data["$schema"] = SCHEMA
    data.setdefault("version", 1)
    data.setdefault("aliases", {})
    data.setdefault("assignments", {})
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def frontmatter_binding(frontmatter: dict) -> str:
    """Return the abstract binding declared by an agent prompt.

    New prompts declare an intelligence quotation (S/A/B).  The legacy
    ``models`` fallback keeps older third-party prompts readable while the
    source prompts migrate to quotation-based bindings.
    """
    quotation = str(frontmatter.get("intelligence_quotation") or "").strip()
    if quotation:
        return quotation
    models = frontmatter.get("models") or []
    if isinstance(models, str):
        models = [models]
    return str(models[0]).strip() if models else ""


def _role_assignment(quotation: str, root: Path) -> str:
    """Resolve a quotation through project-then-user role assignments."""
    if quotation not in INTELLIGENCE_QUOTATIONS:
        return ""
    for path in (config_path(True, root), config_path(False)):
        assignments = load_config(path).get("assignments") or {}
        roles = assignments.get("roles") or {}
        value = str(roles.get(quotation) or "").strip()
        if value:
            return value
    return ""


def opencode_models() -> list[str]:
    """Return model identifiers from a bounded, non-interactive OpenCode call."""
    try:
        out = subprocess.check_output(
            ["opencode", "models"],
            text=True,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return []
    models = []
    for line in out.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if "/" in token:
            models.append(token)
    return models


def auth_providers() -> set[str]:
    """Provider IDs with valid credentials, from `~/.local/share/opencode/auth.json`.

    The file is a JSON object whose keys are the same provider IDs that
    `opencode models` uses in the `<provider>/<model>` prefix. This is the
    source of truth; we don't parse the TUI box-drawing of `opencode auth list`
    because its display names (e.g. "MiniMax (minimaxi.com)") don't match
    the actual provider keys (e.g. "minimax-cn").
    """
    auth_file = (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        / "opencode"
        / "auth.json"
    )
    if not auth_file.exists():
        return set()
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return {k for k, v in data.items() if isinstance(v, dict) and v.get("key")}


def model_costs() -> dict[str, tuple[float, float]]:
    """{full_id: (input_cost, output_cost)} from `opencode models --verbose`.

    Output is a sequence of `<provider>/<id>\n{...}\n` blocks. We walk the
    stream tracking brace depth to extract each JSON object. Returns {} on
    failure (opencode missing, parse error, etc.).
    """
    try:
        out = subprocess.check_output(
            ["opencode", "models", "--verbose"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return {}
    costs: dict[str, tuple[float, float]] = {}
    i = 0
    n = len(out)
    while i < n:
        if out[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        while j < n:
            ch = out[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(out[i : j + 1])
                        mid = data.get("id", "")
                        prov = data.get("providerID", "")
                        if mid and prov:
                            cost = data.get("cost") or {}
                            costs[f"{prov}/{mid}"] = (
                                float(cost.get("input", 0) or 0),
                                float(cost.get("output", 0) or 0),
                            )
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
            j += 1
        else:
            break
    return costs


def is_free(model: str, costs: dict[str, tuple[float, float]]) -> bool:
    c = costs.get(model)
    return c is not None and c[0] == 0 and c[1] == 0


def probe_model(model: str, timeout: int = 30) -> bool:
    """Send a minimal request to verify the model is actually callable.

    Uses `opencode run --model <m> "ping"`. Best-effort: 30s timeout, exit 0
    counts as success. Consumes a small number of tokens.
    """
    try:
        result = subprocess.run(
            ["opencode", "run", "--model", model, "ping"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def used_models(root=None) -> list[str]:
    root = root or git_root() or Path.cwd()
    from .board import agent_source, parse_frontmatter

    result = []
    for fp in sorted(agent_source(root).glob("*.md")):
        if fp.name in {"README.md", "ROSTER.md"}:
            continue
        fm, _ = parse_frontmatter(fp.read_text(encoding="utf-8"))
        binding = frontmatter_binding(fm)
        if binding:
            result.append(binding)
    return sorted(set(result))


def _rank(
    candidates: list[str],
    costs: dict[str, tuple[float, float]],
    auth: set[str] | None = None,
) -> str:
    """Pick best candidate: free > user-auth'd non-opencode provider > opencode/Zen > alphabetical."""

    def _key(m: str) -> tuple:
        prov = m.split("/", 1)[0]
        free_rank = 0 if is_free(m, costs) else 1
        if prov == "opencode":
            provider_rank = 2
        elif auth is not None and prov in auth:
            provider_rank = 0
        elif auth is not None:
            provider_rank = 1
        else:
            provider_rank = 1
        return (free_rank, provider_rank, m)

    return sorted(candidates, key=_key)[0]


def _filter_auth(candidates: list[str], auth: set[str] | None) -> list[str]:
    """If auth info is available, keep only candidates whose provider is auth'd.

    Returns candidates unchanged when auth is None (no auth info) or empty
    (caller signalled "auth discovery unavailable, don't filter").
    """
    if not auth:
        return candidates
    return [m for m in candidates if m.split("/", 1)[0] in auth]


def resolve_model(
    name: str,
    root=None,
    models=None,
    auth: set[str] | None = None,
    costs: dict | None = None,
) -> str:
    root = root or git_root() or Path.cwd()
    assigned = _role_assignment(name, root)
    if assigned and assigned != name:
        return resolve_model(assigned, root=root, models=models, auth=auth, costs=costs)
    project_aliases = load_config(config_path(True, root)).get("aliases", {})
    user_aliases = load_config(config_path(False)).get("aliases", {})
    if name in project_aliases:
        return project_aliases[name]
    if name in user_aliases:
        return user_aliases[name]
    candidates = models if models is not None else opencode_models()
    target = normalize(name)
    strong = [m for m in candidates if normalize(m.split("/")[-1]) == target]
    authed_strong = _filter_auth(strong, auth)
    if authed_strong:
        return _rank(authed_strong, costs or {}, auth)
    if strong and not auth:
        return _rank(strong, costs or {}, auth)
    weak = _levenshtein_candidates(name, candidates)
    authed_weak = _filter_auth(weak, auth)
    if authed_weak:
        return _rank(authed_weak, costs or {}, auth)
    if weak and not auth:
        return _rank(weak, costs or {}, auth)
    return name


def _classify(
    name: str, models: list[str], auth: set[str] | None, costs: dict
) -> tuple[str, str, str]:
    """Return (status, resolved, note).

    status ∈ {alias, ok, candidate, unresolved}
    note  ∈ {'', 'weak', 'unauthenticated', 'weak+unauthenticated', 'probed_ok', 'probe_failed'}
    """
    project_aliases = load_config(config_path(True)).get("aliases", {})
    user_aliases = load_config(config_path(False)).get("aliases", {})
    if name in project_aliases:
        return "alias", project_aliases[name], ""
    if name in user_aliases:
        return "alias", user_aliases[name], ""
    target = normalize(name)
    strong = [m for m in models if normalize(m.split("/")[-1]) == target]
    if strong:
        authed = _filter_auth(strong, auth)
        if authed:
            return "ok", _rank(authed, costs, auth), ""
        if auth is not None:
            return "candidate", _rank(strong, costs, auth), "unauthenticated"
        return "ok", _rank(strong, costs, auth), ""
    weak = [
        m
        for m in models
        if target in normalize(m.split("/")[-1])
        or normalize(m.split("/")[-1]) in target
    ]
    if weak:
        authed = _filter_auth(weak, auth)
        if len(authed) == 1:
            return "ok", authed[0], "weak"
        if auth is not None and weak and not authed:
            return "candidate", _rank(weak, costs, auth), "weak+unauthenticated"
        if len(weak) == 1 and not auth:
            return "ok", weak[0], "weak"
    return "unresolved", name, ""


def cmd_list(args):
    from ._color import cyan, dim

    for name in used_models():
        resolved = resolve_model(name)
        if resolved == name:
            print(f"{name}\t{dim('-')}")
        else:
            print(f"{name}\t{cyan(resolved)}")
    return 0


def cmd_doctor(args):
    from ._color import (
        cyan,
        dim,
        green as g,
        red as r,
        ok,
        Spinner,
    )

    quiet = getattr(args, "quiet", False)
    used = used_models()
    if not quiet:
        print(
            f"{cyan('[1/4]')} scanning source agents: found {len(used)} abstract model(s)",
            flush=True,
        )
        print(
            f"      sample: {', '.join(used[:3])}{'...' if len(used) > 3 else ''}",
            flush=True,
        )
    if not quiet:
        print(f"{cyan('[2/4]')} querying opencode models (subprocess)...", flush=True)
    with Spinner("querying opencode models"):
        models = opencode_models()
    if not quiet:
        print(f"      returned {len(models)} models", flush=True)
        print(f"{cyan('[3/4]')} reading auth.json + model costs", flush=True)
    with Spinner("reading auth.json + model costs"):
        auth = auth_providers() if models else None
        costs = model_costs() if models else {}
    if not quiet:
        if auth:
            print(f"      auth providers ({len(auth)}): {sorted(auth)}", flush=True)
        else:
            print(
                f"      auth providers: {dim('(none / auth.json missing)')}", flush=True
            )
        free = sum(1 for v in costs.values() if v == (0, 0))
        print(f"      model costs: {len(costs)}, of which {free} are free", flush=True)
        print(
            f"{cyan('[4/4]')} three-layer validation {dim('(alias -> strong/weak match -> auth filter)')}",
            flush=True,
        )
    all_ok = True
    fixes: dict[str, str] = {}
    # Keep configured legacy aliases visible even when current agents use the
    # S/A/B intelligence quotations. This preserves the doctor contract for
    # users migrating an existing models.json.
    configured_aliases = load_config(config_path(False)).get("aliases") or {}
    for alias, target in sorted(configured_aliases.items()):
        print(f"{ok()} {alias} -> {target} {dim('(alias)')}")
    for name in used_models():
        status, resolved, note = _classify(name, models, auth, costs)
        if status == "alias":
            print(f"{ok()} {name} -> {resolved} {dim('(alias)')}")
            continue
        if status == "ok":
            tag = f" {dim('(' + note + ')')}" if note else ""
            line = f"{ok()} {name} -> {resolved}{tag}"
            if args.probe:
                if probe_model(resolved):
                    line += f" {g('(probed ok)')}"
                else:
                    line += f" {r('(probe failed)')}"
                    all_ok = False
            print(line)
            fixes[name] = resolved
            continue
        if status == "candidate":
            tag = f" ({note})" if note else ""
            print(
                f"~ {name} -> {resolved}{tag}; "
                f"run: lk models bind {name} <provider>/<id> after opencode /connect"
            )
            all_ok = False
            continue
        print(f"✗ {name} unresolved; run: lk models bind {name} provider/{name}")
        all_ok = False
    if args.fix_auto and fixes:
        path = config_path(False)
        data = load_config(path)
        data["aliases"].update(fixes)
        save_config(path, data)
        print(f"--fix-auto wrote {len(fixes)} aliases to {path}")
    return 0 if all_ok else 1


def cmd_bind(args):
    if args.all_unresolved or args.abstract is None:
        return _interactive_bind_batch(args.project)
    if args.full is None:
        return _interactive_bind_one(args.abstract, args.project)
    return _direct_bind(args.abstract, args.full, args.project)


def _direct_bind(abstract: str, full: str, project: bool) -> int:
    path = config_path(project)
    data = load_config(path)
    data["aliases"][abstract] = full
    save_config(path, data)
    from ._color import ok

    print(f"{ok()} {abstract} -> {full} (written to {path})")
    return 0


def _probe_or_skip(model: str, project: bool, allow_skip: bool = True) -> bool:
    """Probe model before binding. Returns True if usable OR user chose skip.

    If model is unusable, prompts user: retry / skip / cancel.
    """
    from ._color import Spinner, ok as _ok, fail as _fail, warn, dim

    print(f"  {dim('validating')} {model} ...", flush=True)
    with Spinner(f"probe {model}"):
        ok = probe_model(model)
    if ok:
        print(f"  {_ok('usable')}")
        return True
    print(
        f"  {_fail('unusable')} (probe failed / key expired / model retired / 30s timeout)"
    )
    if not allow_skip:
        return False
    while True:
        try:
            choice = (
                input(
                    "  [r] retry / [s] skip (do not bind) / [a] force bind? [r/s/a]: "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {warn('interrupted')}")
            return False
        if choice in ("r", "retry", ""):
            print(f"  {dim('retrying...')}")
            with Spinner(f"probe {model}"):
                ok = probe_model(model)
            if ok:
                print(f"  {_ok('usable')}")
                return True
            print(f"  {_fail('still unusable')}")
            continue
        if choice in ("s", "skip"):
            print(f"  {dim('skipped')}")
            return False
        if choice in ("a", "always"):
            print(f"  {warn('force-saving; OpenCode may fail at runtime')}")
            return True
        print(f"  {dim('invalid')}")


def _levenshtein_candidates(
    abstract: str, candidates: list[str], min_sim: float = 0.7
) -> list[str]:
    """Return candidates whose model-id is close to `abstract` by Levenshtein.

    Uses `louke._common.similarity` (1 - lev/max_len). Keeps any candidate
    within `min_sim` of the best score, so we don't accidentally drop ties
    (e.g. `kimi-2.7-code` vs both `kimi-k2.6` and `kimi-k2.7-code`).
    """
    from ._common import similarity

    target = normalize(abstract)
    if not target:
        return []
    scored: list[tuple[str, float]] = []
    for m in candidates:
        mid = normalize(m.split("/")[-1])
        if not mid:
            continue
        sim = similarity(target, mid)
        if sim >= min_sim:
            scored.append((m, sim))
    if not scored:
        return []
    best = max(s for _, s in scored)
    threshold = max(min_sim, best - 0.05)
    return [m for m, s in scored if s >= threshold]


def _rank_candidates(abstract: str, models: list[str]) -> list[str]:
    """Return relevant model candidates, sorted by Levenshtein similarity.

    Strategy: normalize both abstract and model (strip non-alphanumeric, lowercase),
    then compute similarity = 1 - levenshtein(a, m) / max(len(a), len(m)).
    Sort by similarity desc, then alphabetical. Top 12 returned.
    Falls back to first 20 models if no good match.
    """
    from ._common import similarity

    abstract_norm = normalize(abstract)
    if not abstract_norm:
        return models[:20]
    scored = []
    for m in models:
        m_norm = normalize(m.split("/")[-1])
        if not m_norm:
            continue
        sim = similarity(abstract_norm, m_norm)
        if sim > 0:
            scored.append((m, sim))
    if not scored:
        return models[:20]
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [m for m, _ in scored[:12]]


def _interactive_bind_one(abstract: str, project: bool) -> int:
    """Interactively bind one abstract: list candidates -> user picks/types -> probe -> write."""
    from ._color import info, warn, dim, red, cyan
    from .models import auth_providers

    print(
        f"\n{info()} {cyan(abstract)} {warn('no match found')} (one of {len(extract_unresolved(project))} unresolved)"
    )

    # 1. Try opencode models
    candidates: list[str] = []
    opencode_ok = False
    try:
        from ._color import Spinner

        with Spinner("querying opencode models"):
            candidates = opencode_models()
        opencode_ok = bool(candidates)
    except Exception:
        pass

    if opencode_ok:
        relevant = _rank_candidates(abstract, candidates)
        print(
            f"  {dim('opencode models:')} {len(candidates)} total, {len(relevant)} relevant to {cyan(abstract)}:"
        )
        for i, m in enumerate(relevant, 1):
            print(f"  {dim(str(i).rjust(2))}. {m}")
    else:
        # 2. Fallback: list auth providers (read from auth.json)
        auth = auth_providers()
        print(
            f"  {dim('(opencode CLI not installed; can only list auth providers; use 0 to enter a custom full model)')}"
        )
        for i, p in enumerate(sorted(auth), 1):
            print(f"  {dim(str(i).rjust(2))}. {p}/<model>")
    print(f"  {dim(' 0')}. custom provider/model")
    print(f"  {dim(' q')}. skip")

    while True:
        try:
            choice = (
                input(
                    f"\n  {cyan('->')} pick [1-{len(candidates) if opencode_ok else len(auth)}/0/q]: "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {warn('interrupted, not bound')}")
            return 1

        if choice in ("q", "quit"):
            print(f"  {dim('skipped')} {abstract}")
            return 0
        if choice == "0":
            try:
                custom = input(
                    f"  {cyan('->')} provider/model (e.g. kimi-for-coding/kimi-latest): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print(f"  {warn('interrupted')}")
                return 1
            if not custom:
                continue
            if opencode_ok and custom not in candidates:
                # warn but accept
                confirm = (
                    input(
                        f"  {warn(custom)} is not in opencode models. Bind anyway? [y/N]: "
                    )
                    .strip()
                    .lower()
                )
                if confirm != "y":
                    continue
            # NEW: probe custom before save
            if not _probe_or_skip(custom, project):
                continue
            return _direct_bind(abstract, custom, project)
        if choice.isdigit():
            idx = int(choice) - 1
            pool = relevant if opencode_ok else sorted(auth)
            if 0 <= idx < len(pool):
                selected = pool[idx]
                # NEW: probe before save
                if not _probe_or_skip(selected, project):
                    continue
                return _direct_bind(abstract, selected, project)
        print(f"  {red('invalid choice')}, retry")


def extract_unresolved(project: bool = False) -> list[str]:
    """Return list of abstract model names that can't be resolved to a real model.

    Uses the actual resolve_model to detect unresolved: if result == input,
    the abstract can't be resolved through alias / opencode models / auth filter.
    """
    used = used_models()
    return [n for n in used if resolve_model(n) == n]


def _interactive_bind_batch(project: bool) -> int:
    """Batch interactive: bind each unresolved abstract one by one."""
    from ._color import info, dim, cyan

    unresolved = extract_unresolved(project)
    if not unresolved:
        print(f"{info()} no unresolved abstracts, nothing to bind")
        return 0
    print(
        f"{info()} found {cyan(str(len(unresolved)))} unresolved abstract(s): {', '.join(unresolved)}\n"
    )
    for i, name in enumerate(unresolved, 1):
        print(f"{dim(f'[{i}/{len(unresolved)}]')} ", end="")
        if _interactive_bind_one(name, project) != 0:
            return 1
    return 0


def cmd_unbind(args):
    path = config_path(args.project)
    data = load_config(path)
    data["aliases"].pop(args.abstract, None)
    save_config(path, data)
    return 0
