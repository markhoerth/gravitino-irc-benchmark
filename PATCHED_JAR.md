# Bundled hotfix JAR — provenance

This repo bundles a single patched JAR at
`dockerfiles/gravitino-iceberg-rest-server-1.2.0.jar`. It is an official
Apache Gravitino engineering build, not a local modification.

## Identification

| Field | Value |
|---|---|
| Filename | `gravitino-iceberg-rest-server-1.2.0.jar` |
| Size | 219,789 bytes (≈214.6 KiB) |
| SHA-1 | `876ee5bf1099acdcb7d8e4f6ccc6d6b603d53a0e` |
| Built by | Apache Gravitino engineering |
| Source tag | [`1.2.0-hotfix-release`](https://github.com/apache/gravitino/releases/tag/1.2.0-hotfix-release) |
| Tag commit | `38021e1` |
| Delta from stock 1.2.0 | Exactly one commit |

## What is in it

The `1.2.0-hotfix-release` tag is the `v1.2.0` release tag with one commit
applied on top: the automated cherry-pick of PR [#10767][pr10767]
(tracked as backport PR [#10802][pr10802], fixing issue [#10766][is10766]).

```
$ git log v1.2.0..38021e1 --oneline
38021e13b [Cherry-pick to branch-1.2] [#10766] fix(iceberg): skip table import
          for staged creates in IcebergTableHookDispatcher (#10767) (#10802)
```

## What it fixes

`CREATE TABLE` issued through Trino against the Gravitino Iceberg REST
Catalog fails with `NoSuchTableException` whenever authorization is enabled.

Root cause: `IcebergTableHookDispatcher.createTable()` unconditionally calls
`importTable()` after creating a table. Trino sends `stageCreate=true` on
every `CREATE TABLE`, meaning the table is not yet committed when the import
path runs `loadTable`. With authorization enabled the hook dispatcher is
wired into the request path, so the failure surfaces.

The fix replaces `importTable` with a new `importTableAndSetOwner` helper
that is invoked from the staged-create commit path (the subsequent
`updateTable`) rather than from `createTable`. This preserves the ownership
behaviour while letting the staged create complete normally.

## How to verify the JAR yourself

```bash
# 1. Hash
shasum dockerfiles/gravitino-iceberg-rest-server-1.2.0.jar
# Expected: 876ee5bf1099acdcb7d8e4f6ccc6d6b603d53a0e

# 2. Fix present in bytecode
unzip -p dockerfiles/gravitino-iceberg-rest-server-1.2.0.jar \
  org/apache/gravitino/iceberg/service/dispatcher/IcebergTableHookDispatcher.class \
  > /tmp/htd.class
javap -p /tmp/htd.class | grep importTableAndSetOwner
# Expected: private void importTableAndSetOwner(...)
```

## Interim status

This JAR is an interim artifact. The fix is merged to both `main` and
`branch-1.2` upstream and will ship as part of the next 1.2.x point
release. Once that release is available, replace this JAR with the
official release artifact.

[pr10767]: https://github.com/apache/gravitino/pull/10767
[pr10802]: https://github.com/apache/gravitino/pull/10802
[is10766]: https://github.com/apache/gravitino/issues/10766
