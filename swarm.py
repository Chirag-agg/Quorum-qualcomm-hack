#!/usr/bin/env python3
"""
swarm.py — Antigravity (coder) + DeepSeek V4 free (reviewer) + Codex (escalation)
orchestrator, with Graphify context injection and a human-feedback checkpoint file.

Usage:
    python swarm.py "Build a FastAPI backend that does X and Y"

While it's running, from anywhere (e.g. SSH'd in from your hackathon laptop):
    echo "also add rate limiting" >> feedback.txt
The loop picks this up before its next step — no need to stop anything.
"""

import json
import os
import signal
import subprocess
import sys
import time
import datetime

REPO_DIR = os.getcwd()
LOG_FILE = os.path.join(REPO_DIR, "swarm.log")
FEEDBACK_FILE = os.path.join(REPO_DIR, "feedback.txt")
QUOTA_FILE = os.path.join(REPO_DIR, "codex_quota.json")
GRAPH_FILE = os.path.join(REPO_DIR, "graphify-out", "graph.json")

CODEX_DAILY_LIMIT = int(os.environ.get("SWARM_CODEX_DAILY_LIMIT", 8))          # keep buffer under the real 10/day cap
MAX_ANTIGRAVITY_RETRIES = int(os.environ.get("SWARM_MAX_RETRIES", 3))          # fails before escalating to Codex
POLL_SECONDS = int(os.environ.get("SWARM_POLL_SECONDS", 20))                   # how often it checks feedback.txt while idle
AGY_TIMEOUT_SECONDS = int(os.environ.get("SWARM_AGY_TIMEOUT", 1800))

REVIEWER_MODEL = os.environ.get("SWARM_REVIEWER_MODEL", "deepseek/deepseek-v4-flash")  # ~$0.10/$0.20 per 1M tokens
BUDGET_CAP_USD = float(os.environ.get("SWARM_BUDGET_CAP_USD", 3.00))  # hard stop on cumulative reviewer spend
COST_FILE = os.path.join(REPO_DIR, "reviewer_spend.json")

# Rough per-token pricing for cost tracking — update if OpenRouter's listed price changes,
# or override per-project via env vars if you switch reviewer models.
INPUT_PRICE_PER_TOKEN = float(os.environ.get("SWARM_INPUT_PRICE_PER_M", 0.10)) / 1_000_000
OUTPUT_PRICE_PER_TOKEN = float(os.environ.get("SWARM_OUTPUT_PRICE_PER_M", 0.20)) / 1_000_000

SKILLS_DIR = os.environ.get("SWARM_SKILLS_DIR", os.path.expanduser("~/.agents/skills"))
REPORTS_DIR = os.path.join(REPO_DIR, "swarm_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

USD_TO_INR = 96.5  # approximate, update occasionally — OpenRouter still bills you in USD, this is just for your own reading

def inr(usd: float) -> str:
    return f"₹{usd * USD_TO_INR:.3f} (${usd:.4f})"

_current_proc = None
_stop_requested = False

def _sigint_handler(sig, frame):
    global _stop_requested
    if _stop_requested:
        print("\nSecond interrupt — killing immediately.")
        if _current_proc:
            _current_proc.kill()
        sys.exit(1)
    _stop_requested = True
    print("\nInterrupt received — stopping the current agent step safely, then pausing. "
          "Press Ctrl+C again to force-quit instead of pausing.")
    if _current_proc:
        _current_proc.terminate()

signal.signal(signal.SIGINT, _sigint_handler)

from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)


def get_cumulative_spend() -> float:
    if os.path.exists(COST_FILE):
        return json.load(open(COST_FILE)).get("total_usd", 0.0)
    return 0.0


def add_spend(usage) -> float:
    cost = (usage.prompt_tokens * INPUT_PRICE_PER_TOKEN) + (usage.completion_tokens * OUTPUT_PRICE_PER_TOKEN)
    total = get_cumulative_spend() + cost
    json.dump({"total_usd": total}, open(COST_FILE, "w"))
    return total


