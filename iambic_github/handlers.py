from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage

if TYPE_CHECKING:
    from iambic_github.iambic_plugin import GitHubConfig


async def load(config: GitHubConfig) -> GitHubConfig:
    return config


async def import_github_resources(
    exe_message: ExecutionMessage,
    config: GitHubConfig,
    base_output_dir: str,
    messages: list = None,
    remote_worker=None,
):
    base_runner = bool(not exe_message.provider_id)
    collector_tasks = []

    for organization in config.organizations:
        if organization.iambic_managed == IambicManaged.DISABLED:
            continue
        elif (
            exe_message.provider_id and exe_message.provider_id != organization.organization_name
        ):
            continue

        task_message = exe_message.copy()
        task_message.provider_id = organization.organization_name

        collector_tasks.extend(
            []
        )

    if collector_tasks:
        if base_runner and ctx.use_remote and remote_worker and not messages:
            # TODO: Update to use the remote_worker
            await asyncio.gather(*collector_tasks)
            # TODO: Add a process to gather status messages from the remote worker
        else:
            if remote_worker:
                log.warning(
                    "The remote worker definition must be defined in the config to run remote execution."
                )
            await asyncio.gather(*collector_tasks)

    if base_runner:
        generator_tasks = []
        await asyncio.gather(*generator_tasks)
