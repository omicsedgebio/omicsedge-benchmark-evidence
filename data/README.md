# Data boundary

This repository does not contain genomic data or scientific comparison output.

- `manifests/` contains public artifact metadata and locked experiment choices.
- `raw/` is a future local cache and is git-ignored.
- `staged/` is for future immutable slices/indexes and is git-ignored.
- generated scientific outputs belong under git-ignored `results/compute/`.

Source files must never be overwritten. Every transformation creates a new
artifact record and provenance link.

