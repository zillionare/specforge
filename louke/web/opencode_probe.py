"""OpenCode real model probe for Login readiness verification.

AC-FR0201-01, AC-FR0201-02, AC-FR0301-01

Executes a minimal real ``opencode run --model <id> "please echo hi"``
to verify that at least one configured model is reachable. The probe
does not carry Story, artifact, credential, or workspace file context.
"""

from __future__ import annotations

import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

PROBE_PROMPT = "please echo hi"
SINGLE_TIMEOUT_SECONDS = 15
TOTAL_DEADLINE_SECONDS = 60

#: Canonical recovery surface for every Login model-check diagnosis.
RECOVERY_URL = "/login"


def _actionable_diagnosis(
    *,
    reason: str,
    object_name: str,
    known_facts: str,
    impact: str,
) -> dict[str, Any]:
    """Build a non-secret, actionable diagnosis (interfaces §IF-SETUP-03).

    The diagnosis carries the four contract fields ``object``,
    ``known_facts``, ``impact`` and ``recovery_url`` (acceptance
    AC-NFR0201-02) plus the stable ``reason`` discriminator the readiness
    projection relies on. Provider output (subprocess stderr) is
    deliberately *never* embedded here so a credential printed by the
    provider cannot leak into the manifest, the API, the Guide, or
    evidence (interfaces §1 Redaction).

    Args:
        reason: Stable machine discriminator (``timeout``,
            ``nonzero_exit``, ``executable_not_found``).
        object_name: What failed, in human terms.
        known_facts: Non-secret observed facts (exit code, deadline).
        impact: The consequence for Login readiness.

    Returns:
        A redacted diagnosis dict with the four actionable fields.
    """
    return {
        "reason": reason,
        "object": object_name,
        "known_facts": known_facts,
        "impact": impact,
        "recovery_url": RECOVERY_URL,
    }


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a single model probe attempt.

    Args:
        model_id: The model id that was probed.
        state: ``passed``, ``failed``, or ``uncertain``.
        diagnosis: Non-secret diagnostic dict, or ``None``.
    """

    model_id: str
    state: str
    diagnosis: dict[str, Any] | None = None


@dataclass
class ModelCheckResult:
    """Aggregate result of checking all candidate models.

    Args:
        check_id: Stable identifier for this check attempt.
        revision: Check-scoped revision.
        state: ``queued``, ``running``, ``passed``, ``failed``, or ``uncertain``.
        current_model_id: The model currently being probed, or ``None``.
        attempted: List of individual probe results.
        diagnosis: Non-secret diagnostic, or ``None``.
        observed_at: ISO-8601 timestamp.
    """

    check_id: str
    revision: int
    state: str = "queued"
    current_model_id: str | None = None
    attempted: list[ProbeResult] = field(default_factory=list)
    diagnosis: dict[str, Any] | None = None
    observed_at: str = ""


def is_available() -> bool:
    """Return ``True`` if the ``opencode`` executable is on PATH."""
    return shutil.which("opencode") is not None


def run_minimal(
    *,
    model_id: str,
    prompt: str = PROBE_PROMPT,
    deadline_seconds: int = SINGLE_TIMEOUT_SECONDS,
    executable: str = "opencode",
) -> ProbeResult:
    """Run a single minimal model probe.

    Args:
        model_id: The model id to probe.
        prompt: The minimal prompt (default: ``PROBE_PROMPT``).
        deadline_seconds: Per-model timeout.
        executable: The executable name or path.

    Returns:
        A :class:`ProbeResult` with ``state=passed`` on exit 0,
        ``state=failed`` on non-zero exit, or ``state=uncertain``
        on timeout.
    """
    try:
        proc = subprocess.run(
            [executable, "run", "--model", model_id, prompt],
            capture_output=True,
            text=True,
            timeout=deadline_seconds,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(
            model_id=model_id,
            state="uncertain",
            diagnosis=_actionable_diagnosis(
                reason="timeout",
                object_name="opencode model check",
                known_facts=(
                    f"opencode run --model {model_id} did not finish "
                    f"within {deadline_seconds}s"
                ),
                impact="Login readiness cannot verify a working OpenCode model",
            ),
        )
    except FileNotFoundError:
        return ProbeResult(
            model_id=model_id,
            state="failed",
            diagnosis=_actionable_diagnosis(
                reason="executable_not_found",
                object_name="opencode executable",
                known_facts="the opencode executable was not found on PATH",
                impact="Login readiness cannot run a model check",
            ),
        )
    except OSError:
        return ProbeResult(
            model_id=model_id,
            state="failed",
            diagnosis=_actionable_diagnosis(
                reason="executable_unavailable",
                object_name="opencode executable",
                known_facts="the opencode executable could not be executed",
                impact="Login readiness cannot run a model check",
            ),
        )
    if proc.returncode == 0:
        return ProbeResult(model_id=model_id, state="passed")
    # Non-zero exit: report the exit code only. Subprocess stderr is never
    # embedded so a provider credential cannot leak into the diagnosis.
    return ProbeResult(
        model_id=model_id,
        state="failed",
        diagnosis=_actionable_diagnosis(
            reason="nonzero_exit",
            object_name="opencode model check",
            known_facts=(
                f"opencode run --model {model_id} exited with code {proc.returncode}"
            ),
            impact="Login readiness cannot verify a working OpenCode model",
        ),
    )


def discover_candidates() -> list[str]:
    """Return the configured OpenCode candidate model ids, stably sorted.

    Delegates to :func:`louke.models.opencode_models` (the real ``opencode
    models`` enumeration) and sorts by model id so the probe order is
    deterministic. Returns an empty list when no models are configured.
    """
    from louke.models import opencode_models

    return sorted(opencode_models())


def run_check(
    *,
    candidates: list[str] | None = None,
    single_timeout_seconds: int = SINGLE_TIMEOUT_SECONDS,
    total_deadline_seconds: int = TOTAL_DEADLINE_SECONDS,
) -> ModelCheckResult:
    """Run a full model check across the candidate models.

    AC-FR0201-01, AC-FR0201-02, AC-FR0301-01

    Probes the candidate models in stable order with a per-model timeout
    (``single_timeout_seconds``) bounded by an overall deadline
    (``total_deadline_seconds``). The first model whose minimal request
    exits 0 marks the check ``passed``; reaching the deadline with no
    success is ``uncertain``; otherwise the check is ``failed`` carrying the
    last attempt's non-secret diagnosis. A bare model list / credential /
    executable check never yields ``passed`` — only a real ``opencode run``
    exit 0 does (interfaces §IF-SETUP-03 External invocation).

    Args:
        candidates: Candidate model ids. When ``None``, discovered via
            :func:`discover_candidates`. Injectable for tests.
        single_timeout_seconds: Per-model probe timeout.
        total_deadline_seconds: Overall check deadline.

    Returns:
        A :class:`ModelCheckResult` aggregating the attempts.
    """
    if candidates is None:
        candidates = discover_candidates()
    observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = ModelCheckResult(
        check_id=f"chk_{secrets.token_hex(6)}",
        revision=1,
        state="running",
        observed_at=observed_at,
    )
    if not candidates:
        result.state = "uncertain"
        result.diagnosis = _actionable_diagnosis(
            reason="no_candidates",
            object_name="opencode model check",
            known_facts="no configured OpenCode models were discovered",
            impact="Login readiness cannot verify a working OpenCode model",
        )
        return result

    deadline = time.monotonic() + total_deadline_seconds
    for model_id in candidates:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result.state = "uncertain"
            result.diagnosis = _actionable_diagnosis(
                reason="timeout",
                object_name="opencode model check",
                known_facts=(f"no model succeeded within {total_deadline_seconds}s"),
                impact="Login readiness cannot verify a working OpenCode model",
            )
            break
        result.current_model_id = model_id
        probe = run_minimal(
            model_id=model_id,
            deadline_seconds=min(single_timeout_seconds, max(1, int(remaining))),
        )
        result.attempted.append(probe)
        if probe.state == "passed":
            result.state = "passed"
            result.current_model_id = model_id
            result.diagnosis = None
            return result
    if result.state == "running":
        last = result.attempted[-1]
        result.state = "failed"
        result.diagnosis = last.diagnosis
    return result
