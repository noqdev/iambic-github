import asyncio
from collections import defaultdict

from iambic.core.logger import log

from iambic_github.models import GitHubOrganization, Cursor


async def list_repo_collaborators(github_org: GitHubOrganization) -> dict[str, list]:
    collab_summary = defaultdict(lambda: defaultdict(list))
    query = """
    query ($orgName: String!, $repoCursor: String, $collaboratorCursor: String) {
      organization(login: $orgName) {
        repositories(first: 100, after: $repoCursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            projectsUrl
            collaborators(first: 100, after: $collaboratorCursor, affiliation: ALL) {
              pageInfo {
                hasNextPage
                endCursor
              }
              edges {
                permission
                permissionSources {
                  permission
                  source {
                    __typename
                    ... on Project {
                      name
                    }
                  }
                  source {
                    __typename
                    ... on Repository {
                      name
                    }
                  }
                }
                node {
                  login
                }
              }
            }
          }
        }
      }
    }
    """

    gh_response = await github_org.list(
        query,
        [
            Cursor(
                cursor_var="repoCursor",
                has_next_page_key="organization.repositories.pageInfo.hasNextPage",
                end_cursor_key="organization.repositories.pageInfo.endCursor",
            ),
            Cursor(
                cursor_var="collaboratorCursor",
                has_next_page_key="organization.repositories.pageInfo.hasNextPage",
                end_cursor_key="organization.repositories.pageInfo.endCursor",
            ),
        ],
        "organization.repositories.nodes",
        {"orgName": github_org.organization_name}
    )

    for repo in gh_response:
        for collaborator in repo["collaborators"]["edges"]:
            ps_map = defaultdict(set)
            for ps in collaborator["permissionSources"]:
                ps_map[ps["source"]["__typename"]].add(ps["permission"])

            # If a repo permission is defined with a conditional check to remove owner permissions that are inherited
            perm = ps_map.get("Repository")
            if perm and (perm != ps_map.get("Organization") or perm != {"ADMIN"}):
                if len(perm) == 1:
                    perm = perm.pop()
                else:
                    log.warning(
                        "GitHub Member detected with mixed roles",
                        member=collaborator["node"]["login"],
                        repo=repo["name"],
                    )
                    perm = [p for p in perm if p != "ADMIN"][0]
                collab_summary[collaborator["node"]["login"]].append({repo["name"]: perm})

    return {k: {"repositories": v} for k, v in collab_summary.items()}


async def list_members_partial(github_org: GitHubOrganization) -> dict:
    response = {}
    query = """
    query ($orgName: String!, $cursor: String) {
      organization(login: $orgName) {
        membersWithRole(first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          edges {
            role
            node {
              login
            }
          }
        }
      }
    }
    """
    partial_resp = await github_org.list(
        query,
        "organization.membersWithRole.pageInfo.hasNextPage",
        "organization.membersWithRole.pageInfo.endCursor",
        "organization.membersWithRole.edges",
        {"orgName": github_org.organization_name}
    )

    for member in partial_resp:
        response[member["node"]["login"]] = {"role": member["role"]}

    return response


async def list_members(github_org: GitHubOrganization) -> list[dict]:
    members = defaultdict(dict)
    partial_responses = await asyncio.gather(
        list_members_partial(github_org),
        list_repo_collaborators(github_org)
    )
    for response in partial_responses:
        for k, v in response.items():
            members[k].update(v)

    return [{k: v} for k, v in members.items()]