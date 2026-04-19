# STING-db Interaction Data

* Download from: https://string-db.org/cgi/download.pl

## Summary - Input

### Interaction Data

File | Description
-----|------------
9606.protein.physical.links.detailed.v12.0.txt.gz | protein network data (physical subnetwork, incl. subscores per channel)

### Accessory Data

File | Description
-----|------------
9606.protein.aliases.v12.0.txt.gz | aliases for STRING proteins: locus names, accessions, descriptions...

## Summary - Output

File | Description
-----|------------
9606-protein-gene-mapping-v12-0.csv | Table mapping protein_id to gene_entrez_id and gene_symbol
9606-protein-physical-links-detailed-with-genes-v12-0.csv | Table of Physical Interaction Detailed plus gene information

## Details - Input

### Interaction Data

#### 9606.protein.physical.links.detailed.v12.0.txt.gz

```
protein1 protein2 experimental database textmining combined_score
9606.ENSP00000000233 9606.ENSP00000257770 312 0 0 311
9606.ENSP00000000233 9606.ENSP00000226004 162 0 0 161
9606.ENSP00000000233 9606.ENSP00000434442 0 500 0 499
```

### Accessory Data

#### 9606.protein.aliases.v12.0.txt.gz

```
#string_protein_id	alias	source
9606.ENSP00000000233	2B6H	Ensembl_PDB
9606.ENSP00000000233	2B6H	UniProt_DR_PDB
9606.ENSP00000000233	381	Ensembl_HGNC_entrez_id
```

## Details - Output

#### 9606-protein-gene-mapping-v12-0.csv

```csv
protein_id,gene_entrez_id,gene_symbol
9606.ENSP00000000233,381,ARF5
9606.ENSP00000000412,4074,M6PR
9606.ENSP00000001008,2288,FKBP4
```

#### 9606-protein-physical-links-detailed-with-genes-v12-0.csv

```csv
protein1,protein2,gene1_id,gene1_symbol,gene2_id,gene2_symbol,experimental,database,textmining,combined_score
9606.ENSP00000000233,9606.ENSP00000257770,381,ARF5,4907,NT5E,312,0,0,311
9606.ENSP00000000233,9606.ENSP00000226004,381,ARF5,1845,DUSP3,162,0,0,161
9606.ENSP00000000233,9606.ENSP00000434442,381,ARF5,84364,ARFGAP2,0,500,0,499
```
