"""Require successful model actions from both fictional agents on both platforms."""
import json
from pathlib import Path
import re
import sys

name = sys.argv[1] if len(sys.argv) > 1 else "installation-check-final"
assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name)
directory = Path(__file__).resolve().parents[1] / "backend/uploads" / name
summary = {}
for platform in ("twitter", "reddit"):
    rows = [json.loads(line) for line in (directory / platform / "actions.jsonl").read_text(encoding="utf-8").splitlines()]
    seed = [row for row in rows if row.get("round") == 0 and "action_type" in row]
    actual = [row for row in rows if row.get("round") == 1 and "action_type" in row]
    end = [row for row in rows if row.get("event_type") == "simulation_end"]
    assert len(seed) == 1, f"{platform}: expected one seed post"
    assert len(actual) == 2, f"{platform}: seed post was duplicated or agent action is missing"
    assert {row["agent_id"] for row in actual} == {0, 1}
    assert all(row.get("success") for row in actual)
    assert all(row["action_args"].get("content") or row["action_args"].get("quote_content") for row in actual)
    assert len(end) == 1 and end[0]["total_rounds"] == 1 and end[0]["total_actions"] == 3
    assert (directory / f"{platform}_simulation.db").exists()
    summary[platform] = {"completed": True, "model_agent_actions": 2, "seed_posts_counted_once": True}
print(json.dumps(summary, indent=2))
