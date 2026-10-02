# Releases

One directory per immutable Evidence Atlas release. See
[`docs/atlas/release_model.md`](../docs/atlas/release_model.md).

| Release | Status | Record |
|---|---|---|
| v1.0.0 | RELEASED, frozen | [`release_record.json`](v1.0.0/release_record.json) · [`scientific_release.sha256`](v1.0.0/scientific_release.sha256) (197, tag `v1.0.0`) · [`web_delivery.sha256`](v1.0.0/web_delivery.sha256) (270, commit `da19599`) · [`frozen_artifacts.sha256`](v1.0.0/frozen_artifacts.sha256) (union, 467) |

Files in a release directory are never edited after the release is
published. Corrections create a new release directory.

Verify v1.0.0:

```bash
python scripts/atlas/build_v1_freeze_manifest.py --check
```