def verify_reviewer_model():
    """Fire a tiny real request at startup so a bad key/model shows up immediately."""
    try:
        resp = client.chat.completions.create(
            model=REVIEWER_MODEL,
            messages=[{"role": "user", "content": "reply with just: ok"}],
            max_tokens=50,
            extra_body={"provider": {"allow_fallbacks": True}, "reasoning": {"exclude": True}},
        )
        content = resp.choices[0].message.content
        if content is None:
            log(f"WARNING: model returned no content. Full response: {resp}")
            sys.exit(1)
        spend = add_spend(resp.usage)
        log(f"Reviewer model check passed: {content.strip()!r} "
            f"(cumulative spend so far: {inr(spend)})")
    except Exception as e:
        log(f"FATAL: reviewer model check failed: {e}")
        sys.exit(1)


def log(msg: str):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def check_feedback() -> str | None:
    if os.path.exists(FEEDBACK_FILE) and os.path.getsize(FEEDBACK_FILE) > 0:
        with open(FEEDBACK_FILE) as f:
            content = f.read().strip()
        open(FEEDBACK_FILE, "w").close()  # clear it
        log(f"HUMAN FEEDBACK RECEIVED: {content}")
        return content
    return None


def get_codex_quota() -> int:
    today = str(datetime.date.today())
    if os.path.exists(QUOTA_FILE):
        data = json.load(open(QUOTA_FILE))
        if data.get("date") == today:
            return data.get("used", 0)
    return 0


def bump_codex_quota():
    today = str(datetime.date.today())
    used = get_codex_quota() + 1
    json.dump({"date": today, "used": used}, open(QUOTA_FILE, "w"))
    return used


def graph_context(task: str) -> str:
    """Ask Graphify for the relevant subgraph instead of dumping raw files."""
    try:
        result = subprocess.run(
            ["graphify", "query", task, "--budget", "1500", "--graph", GRAPH_FILE],
            capture_output=True, text=True, timeout=60,
        )
        return result.stdout.strip()
    except Exception as e:
        log(f"graphify query failed, continuing without it: {e}")
        return ""


def stream_subprocess(cmd, timeout=1800, shell=False, prefix=""):
    """
    Run a subprocess and print its output live, line by line, so you can
    actually watch the agent working — instead of a silent wait until it
    finishes. Still returns the full captured text for the empty-output
    retry check and downstream logic.
    """
    global _current_proc
    proc = subprocess.Popen(
        cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, stdin=subprocess.DEVNULL,
    )
    _current_proc = proc
    lines = []
    start = time.time()
    try:
        for line in proc.stdout:
            print(f"{prefix}{line}", end="", flush=True)
            with open(LOG_FILE, "a") as f:
                f.write(f"{prefix}{line}")
            lines.append(line)
            if _stop_requested:
                break
            if time.time() - start > timeout:
                proc.kill()
                log(f"{prefix}TIMEOUT after {timeout}s, killing process")
                break
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        _current_proc = None
    return "".join(lines)


def run_antigravity(instruction: str) -> str:
    """
    Headless Antigravity call, streamed live to the terminal. agy has a known
    bug where output can come back empty under a non-TTY subprocess — if that
    happens once, retry via `script` which fakes a pty and usually fixes it.
    """
    cmd = [
        "agy", "-p", instruction,
        "--add-dir", REPO_DIR,              # CWD does NOT scope the session — this was the actual root cause
        "--print-timeout", "30m",           # agy's own internal default is 5m, well under our 1800s subprocess timeout
        "--dangerously-skip-permissions",  # verify this flag name with `agy --help` on your version
    ]
    log("=== Antigravity working (live output below) ===")
    output = stream_subprocess(cmd, timeout=AGY_TIMEOUT_SECONDS, prefix="[antigravity] ")
    if not output.strip():
        log("agy returned empty output, retrying with a fake pty via `script`")
        pty_cmd = f'script -qec \'{" ".join(cmd)}\' /dev/null'
        output = stream_subprocess(pty_cmd, timeout=AGY_TIMEOUT_SECONDS, shell=True, prefix="[antigravity] ")
    return output


