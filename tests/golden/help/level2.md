# deletePage

DELETE `/pages/{id}`

Delete page

Delete a page by id.

## Parameters

- `--id` (path, integer) (required)
- `--purge` (query, boolean)
- `--draft` (query, boolean)

## Body

No top-level body properties.

## Behavior

- Risk: irreversible.
- Dry-run by default; --confirm sends the request.
- x-atlassian-connect-scope: "DELETE"
- x-atlassian-oauth2-scopes: [{"scheme": "oAuthDefinitions", "scopes": ["delete:page:confluence"], "state": "Current"}]
- Use --full for the complete description; --examples for examples.
