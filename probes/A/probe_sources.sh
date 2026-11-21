#!/bin/bash
# Probe every public data source GeneSleuth depends on; timings + outputs go to probes/A/outputs/.
# Run inside WSL:  wsl -d Ubuntu-22.04 -- bash probes/A/probe_sources.sh
OUT=/mnt/c/Users/muham/Hackathon/gemini4_a1/probes/A/outputs
SCR=/tmp/a1_probe; mkdir -p $SCR; cd $SCR
export PATH=$HOME/bio/bin:$PATH
U=https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV
G=https://storage.googleapis.com/gcp-public-data--gnomad/release/4.1/vcf/genomes
MANE=https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current
CV=https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38
T() { local s=$(date +%s.%N); "$@"; local rc=$?; local e=$(date +%s.%N); echo "[timing] $(echo "$e - $s" | bc) s rc=$rc :: $*" >&2; return $rc; }
exec 2> >(tee $OUT/probe_timings.log >&2)

echo "== HEAD checks" > $OUT/head_checks.txt
for url in $MANE/MANE.GRCh38.v1.5.summary.txt.gz $MANE/MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz \
  $U/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz.tbi \
  $G/gnomad.genomes.v4.1.sites.chr2.vcf.bgz.tbi $CV/clinvar.vcf.gz $CV/clinvar.vcf.gz.tbi \
  https://panelapp.genomicsengland.co.uk/api/v1/panels/402/ \
  https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa ; do
  echo "--- $url" >> $OUT/head_checks.txt
  curl -sIL --max-time 30 "$url" | grep -iE '^(HTTP|content-length|last-modified)' >> $OUT/head_checks.txt
done

T curl -s --max-time 60 $MANE/MANE.GRCh38.v1.5.summary.txt.gz -o mane_summary.txt.gz
zcat mane_summary.txt.gz | head -3 > $OUT/mane_summary_head.txt
zcat mane_summary.txt.gz | grep -wE "SCN1A|DNM1" | cut -f1-12 >> $OUT/mane_summary_head.txt
T curl -s --max-time 120 $MANE/MANE.GRCh38.v1.5.ensembl_genomic.gtf.gz -o mane.gtf.gz
zcat mane.gtf.gz | head -8 > $OUT/mane_gtf_head.txt
zcat mane.gtf.gz | awk -F'\t' '$3!="gene"{c[$3]++} END{for(k in c) print k, c[k]}' > $OUT/mane_gtf_feature_counts.txt

echo "== 1000G sample check"
T bcftools query -l $U/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz > samples.txt
wc -l < samples.txt > $OUT/1kg_nsamples.txt; grep -E "NA12878|HG00096" samples.txt > $OUT/1kg_sample_present.txt
echo "== 1000G SCN1A stream"
T bcftools view -s NA12878 -r chr2:165980000-166140000 $U/1kGP_high_coverage_Illumina.chr2.filtered.SNV_INDEL_SV_phased_panel.vcf.gz | bcftools view -i 'GT="alt"' -Oz -o scn1a.vcf.gz
tabix -p vcf scn1a.vcf.gz
bcftools view -H scn1a.vcf.gz | wc -l > $OUT/1kg_scn1a_nonref_count.txt
bcftools view -h scn1a.vcf.gz | grep -E "^##INFO|^##FILTER|^#CHROM" | head -40 > $OUT/1kg_header_info.txt
bcftools view -H scn1a.vcf.gz | head -5 | cut -c1-400 > $OUT/1kg_scn1a_records_head.txt
bcftools query -f '%FILTER\n' scn1a.vcf.gz | sort | uniq -c > $OUT/1kg_scn1a_filter_counts.txt

echo "== gnomAD streaming at the sample's own positions (-R)"
bcftools query -f '%CHROM\t%POS\n' scn1a.vcf.gz > pos.tsv
T bcftools view -R pos.tsv -G $G/gnomad.genomes.v4.1.sites.chr2.vcf.bgz | bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\t%AF\t%AF_grpmax\t%AN\n' > gnomad_scn1a_at_positions.tsv
wc -l < gnomad_scn1a_at_positions.tsv > $OUT/gnomad_R_count.txt; head -5 gnomad_scn1a_at_positions.tsv > $OUT/gnomad_R_head.txt
echo "== gnomAD full-region stream (rehearsal cmd 2, region only)"
T bcftools view -r chr2:165980000-166140000 $G/gnomad.genomes.v4.1.sites.chr2.vcf.bgz | bcftools annotate -x '^INFO/AF,INFO/AF_grpmax,INFO/AN' -Oz -o gnomad_scn1a_region.vcf.gz
bcftools view -H gnomad_scn1a_region.vcf.gz | wc -l > $OUT/gnomad_region_count.txt

echo "== ClinVar remote region"
T bcftools view -r 2:165980000-166140000 -i 'INFO/CLNSIG~"athogenic" && INFO/CLNSIG!~"onflicting"' $CV/clinvar.vcf.gz -H > clinvar_scn1a.txt
wc -l < clinvar_scn1a.txt > $OUT/clinvar_remote_count.txt; head -2 clinvar_scn1a.txt | cut -c1-600 > $OUT/clinvar_remote_head.txt

echo "== VEP REST"
T curl -s --max-time 60 -X POST -H 'Content-Type: application/json' -H 'Accept: application/json' https://rest.ensembl.org/vep/homo_sapiens/region \
  -d '{"variants":["2 165991234 . A G . . .","9 128225994 . G A . . ."]}' > $OUT/vep_rest_response.json
echo "== PanelApp"
T curl -s --max-time 60 https://panelapp.genomicsengland.co.uk/api/v1/panels/402/ -o panelapp402.json
python3 - <<'PY' > $OUT/panelapp_summary.txt
import json
d=json.load(open('/tmp/a1_probe/panelapp402.json'))
print(d.get('name'), d.get('version'), d.get('version_created'))
g=d['genes']; print('genes',len(g),'green',sum(1 for x in g if str(x.get('confidence_level'))=='3'))
print(sorted(x['gene_data']['gene_symbol'] for x in g if str(x.get('confidence_level'))=='3')[:10])
PY
echo DONE > $OUT/probe_done.txt
