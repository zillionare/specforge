"""Authenticated v0.14 Story read model and Scribe task endpoints."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from louke.runtime.store import RunNotFoundError
from louke.runtime.scribe_entry import ScribeEntryService, ScribeTaskError

from louke.web.auth import (
    SESSION_COOKIE,
    csrf_token_for_session,
    current_user,
    same_origin,
)
from louke.web.csrf_middleware import verify_token as verify_csrf_token


async def story_page(request: Request) -> HTMLResponse | JSONResponse:
    """Render the canonical Story page with its current task summary."""
    user_or_response = _require_human(request, csrf_required=False)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    binding = _project_binding(request)
    if binding is None or not binding.get("run_id"):
        return _error("NOT_FOUND", "no Runtime run exists", 404)
    run = _run_for_binding(request, str(binding["run_id"]))
    if run is None:
        return _error("NOT_FOUND", "persisted project run does not exist", 404)
    artifact = request.app.state.story_entry.artifact(run.run_id)
    if artifact is None:
        return _error("NOT_FOUND", "Story artifact does not exist", 404)
    task = _task_for_artifact(request, run.run_id)
    body = escape(artifact.body_md)
    task_text = escape(str(task.get("task_id"))) if task else "not created"
    gate = _scribe(request).story_gate(run.run_id)
    csrf = escape(
        csrf_token_for_session(
            request.app.state.store, request.cookies.get(SESSION_COOKIE, "")
        ),
        quote=True,
    )
    task_id = escape(str(task.get("task_id"))) if task else ""
    run_id = escape(run.run_id)
    return HTMLResponse(
        "<html><body><main id='story-page'>"
        f"<h1>Story</h1><p data-run='{escape(run.run_id)}'>"
        f"Phase: {escape(run.current_step)} · Revision: {artifact.revision}</p>"
        f"<pre data-task='{task_text}'>{body}</pre>"
        f"{_chat_markup(run_id, task_id, csrf)}"
        f"{_chat_script(run_id, task_id, csrf)}"
        f"{_decision_markup(run_id, request.path_params['project_id'], run.revision, artifact.revision, gate, csrf)}"
        "</main></body></html>"
    )


async def current_project(request: Request) -> JSONResponse:
    """Return the current project/run and Story task read model."""
    user_or_response = _require_human(request, csrf_required=False)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    binding = _project_binding(request)
    if binding is None or not binding.get("run_id"):
        return _error("NOT_FOUND", "no Runtime run exists", 404)
    run = _run_for_binding(request, str(binding["run_id"]))
    if run is None:
        return _error("NOT_FOUND", "persisted project run does not exist", 404)
    artifact = request.app.state.story_entry.artifact(run.run_id)
    task = _task_for_artifact(request, run.run_id)
    gate = _scribe(request).story_gate(run.run_id)
    project = binding.get("project") if isinstance(binding.get("project"), dict) else {}
    return JSONResponse(
        {
            "project": {
                "project_id": project.get("project_id", binding["project_id"]),
                "spec_id": project.get("spec_id"),
            },
            "run": {
                "run_id": run.run_id,
                "revision": run.revision,
                "phase": run.current_step,
                "status": run.status,
            },
            "artifact": _artifact_model(artifact) if artifact else None,
            "task": _task_summary(task),
            "human_wait": gate["human_wait"],
            "story_gate": gate,
            "allowed_actions": (["story_decision"] if gate["pending_action"] else []),
            "continue_url": f"/projects/{request.path_params['project_id']}/requirements/story",
        }
    )


async def run_action(request: Request) -> JSONResponse:
    """Apply one authenticated Runtime-owned Human phase action."""
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("JSON object payload is required")
        if payload.get("action") != "story_decision":
            raise ScribeTaskError(
                "WORKFLOW_STATE_CONFLICT", "only story_decision is available at M-STORY"
            )
        action_payload = payload.get("payload")
        if not isinstance(action_payload, dict):
            raise ValueError("payload object is required")
        if "actor_kind" in action_payload or "actor" in action_payload:
            raise ScribeTaskError(
                "HUMAN_AUTHORITY_REQUIRED",
                "actor identity is derived from the authenticated Human session",
            )
        binding = request.app.state.release_entry.project_for_run(
            request.path_params["run_id"]
        )
        requested_project = action_payload.get("project_id")
        if binding is None or (
            requested_project is not None and requested_project != binding["project_id"]
        ):
            return _error("NOT_FOUND", "run is not bound to this project", 404)
        result = _scribe(request).decide_story(
            run_id=request.path_params["run_id"],
            value=_required_string(action_payload, "candidate"),
            reason=_required_string(action_payload, "reason"),
            expected_run_revision=_required_int(payload, "expected_run_revision"),
            expected_artifact_revision=_required_int(
                payload, "expected_artifact_revision"
            ),
            idempotency_key=_required_string(payload, "idempotency_key"),
            actor=f"human:{user_or_response.username}",
            actor_kind="human",
        )
    except ScribeTaskError as exc:
        return _error(exc.code, exc.message, _status_for_error(exc.code))
    except ValueError as exc:
        return _error("VALIDATION_FAILED", str(exc), 400)
    return JSONResponse(result)


async def story_artifact(request: Request) -> JSONResponse:
    """Return the persisted Story artifact without exposing write authority."""
    user_or_response = _require_human(request, csrf_required=False)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    if request.path_params["kind"] != "story":
        return _error("NOT_FOUND", "only the Story artifact is available", 404)
    artifact = request.app.state.story_entry.artifact(request.path_params["run_id"])
    if artifact is None:
        return _error("NOT_FOUND", "Story artifact does not exist", 404)
    return JSONResponse(_artifact_model(artifact))


async def task_read(request: Request) -> JSONResponse:
    """Return a task bound to the requested Runtime run."""
    user_or_response = _require_human(request, csrf_required=False)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        return JSONResponse(_scribe(request).task_read(**request.path_params))
    except ScribeTaskError as exc:
        return _error(exc.code, exc.message, 409)


async def task_messages(request: Request) -> JSONResponse:
    """Return persisted Chat messages for a bound Scribe task."""
    user_or_response = _require_human(request, csrf_required=False)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        return JSONResponse(
            {"messages": _scribe(request).list_messages(**request.path_params)}
        )
    except ScribeTaskError as exc:
        return _error(exc.code, exc.message, 409)


async def task_reply(request: Request) -> JSONResponse:
    """Persist and dispatch one authenticated Human Chat reply."""
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    payload = await request.json()
    try:
        result = _scribe(request).reply(
            run_id=request.path_params["run_id"],
            task_id=request.path_params["task_id"],
            client_message_id=_required_string(payload, "client_message_id"),
            correlation_id=_required_string(payload, "correlation_id"),
            body=_required_string(payload, "body"),
            expected_attempt_id=_required_string(payload, "expected_attempt_id"),
            expected_artifact_revision=_required_int(
                payload, "expected_artifact_revision"
            ),
        )
    except ScribeTaskError as exc:
        return _error(exc.code, exc.message, 409)
    except ValueError as exc:
        return _error("VALIDATION_ERROR", str(exc), 400)
    return JSONResponse(result, status_code=202)


async def task_reconcile(request: Request) -> JSONResponse:
    """Reconcile a task with its existing OpenCode session."""
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        return JSONResponse(
            _scribe(request).reconcile(
                request.path_params["run_id"], request.path_params["task_id"]
            )
        )
    except ScribeTaskError as exc:
        return _error(exc.code, exc.message, 409)


async def task_retry(request: Request) -> JSONResponse:
    """Retry a blocked task using the server-owned workspace path."""
    user_or_response = _require_human(request, csrf_required=True)
    if isinstance(user_or_response, JSONResponse):
        return user_or_response
    try:
        result = _scribe(request).retry(
            request.path_params["run_id"],
            request.path_params["task_id"],
            str(Path(request.app.state.scribe_entry.workspace_root or "")),
        )
    except ScribeTaskError as exc:
        return _error(exc.code, exc.message, 409)
    return JSONResponse(result, status_code=202)


def _scribe(request: Request) -> ScribeEntryService:
    """Return the application-owned Scribe service."""
    return request.app.state.scribe_entry


def _project_binding(request: Request) -> dict[str, Any] | None:
    """Resolve a project path through its exact persisted release identity."""
    return request.app.state.release_entry.current_project(
        request.path_params["project_id"]
    )


def _run_for_binding(request: Request, run_id: str):
    """Return only the run named by the persisted project binding."""
    try:
        return request.app.state.v12_run_store.get_run(run_id)
    except RunNotFoundError:
        return None


def _task_for_artifact(request: Request, run_id: str) -> dict[str, Any] | None:
    """Read the task bound to a run without creating a new task."""
    return _scribe(request).task_for_run(run_id)


def _artifact_model(artifact: Any) -> dict[str, Any]:
    """Build the public Story artifact model."""
    return {
        "kind": "story",
        "path": "story.md",
        "body_md": artifact.body_md,
        "revision": artifact.revision,
        "version_token": artifact.digest,
        "digest": artifact.digest,
        "commit_sha": artifact.commit_sha,
        "locked": True,
        "readonly": True,
        "readonly_reason": "Scribe lease owns Story task scope",
    }


def _task_summary(task: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the compact current-model task summary."""
    if task is None:
        return None
    return {
        "task_id": task["task_id"],
        "attempt_id": task["active_attempt_id"],
        "session_id": task["session_id"],
        "status": task["status"],
        "connection": task["connection"],
    }


