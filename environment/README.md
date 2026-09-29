# Comparator environment

`comparator-lock.yaml` is the semantic lock. `Dockerfile.phase1a` composes the
digest-pinned hap.py BioContainer with the checksum-pinned official RTG 3.12.1
Linux distribution.

The image has not been built during bootstrap. Before compute, build with
BuildKit on linux/amd64, capture the resulting content digest, and verify the
runtime versions listed in the lock. A build or pull by mutable tag is not
acceptable for a scientific run.

The base BioContainer alone is not treated as proof that RTG vcfeval is present;
the RTG executable is overlaid explicitly and independently verified.

