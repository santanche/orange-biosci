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

    def log_message(self, message):
        self.log_area.append(message)
        self.log_area.repaint()
        self.log_area.append(message)
        self.log_area.repaint()

    def parse_soft_file_directly(self, filename, substring):
        """Parse SOFT file directly to extract sample info and expression data"""
        matching_samples = {}
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
            return {}
        
        return matching_samples

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
        
        # Highlight matching samples in the list
        self.highlight_matching_samples()
        
        # Parse the file
        expression_data = self.parse_soft_file_directly(self.soft_file_path, self.sample_substring)
        
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
        self.create_orange_table(expression_data, all_genes)

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

    def create_orange_table(self, expression_data, all_genes):
        """Convert expression data to Orange Table format"""
        
        # Create domain
        # Each sample becomes a feature (column)
        sample_names = list(expression_data.keys())
        
        # Create continuous variables for each sample
        attributes = [ContinuousVariable(sample_name) for sample_name in sample_names]
        
        # Gene ID as meta attribute
        metas = [StringVariable("Gene_ID")]
        
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
                    X[gene_idx, sample_idx] = sample_data[gene_id]
        
        # Create meta data (gene IDs)
        gene_ids = np.array(all_genes).reshape(-1, 1)
        
        # Create Orange Table
        table = Table.from_numpy(domain, X, metas=gene_ids)
        
        self.log_message(f"Created Orange Table: {n_genes} genes x {n_samples} samples")
        self.log_message(f"Non-missing values: {np.count_nonzero(~np.isnan(X))}")
        
        # Send the table to output
        self.Outputs.data.send(table)


# For testing the widget
if __name__ == "__main__":
    WidgetPreview(OWGeoSoftExtractor).run()
