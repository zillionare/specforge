#!/usr/bin/env bats

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

@test "board opencode installs prefixed skills from louke/agents/_skills/" {
    cd "$REPO_ROOT"
    rm -rf .opencode

    run python3 -m louke board opencode --quiet
    [ "$status" -eq 0 ] || {
        echo "FAIL: lk board opencode exited $status: $output"
        false
    }

    for skill in lk-inline-discussion lk-security-checklist; do
        f=".opencode/skill/${skill}/SKILL.md"
        [ -f "$f" ] || { echo "FAIL: $f not generated"; false; }
        run grep -E "^name: ${skill}$" "$f"
        [ "$status" -eq 0 ] || { echo "FAIL: $f missing renamed skill frontmatter"; false; }
    done

    # lk-reserve-memory was removed (UT-010 reverse contract); no SKILL.md generated.
    [ ! -f .opencode/skill/lk-reserve-memory/SKILL.md ] || {
        echo "FAIL: lk-reserve-memory skill should not be generated anymore"
        false
    }
}

@test "board opencode does not leak lk-reserve-memory into any generated agent" {
    cd "$REPO_ROOT"
    rm -rf .opencode
    run python3 -m louke board opencode --quiet
    [ "$status" -eq 0 ]
    for f in .opencode/agents/*.md; do
        [ -f "$f" ] || continue
        if grep -q "lk-reserve-memory" "$f"; then
            echo "FAIL: $f leaks lk-reserve-memory"
            cat "$f"
            false
        fi
    done
}
