from pathlib import Path

import pytest
from inspect_ai.util._sandbox.docker.docker import DockerSandboxEnvironment
from inspect_ai.util._sandbox.registry import registry_find_sandboxenv

from messageboard_audit_bench.sandbox import IsolatedDockerSandbox
from messageboard_audit_bench.task import _inspect_sandbox


def test_custom_sandbox_is_registered_and_keeps_network_disabled():
    spec = _inspect_sandbox("verbatim")
    assert registry_find_sandboxenv(spec.type) is IsolatedDockerSandbox
    service = spec.config.services["default"]
    assert service.network_mode == "none"
    assert service.cap_drop == ["ALL"]
    assert service.user == "1000:1000"


@pytest.mark.asyncio
async def test_root_exec_is_declined_and_default_exec_is_non_root(monkeypatch):
    captured = {}

    async def execute(self, cmd, **kwargs):
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(DockerSandboxEnvironment, "exec", execute)
    environment = IsolatedDockerSandbox("default", None, Path("/work"))
    with pytest.raises(PermissionError):
        await environment.exec(["id"], user="root")
    assert not captured
    assert await environment.exec(["id"]) == "result"
    assert captured["user"] == "1000:1000"


@pytest.mark.asyncio
async def test_sample_factory_wraps_every_service(monkeypatch):
    project = object()
    original = DockerSandboxEnvironment("default", project, Path("/work"))

    async def initialize(cls, task_name, config, metadata):
        return {"default": original}

    monkeypatch.setattr(DockerSandboxEnvironment, "sample_init", classmethod(initialize))
    environments = await IsolatedDockerSandbox.sample_init("test", None, {})
    wrapped = environments["default"]
    assert isinstance(wrapped, IsolatedDockerSandbox)
    assert wrapped._project is project
    assert wrapped._service == original._service
    assert wrapped._working_dir == original._working_dir
    with pytest.raises(PermissionError):
        await wrapped.exec(["id"], user="root")
