# 03 – Data plan (GeneSleuth)

Research only, no project code. Checked 2026-11-19: URLs answered HTTP 200 and sizes come from `Content-Length`, unless a line says **[est]** (my estimate) or **[unverified]**.

## Download checklist

| # | Dataset | URL | Size | Used for |
|---|---|---|---|---|
| 1 | ClinVar GRCh38 VCF + .tbi | https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz (+`.tbi`) | 201.6 MB + 0.6 MB | Variants to plant; truth labels |
| 2 | ClinVar variant_summary (current) | https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz | 458.5 MB | Disease IDs (OMIM/MONDO), review status |
| 3 | ClinVar variant_summary snapshot (old) | https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/variant_summary_2025-01.txt.gz | 288.3 MB | Diff against #2 to get a post-cutoff test set |
| 4 | HPO annotations | https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa | 35.8 MB | Disease→HPO terms with frequencies |
| 5 | HPO gene→phenotype | …/releases/latest/download/genes_to_phenotype.txt | 20.8 MB | Score how well a gene matches the phenotype |
| 6 | HPO ontology | …/releases/latest/download/hp.json | 21.9 MB | Ancestors for semantic similarity and noisy synthetic patients |
| 7 | MANE v1.5 summary | https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.5.summary.txt.gz | 1.1 MB | Gene start/end (GRCh38) |
| 8 | MANE v1.5 Ensembl GTF | …/MANE_human/current/MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz | 8.6 MB | Exon and UTR boundaries; distance to splice site |
| 9 | PanelApp epilepsy panel JSON | https://panelapp.genomicsengland.co.uk/api/v1/panels/402/ | 0.9 MB | Source for the gene list |
| 10 | 1000G high-coverage phased VCF, **gene regions only (streamed)** | https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/ | ~200–300 MB streamed **[est]**; ~1–3 MB output | Background genome |
| 11 | gnomAD v4.1 genomes, **gene regions only (streamed)** | https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/genomes/gnomad.genomes.v4.1.sites.chr{N}.vcf.bgz | ~1.5–2 GB streamed **[est]**; ~50 MB output after removing INFO fields | Allele frequency filter |
| 12 | (opt) GENCODE v50 basic GTF | https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/latest_release/gencode.v50.basic.annotation.gtf.gz | 80.0 MB | All transcripts, if MANE is not enough |
| 13 | (opt) hg38 FASTA | https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz | 983.7 MB | `bcftools norm` and REF checks when planting indels |
| 14 | (opt, 23andMe) hg19→hg38 chain | https://hgdownload.soe.ucsc.edu/goldenPath/hg19/liftOver/hg19ToHg38.over.chain.gz | 0.2 MB | Liftover |
| 15 | (opt, 23andMe) GRCh37 FASTA | e.g. https://hgdownload.soe.ucsc.edu/goldenPath/hg19/bigZips/hg19.fa.gz | ~0.9 GB **[est]** | `--tsv2vcf` needs a reference |

**Total.** Core files 1–9: about **1.04 GB**. Add about **2 GB** of streamed regions (10–11) for about **3 GB** of network, but only about 1.1 GB stays on disk. With all optional files: about **5 GB**.

Do not download `ClinVarVCVRelease_00-latest.xml.gz` (6.09 GB) unless you need exact creation dates (see §3).

**Tooling gap.** This Windows machine has no `bcftools` or `tabix`. Install them in WSL2 Ubuntu (`sudo apt install bcftools tabix`; the apt build includes libcurl, so it can read https) or use a Docker bcftools image. Do this before Saturday.

---

## 1. 1000 Genomes / NYGC high coverage (GRCh38)

- **Phased panel**, 3,202 samples, split by chromosome (`chr` prefix):
  - Example: `…/20220422_3202_phased_SNV_INDEL_SV/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz` is 2.51 GB; chr1 is 2.39 GB; each `.tbi` is ~0.2 MB.
  - chrX is `…chrX.filtered.SNV_INDEL_SV_phased_panel.v2.vcf.gz`. v1 was withdrawn on 2022-08-03 because of male ploidy (see `change_log.txt`).
