from datetime import datetime
import threading

from flask import Flask
from types import SimpleNamespace

from app.api import graph as graph_api
from app.api import simulation as simulation_api
from app.models.project import Project, ProjectStatus
from app.services.simulation_manager import SimulationStatus
from app.models.task import TaskStatus


def _project(status, graph_id="graph-1"):
    now = datetime.now().isoformat()
    return Project(
        project_id="proj-1",
        name="Project",
        status=status,
        created_at=now,
        updated_at=now,
        ontology={"entity_types": [], "edge_types": []},
        graph_id=graph_id,
        graph_build_task_id="task-1",
        zep_batch_id="batch-1",
        zep_batch_operation_id="operation-1",
    )


def _json_result(result):
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return response.get_json(), status


def test_project_reset_preserves_the_graph_and_requires_new_draft(monkeypatch):
    project = _project(ProjectStatus.GRAPH_COMPLETED)
    events = []

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def delete_graph(self, graph_id):
            events.append(("cloud-delete", graph_id))

    monkeypatch.setattr(graph_api, "GraphBuilderService", Builder)
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, saved: events.append(("save", saved.graph_id))),
    )

    app = Flask(__name__)
    with app.test_request_context("/api/graph/project/proj-1/reset", method="POST"):
        body, status = _json_result(graph_api.reset_project("proj-1"))

    assert status == 409
    assert body["new_project_required"] is True
    assert events == []
    assert project.graph_id == "graph-1"
    assert project.zep_batch_id == "batch-1"


def test_project_reset_refuses_a_graph_with_an_active_simulation(monkeypatch):
    project = _project(ProjectStatus.GRAPH_COMPLETED)
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        graph_api.ZepGraphMemoryManager,
        "get_simulation_ids_for_graph",
        classmethod(lambda _cls, _graph_id: ["sim-active"]),
    )

    app = Flask(__name__)
    with app.test_request_context("/api/graph/project/proj-1/reset", method="POST"):
        body, status = _json_result(graph_api.reset_project("proj-1"))

    assert status == 409
    assert "sim-active" in body["error"]


def test_graph_delete_cannot_discard_an_updater_during_finalization(monkeypatch):
    monkeypatch.setattr(
        graph_api.ZepGraphMemoryManager,
        "get_simulation_ids_for_graph",
        classmethod(lambda _cls, _graph_id: ["sim-finalizing"]),
    )
    discarded = []
    monkeypatch.setattr(
        graph_api.ZepGraphMemoryManager,
        "discard_inactive_updater",
        classmethod(
            lambda _cls, simulation_id: discarded.append(simulation_id)
        ),
    )
    lock = graph_api.SimulationRunner._finalization_lock("sim-finalizing")
    lock.acquire()
    try:
        assert graph_api._active_graph_consumers("graph-1") == ["sim-finalizing"]
    finally:
        lock.release()

    assert discarded == []


def test_repeated_build_request_reuses_the_existing_task(monkeypatch):
    project = _project(ProjectStatus.GRAPH_BUILDING)
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        graph_api,
        "TaskManager",
        lambda: SimpleNamespace(
            get_task=lambda _task_id: SimpleNamespace(status=TaskStatus.PROCESSING)
        ),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/graph/build",
        method="POST",
        json={"project_id": "proj-1", "force": True},
    ):
        body, status = _json_result(graph_api.build_graph())

    assert status == 200
    assert body["success"] is True
    assert body["data"]["reused"] is True
    assert body["data"]["task_id"] == "task-1"
    assert body["data"]["graph_id"] == "graph-1"


