# adf

## createBlogPost

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

## createPage

For ADF input, set body.representation to atlas_doc_format and body.value to a JSON-serialized ADF document string. storage uses XHTML in body.value; these representations are distinct.

```json
{"spaceId":"123","status":"draft"}
```

```sh
confluence-as api call createPage --field 'spaceId="123"' --field status=draft
```

## getBlogPostById

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

## getBlogPostVersions

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

## getBlogPosts

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

## getBlogPostsInSpace

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

## getLabelBlogPosts

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

## getLabelPages

Tagged body fields accept Markdown or @file; storage is the default write representation. --representation atlas_doc_format writes stringified ADF. Reads render Markdown with lossless placeholders; --raw preserves stored bodies. Use the explicit body-format query parameter to request a read representation.

Showing entries 1–8 of 14. Continue: help adf --offset 8.