def _status_for_error(code: str) -> int:
    """Map controlled phase-action errors to their stable HTTP status."""
    if code in {"HUMAN_AUTHORITY_REQUIRED"}:
        return 403
    if code in {"NOT_FOUND"}:
        return 404
    if code in {
        "VALIDATION_FAILED",
        "RESULT_ROLE_CONFLICT",
        "RESULT_WRITE_SCOPE_DENIED",
    }:
        return 400
    return 409


def _require_human(request: Request, *, csrf_required: bool):
    """Require a server-authenticated Human session and optional CSRF proof."""
    session = request.cookies.get(SESSION_COOKIE)
    user = current_user(request.app.state.store, session)
    if user is None:
        return _error("AUTH_REQUIRED", "login required", 401)
    if csrf_required and not same_origin(
        request, getattr(request.app.state, "allowed_origin", None)
    ):
        return _error(
            "ORIGIN_FORBIDDEN",
            "configured same-origin Origin header required",
            403,
        )
    if csrf_required and not verify_csrf_token(
        token=request.headers.get("x-louke-csrf", ""),
        session_id=session,
    ):
        return _error("CSRF_INVALID", "valid session-bound CSRF token required", 403)
    return user


def _required_string(payload: dict[str, Any], field: str) -> str:
    """Return a required non-empty string field."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_int(payload: dict[str, Any], field: str) -> int:
    """Return a required integer field without accepting booleans."""
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _error(code: str, message: str, status: int) -> JSONResponse:
    """Return a stable API error envelope."""
    return JSONResponse({"error_code": code, "message": message}, status_code=status)


def _chat_markup(run_id: str, task_id: str, csrf: str) -> str:
    """Return task-bound Scribe Chat controls without Human gate actions."""
    if not task_id:
        return "<section id='scribe-chat' data-task-id=''>Scribe task unavailable</section>"
    return (
        "<section id='scribe-chat' aria-label='Scribe Chat' "
        f"data-run-id='{run_id}' data-task-id='{task_id}' data-csrf='{csrf}'>"
        "<h2>Scribe Chat</h2><dl id='scribe-facts'></dl>"
        "<p id='scribe-status'>Loading</p><ol id='scribe-messages'></ol>"
        "<form id='scribe-reply'><textarea id='scribe-body' required></textarea>"
        "<button id='scribe-send' type='submit'>Send</button></form>"
        "<button id='scribe-retry' type='button' hidden>Retry</button>"
        "<button id='scribe-reconcile' type='button' hidden>Reconcile</button>"
        "</section>"
    )


def _chat_script(run_id: str, task_id: str, csrf: str) -> str:
    """Return the browser controller for persisted task-bound Chat."""
    return f"""<script>