- **Unfiltered genotypes** are in `…/working/20201028_3202_raw_GT_with_annot/`. That directory was not opened **[unverified]**.
- **No per-sample VCFs exist.** Use `bcftools view -s SAMPLE -r REGIONS <https URL>`. With the remote `.tbi`, htslib fetches only the BGZF blocks for those regions, so you never download the whole file.
- **Sample.** Use **NA12878** (CEU, also GIAB HG001). It is very well characterised. I believe it is in the 3,202 set as part of the related trios **[verify with `bcftools query -l`]**. Backup: HG00096.
- **Caveat.** The phased panel's site filters may drop some singletons, and its README has the details (`README_1kGP_phased_panel_110722.pdf`). This is acceptable because the planted variant is added by us anyway **[unverified]**.
- **Licence.** The IGSR data reuse policy allows unrestricted use with citation (Byrska-Bishop et al., *Cell* 2022). Committing a small regional VCF for NA12878 to a public repo is fine; add a citation. Check https://www.internationalgenome.org/IGSR_disclaimer **[policy page not re-read today]**.

## 2. gnomAD v4.1 allele frequencies

- **Genomes sites VCF**, split by chromosome: chr2 is 46.6 GB, its `.tbi` is 0.23 MB. The joint exome+genome VCF (`release/4.1/vcf/joint/gnomad.joint.v4.1.sites.chr2.vcf.bgz`) is 69.4 GB. Remote tabix works on both through `https://storage.googleapis.com/...`.
- **Smallest practical approach:** stream the regions, keep only the frequency fields, and save a local file:
  `bcftools view -r <regions> URL | bcftools annotate -x ^INFO/AC,INFO/AN,INFO/AF,INFO/AF_grpmax,INFO/nhomalt`
  - ~9.2 Mb of regions is about 2.2M records. At ~750 B per record compressed, that is about **1.7 GB streamed** **[est]**.
  - Cheaper option: give `-R` only the sample's own variant positions (~15k). Then far fewer blocks are fetched.
- **Fallbacks:**
  1. The `AF` field inside the 1000G panel (3,202 samples) is free and works as a first-pass filter.
  2. myvariant.info batch POST (up to 1,000 IDs per call) returns gnomAD AF.
  3. gnomAD GraphQL API (`https://gnomad.broadinstitute.org/api`) is rate-limited, roughly 10 requests per minute **[unverified]**. It is fine for the planted variant but not for bulk lookups.
- **Licence:** I believe gnomAD releases data as CC0 or equivalent open terms **[unverified]**. Committing a stripped AF table for 58 genes should be fine.

## 3. ClinVar

- **VCF:** uses chromosome names `1`, not `chr1`. Rename with `bcftools annotate --rename-chrs` before merging with 1000G or gnomAD.
  - Useful INFO fields: `CLNSIG`, `CLNREVSTAT`, `MC` (Sequence Ontology consequence|term), `GENEINFO`, `CLNDISDB`, `CLNDN`.
- **variant_summary.txt.gz:** 43 columns (header checked). Relevant ones:
  - `ClinicalSignificance`, `ReviewStatus`, `PhenotypeIDS` (OMIM/MONDO), `Assembly` (filter to GRCh38), `VariationID`, `PositionVCF`, `ReferenceAlleleVCF`, `AlternateAlleleVCF`.
- **Selecting variants.** Keep `CLNSIG` containing Pathogenic or Likely_pathogenic, without "Conflicting", and at ≥1 review star. I counted these in the 2026-11-15 VCF for the 58 genes in §5:
  - **16,294 P/LP variants** in total.
  - **~1,390 SNVs** whose only consequences are canonical splice or non-coding (splice_donor/acceptor plus intron/UTR).
  - **169 SNVs that are deep non-coding**: every `MC` term is intron, 5′/3′ UTR, splice_region, non-coding transcript, or upstream/downstream. Top genes: SCN1A 50, TSC2 37, STXBP1 18, TSC1 11, KCNQ2 10.
  - The 169 are the AlphaGenome showcase pool. The 1,390 splice SNVs are the main benchmark pool.
