from __future__ import annotations

from pydantic import BaseModel, Field, validator

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.azure_ad.handlers import import_azure_ad_resources, load
from iambic_github.models import GitHubOrganization


class GitHubConfig(BaseModel):
    organizations: list[GitHubOrganization] = Field(
        description="A list of GitHub Organizations."
    )

    @validator(
        "organizations", allow_reuse=True
    )  # the need of allow_reuse is possibly related to how we handle inheritance
    def validate_github_organizations(cls, orgs: list[organizations]):
        url_set = set()
        org_name_set = set()
        for org in orgs:
            if org.github_url in url_set:
                raise ValueError(
                    f"github_url must be unique within organizations: {org.github_url}"
                )
            else:
                url_set.add(org.github_url)

            if org.organization_name in org_name_set:
                raise ValueError(
                    f"organization_name must be unique within organizations: {org.organization_name}"
                )
            else:
                org_name_set.add(org.organization_name)

        return orgs

    def get_organization(self, organization_name: str) -> GitHubOrganization:
        for o in self.organizations:
            if o.organization_name == organization_name:
                return o
        raise Exception(f"Could not find organization for {organization_name}")


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="github",
    version=PLUGIN_VERSION,
    provider_config=GitHubConfig,
    async_import_callable=import_azure_ad_resources,
    async_load_callable=load,
    requires_secret=True,
    templates=[],
)