const scribeRun = {run_id!r};
const scribeTask = {task_id!r};
const scribeCsrf = {csrf!r};
const chat = document.getElementById("scribe-chat");
const facts = document.getElementById("scribe-facts");
const statusLine = document.getElementById("scribe-status");
const messages = document.getElementById("scribe-messages");
const send = document.getElementById("scribe-send");
const body = document.getElementById("scribe-body");
const retry = document.getElementById("scribe-retry");
const reconcile = document.getElementById("scribe-reconcile");
let task;
function showTask(value) {{
  task = value;
  facts.textContent = `Role: ${{value.role}} · Task: ${{value.task_id}} · Attempt: ${{value.active_attempt.attempt_id}} · Session: ${{value.session_id || "none"}}`;
  statusLine.textContent = `Connection: ${{value.connection}} · Status: ${{value.status}}${{value.last_error ? ` · Error: ${{value.last_error}}` : ""}}`;
  retry.hidden = !value.allowed_actions.includes("retry");
  reconcile.hidden = !value.allowed_actions.includes("reconcile");
  send.disabled = false;
}}
async function refreshChat() {{
  const taskResponse = await fetch(`/api/runs/${{scribeRun}}/tasks/${{scribeTask}}`);
  if (!taskResponse.ok) {{ statusLine.textContent = "Scribe task unavailable"; return; }}
  showTask(await taskResponse.json());
  const messageResponse = await fetch(`/api/runs/${{scribeRun}}/tasks/${{scribeTask}}/messages`);
  if (!messageResponse.ok) return;
  messages.replaceChildren();
  for (const item of (await messageResponse.json()).messages) {{
    const node = document.createElement("li");
    node.textContent = `${{item.role}}: ${{item.body}} (${{item.status}})`;
    messages.appendChild(node);
  }}
}}
document.getElementById("scribe-reply").addEventListener("submit", async (event) => {{
  event.preventDefault();
  if (!task || !body.value.trim()) return;
  send.disabled = true;
  const clientMessageId = crypto.randomUUID();
  try {{
    await fetch(`/api/runs/${{scribeRun}}/tasks/${{scribeTask}}/messages`, {{
      method: "POST", headers: {{"Content-Type": "application/json", "X-Louke-CSRF": scribeCsrf}},
      body: JSON.stringify({{client_message_id: clientMessageId, correlation_id: `chat:${{clientMessageId}}`, body: body.value, expected_attempt_id: task.active_attempt.attempt_id, expected_artifact_revision: task.artifact.revision}})
    }});
    body.value = "";
    await refreshChat();
  }} finally {{ send.disabled = false; }}
}});
  retry.addEventListener("click", async () => {{ retry.disabled = true; await fetch(`/api/runs/${{scribeRun}}/tasks/${{scribeTask}}/retry`, {{method: "POST", headers: {{"X-Louke-CSRF": scribeCsrf}}}}); retry.disabled = false; await refreshChat(); }});
  reconcile.addEventListener("click", async () => {{ reconcile.disabled = true; await fetch(`/api/runs/${{scribeRun}}/tasks/${{scribeTask}}/reconcile`, {{method: "POST", headers: {{"X-Louke-CSRF": scribeCsrf}}}}); reconcile.disabled = false; await refreshChat(); }});