- **Date fields.**
  - Neither the VCF nor variant_summary has a "date first submitted". variant_summary only has `LastEvaluated`.
  - submission_summary (407.5 MB) only has `DateLastEvaluated`.
  - **Approach:** take VariationIDs that are in the current variant_summary but not in an old snapshot. Monthly snapshots back to 2014 are under `tab_delimited/archive/` (2025+ at top level, older years in `archive/YYYY/`).
  - Pick the snapshot month that matches Gemini's published knowledge cutoff **[look up on the day]**.
  - The VCV XML has `DateCreated` on each VariationArchive, which gives exact dates, but the file is 6.1 GB **[attribute name from memory, unverified]**.

## 4. HPO

- **phenotype.hpoa** (release 2026-09-02). Columns: `database_id, disease_name, qualifier, hpo_id, reference, evidence, onset, frequency, sex, modifier, aspect, biocuration`.
  - Keep `aspect == P` and drop rows with `qualifier == NOT`.
  - `frequency` is either an HPO frequency term (HP:0040280–HP:0040285) or a fraction like `n/m`.
- **genes_to_phenotype.txt** columns: `ncbi_gene_id, gene_symbol, hpo_id, hpo_name, frequency, disease_id`.
- **Synthetic patients**, following the usual Exomiser/LIRICAL simulation approach:
  1. Get the disease from ClinVar `PhenotypeIDS` (prefer `OMIM:`; MONDO→OMIM via `CLNDISDB`).
  2. Sample 5–8 of its phenotype terms, weighting each by its frequency.
  3. Replace about 30% of the terms with a parent term from `hp.json` to add imprecision.
  4. Add 1–2 random unrelated terms as noise.
  5. Fix the random seed for each case.
- **Licence:** HPO annotations are free to use with attribution.

## 5. Gene list (58 genes, all "green" on PanelApp 402)

**Source:** Genomics England PanelApp panel 402, now named **"Early onset or syndromic epilepsy" v9.100** (2026-11-11). It has 920 genes, 632 of them green. That is too many for the demo, so I picked well-known DEE/epilepsy genes and checked that every one is green:

SCN1A SCN2A SCN3A SCN8A SCN1B KCNQ2 KCNQ3 KCNT1 KCNA2 KCNB1 KCNMA1 CACNA1A CACNA1E HCN1 GRIN1 GRIN2A GRIN2B GRIN2D GABRA1 GABRB2 GABRB3 GABRG2 SLC2A1 SLC6A1 SLC12A5 SLC13A5 STXBP1 SYNGAP1 CDKL5 PCDH19 DEPDC5 NPRL2 NPRL3 TSC1 TSC2 MTOR PRRT2 CHD2 MECP2 FOXG1 ARX DNM1 ALDH7A1 PNPO POLG TBC1D24 SZT2 WWOX UBE3A MEF2C STX1B PIGA SPTAN1 GNAO1 CSTB EPM2A NHLRC1 PURA

- MANE spans add up to **7.99 Mb**, or **9.15 Mb with ±10 kb flanks**.
- The largest genes are WWOX (1.11 Mb), KCNMA1 (0.75 Mb) and GRIN2B (0.44 Mb). Drop WWOX if you need to save time.
- Cross-check source: ClinGen epilepsy gene curation.

## 6. Gene coordinates

- **Regions BED:** MANE summary columns `symbol, GRCh38_chr (NC_ accession), chr_start, chr_end, chr_strand`. Map `NC_0000NN.x` to `chrN`.
- **Exons and UTRs:** MANE Ensembl GTF. GENCODE v50 basic is only needed for non-MANE transcripts.

## 7. 23andMe (optional opener)

