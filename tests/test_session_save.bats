#!/usr/bin/env bats

# v0.6+ reverse contract (UT-010): lk-reserve-memory is removed; no agent
# may reference it, no agent may carry a "会话保存" / "Session save"
# section, the skill directory must not exist, no agent may prescribe
# .louke/raw/ as a save target.

AGENTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/louke/agents"

@test "session-save: lk-reserve-memory skill directory is removed" {
    [ ! -d "$AGENTS_DIR/_skills/reserve-memory" ]
}

@test "session-save: no agent references lk-reserve-memory" {
    for agent in Archer Devon Judge Maestro Prism Sage Scout Scribe Shield Librarian Lex Keeper Warden; do
        f="$AGENTS_DIR/$agent.md"
        [ -f "$f" ] || continue
        run grep -q "lk-reserve-memory" "$f"
        [ "$status" -ne 0 ] || { echo "FAIL: $agent.md still references lk-reserve-memory"; false; }
    done
}

@test "session-save: no agent has a 会话保存 / Session save section" {
    for agent in Archer Devon Judge Maestro Prism Scout Shield Librarian Keeper Warden; do
        f="$AGENTS_DIR/$agent.md"
        [ -f "$f" ] || continue
        run grep -qE "## .*[Ss]ession [Ss]av(e|ing)|## .*会话保存" "$f"
        [ "$status" -ne 0 ] || { echo "FAIL: $agent.md still has a session save section"; false; }
    done
}

@test "session-save: no agent references .louke/raw/ as a save target" {
    for agent in Archer Devon Judge Maestro Prism Sage Scout Scribe Shield Librarian Lex Keeper Warden; do
        f="$AGENTS_DIR/$agent.md"
        [ -f "$f" ] || continue
        run grep -qE "\.louke/raw/\{yy-mm-dd\}" "$f"
        [ "$status" -ne 0 ] || { echo "FAIL: $agent.md still prescribes .louke/raw/ save path"; false; }
    done
}
