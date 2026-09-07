"""Inspect Docker sandbox whose harness and agents share one non-root user.

Inspect normally injects its remote-exec server as root when Docker permits it.
Without DAC_OVERRIDE, that server's model proxy cannot write the agent-owned
bridge request directory. Declining root execution selects Inspect's supported
unprivileged injection path, keeping the server, proxy and CLI under uid 1000.
"""
from __future__ import annotations

from inspect_ai.util import sandboxenv
from inspect_ai.util._sandbox.docker.docker import DockerSandboxEnvironment


@sandboxenv(name="isolated-docker")
class IsolatedDockerSandbox(DockerSandboxEnvironment):
    @classmethod
    async def sample_init(cls, task_name, config, metadata):
        environments = await super().sample_init(task_name, config, metadata)
        # Docker's factory constructs its concrete base class. Preserve the
        # running projects while wrapping their execution policy per sample.
        return {
            name: cls(env._service, env._project, env._working_dir)
            for name, env in environments.items()
        }

    async def exec(self, cmd, input=None, cwd=None, env=None, user=None,
                   timeout=None, timeout_retry=True, concurrency=True):
        if user not in (None, "agent", "1000", "1000:1000"):
            raise PermissionError("benchmark sandbox permits only uid 1000 execution")
        return await super().exec(
            cmd, input=input, cwd=cwd, env=env, user="1000:1000", timeout=timeout,
            timeout_retry=timeout_retry, concurrency=concurrency,
        )
