"""
Week 10 Track A resilience test (PRD §10 Test #6, RULES.md invariants #1/#2).

Runs a monitored (SDK-attached) LangGraph workload against the local stack,
kills the backend container mid-run, and verifies the monitored agent's
execution is genuinely unaffected: the process must finish ALL workloads,
exit 0, and produce no traceback (fail-silent warnings are expected and OK).
We observe the agent's actual outputs and exit — not just absence of exceptions.

Usage (stack must be running): python scripts/resilience-backend-kill.py
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "examples" / "langgraph_demo_agent"))

AGENT_CODE = r"""
import asyncio, sys, os
sys.path.insert(0, r"{repo}\examples\langgraph_demo_agent")
from branching_agent import run_branching_agent

async def main():
    results = []
    # 30 sequential invocations, ~0.5s each -> ~15s window for the mid-run kill
    for i in range(30):
        res = await run_branching_agent(f"Calculate {i} * 2", trace_id="trace-resilience-kill")
        results.append(res["result"])
        await asyncio.sleep(0.4)
    # Agent-visible outcome: all 30 nodes produced correct outputs
    assert len(results) == 30, f"only {{len(results)}}/30 workloads completed"
    assert all("[Calculator Node]" in r for r in results)
    print("AGENT-COMPLETED-OK: 30/30 workloads, all outputs correct")

asyncio.run(main())
"""


def main():
    env = dict(os.environ)
    env.update({
        "AGENTSCOPE_API_KEY": "test-key",
        "AGENTSCOPE_INGEST_URL": "http://localhost:8000/ingest",
        "PYTHONUNBUFFERED": "1",
    })
    code = AGENT_CODE.replace("{repo}", str(REPO))

    print("starting monitored agent workload (30 invocations, ~15s)...")
    proc = subprocess.Popen([sys.executable, "-c", code], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, cwd=str(REPO))

    time.sleep(4.0)
    print("killing backend container mid-run...")
    subprocess.run(["docker", "compose", "stop", "backend"], cwd=str(REPO / "infra"),
                   capture_output=True, check=True)
    kill_time = time.time()

    stdout, _ = proc.communicate(timeout=120)
    elapsed = time.time() - kill_time
    print(f"agent exited code={proc.returncode} after backend kill ({elapsed:.1f}s later)")
    print("---- agent output (tail) ----")
    print("\n".join(stdout.splitlines()[-15:]))

    tb = "Traceback" in stdout
    ok = proc.returncode == 0 and "AGENT-COMPLETED-OK" in stdout and not tb

    print("\n---- verification ----")
    print(f"  exit code 0:               {proc.returncode == 0}")
    print(f"  all 30 workloads completed: {'AGENT-COMPLETED-OK' in stdout}")
    print(f"  no traceback in agent:     {not tb}")
    print(f"  RESULT: {'PASS' if ok else 'FAIL'}")

    subprocess.run(["docker", "compose", "start", "backend"], cwd=str(REPO / "infra"),
                   capture_output=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