def test_stale_build_after_restart_is_recoverable_instead_of_reused(monkeypatch):
    project = _project(ProjectStatus.GRAPH_BUILDING)
    project.zep_batch_id = None
    project.zep_batch_operation_id = None
    saved = []
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, value: saved.append(value.status)),
    )
    monkeypatch.setattr(
        graph_api,
        "TaskManager",
        lambda: SimpleNamespace(get_task=lambda _task_id: None),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/graph/build",
        method="POST",
        json={"project_id": "proj-1"},
    ):
        body, status = _json_result(graph_api.build_graph())

    assert status == 409
    assert body["recoverable"] is True
    assert project.status == ProjectStatus.FAILED
    assert saved == [ProjectStatus.FAILED]


def test_stale_build_resumes_a_persisted_processing_batch(monkeypatch):
    project = _project(ProjectStatus.GRAPH_BUILDING)
    created_threads = []

    class Tasks:
        def get_task(self, _task_id):
            return None

        def claim_task(self, *_args, **_kwargs):
            return "task-resumed", True

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def get_batch_summary(self, batch_id):
            assert batch_id == "batch-1"
            return SimpleNamespace(status="processing")

    class Thread:
        def __init__(self, *, target, daemon):
            created_threads.append((target, daemon))

        def start(self):
            pass

    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(graph_api, "TaskManager", Tasks)
    monkeypatch.setattr(graph_api, "GraphBuilderService", Builder)
    monkeypatch.setattr(graph_api.threading, "Thread", Thread)
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_extracted_text",
        classmethod(lambda _cls, _project_id: "source text"),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, _project: None),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/graph/build",
        method="POST",
        json={"project_id": "proj-1"},
    ):
        body, status = _json_result(graph_api.build_graph())

    assert status == 200
    assert body["data"]["resumed"] is True
    assert body["data"]["task_id"] == "task-resumed"
    assert project.graph_build_task_id == "task-resumed"
    assert len(created_threads) == 1


def test_project_delete_removes_cloud_graph_before_local_files(monkeypatch):
    project = _project(ProjectStatus.GRAPH_COMPLETED)
    events = []

    class Builder:
        def __init__(self, **_kwargs):
            pass

        def delete_graph(self, graph_id):
            events.append(("cloud-delete", graph_id))

    monkeypatch.setattr(graph_api, "GraphBuilderService", Builder)
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "delete_project",
        classmethod(
            lambda _cls, project_id: events.append(("local-delete", project_id)) or True
        ),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/graph/project/proj-1",
        method="DELETE",
    ):
        body, status = _json_result(graph_api.delete_project("proj-1"))

    assert status == 200
    assert body["success"] is True
    assert events == [
        ("cloud-delete", "graph-1"),
        ("local-delete", "proj-1"),
    ]


def test_completed_build_request_is_idempotent_without_force(monkeypatch):
    project = _project(ProjectStatus.GRAPH_COMPLETED)
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/graph/build",
        method="POST",
        json={"project_id": "proj-1"},
    ):
        body, status = _json_result(graph_api.build_graph())

    assert status == 200
    assert body["data"]["reused"] is True
    assert body["data"]["graph_id"] == "graph-1"


def test_force_must_be_a_json_boolean(monkeypatch):
    project = _project(ProjectStatus.GRAPH_COMPLETED)
    monkeypatch.setattr(graph_api.Config, "ZEP_API_KEY", "test-key")
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _project_id: project),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/graph/build",
        method="POST",
        json={"project_id": "proj-1", "force": "false"},
    ):
        body, status = _json_result(graph_api.build_graph())

    assert status == 400
    assert "boolean" in body["error"]


def test_reset_never_enters_destructive_graph_barrier(monkeypatch):
    project = _project(ProjectStatus.GRAPH_COMPLETED)
    monkeypatch.setattr(graph_api.ProjectManager, 'get_project', lambda _: project)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Reset must never delete a historical graph')
    monkeypatch.setattr(graph_api, '_delete_cloud_graph_if_present', forbidden)
    app = Flask(__name__)
    with app.test_request_context('/reset', method='POST'):
        body, status = _json_result(graph_api.reset_project('proj-1'))
    assert status == 409
    assert body['new_project_required'] is True
    assert project.graph_id == 'graph-1'
