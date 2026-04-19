#!/usr/bin/env python3
"""
Script to filter protein-gene-link CSV based on selected genes.
Usage: python filter_protein_links.py <selected_genes_file> [output_file]
"""

import csv
import sys
import os
from pathlib import Path

def read_selected_genes(selected_genes_file):
    """
    Read the selected genes CSV file and return a set of gene IDs.
    Assumes the file has one column with gene IDs (no header).
    """
    selected_genes = set()
    
    try:
        with open(selected_genes_file, 'r') as f:
            # Try to detect if there's a header
            first_line = f.readline().strip()
            f.seek(0)
            
            reader = csv.reader(f)
            
            # Check if first row might be a header (if it contains 'gene' or similar text)
            first_row = next(reader)
            if first_row and (first_row[0].lower() == 'gene' or 
                             first_row[0].lower() == 'gene_id' or
                             first_row[0].lower() == 'geneid'):
                # Skip header
                for row in reader:
                    if row and row[0].strip():
                        selected_genes.add(row[0].strip())
            else:
                # No header, process all rows
                selected_genes.add(first_row[0].strip())
                for row in reader:
                    if row and row[0].strip():
                        selected_genes.add(row[0].strip())
    
    except FileNotFoundError:
        print(f"Error: File '{selected_genes_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading '{selected_genes_file}': {e}")
        sys.exit(1)
    
    return selected_genes

def filter_protein_links(protein_links_file, selected_genes, output_file):
    """
    Filter the protein-gene-link CSV file to keep only records where
    gene1 or gene2 is in selected_genes set.
    """
    if not os.path.exists(protein_links_file):
        print(f"Error: Protein links file '{protein_links_file}' not found.")
        sys.exit(1)
    
    filtered_count = 0
    total_count = 0
    
    try:
        with open(protein_links_file, 'r') as infile, \
             open(output_file, 'w', newline='') as outfile:
            
            reader = csv.DictReader(infile)
            
            # Write header to output file
            writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            for row in reader:
                total_count += 1
                gene1 = row.get('gene1', '').strip()
                gene2 = row.get('gene2', '').strip()
                
                # Check if either gene is in the selected set
                if gene1 in selected_genes or gene2 in selected_genes:
                    writer.writerow(row)
                    filtered_count += 1
        
        print(f"\nProcessing complete!")
        print(f"Total records processed: {total_count}")
        print(f"Records matching selected genes: {filtered_count}")
        print(f"Output saved to: {output_file}")
        
    except Exception as e:
        print(f"Error processing files: {e}")
        sys.exit(1)

def main():
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python filter_protein_links.py <selected_genes_file> [output_file]")
        print("\nArguments:")
        print("  selected_genes_file: CSV file with one column containing gene IDs")
        print("  output_file: (optional) Output CSV file name")
        print("\nExample:")
        print("  python filter_protein_links.py selected_genes.csv")
        print("  python filter_protein_links.py selected_genes.csv filtered_links.csv")
        sys.exit(1)
    
    selected_genes_file = sys.argv[1]
    
    # Set default output filename if not provided
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        # Generate default output filename
        input_path = Path(selected_genes_file)
        output_file = f"{input_path.stem}_filtered_links.csv"
    
    # Default protein links file name
    protein_links_file = "9006-protein-physical-links-detailed-with-genes-v12-0.csv"
    
    # Check if protein links file exists in current directory
    if not os.path.exists(protein_links_file):
        print(f"Warning: '{protein_links_file}' not found in current directory.")
        protein_links_file = input(f"Please enter the path to the protein-gene-link CSV file: ").strip()
        
        if not os.path.exists(protein_links_file):
            print(f"Error: File '{protein_links_file}' not found.")
            sys.exit(1)
    
    print(f"Reading selected genes from: {selected_genes_file}")
    selected_genes = read_selected_genes(selected_genes_file)
    print(f"Loaded {len(selected_genes)} unique gene IDs")
    print(f"Sample genes: {list(selected_genes)[:5]}...")
    
    print(f"\nFiltering protein links from: {protein_links_file}")
    filter_protein_links(protein_links_file, selected_genes, output_file)

if __name__ == "__main__":
    main()
