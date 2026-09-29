# Unresolved scientific risks

1. **Original-comparison non-reproducibility.** Public precisionFDA V2 files do
   not bind each retained result to an exact hap.py/RTG build, command, truth
   patch, reference checksum, or annotated VCF. Phase 1A is intentionally a new
   v4.2.1 regeneration, not a reproduction of the original V4.1 HG002 result.
2. **Reference identity uncertainty.** The challenge establishes GRCh38 and the
   inspected query header matches GRCh38 contig lengths, but the participant's
   exact FASTA bytes are not bound to the query artifact. The locked GIAB no-alt
   reference is explicit for regeneration; incompatibility must fail preflight.
3. **Truth-release sensitivity.** GIAB v4.2.1 differs from the challenge's
   described HG002 V4.1 family. Outcomes may change because the truth and
   assessable universe changed.
4. **Incomplete experiment metadata.** NeuSomatic's submission version for
   `60Z59` and PEPPER/DeepVariant versions for `RU88N` are unknown. These runs
   remain useful historical observations but cannot support exact end-to-end
   caller reproduction.
5. **Interval representativeness.** A coordinate-selected 1 Mb window proves a
   pipeline and data model only. It cannot estimate genome-wide performance or
   characterize either technology.
6. **Boundary effects.** Complex representations and superloci can extend past
   BED or extraction boundaries. Padding plus core containment reduces but does
   not eliminate comparator-boundary sensitivity; boundary events are audit
   diagnostics, not Phase 1A evidence.
7. **Cross-run event identity.** hap.py `BS` identifiers are run-scoped. Exact
   allele or coordinate matches across runs are candidate correspondences, not
   proof of one biological event. A reviewed equivalence model remains future
   work.
8. **Legacy runtime risk.** hap.py 0.3.15 uses a Python 2-era environment. The
   digest-pinned container and RTG overlay reduce drift but must be proven on
   the current Colab/container runner before scientific compute.
9. **Publisher checksum gaps.** The GIAB v4.2.1 primary truth VCF/BED directory
   does not expose checksums for those primary files. Byte sizes can be checked
   before download and SHA-256 recorded afterward, but there is no independent
   publisher hash for those objects in the audited directory.
10. **No stratification claims in Phase 1A.** The benchmark BED defines the
    assessed region, but Phase 1A does not ingest the full GIAB genomic
    stratification bundle. The proof cannot attribute an outcome to difficult
    genomic context beyond recorded benchmark-region/boundary status.

