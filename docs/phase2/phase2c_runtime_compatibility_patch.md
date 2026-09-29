# Phase 2C runtime compatibility patch

## Status

Implementation-only compatibility patch after the first frozen Phase 2C
Colab execution attempt.

## Pre-patch frozen state

- Pre-compute freeze commit: `7ca60b7a01b04b3cf692e04fd5577b6e5a037b29`
- Original runner SHA-256:
  `a221d9d0b25db963b83082c81161bbc23cddaa2701d7211df4bf9634940ee44d`
- Frozen scientific protocol, source selection, region panel, comparator
  identity, and schema semantics remain unchanged.

## Observed failure

The runner stopped during `comparator/runtime installation` while recording
`samtools --version`.

Python 3.13 attempted strict UTF-8 decoding of captured subprocess output and
raised:

`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xab ...`

The failure occurred before Phase 2 query/truth genomic downloads and before
hap.py/vcfeval benchmarking or outcome inspection.

## Patch

Captured external-command text is now decoded explicitly with:

- `encoding="utf-8"`
- `errors="replace"`

This applies to the runner's shared `run()` and `run_to_file()` subprocess
helpers.

The change only makes runtime/tool output capture tolerant of isolated
non-UTF-8 bytes. It does not modify command arguments, source URLs, checksums,
benchmark regions, truth definitions, comparator versions, evidence parsing,
identity semantics, scoring policy, or validation criteria.

## Post-patch runner

- Runner SHA-256: `eb1838e100e31cadbae052cc1f08c175208e9e6046ef4365efa36d4ba0b4a718`

The notebook is regenerated from this exact runner and remains gated with
`EXECUTE_COMPARISON = False` by default.
