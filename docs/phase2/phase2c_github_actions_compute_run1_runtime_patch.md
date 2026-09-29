# Project 003 Phase 2C — GitHub Actions Compute Run 1 Runtime Patch

## Status

RUNTIME-ONLY PATCH FROZEN BEFORE COMPUTE RERUN.

## Failed execution

- Workflow: Project 003 Phase 2C Compute
- Run ID: `36631324362`
- Run attempt: `1`
- Repository commit:
  `6b654c48263a4d90bf9161b682810e51725c5045`
- Result: `COMPARATOR_ENVIRONMENT_BLOCKED`
- Failure stage: `comparator/runtime installation`

Observed error:

`E: List directory /var/lib/apt/lists/partial is missing. - Acquire (13: Permission denied)`

The workflow cleanup intentionally removed `/var/lib/apt/lists/*`.
The compute runner subsequently invoked `apt-get update` as the
unprivileged runner user.

## Evidence boundary

The diagnostic command log contained only the attempted APT update and
diagnostic archive packaging before termination.

Therefore this failed execution did not:

- retrieve any Phase 2 query VCF;
- retrieve HG003 or HG004 benchmark truth VCFs;
- retrieve the GRCh38 benchmark reference;
- execute hap.py on genomic inputs;
- inspect benchmark outcomes;
- create Phase 2C EVENT or OBSERVATION evidence;
- perform Phase 2D biological identity expansion.

## Patch

The Actions runner changes only operating-system package installation
privilege:

- `apt-get update` -> `sudo apt-get update`
- `apt-get install` -> `sudo apt-get install`

No frozen scientific source, interval, truth set, comparator version,
comparator digest, comparison parameters, event logic, observation logic,
or validation criterion is changed.

Original runner SHA-256:

`f15e206c414024144a2e5f348f6c5612b17983edca9ee40f2e66bc6b2501a33b`

Patched runner SHA-256:

`24011ab7187c57c020fb614e5570fddf0e80a734cf1332f8a0891abc500be071`

The frozen Phase 2C scientific protocol and GitHub Actions runtime
amendment remain authoritative.
