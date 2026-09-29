# Phase 1A compute and Google Colab plan

This document defines a future compute proof. The bootstrap did not download
genomic data and did not run hap.py or vcfeval.

## Locked submissions

| Submission | Technology condition | Public pipeline metadata | Selection basis |
|---|---|---|---|
| `60Z59` / HG002 | Illumina NovaSeq 6000, challenge input reported at 35x | `RN-Illumina`; BWA 0.7.15; NeuSomatic version `UNKNOWN`; GATK 4.1.7.0; Picard 2.22.4 | Phase 0B already verified this exact BGZF artifact/header/checksum and public methods; no result metric was consulted. |
| `RU88N` / HG002 | ONT PromethION R9.4, challenge input reported at 47x; challenge FASTQs were Guppy 3.6 basecalled | `PEPPER-DeepVariant (ONT)`; minimap2 2.17-r941; PEPPER and DeepVariant versions `UNKNOWN` | Single-technology ONT artifact with exact PDR mapping and methods; no result metric was consulted. |

The metadata claims above come from the NIST PDR documentation, the pinned
NIST analysis-repository metadata table, and `submission_methods.txt`. Missing
versions remain `UNKNOWN`.

## Locked truth, reference, and interval

- Truth: `HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` plus its public TBI.
- Benchmark regions:
  `HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed`.
- Reference:
  `GCA_000001405.15_GRCh38_no_alt_analysis_set.fasta.gz` plus FAI/GZI.
- Core interval (registry coordinates): `chr20:[10,000,000,11,000,000)`,
  0-based half-open, exactly 1,000,000 bases.
- Human display interval: `chr20:10,000,001-11,000,000`, 1-based inclusive.
- Extraction interval: `chr20:[9,999,000,11,001,000)`, providing 1,000 bases
  of padding on each side.

The interval was selected before comparison by an engineering rule: a fixed
1 Mb window on the relatively small autosome chr20, away from chromosome ends
and the modeled centromere. No submission result or error distribution was
inspected. The benchmark BED overlap has intentionally not been inspected
during bootstrap. If the locked core has no assessable bases, that is a locked
FAIL and requires a versioned design revision, not an ad hoc interval change.

## Locked comparator environment

`environment/comparator-lock.yaml` is authoritative.

- hap.py `0.3.15`, upstream tag commit
  `84011695b2ff2406c16a335106db6831fb67fdfe`;
- BioContainers hap.py image
  `quay.io/biocontainers/hap.py@sha256:d63b963a6cb01b4830393b22369e7b91d298e4156dde353739e74e4cfa4f96d0`;
- RTG Tools/vcfeval `3.12.1`, upstream tag commit
  `a9d16d88b80fc660ba3ad7d6b9e7acc45e0befd7`;
- official RTG Linux x64 ZIP SHA-256
  `ba43cadbb3e79bff74e7d2f8540dd5e201574ec8e293ba555f3aeefd1375dfc5`;
- comparison engine `vcfeval`; and
- annotated hap.py output enabled with `-V`.

The hap.py 0.3.15 source release itself updated its bundled RTG dependency to
3.12.1. The separate RTG distribution is nevertheless locked explicitly so
the executable invoked in Colab is attributable.

Before genomic compute, the runtime must print and capture hap.py, RTG, Java,
bcftools, samtools, and Python versions. A derived image built from
`environment/Dockerfile.phase1a` must be tagged by its content digest in the
run record; the source lock alone is not a substitute for the built digest.

## Colab execution strategy

The future notebook is deliberately staged and fail-closed:

1. Start a fresh CPU Colab runtime. Record runtime metadata and allocate a
   persistent work directory, preferably mounted Google Drive for cache only.
2. Install a pinned rootless container runner and pull the locked hap.py image
   by digest. Download the locked RTG ZIP, verify its SHA-256 before extraction,
   and expose its `rtg` executable to the container. Alternatively build the
   checked-in derived Dockerfile elsewhere and pull that image by its recorded
   digest; never use a mutable tag for a scientific run.
3. Download the two whole query VCFs because the PDR deposit has no TBI/CSI.
   Verify their published SHA-256 values before use.
4. Download the GIAB BED and public indexes. Use the indexed GIAB truth and
   BGZF reference to retrieve only the padded chr20 slice where the toolchain
   supports HTTP range access. If range retrieval is unreliable, use the
   documented full-download fallback without changing artifact identity.
5. Compute and record SHA-256 for every downloaded file, including GIAB files
   for which no public SHA-256 sidecar is supplied. Validate expected byte sizes
   and the published reference MD5 values.
6. Normalize only container/sort/index prerequisites, retaining the original
   query artifacts and recording every derived slice/index as a new
   `SOURCE_ARTIFACT`. Never overwrite a source object.
7. Build an RTG SDF from the exact reference slice. Intersect the benchmark BED
   with the padded interval. Preserve core and padding boundaries separately.
8. Run the same hap.py/vcfeval command template once per experiment with `-V`,
   the locked truth, effective BED, reference/SDF, and parameters. Capture
   stdout, stderr, exit status, wall time, peak RSS where available, and command
   argv as output artifacts.
9. Normalize annotated records to the six schemas, excluding boundary-only
   diagnostics from the evidence export while retaining them in audit output.
10. Write typed Parquet tables, create a DuckDB database/views, run the locked
    event query, and execute all Phase 1A validation checks.
11. Persist manifests and checksums before the ephemeral runtime ends. Do not
    publish remotely as part of Phase 1A.

The notebook defaults to `EXECUTE_COMPARISON = False`. A user must explicitly
change the flag in a future compute session after the preflight manifest passes.

## Proposed command contract

The exact path names are run-local, but the semantic argv is locked:

```text
hap.py TRUTH_SLICE QUERY_SLICE
  -f EFFECTIVE_PADDED_BED
  -r REFERENCE_CHR20_FASTA
  -o RUN_OUTPUT_PREFIX
  -V
  --engine=vcfeval
  --engine-vcfeval-path /opt/rtg-tools-3.12.1/rtg
  --engine-vcfeval-template REFERENCE_CHR20_SDF
  --threads 2
```

No quality threshold is added. Source FILTER values and comparator not-assessed
states are retained. Any required syntax-only adjustment discovered during
preflight must be documented as a lock-file revision before comparison.

## Download and compute estimates

Known full genomic source objects total approximately 1.225 GB decimal before
tools: 168.46 MB for the two query VCFs, 156.25 MB truth VCF, 1.66 MB truth
index, 11.49 MB BED, and 887.12 MB for reference plus indexes. The locked
hap.py image layers are approximately 233.6 MB compressed and the RTG ZIP is
50.7 MB, yielding a conservative cold-runtime transfer near **1.51 GB**.

With HTTP range extraction, expected genomic transfer is approximately
**200–260 MB**: both whole unindexed queries dominate (168.46 MB), plus the BED,
indexes, one chr20 reference slice, and a small truth slice. Including cold
tool acquisition gives an expected optimized first run of roughly
**485–550 MB**. Range behavior and container-runner overhead make this an
engineering estimate, not a measured benchmark.

Expected resources for two 1 Mb padded comparisons are 2–4 vCPUs, less than
8 GB RAM, approximately 6 GB temporary disk (to allow container expansion,
reference/SDF, source VCFs, slices, and outputs), and 10–30 minutes of comparison
time after setup. Allow 30–60 minutes end to end on a free Colab CPU runtime.
These estimates must be replaced by measured values after the proof.
