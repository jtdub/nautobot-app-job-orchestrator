"""Tests for Workflow model validation."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from job_orchestrator.models import Workflow


class WorkflowCleanTest(TestCase):
    """Workflow.clean() should reject structurally invalid graphs."""

    def test_valid_graph_with_unknown_job_is_rejected(self):
        workflow = Workflow(
            name="bad-job",
            graph={
                "nodes": [
                    {"id": "s", "type": "start", "position": {"x": 0, "y": 0}},
                    {
                        "id": "a",
                        "type": "job",
                        "position": {"x": 0, "y": 1},
                        "data": {"job_id": "00000000-0000-0000-0000-000000000000"},
                    },
                ],
                "edges": [{"id": "e1", "source": "s", "target": "a", "data": {"condition": "on_complete"}}],
            },
        )
        with self.assertRaises(ValidationError):
            workflow.full_clean()

    def test_empty_draft_passes_clean_but_not_runnable(self):
        # Drafts may be saved (clean is lenient) but cannot be executed until they have a start node.
        workflow = Workflow(name="empty", graph={"nodes": [], "edges": []})
        workflow.full_clean()  # should not raise
        with self.assertRaises(ValidationError):
            workflow.validate_runnable()

    def test_missing_start_blocks_run_only(self):
        # A graph with no job nodes (so no job resolution) but also no start node:
        # lenient clean accepts it; validate_runnable rejects it.
        graph = {"nodes": [{"id": "end", "type": "stop", "position": {"x": 0, "y": 0}}], "edges": []}
        workflow = Workflow(name="no-start", graph=graph)
        workflow.full_clean()  # lenient clean passes
        with self.assertRaises(ValidationError):
            workflow.validate_runnable()