refreshChat();
</script>"""


def _decision_markup(
    run_id: str,
    project_id: str,
    run_revision: int,
    artifact_revision: int,
    gate: dict[str, Any],
    csrf: str,
) -> str:
    """Render Human-only Story decision controls outside the Chat surface."""
    recommendation = escape(str(gate.get("recommendation") or "pending"))
    reason = escape(
        str(gate.get("reason") or "Awaiting a valid Scribe recommendation.")
    )
    if not gate.get("human_wait"):
        return (
            "<section id='story-decision-gate'><h2>Story decision</h2>"
            f"<p data-recommendation='{recommendation}'>{reason}</p></section>"
        )
    return f"""<section id='story-decision-gate' data-run-id='{escape(run_id)}' data-project-id='{escape(project_id)}'>
<h2>Human story decision</h2><p id='scribe-recommendation'>Recommendation: {recommendation}</p>
<p id='scribe-reason'>{reason}</p><label>Reason<textarea id='story-decision-reason' required></textarea></label>
<div id='story-decision-actions'><button data-decision='Go' type='button'>Go</button>
<button data-decision='Park' type='button'>Park</button><button data-decision='No-Go' type='button'>No-Go</button></div>
<p id='story-decision-status'>Human action required</p>
<script>
const decisionCsrf = {csrf!r};
const decisionGate = document.getElementById('story-decision-gate');
const decisionStatus = document.getElementById('story-decision-status');
for (const button of decisionGate.querySelectorAll('[data-decision]')) {{
  button.addEventListener('click', async () => {{
    for (const candidate of decisionGate.querySelectorAll('[data-decision]')) candidate.disabled = true;
    const idempotencyKey = crypto.randomUUID();
    try {{
      const response = await fetch('/api/runs/{escape(run_id)}/actions', {{
        method: 'POST', headers: {{'Content-Type': 'application/json', 'Origin': window.location.origin, 'X-Louke-CSRF': decisionCsrf}},
        body: JSON.stringify({{action: 'story_decision', expected_run_revision: {run_revision}, expected_artifact_revision: {artifact_revision}, idempotency_key: idempotencyKey,
          payload: {{candidate: button.dataset.decision, reason: document.getElementById('story-decision-reason').value, project_id: '{escape(project_id)}'}}}})
      }});
      decisionStatus.textContent = response.ok ? 'Decision recorded' : 'Decision rejected; refresh current state';
    }} finally {{
      for (const candidate of decisionGate.querySelectorAll('[data-decision]')) candidate.disabled = false;
    }}
  }});
}}
</script></section>"""