def get_diff() -> str:
    tracked = subprocess.run(
        ["git", "diff", "--", ".",
         ":!swarm.log",
         ":!reviewer_spend.json",
         ":!codex_quota.json",
         ":!swarm_reports/"],
        capture_output=True, text=True
    ).stdout

    untracked = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        capture_output=True, text=True
    ).stdout

    untracked_files = [
        line[3:] for line in untracked.splitlines()
        if line.startswith("??") and not any(
            excl in line for excl in ["swarm.log", "reviewer_spend.json", "codex_quota.json", "swarm_reports/"]
        )
    ]

    untracked_diff = ""
    for f in untracked_files:
        result = subprocess.run(
            ["git", "diff", "--no-index", "/dev/null", f],
            capture_output=True, text=True
        )
        untracked_diff += result.stdout

    return tracked + untracked_diff


def review_with_deepseek(diff: str, task_description: str, graph_ctx: str) -> str:
    if not diff.strip():
        return "FAIL\n- No changes detected in the diff."
    spend_so_far = get_cumulative_spend()
    if spend_so_far >= BUDGET_CAP_USD:
        log(f"BUDGET CAP HIT ({inr(spend_so_far)} >= {inr(BUDGET_CAP_USD)}). "
            f"Stopping automated reviews — raise BUDGET_CAP_USD in the script if you want to continue.")
        sys.exit(1)
    resp = client.chat.completions.create(
        model=REVIEWER_MODEL,
        messages=[
            {"role": "system", "content": (
                "You are a strict senior code reviewer for a hackathon project. "
                "Check correctness, obvious bugs, and whether the diff actually "
                "achieves the stated task, including any explicit constraints. "
                "Reply with PASS or FAIL on the first line, then bullet issues if any."
            )},
            {"role": "user", "content": (
                f"Task / spec:\n{task_description}\n\n"
                f"Relevant code context:\n{graph_ctx}\n\n"
                f"Diff to review:\n{diff}"
            )},
        ],
        extra_body={"provider": {"allow_fallbacks": True}, "reasoning": {"exclude": True}},
    )
    total = add_spend(resp.usage)
    log(f"Reviewer call cost tracked. Cumulative spend: {inr(total)} / {inr(BUDGET_CAP_USD)} cap")
    content = resp.choices[0].message.content
    if content is None:
        log(f"WARNING: reviewer returned no content, treating as FAIL. Full response: {resp}")
        return "FAIL\n- Reviewer returned empty response, treat as inconclusive and retry."
    return content


def run_codex_escalation(task: str, issues: str) -> str:
    used = get_codex_quota()
    if used >= CODEX_DAILY_LIMIT:
        log(f"Codex daily quota exhausted ({used}/{CODEX_DAILY_LIMIT}) — skipping escalation")
        return ""
    bump_codex_quota()
    log(f"Escalating to Codex ({used + 1}/{CODEX_DAILY_LIMIT} used today)")
    prompt = f"Task: {task}\n\nThis was stuck after {MAX_ANTIGRAVITY_RETRIES} attempts. Known issues:\n{issues}\n\nFix it."
    # NOTE: this flag also disables sandboxing, not just confirmation prompts —
    # Codex-run commands execute directly on this machine with no containment.
    # Worth checking swarm.log after each escalation rather than treating fully hands-off.
    log("=== Codex working (live output below) ===")
    output = stream_subprocess(
        ["codex", "exec", prompt, "--dangerously-bypass-approvals-and-sandbox"],
        timeout=AGY_TIMEOUT_SECONDS, prefix="[codex] ",
    )
    return output


def build_guardrails() -> str:
    return (
        f"You have access to a skills library at {SKILLS_DIR} — before starting, "
        f"check if any skill there is relevant to this task and use it if so.\n\n"
        f"HARD RULE: never run `git commit` or `git push` under any circumstances. "
        f"Leave all changes uncommitted in the working directory — a human reviews and "
        f"commits everything manually. This repo also has a pre-commit hook that will "
        f"reject any commit attempt, so do not waste time trying.\n"
    )


