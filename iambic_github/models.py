from __future__ import annotations

import asyncio
import json
import os
import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Union

import aiohttp
from iambic.plugins.v0_1_0.github.github_app import get_app_bearer_token
from pydantic import BaseModel, Field, SecretStr

from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, TemplateChangeDetails

from iambic_github.exceptions import GraphQLQueryException
from iambic_github.utils import get_dict_value

if TYPE_CHECKING:
    from iambic_github.iambic_plugin import GitHubConfig

    MappingIntStrAny = typing.Mapping[int | str, any]
    AbstractSetIntStr = typing.AbstractSet[int | str]


@dataclass
class Cursor:
    cursor_var: str
    has_next_page_key: str
    end_cursor_key: str


class GitHubOrganization(BaseModel):
    organization_name: str
    github_url: str
    app_id: str
    installation_id: SecretStr
    private_key: SecretStr
    client: Any = None
    bearer_token: str = ""
    iambic_managed: IambicManaged = IambicManaged.UNDEFINED

    class Config:
        arbitrary_types_allowed = True

    async def get_bearer_token(self) -> str:
        if not self.bearer_token:
            bearer_token = get_app_bearer_token(self.private_key.get_secret_value(), self.app_id)
            bearer_token = f"Bearer {bearer_token}"
            install_id = self.installation_id.get_secret_value()
            access_tokens_url = (
                f"https://api.github.com/app/installations/{install_id}/access_tokens"
            )
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": bearer_token,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(access_tokens_url, headers=headers) as resp:
                    payload = json.loads(await resp.text())
                    installation_token = payload["token"]
                    self.bearer_token = f"Bearer {installation_token}"

        return self.bearer_token

    def get_github_api_url(self) -> str:
        # Return the GitHub api url

        if self.github_url.startswith("https://api.") and self.github_url.endswith("/graphql"):
            return self.github_url

        github_url = self.github_url.split("://")[-1]
        if not github_url.startswith("api."):
            github_url = f"api.{github_url}"

        github_url = github_url.split("/")[0]
        self.github_url = f"https://{github_url}/graphql"
        return self.github_url

    async def _make_request(
        self,
        request_type: str,
        query: str,
        variables: dict = None,
        cursors: list[Cursor] = None,
        nodes_key: str = None,
    ) -> Union[dict, list, None]:
        request_params = {"json": {"query": query}}
        if variables:
            request_params["json"]["variables"] = variables

        response = []
        is_list = bool(request_type == "list")
        if is_list:
            assert cursors is not None
            request_params["json"].setdefault("variables", {})
            for cursor in cursors:
                request_params["json"]["variables"].setdefault(cursor.cursor_var, None)
            request_type = "post"

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": await self.get_bearer_token(),
                "Accept": "application/vnd.github.vixen-preview+json",
            }
            while True:
                async with getattr(session, request_type)(
                    self.get_github_api_url(), headers=headers, **request_params
                ) as resp:
                    if resp.status == 429:
                        # Handle rate limit exceeded error
                        retry_after = int(resp.headers.get("Retry-After", "1"))
                        await asyncio.sleep(retry_after)
                        continue

                    if not resp.ok:
                        log.error(
                            "GitHub request failed",
                            message=await resp.text(),
                            status_code=resp.status,
                        )
                        resp.raise_for_status()

                    try:
                        if data := (await resp.json()):
                            if errors := data.get("errors"):
                                log.error(
                                    "GitHub request failed",
                                    message=errors,
                                )
                                raise GraphQLQueryException(str(errors))
                            data = data["data"]
                    except aiohttp.ContentTypeError:
                        return

                    if is_list:
                        response.extend(get_dict_value(nodes_key, data, []))
                        while True:
                            cur_cursor = cursors[0]
                            if get_dict_value(cur_cursor.has_next_page_key, data):
                                break
                            elif len(cursors) > 1:
                                del(cursors[0])
                            else:
                                return response

                        request_params["json"]["variables"][cur_cursor.cursor_var] = get_dict_value(
                            cur_cursor.end_cursor_key,
                            data
                        )
                    else:
                        return data

    async def post(self, query: str, variables: dict = None):
        return await self._make_request("post", query, variables)

    async def get(self, query: str, variables: dict = None):
        return await self._make_request("get", query, variables)

    async def list(self, query: str, cursors: list[Cursor], nodes_key: str, variables: dict = None):
        return await self._make_request("list", query, variables, cursors, nodes_key)

    async def patch(self, query: str, variables: dict = None):
        return await self._make_request("patch", query, variables)

    async def delete(self, query: str, variables: dict = None):
        return await self._make_request("delete", query, variables)

    def dict(
        self,
        *,
        include: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        exclude: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> "DictStrAny":  # noqa
        required_exclude = {"bearer_token", "client"}
        if not exclude:
            exclude = required_exclude
        elif isinstance(exclude, set):
            exclude.update(required_exclude)

        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )


class GitHubTemplate(BaseTemplate):
    org: str = Field(
        ...,
        description="Name of the GitHub Organization that's associated with the resource",
    )

    @property
    def resource_id(self) -> str:
        return self.properties.resource_id

    async def apply(self, config: GitHubConfig) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=self.resource_id,
        )

        if self.iambic_managed == IambicManaged.IMPORT_ONLY:
            log_str = "Resource is marked as import only."
            log.info(log_str, **log_params)
            template_changes.proposed_changes = []
            return template_changes

        for github_organization in config.organizations:
            if github_organization.organization_name != self.org:
                continue

            if ctx.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, organization_name=github_organization.organization_name, **log_params)
            tasks.append(self._apply_to_account(github_organization))

        account_changes = list(await asyncio.gather(*tasks))
        template_changes.extend_changes(account_changes)

        if template_changes.exceptions_seen:
            cmd_verb = "applying" if ctx.execute else "detecting"
            log.error(
                f"Error encountered when {cmd_verb} resource changes.",
                **log_params,
            )
        elif account_changes and ctx.execute:
            if self.deleted:
                self.delete()
                log.info(
                    "Successfully removed resource from all GitHub organizations.",
                    **log_params,
                )
            else:
                log.info(
                    "Successfully applied resource changes to all GitHub organizations.",
                    **log_params,
                )
        elif account_changes:
            log.info(
                "Successfully detected required resource changes on all GitHub organizations.",
                **log_params,
            )
        else:
            log.debug(
                "No changes detected for resource on any GitHub organization.",
                **log_params,
            )

        return template_changes

    def set_default_file_path(self, repo_dir: str, file_name: str):
        if not file_name.endswith(".yaml"):
            file_name = f"{file_name}.yaml"

        self.file_path = os.path.expanduser(
            os.path.join(
                repo_dir,
                f"resources/{self.resource_type.replace(':', '/')}/{self.idp_name}/{file_name}",
            )
        )
