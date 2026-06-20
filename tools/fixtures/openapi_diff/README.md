# OpenAPI Diff Ordering Fixtures

These fixtures exercise `tools/openapi_diff.lua` against semantically identical
OpenAPI objects whose YAML keys and list entries are ordered differently.

Validation examples:

```sh
lua tools/openapi_diff.lua --left tools/fixtures/openapi_diff/reordered-left.yaml --right tools/fixtures/openapi_diff/reordered-right.yaml
lua tools/openapi_diff.lua --left tools/fixtures/openapi_diff/reordered-left.yaml --right tools/fixtures/openapi_diff/changed-type.yaml
```

