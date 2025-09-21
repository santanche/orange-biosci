# Orange Widget for GEO SOFT Expression Data Extraction

import os
from collections import defaultdict
import numpy as np
from pkg_resources import resource_filename

from AnyQt.QtWidgets import QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QFileDialog, QTextEdit, QListWidget, QSplitter
from AnyQt.QtCore import Qt

from Orange.widgets.widget import OWWidget, Input, Output
from Orange.widgets.settings import Setting
from Orange.widgets import gui
from Orange.data import Table, Domain, ContinuousVariable, StringVariable, DiscreteVariable
from Orange.widgets.utils.widgetpreview import WidgetPreview

class OWGeoSoftExtractor(OWWidget):
    name = "GEO SOFT Extractor"
    description = "Extract gene expression data from GEO SOFT files by sample substring"
    icon = resource_filename(__name__, "../icons/soft-extractor-icon.svg")
    priority = 100
    keywords = ["GEO", "SOFT", "gene", "expression", "extract"]

    # Widget settings
    soft_file_path = Setting("")
    sample_substring = Setting("Basal")
    table_name = Setting("GEO Expression Data")
    transform_log2 = Setting(False)
    
    # Outputs
    class Outputs:
        data = Output("Data", Table)

    def __init__(self):
        super().__init__()
        
        # GUI
        self.setup_gui()
        
        # Internal variables
        self.expression_data = None
        self.all_sample_titles = []
        self.platform_data = {}  # Store platform annotation data

    def setup_gui(self):
        # Main layout with splitter
        splitter = QSplitter(Qt.Horizontal)
        self.controlArea.layout().addWidget(splitter)
        
        # Left panel - controls
        left_panel = gui.widgetBox(None, "Parameters")
        splitter.addWidget(left_panel)
        
        # File selection
        file_box = gui.widgetBox(left_panel, "SOFT File")
        self.file_edit = QLineEdit()
        self.file_edit.setText(self.soft_file_path)
        self.file_edit.textChanged.connect(self.on_file_changed)
        
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_edit)
        
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(browse_button)
        
        file_widget = gui.widgetBox(file_box)
        file_widget.layout().addLayout(file_layout)
        
        # Load samples button
        self.load_samples_button = QPushButton("Load Sample Titles")
        self.load_samples_button.clicked.connect(self.load_sample_titles)
        file_box.layout().addWidget(self.load_samples_button)
        
        # Sample substring input
        gui.lineEdit(left_panel, self, "sample_substring", "Sample Substring:", 
                    callback=self.on_substring_changed)
        
        # Table name input
        gui.lineEdit(left_panel, self, "table_name", "Output Table Name:")
        
        # Log2 transform checkbox
        gui.checkBox(left_panel, self, "transform_log2", "Transform log2 to actual values",
                    callback=self.on_transform_changed)
        
        # Extract button
        self.extract_button = QPushButton("Extract Expression Data")
        self.extract_button.clicked.connect(self.extract_data)
        self.extract_button.setEnabled(False)
        left_panel.layout().addWidget(self.extract_button)
        
        # Status/log area
        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(120)
        self.log_area.setReadOnly(True)
        gui.widgetBox(left_panel, "Log").layout().addWidget(self.log_area)
        
        # Right panel - sample list
        right_panel = gui.widgetBox(None, "Available Sample Titles")
        splitter.addWidget(right_panel)
        
        # Sample list widget
        self.sample_list = QListWidget()
        self.sample_list.itemDoubleClicked.connect(self.on_sample_double_clicked)
        right_panel.layout().addWidget(self.sample_list)
        
        # Add a label for instructions
        instruction_label = QLabel("Double-click a sample to use as substring filter")
        instruction_label.setWordWrap(True)
        instruction_label.setStyleSheet("color: gray; font-size: 10px;")
        right_panel.layout().addWidget(instruction_label)
        
        # Set splitter proportions
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select SOFT File", "", "SOFT Files (*.soft);;All Files (*)"
        )
        if file_path:
            self.soft_file_path = file_path
            self.file_edit.setText(file_path)

    def on_file_changed(self):
        self.soft_file_path = self.file_edit.text()

    def on_sample_double_clicked(self, item):
        """Handle double-click on sample list item"""
        sample_text = item.text()
        # Extract a meaningful substring from the sample title
        # You can modify this logic to extract different parts
        words = sample_text.split()
        if len(words) > 0:
            # Use the first meaningful word (skip common prefixes)
            for word in words:
                if len(word) > 3 and word.lower() not in ['sample', 'gsm', 'title']:
                    self.sample_substring = word
                    break
            else:
                # If no good word found, use first word
                self.sample_substring = words[0]
        
        self.log_message(f"Selected substring: '{self.sample_substring}' from sample: {sample_text}")

    def load_sample_titles(self):
        """Load and display all sample titles from the SOFT file"""
        if not self.soft_file_path or not os.path.exists(self.soft_file_path):
            self.log_message("Please select a valid SOFT file first")
            return
        
        self.log_message("Loading sample titles...")
        self.sample_list.clear()
        self.all_sample_titles = []
        
        try:
            sample_titles = self.get_all_sample_titles(self.soft_file_path)
            self.all_sample_titles = sample_titles
            
            # Populate the list widget
            for sample_id, title in sample_titles:
                display_text = f"{sample_id}: {title}"
                self.sample_list.addItem(display_text)
            
            self.log_message(f"Loaded {len(sample_titles)} sample titles")
            self.extract_button.setEnabled(True)
            
        except Exception as e:
            self.log_message(f"Error loading sample titles: {str(e)}")

    def get_all_sample_titles(self, filename):
        """Extract all sample titles from SOFT file"""
        sample_titles = []
        current_sample = None
        
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                
                # Check for sample start
                if line.startswith('^SAMPLE'):
                    current_sample = line.split('=')[1].strip() if '=' in line else None
                    
                # Get sample title/description
                elif current_sample and line.startswith('!Sample_title'):
                    title = line.split('=')[1].strip() if '=' in line else ""
                    sample_titles.append((current_sample, title))
                    current_sample = None  # Reset to avoid duplicates
        
        return sample_titles

    def on_substring_changed(self):
        pass  # Settings are automatically saved

    def on_table_name_changed(self):
        pass  # Settings are automatically saved

    def on_transform_changed(self):
        pass  # Settings are automatically saved

    def parse_sample_characteristics(self, characteristics_list):
        """Parse sample characteristics into label-value pairs"""
        parsed_chars = {}
        class_chars = ''
        
        for char_line in characteristics_list:
            # Each characteristic is typically in format "label: value"
            if ':' in char_line:
                parts = char_line.split(':', 1)  # Split only on first colon
                if len(parts) == 2:
                    label = parts[0].strip()
                    value = parts[1].strip()
                    # Clean up common label variations
                    label = label.replace(' ', '_').lower()
                    parsed_chars[label] = value
                    class_chars += value + ('|' if len(class_chars) > 0 else '')
            else:
                # If no colon, treat the whole thing as a characteristic
                # Use a generic label with index
                generic_label = f"characteristic_{len(parsed_chars)}"
                parsed_chars[generic_label] = char_line.strip()

        parsed_chars['class'] = class_chars

        return parsed_chars

    def log_message(self, message):
        self.log_area.append(message)
        self.log_area.repaint()

    def parse_platform_data(self, filename):
        """Extract platform annotation data from SOFT file"""
        platform_data = {}
        current_platform = None
        in_platform_table = False
        in_table_header = False
        header_indices = {}
        
        try:
            with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    
                    # Check for platform start
                    if line.startswith('^PLATFORM'):
                        current_platform = line.split('=')[1].strip() if '=' in line else None
                        in_platform_table = False
                        in_table_header = False
                        header_indices = {}
                        self.log_message(f"Found platform: {current_platform}")
                        
                    # Check for platform table start
                    elif current_platform and line.startswith('!platform_table_begin'):
                        in_platform_table = True
                        in_table_header = True
                        self.log_message("Started parsing platform table")
                        continue
                        
                    # Check for platform table end
                    elif line.startswith('!platform_table_end'):
                        in_platform_table = False
                        self.log_message("Finished parsing platform table")
                        
                    # Parse platform table header
                    elif in_platform_table and current_platform and in_table_header:
                        # headers = line[1:].split('\t')  # Remove # and split
                        headers = line.split('\t')
                        in_table_header = False
                        for idx, header in enumerate(headers):
                            header_indices[header.strip().lower()] = idx
                        self.log_message(f"Platform headers: {list(header_indices.keys())}")
                        
                    # Parse platform table data
                    elif in_platform_table and current_platform and line and not line.startswith('!') and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) > 0:
                            probe_id = parts[0].strip()
                            entrez_id = None
                            
                            # Look for Entrez ID in different possible columns (expanded search)
                            possible_fields = ['gene', 'geneid', 'entrez_gene_id', 'gene_id', 'ncbi_gene_id', 'gene_assignment']
                            
                            for field_name in possible_fields:
                                if field_name in header_indices:
                                    col_idx = header_indices[field_name]
                                    if col_idx < len(parts) and parts[col_idx].strip():
                                        value = parts[col_idx].strip()
                                        
                                        if field_name == 'gene_assignment':
                                            # For gene_assignment, look for Entrez ID in the assignment string
                                            # Format is often: Symbol // Description // Chromosome // Map Location // Entrez ID // ...
                                            assignment_parts = value.split('//')
                                            for i, part in enumerate(assignment_parts):
                                                part = part.strip()
                                                # Check if this part looks like an Entrez ID (numeric)
                                                if part and part.isdigit() and len(part) > 2:
                                                    entrez_id = part
                                                    break
                                            if entrez_id:
                                                break
                                        else:
                                            # For other fields, try to extract numeric Entrez ID
                                            # Handle multiple values separated by /// or ///
                                            if '///' in value:
                                                candidates = value.split('///')
                                            elif '//' in value:
                                                candidates = value.split('//')
                                            else:
                                                candidates = [value]
                                            
                                            for candidate in candidates:
                                                candidate = candidate.strip()
                                                # Try to extract just the numeric part
                                                if candidate.isdigit() and len(candidate) > 2:
                                                    entrez_id = candidate
                                                    break
                                                # Sometimes it's in format like "EntrezGene:12345"
                                                elif ':' in candidate:
                                                    parts_colon = candidate.split(':')
                                                    if len(parts_colon) > 1 and parts_colon[1].strip().isdigit():
                                                        entrez_id = parts_colon[1].strip()
                                                        break
                                            
                                            if entrez_id:
                                                break
                            
                            if entrez_id:
                                platform_data[probe_id] = entrez_id
                                
        except Exception as e:
            self.log_message(f"Error parsing platform data: {str(e)}")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}")
        
        return platform_data

    def parse_soft_file_directly(self, filename, substring):
        """Parse SOFT file directly to extract sample info and expression data"""
        matching_samples = {}
        sample_characteristics = {}
        current_sample = None
        current_sample_title = None
        in_sample_table = False
        sample_data = defaultdict(dict)
        
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    
                    # Check for sample start
                    if line.startswith('^SAMPLE'):
                        current_sample = line.split('=')[1].strip() if '=' in line else None
                        current_sample_title = None
                        in_sample_table = False
                        
                    # Get sample title/description
                    elif current_sample and line.startswith('!Sample_title'):
                        title = line.split('=')[1].strip() if '=' in line else ""
                        if substring.lower() in title.lower():
                            current_sample_title = title
                            self.log_message(f"Found matching sample: {current_sample} - {title}")
                            
                    # Get sample characteristics
                    elif current_sample and current_sample_title and line.startswith('!Sample_characteristics_ch1'):
                        characteristics = line.split('=')[1].strip() if '=' in line else ""
                        if current_sample not in sample_characteristics:
                            sample_characteristics[current_sample] = []
                        sample_characteristics[current_sample].append(characteristics)
                        
                    # Check for table start
                    elif current_sample and current_sample_title and line.startswith('!sample_table_begin'):
                        in_sample_table = True
                        continue
                        
                    # Check for table end
                    elif line.startswith('!sample_table_end'):
                        in_sample_table = False
                        if current_sample and current_sample_title:
                            # Store the sample data
                            matching_samples[f"{current_sample}"] = dict(sample_data[current_sample])
                        
                    # Parse table data
                    elif in_sample_table and current_sample and current_sample_title:
                        if line and not line.startswith('!') and not line.startswith('#'):
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                gene_id = parts[0]
                                try:
                                    expression_value = float(parts[1])
                                    sample_data[current_sample][gene_id] = expression_value
                                except (ValueError, IndexError):
                                    continue
        except Exception as e:
            self.log_message(f"Error parsing file: {str(e)}")
            return {}, {}
        
        return matching_samples, sample_characteristics

    def extract_data(self):
        if not self.soft_file_path or not os.path.exists(self.soft_file_path):
            self.log_message("Please select a valid SOFT file")
            return
            
        if not self.sample_substring.strip():
            self.log_message("Please enter a sample substring")
            return

        # Clear previous results
        self.log_area.clear()
        self.log_message(f"Parsing SOFT file for samples containing '{self.sample_substring}'...")
        
        # First, parse platform data for Entrez IDs
        self.log_message("Parsing platform annotation data...")
        self.platform_data = self.parse_platform_data(self.soft_file_path)
        self.log_message(f"Found Entrez IDs for {len(self.platform_data)} probes")
        
        # Highlight matching samples in the list
        self.highlight_matching_samples()
        
        # Parse the file
        expression_data, sample_characteristics = self.parse_soft_file_directly(self.soft_file_path, self.sample_substring)
        
        if not expression_data:
            self.log_message(f"No samples found containing substring '{self.sample_substring}'")
            self.Outputs.data.send(None)
            return
        
        self.log_message(f"Found {len(expression_data)} matching samples")
        
        # Get all unique gene IDs
        all_genes = set()
        for sample_data in expression_data.values():
            all_genes.update(sample_data.keys())
        all_genes = sorted(list(all_genes))
        
        self.log_message(f"Found {len(all_genes)} genes")
        
        if not all_genes:
            self.log_message("No gene expression data found")
            self.Outputs.data.send(None)
            return
        
        # Create Orange Table
        self.create_orange_table(expression_data, all_genes, sample_characteristics)

    def highlight_matching_samples(self):
        """Highlight samples in the list that match the current substring"""
        if not self.sample_substring.strip():
            return
            
        substring_lower = self.sample_substring.lower()
        
        for i in range(self.sample_list.count()):
            item = self.sample_list.item(i)
            if substring_lower in item.text().lower():
                item.setBackground(item.listWidget().palette().highlight())
                item.setForeground(item.listWidget().palette().highlightedText())
            else:
                item.setBackground(item.listWidget().palette().base())
                item.setForeground(item.listWidget().palette().text())

    def create_orange_table(self, expression_data, all_genes, sample_characteristics):
        """Convert expression data to Orange Table format"""
        
        # Create domain
        # Each sample becomes a feature (column)
        sample_names = list(expression_data.keys())
        
        # Create continuous variables for each sample with parsed characteristics as separate attributes
        attributes = []
        for sample_name in sample_names:
            var = ContinuousVariable(sample_name)
            
            # Parse sample characteristics into individual label-value pairs
            if sample_name in sample_characteristics:
                characteristics_list = sample_characteristics[sample_name]
                parsed_chars = self.parse_sample_characteristics(characteristics_list)
                
                # Set each characteristic as a separate variable attribute
                if parsed_chars:
                    var.attributes = parsed_chars
                    self.log_message(f"Sample {sample_name} characteristics: {list(parsed_chars.keys())}")
            
            attributes.append(var)
        
        # Gene ID as "genes" and Entrez ID as meta attributes
        metas = [StringVariable("genes"), StringVariable("Entrez ID")]
        
        domain = Domain(attributes, metas=metas)
        
        # Create data matrix
        # Rows = genes, Columns = samples
        n_genes = len(all_genes)
        n_samples = len(sample_names)
        
        X = np.full((n_genes, n_samples), np.nan)
        
        # Fill expression values
        for sample_idx, sample_name in enumerate(sample_names):
            sample_data = expression_data[sample_name]
            for gene_idx, gene_id in enumerate(all_genes):
                if gene_id in sample_data:
                    value = sample_data[gene_id]
                    # Apply log2 transformation if requested
                    if self.transform_log2:
                        try:
                            # Transform from log2 to actual value: 2^x
                            value = 2 ** value
                        except (OverflowError, ValueError):
                            # Handle potential overflow or invalid values
                            value = np.nan
                    X[gene_idx, sample_idx] = value
        
        # Create meta data (gene IDs and Entrez IDs)
        gene_ids = np.array(all_genes).reshape(-1, 1)
        entrez_ids = []
        
        for gene_id in all_genes:
            entrez_id = self.platform_data.get(gene_id, "")
            entrez_ids.append(entrez_id)
        
        entrez_ids = np.array(entrez_ids).reshape(-1, 1)
        metas_data = np.hstack([gene_ids, entrez_ids])
        
        # Create Orange Table
        table = Table.from_numpy(domain, X, metas=metas_data)
        
        # Set the table name
        if self.table_name.strip():
            table.name = self.table_name.strip()
        else:
            table.name = "GEO Expression Data"
        
        self.log_message(f"Created Orange Table '{table.name}': {n_genes} genes x {n_samples} samples")
        self.log_message(f"Non-missing values: {np.count_nonzero(~np.isnan(X))}")
        entrez_count = np.count_nonzero([e for e in entrez_ids.flatten() if e])
        self.log_message(f"Genes with Entrez IDs: {entrez_count}")
        if self.transform_log2:
            self.log_message("Applied log2 to actual value transformation (2^x)")
        
        # Send the table to output
        self.Outputs.data.send(table)


# For testing the widget
if __name__ == "__main__":
    WidgetPreview(OWGeoSoftExtractor).run()