- **Format:** TSV with `#` comment lines and the columns `rsid, chromosome, position, genotype` (for example `AG`, `--` for no call). The build is **GRCh37**. The v5 chip has ~630k mostly common SNPs.
- **Not usable as the background genome.** The chip contains almost no rare variants. Use it only as a "your genome, your risk alleles" demo opener.
- **Convert:** `bcftools convert --tsv2vcf raw.txt -f hg19/GRCh37.fa -s ME -c ID,CHROM,POS,AA -Oz -o me37.vcf.gz`. The FASTA chromosome names must match the file's (`1` vs `chr1`).
- **Liftover:** `bcftools +liftover` (freeseek plugin, not in apt by default **[unverified]**), CrossMap (`pip install CrossMap`, then `CrossMap vcf hg19ToHg38.over.chain.gz …`), or Picard LiftoverVcf. Use chain #14.
- **Privacy:** never commit personal 23andMe data.

## 8. Expected numbers

| Stage | Count | Basis |
|---|---|---|
| Variant sites per genome (SNV+indel) | 4.1–5.0 M | 1000G Phase 3, *Nature* 2015 (cited) |
| Rare (AF<0.5%) per genome | ~40–200k (more in African ancestry) | 1000G 2015 (cited, from memory) |
| AF<0.1% per genome | ~20–80k | **[est]** |
| In 58 genes ±10 kb (9.15 Mb ≈ 0.3% of genome), any AF | ~12–16k | **[est]**, at ~1.5 variants/kb |
| …and AF<0.1% | ~50–250 | **[est]** |
| …and AF<1% | ~300–600 | **[est]** |

The ~400-candidate target fits **AF<1%**, or AF<0.1% with ±50 kb flanks. Measure the real numbers in rehearsal.

---

## Commands to rehearse (PRACTICE ONLY: throwaway, not project code)

Run these in WSL2. Delete the outputs afterwards.

```bash
# 0. sanity: list samples remotely (downloads only the header)
U=https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV
bcftools query -l $U/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz | grep -c .
bcftools query -l $U/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz | grep NA12878

# 1. stream one gene (SCN1A, chr2 ~165.98-166.13 Mb) for one sample; keep only non-ref genotypes
bcftools view -s NA12878 -r chr2:165980000-166140000 \
  $U/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz \
  | bcftools view -i 'GT="alt"' -Oz -o practice_scn1a.vcf.gz && tabix -p vcf practice_scn1a.vcf.gz
bcftools view -H practice_scn1a.vcf.gz | wc -l

# 2. gnomAD AF for the same region, keeping only frequency fields (time it)
G=https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/genomes
time bcftools view -r chr2:165980000-166140000 $G/gnomad.genomes.v4.1.sites.chr2.vcf.bgz \
  | bcftools annotate -x '^INFO/AF,INFO/AF_grpmax,INFO/AN' -Oz -o practice_gnomad_scn1a.vcf.gz

# 3. annotate sample with gnomAD AF, then filter rare
tabix -p vcf practice_gnomad_scn1a.vcf.gz
bcftools annotate -a practice_gnomad_scn1a.vcf.gz -c INFO/gnomAD_AF:=INFO/AF practice_scn1a.vcf.gz \
  | bcftools view -i 'INFO/gnomAD_AF<0.001 || INFO/gnomAD_AF="."' -H | wc -l

# 4. ClinVar: rename chroms, pull P/LP in SCN1A
for c in {1..22} X Y; do printf '%s\tchr%s\n' $c $c; done > chrmap.txt; printf 'MT\tchrM\n' >> chrmap.txt
bcftools annotate --rename-chrs chrmap.txt clinvar.vcf.gz -Oz -o clinvar.chr.vcf.gz && tabix -p vcf clinvar.chr.vcf.gz
bcftools view -r chr2:165980000-166140000 -i 'INFO/CLNSIG~"athogenic" && INFO/CLNSIG!~"onflicting"' clinvar.chr.vcf.gz -H | wc -l

# 5. plant one ClinVar variant (practice): concat + sort
bcftools view -r chr2:165980000-166140000 clinvar.chr.vcf.gz -H | head -1   # inspect; build a 1-line VCF by hand
# bcftools concat -a practice_scn1a.vcf.gz planted.vcf.gz | bcftools sort

# 6. HPO: terms for Dravet (OMIM:607208)
awk -F'\t' '$1=="OMIM:607208" && $11=="P"' phenotype.hpoa | cut -f4,7 | head
```
