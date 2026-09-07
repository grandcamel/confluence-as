# adf

## createPage

For ADF input, set body.representation to atlas_doc_format and body.value to a JSON-serialized ADF document string. storage uses XHTML in body.value; these representations are distinct.

```json
{"spaceId":"123","status":"draft"}
```

```sh
confluence-as api call createPage --field 'spaceId="123"' --field status=draft
```

## updatePage

For ADF input, set body.representation to atlas_doc_format and body.value to a JSON-serialized ADF document string. storage uses XHTML in body.value; these representations are distinct.

```json
{"number":2,"message":"Example update"}
```

```sh
confluence-as api call updatePage --id 123 --body @page.json --confirm
```