def write_report(cycle_num: int, task: str, antigravity_out: str, diff: str, verdict: str):
    """Human-readable markdown summary of one loop cycle, for easier feedback-writing."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(REPORTS_DIR, f"cycle_{cycle_num:03d}_{stamp}.md")
    content = f"""# Cycle {cycle_num} — {stamp}

## Task at this point
{task}

## What Antigravity said/did
```
{antigravity_out[:4000]}
```

## Diff produced
```diff
{diff[:4000] if diff.strip() else "(no changes detected)"}
```

## Reviewer verdict
{verdict}
"""
    with open(path, "w") as f:
        f.write(content)
    # Also keep a rolling "latest" copy for convenience
    with open(os.path.join(REPORTS_DIR, "LATEST.md"), "w") as f:
        f.write(content)
    log(f"Report written: {path}")


def swarm_loop(initial_task: str):
    global _stop_requested
    verify_reviewer_model()
    task = initial_task
    log(f"Starting task: {task}")
    attempt = 0
    cycle = 0

    while True:
        while True:  # inner work loop, runs until PASS+idle-interrupt or a pause
            fb = check_feedback()
            if fb:
                task = f"{task}\n\nAdditional instruction from human: {fb}"
                attempt = 0

            ctx = graph_context(task)
            full_prompt = f"{build_guardrails()}\n{task}\n\nRelevant project context:\n{ctx}"
            log("Running Antigravity...")
            antigravity_out = run_antigravity(full_prompt)

            if _stop_requested:
                break

            diff = get_diff()
            if not diff.strip():
                log("WARNING: diff is empty — Antigravity responded but wrote no file changes. "
                    "This usually means the CLI flag used is a 'plan/chat' mode, not a file-editing "
                    "agent mode. Try running `agy --help` and check for a dedicated edit/agent flag.")

            log("Sending diff to reviewer...")
            verdict = review_with_deepseek(diff, task, ctx)
            log(f"Review verdict:\n{verdict}")

            cycle += 1
            write_report(cycle, task, antigravity_out, diff, verdict)

            if verdict.strip().upper().startswith("PASS"):
                log("Task PASSED review. Idling — send new instructions any time with:\n"
                    "  echo \"your next instruction\" >> feedback.txt")
                attempt = 0
                idle_broken_by_pause = False
                while True:
                    for _ in range(POLL_SECONDS):
                        if _stop_requested:
                            idle_broken_by_pause = True
                            break
                        time.sleep(1)
                    if _stop_requested:
                        break
                    fb = check_feedback()
                    if fb:
                        task = fb
                        attempt = 0
                        break
                if idle_broken_by_pause:
                    break
                continue

            attempt += 1
            if attempt < MAX_ANTIGRAVITY_RETRIES:
                log(f"FAILED review, retry {attempt}/{MAX_ANTIGRAVITY_RETRIES} with Antigravity")
                task = f"{task}\n\nFix these review issues:\n{verdict}"
            else:
                log("Stuck after max retries — escalating to Codex")
                codex_out = run_codex_escalation(task, verdict)
                if codex_out:
                    log(f"Codex output:\n{codex_out[:500]}...")
                attempt = 0

            if _stop_requested:
                break

        # Paused via Ctrl+C — offer to resume instead of dying
        log("PAUSED. Edit feedback.txt or task.md if you want to redirect it, "
            "then press Enter here to resume, or Ctrl+C again to quit for real.")
        try:
            input()
        except KeyboardInterrupt:
            log("Exiting.")
            sys.exit(0)
        _stop_requested = False
        fb = check_feedback()
        if fb:
            task = fb


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python swarm.py "<short task prompt>"')
        print("  python swarm.py task.md          (reads the whole file as the task)")
        sys.exit(1)

    arg = sys.argv[1]
    if os.path.isfile(arg):
        with open(arg) as f:
            initial_task = f.read().strip()
        print(f"Loaded task from {arg} ({len(initial_task)} chars)")
    else:
        initial_task = " ".join(sys.argv[1:])

    swarm_loop(initial_task)