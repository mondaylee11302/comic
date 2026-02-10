from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comic_splitter.workflow import (
    AgentRetryMatrix,
    PanelScriptOptions,
    PanelScriptPaths,
    PanelScriptWorkflow,
    StoryboardOptions,
    StoryboardPaths,
    StoryboardWorkflow,
)
from comic_splitter.workflow.runtime import run_agents_with_retry


class _FlakyAgent:
    def __init__(self, name: str, fail_times: int, exc: Exception):
        self.name = name
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    def run(self, _ctx) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc


class WorkflowRetryIntegrationTests(unittest.TestCase):
    def test_runner_retries_runtime_error(self) -> None:
        logs = []
        agent = _FlakyAgent(name="a", fail_times=1, exc=RuntimeError("transient"))
        run_agents_with_retry(
            agents=[agent],
            run_one=lambda a: a.run(None),
            log=logs.append,
            retry=AgentRetryMatrix(default_max_attempts=2, default_backoff_sec=0.0, max_backoff_sec=0.0),
        )
        self.assertEqual(agent.calls, 2)
        self.assertTrue(any("agent_retry=a" in x for x in logs))

    def test_runner_no_retry_value_error(self) -> None:
        logs = []
        agent = _FlakyAgent(name="b", fail_times=1, exc=ValueError("bad input"))
        with self.assertRaises(ValueError):
            run_agents_with_retry(
                agents=[agent],
                run_one=lambda a: a.run(None),
                log=logs.append,
                retry=AgentRetryMatrix(default_max_attempts=3, default_backoff_sec=0.0, max_backoff_sec=0.0),
            )
        self.assertEqual(agent.calls, 1)
        self.assertTrue(any("retryable=False" in x for x in logs))

    def test_storyboard_workflow_uses_retry_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = []
            wf = StoryboardWorkflow(
                paths=StoryboardPaths(
                    image_path=Path("/tmp/fake.psd"),
                    out_dir=Path(td) / "out",
                    debug_dir=Path(td) / "out" / "debug",
                    prefix="p",
                ),
                options=StoryboardOptions(),
                log=logs.append,
                retry_matrix=AgentRetryMatrix(
                    default_max_attempts=1,
                    default_backoff_sec=0.0,
                    max_backoff_sec=0.0,
                    per_agent_max_attempts={"fake_story_agent": 2},
                ),
            )
            fake = _FlakyAgent(name="fake_story_agent", fail_times=1, exc=RuntimeError("once"))
            wf.agents = [fake]
            wf.run()
            self.assertEqual(fake.calls, 2)

    def test_panel_script_workflow_uses_retry_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = []
            wf = PanelScriptWorkflow(
                paths=PanelScriptPaths(
                    out_dir=Path(td),
                    prefix="p",
                    panel_id="panel_001",
                ),
                options=PanelScriptOptions(),
                log=logs.append,
                retry_matrix=AgentRetryMatrix(
                    default_max_attempts=1,
                    default_backoff_sec=0.0,
                    max_backoff_sec=0.0,
                    per_agent_max_attempts={"fake_panel_agent": 2},
                ),
            )
            fake = _FlakyAgent(name="fake_panel_agent", fail_times=1, exc=RuntimeError("once"))
            wf.agents = [fake]
            wf.run()
            self.assertEqual(fake.calls, 2)


if __name__ == "__main__":
    unittest.main()

