# Probe report A1 (data sources), run 2026-11-21 ~13:35-13:50 ET

Raw outputs: `probes/A/outputs/` (script: `probes/A/probe_sources.sh`, timings in `probe_timings.log`).

## Blocking finding (fixed)
- The apt `bcftools 1.13` / `htslib` in WSL Ubuntu-22.04 is built WITHOUT libcurl: any `https://` input fails with
  `Protocol not supported`. A libcurl-enabled **bcftools 1.25 / htslib 1.25** was installed with micromamba into
  `~/bio` (WSL). `genesleuth/data/bcf.py` (`run_bcftools`, `run_tool`, `run_shell`) prefers `~/bio/bin` automatically.
  Rebuild if needed: `curl -sL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj bin/micromamba` then
  `micromamba create -y -p ~/bio -c conda-forge -c bioconda bcftools htslib` (about 2 min).

## Sources (all confirmed working today)
| Source | URL / call | Result | Time |
|---|---|---|---|
| MANE v1.5 summary | `https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.5.summary.txt.gz` | 200, 1.1 MB, header `#NCBI_GeneID Ensembl_Gene HGNC_ID symbol name RefSeq_nuc RefSeq_prot Ensembl_nuc Ensembl_prot MANE_status GRCh38_chr chr_start chr_end chr_strand`; all 58 panel genes have a MANE Select row | 1 s |
| MANE Ensembl GTF | `.../MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz` | 200, 8.6 MB; features exon/CDS/UTR (no 5'/3' split; derived from strand + CDS)/start_codon/stop_codon/transcript; chromosomes are `chr`-prefixed | 2-6 s |
| 1000G NYGC phased panel (GRCh38) | `https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/1kGP_high_coverage_Illumina.{chrom}.filtered.SNV_INDEL_SV_phased_panel.vcf.gz` (chrX: `...panel.v2.vcf.gz`) | 3,202 samples; **NA12878 and HG00096 both present**, so DEFAULT_SAMPLE stays NA12878. SCN1A region (`chr2:165980000-166140000`) for NA12878 -> 274 non-ref records. FILTER is `.` for every record (no PASS), INFO has AF/AC/AN (+ per-population AF). Multi-allelic records are split (id `2:pos:ref:alt`) | open+list samples 12 s; SCN1A stream 11.7 s |
| gnomAD v4.1 genomes | `https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/genomes/gnomad.genomes.v4.1.sites.{chrom}.vcf.bgz` | chr-prefixed; fields AF, AF_grpmax, AN present. `bcftools view -G -R <positions>` at the 274 SCN1A positions -> 848 records (multiple alleles per position; match on ref/alt) in 11.7 s; whole-region stream (160 kb) -> 36,688 records in 14.5 s | see timings |
| ClinVar GRCh38 VCF | `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz` (+`.tbi`) | remote region query works with unprefixed contigs (`2:165980000-166140000`): 2,218 P/LP (no Conflicting) records in the SCN1A window | 1.2 s |
| Ensembl VEP REST | `POST https://rest.ensembl.org/vep/homo_sapiens/region` with `{"variants": ["2 165991234 . A G . . ."]}` | 200; returns `transcript_consequences[].consequence_terms`, `most_severe_consequence`; used only to name coding consequences | 1.7 s |
| PanelApp | `https://panelapp.genomicsengland.co.uk/api/v1/panels/402/` | "Early onset or syndromic epilepsy" v9.100, 920 genes, 632 green | 1.6 s |
| gnomAD GraphQL, HPO | not probed by A1 | AF comes from the streamed VCF; HPO is A2's slice | |

## Real measurements (NA12878, full panel)
- 58 genes, 9,154,647 bp with +/-10 kb flanks (matches the brief's 9.15 Mb).
- `scripts/data_background.py` stream of all panel chromosomes (8 parallel): **12,923 variants** (non-ref SNVs/indels <= 10 bp) in 148 s.
- gnomAD AF streamed at those positions: 12,920 / 12,923 alleles found in gnomAD genomes v4.1 (3 fall back to the 1000G AF) in 149 s.
- Funnel: AF < 0.1: 1,429; **AF < 0.01: 281**; AF < 0.001: 83; AF < 0.0001: 37. AF < 0.001 is below the 100-300 target, so the pipeline uses AF < 0.01 (281 suspects, all kept; no intron trimming needed).
- Suspect regions: 245 intron, 22 intergenic (flank), 7 3'UTR, 4 coding, 3 promoter, 0 splice. WWOX alone has 95 suspects (largest gene; drop it from the panel if you want a more even spread).
- Annotation: GTF classification is instant; coding variants get VEP most_severe (about 2 s per batch). One planted non-coding variant annotates in about 0.01 s.
- Cross-check against ClinVar MC terms (P/LP SNVs in panel regions): splice donor/acceptor calls agree (790/790 and 631/631 exact among the unambiguous classes); remaining differences are other-isoform terms (MANE Select only is used here).

## Not blocked
Nothing blocks the other slices. The only thing to know: use `genesleuth.data.bcf` for bcftools (it picks the libcurl build).
