# iambic-github
The IAMbic GitHub provider to manage users and teams.


## Current State
> Nothing is currently functional. 

### `GitHubOrganization._make_request`
Concerns:
The pagination is going to take some thought because it's a lesser of 3 evils problem.
Either constantly over fetch which will eat through our request limit, make smaller requests which will increase execution time, or manually munging data and paginating all the things.

Why?
It comes down to the way GraphQL handles nested pagination and GitHub's unforgiving request limit. 
GitHub allows you to retrieve up to 500,000 nodes or make 5,000 requests (`ceil(node_count/100)) per API call`) per hour. 
As a result, listing 1 repo has the same impact as listing 100 repos towards your "request" limit.

Take this simple query as an example:
```graphql
query ($orgName: String!, $memberCursor: String, $repoCursor: String) {
  organization(login: $orgName) {
    membersWithRole(first: 20, after: $memberCursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        role
        node {
          login
          repositories(first: 20, after: $repoCursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              name
              projectsUrl
            }
          }
        }
      }
    }
  }
}
```

This query will return 20 members with their first 20 repositories. In total, this query will return 420 nodes. 
Those 420 nodes will be divided by 100 and rounded up to 5. Those 5 "requests" will be deducted from the 5,000 you can make per hour.

But, what if each member has 200 repositories?
Each time you iterate through the nested cursor you're not just retrieving the relevant parent node, you're retrieving every parent and child node.

So, the cost to return a nested cursor for each page can be calculated by `ceil((parent_nodes + parent_nodes * child_nodes)/100) * total_child_pages` (NOTE: This formula only takes into account 2 cursors). 
In other words, the total number of requests deducted to return 20 users with 200 repos with this query is 100. 

You can increase the number of nodes returned by the child with the hopes of retrieving everything in a single look up. 
The problem is, if everything isn't returned in a single look up, the nodes consumed to paginate will grow by the formula described earlier.

The answer to this may be to not support nested pagination at all but will increase development time and execution time.


Problems: 
* In the process of supporting nested pagination 


### `list_members_partial`
Problems: 
* `GitHubOrganization.list` call needs to have updated params

Missing features:
* Retrieving user teams


### `list_repo_collaborators`
Problems: 
* Hasn't really been tested so it may or may not "work" as-is with the current pagination.

Missing features:
* Including member project roles was not completed

