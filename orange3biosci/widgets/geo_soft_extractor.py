# Orange Widget for GEO SOFT Expression Data Extraction

import os
import gzip
from collections import defaultdict
import numpy as np
from pkg_resources import resource_filename
import urllib.request
import tempfile

from AnyQt.QtWidgets import QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QFileDialog, QTextEdit, QListWidget, QSplitter, QAbstractItemView, QProgressBar, QListWidgetItem
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
    relative_to_workflow = Setting(False)
    
    # Table attributes settings
    taxonomy_id_setting = Setting("9606")
    gene_as_attribute_name = Setting(False)
    gene_id_column = Setting(0)
    
    # Outputs
    class Outputs:
        data = Output("Data", Table)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        
        # GUI
        self.setup_gui()
        
        # Internal variables
        self.expression_data = None
        self.all_sample_titles = []
        self.all_sample_characteristics_dict = {}
        self.gene_info = {}  # Store combined gene information (Entrez ID and Gene Symbol)

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
        
        # Relative to workflow checkbox
        gui.checkBox(file_box, self, "relative_to_workflow", "Relative to Workflow File",
                    callback=self.on_relative_path_changed)
        
        # Load samples button
        self.load_samples_button = QPushButton("Load Sample Titles")
        self.load_samples_button.clicked.connect(self.load_sample_titles)
        file_box.layout().addWidget(self.load_samples_button)
        
        # Sample substring input
        substring_box = gui.widgetBox(left_panel, "Sample Filter")
        gui.lineEdit(substring_box, self, "sample_substring", "Sample Substring(s):",
                    tooltip="Enter one or more substrings separated by commas (e.g., 'Basal, Luminal')")
        
        # Add info label
        info_label = QLabel("Tip: Use commas to separate multiple substrings")
        info_label.setStyleSheet("color: gray; font-size: 9px;")
        substring_box.layout().addWidget(info_label)
        
        # Select button to apply selection from list
        self.select_button = QPushButton("Select in List")
        self.select_button.clicked.connect(self.select_from_list)
        self.select_button.setEnabled(False)
        substring_box.layout().addWidget(self.select_button)
        
        # Table name input
        gui.lineEdit(left_panel, self, "table_name", "Output Table Name:")
        
        # Log2 transform checkbox
        gui.checkBox(left_panel, self, "transform_log2", "Transform log2 to actual values")
        
        # Table Metadata box
        metadata_box = gui.widgetBox(left_panel, "Table Metadata")
        self.tax_id_edit = gui.lineEdit(metadata_box, self, "taxonomy_id_setting", "taxonomy_id:")
        gui.checkBox(metadata_box, self, "gene_as_attribute_name", "gene_as_attribute_name")
        self.gene_id_combo = gui.comboBox(metadata_box, self, "gene_id_column", label="gene_id_column:", items=["genes", "Gene Symbol", "Entrez ID"], sendSelectedValue=False)
        
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
        
        # Progress bar
        progress_box = gui.widgetBox(left_panel, "Progress")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_box.layout().addWidget(self.progress_bar)
        
        # Right vertical splitter
        right_splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(right_splitter)
        
        # Right panel - sample list
        right_panel = gui.widgetBox(None, "Available Sample Titles")
        right_splitter.addWidget(right_panel)
        
        # Sample list widget with multi-selection enabled
        self.sample_list = QListWidget()
        self.sample_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.sample_list.itemDoubleClicked.connect(self.on_sample_double_clicked)
        self.sample_list.itemSelectionChanged.connect(self.on_sample_selection_changed)
        right_panel.layout().addWidget(self.sample_list)
        
        # Add a label for instructions
        instruction_label = QLabel("Double-click a sample to use as substring filter, or use 'Select in List' to preview matches")
        instruction_label.setWordWrap(True)
        instruction_label.setStyleSheet("color: gray; font-size: 10px;")
        right_panel.layout().addWidget(instruction_label)
        
        # Available Characteristics panel
        char_panel = gui.widgetBox(None, "Selected Characteristics for Columns")
        right_splitter.addWidget(char_panel)
        
        self.characteristics_list = QListWidget()
        char_panel.layout().addWidget(self.characteristics_list)
        
        char_instruction = QLabel("Select characteristics to include as attributes in the extracted table.")
        char_instruction.setWordWrap(True)
        char_instruction.setStyleSheet("color: gray; font-size: 10px;")
        char_panel.layout().addWidget(char_instruction)
        
        # Set splitter proportions
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select SOFT File", "", "SOFT Files (*.soft *.soft.gz);;All Files (*)"
        )
        if file_path:
            # Store as relative path if checkbox is checked
            if self.relative_to_workflow:
                file_path = self.make_relative_path(file_path)
            self.soft_file_path = file_path
            self.file_edit.setText(file_path)

    def make_relative_path(self, file_path):
        """Convert absolute path to relative path if possible"""
        try:
            # Get workflow directory if available
            workflow_dir = self.workflowEnv().get("basedir", None) if hasattr(self, 'workflowEnv') else None
            
            if workflow_dir and os.path.isabs(file_path):
                # Try to make path relative to workflow directory
                try:
                    rel_path = os.path.relpath(file_path, workflow_dir)
                    # Only use relative path if it doesn't go above workflow directory
                    if not rel_path.startswith('..'):
                        return rel_path
                except ValueError:
                    # On Windows, relpath fails if paths are on different drives
                    pass
            return file_path
        except Exception:
            return file_path
    
    def get_absolute_path(self, file_path):
        """Convert relative path to absolute path if needed, or handle URL"""
        # Check if it's a URL
        if file_path.startswith('http://') or file_path.startswith('https://') or file_path.startswith('ftp://'):
            return file_path
        
        if not os.path.isabs(file_path):
            try:
                # Get workflow directory if available
                workflow_dir = self.workflowEnv().get("basedir", None) if hasattr(self, 'workflowEnv') else None
                if workflow_dir:
                    return os.path.join(workflow_dir, file_path)
            except Exception:
                pass
        return file_path

    def on_file_changed(self):
        self.soft_file_path = self.file_edit.text()
        
    def on_relative_path_changed(self):
        """Handle change in relative path checkbox"""
        if self.soft_file_path:
            if self.relative_to_workflow:
                # Convert to relative if possible
                self.soft_file_path = self.make_relative_path(self.soft_file_path)
            else:
                # Convert to absolute
                self.soft_file_path = self.get_absolute_path(self.soft_file_path)
            self.file_edit.setText(self.soft_file_path)

    def on_sample_double_clicked(self, item):
        """Handle double-click on sample list item"""
        sample_text = item.text()
        # Extract substring from the new format: "Title (GSMxxxxxx)"
        # Remove the accession in parentheses to get the title
        if '(' in sample_text:
            title = sample_text.split('(')[0].strip()
        else:
            title = sample_text
            
        words = title.split()
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

    def on_sample_selection_changed(self):
        """Update characteristics list based on currently selected samples"""
        selected_sample_ids = []
        for item in self.sample_list.selectedItems():
            item_text = item.text()
            if '(' in item_text and item_text.endswith(')'):
                sample_id = item_text.split('(')[-1][:-1]
                selected_sample_ids.append(sample_id)
        
        self.update_characteristics_list(selected_sample_ids)

    def update_characteristics_list(self, selected_sample_ids):
        """Update the characteristics checklist to only show characteristics that have values in the given samples"""
        if not hasattr(self, 'all_sample_characteristics_dict') or not self.all_sample_characteristics_dict:
            return
            
        self.characteristics_list.clear()
        
        if not selected_sample_ids:
            return
            
        valid_characteristics = set()
        
        # Filter by only selected samples
        for sample in selected_sample_ids:
            if sample in self.all_sample_characteristics_dict:
                parsed_chars = self.all_sample_characteristics_dict[sample]
                for k, v in parsed_chars.items():
                    if k != 'class' and v and v.strip():
                        valid_characteristics.add(k)
                        
        for char_label in sorted(list(valid_characteristics)):
            item = QListWidgetItem(char_label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.characteristics_list.addItem(item)

    def parse_substrings(self, substring_input):
        """Parse comma-separated substrings and return a list"""
        if not substring_input or not substring_input.strip():
            return []
        
        # Split by comma and strip whitespace from each substring
        substrings = [s.strip() for s in substring_input.split(',')]
        # Filter out empty strings
        substrings = [s for s in substrings if s]
        
        return substrings
    
    def select_from_list(self):
        """Highlight samples in the list that match any of the current substrings"""
        substrings = self.parse_substrings(self.sample_substring)
        
        if not substrings:
            self.log_message("Please enter one or more sample substrings first")
            return
        
        self.sample_list.blockSignals(True)
        # Clear any previous selections
        self.sample_list.clearSelection()
        
        # Select all items matching any of the substrings
        matching_count = 0
        
        for i in range(self.sample_list.count()):
            item = self.sample_list.item(i)
            item_text_lower = item.text().lower()
            
            # Check if any substring matches
            for substring in substrings:
                if substring.lower() in item_text_lower:
                    item.setSelected(True)
                    matching_count += 1
                    break  # No need to check other substrings for this item
                    
        self.sample_list.blockSignals(False)
        self.on_sample_selection_changed()
        
        if matching_count > 0:
            if len(substrings) == 1:
                self.log_message(f"Selected {matching_count} samples matching '{substrings[0]}'")
            else:
                substring_list = "', '".join(substrings)
                self.log_message(f"Selected {matching_count} samples matching any of: '{substring_list}'")
        else:
            if len(substrings) == 1:
                self.log_message(f"No samples found containing '{substrings[0]}'")
            else:
                substring_list = "', '".join(substrings)
                self.log_message(f"No samples found containing any of: '{substring_list}'")

    def load_sample_titles(self):
        """Load and display all sample titles from the SOFT file"""
        file_path = self.get_absolute_path(self.soft_file_path)
        if not self.soft_file_path:
            self.log_message("Please select a valid SOFT file first")
            return
        
        # Check if it's a URL or local file
        if not (file_path.startswith('http://') or file_path.startswith('https://') or file_path.startswith('ftp://')):
            if not os.path.exists(file_path):
                self.log_message("Please select a valid SOFT file first")
                return
        
        self.log_message("Loading sample titles...")
        self.sample_list.clear()
        self.all_sample_titles = []
        
        try:
            sample_titles, all_characteristics = self.get_all_sample_titles_and_characteristics(file_path)
            
            # Sort alphabetically by title (not by accession)
            sample_titles.sort(key=lambda x: x[1].lower())
            
            self.all_sample_titles = sample_titles
            
            # Populate the list widget with inverted format: "Title (GSMxxxxxx)"
            for sample_id, title in sample_titles:
                display_text = f"{title} ({sample_id})"
                self.sample_list.addItem(display_text)
                
            # Populate characteristics list
            self.update_characteristics_list([])
            
            self.log_message(f"Loaded {len(sample_titles)} sample titles and {len(all_characteristics)} characteristics")
            self.extract_button.setEnabled(True)
            self.select_button.setEnabled(True)
            
        except Exception as e:
            self.log_message(f"Error loading sample titles: {str(e)}")

    def download_url_to_temp(self, url):
        """Download a URL to a temporary file with progress bar"""
        try:
            self.log_message(f"Downloading file from URL...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # Create a temporary file
            suffix = '.soft.gz' if url.endswith('.gz') else '.soft'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_path = temp_file.name
            temp_file.close()
            
            # Download with progress tracking
            def reporthook(block_num, block_size, total_size):
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(int(downloaded * 100 / total_size), 100)
                    self.progress_bar.setValue(percent)
                    self.progress_bar.repaint()
            
            urllib.request.urlretrieve(url, temp_path, reporthook)
            self.progress_bar.setValue(100)
            self.log_message(f"Download complete")
            self.progress_bar.setVisible(False)
            return temp_path
        except Exception as e:
            self.log_message(f"Error downloading file: {str(e)}")
            self.progress_bar.setVisible(False)
            return None
    
    def open_file(self, filename):
        """Open a file, handling both regular and gzipped files, and URLs"""
        # Check if it's a URL
        if filename.startswith('http://') or filename.startswith('https://') or filename.startswith('ftp://'):
            # Download to temporary file first
            temp_path = self.download_url_to_temp(filename)
            if temp_path is None:
                raise Exception("Failed to download file from URL")
            filename = temp_path
        
        if filename.endswith('.gz'):
            return gzip.open(filename, 'rt', encoding='utf-8', errors='ignore')
        else:
            return open(filename, 'r', encoding='utf-8', errors='ignore')
    
    def get_all_sample_titles_and_characteristics(self, filename):
        """Extract all sample titles and unique characteristic from SOFT file"""
        sample_titles = []
        sample_characteristics_dict = defaultdict(list)
        current_sample = None
        
        with self.open_file(filename) as f:
            for line in f:
                line = line.strip()
                
                # Check for taxonomy ID
                if line.startswith('!Series_platform_taxid') or line.startswith('!Platform_taxid') or line.startswith('!Sample_taxid_ch1'):
                    tax_id = line.split('=')[1].strip() if '=' in line else None
                    if tax_id:
                        self.taxonomy_id_setting = tax_id
                        try:
                            if hasattr(self, 'tax_id_edit'):
                                self.tax_id_edit.setText(tax_id)
                        except Exception:
                            pass
                
                if line.startswith('^SAMPLE'):
                    current_sample = line.split('=')[1].strip() if '=' in line else None
                    
                elif current_sample and line.startswith('!Sample_title'):
                    title = line.split('=')[1].strip() if '=' in line else ""
                    sample_titles.append((current_sample, title))
                    
                elif current_sample and line.startswith('!Sample_characteristics_ch1'):
                    characteristics = line.split('=')[1].strip() if '=' in line else ""
                    sample_characteristics_dict[current_sample].append(characteristics)

                elif current_sample and line.startswith('!sample_table_begin'):
                    current_sample = None # stop collecting for this sample
                    
        # Now parse all characteristics to get unique labels
        valid_characteristics = set()
        self.all_sample_characteristics_dict = {}
        for sample, char_list in sample_characteristics_dict.items():
            parsed_chars = self.parse_sample_characteristics(char_list)
            self.all_sample_characteristics_dict[sample] = parsed_chars
            for k, v in parsed_chars.items():
                if k != 'class' and v and v.strip():
                    valid_characteristics.add(k)
                    
        return sample_titles, sorted(list(valid_characteristics))

    def parse_sample_characteristics(self, characteristics_list):
        """Parse sample characteristics into label-value pairs"""
        parsed_chars = {}
        
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
            else:
                # If no colon, treat the whole thing as a characteristic
                # Use a generic label with index
                generic_label = f"characteristic_{len(parsed_chars)}"
                parsed_chars[generic_label] = char_line.strip()
        
        parsed_chars['class'] = '|'.join([parsed_chars[k] for k in sorted(parsed_chars.keys())])
        
        return parsed_chars

    def log_message(self, message):
        self.log_area.append(message)
        self.log_area.repaint()

    def parse_platform_data(self, filename):
        """Extract platform annotation data from SOFT file - using working approach from original code"""
        platform_data = {}
        current_platform = None
        in_platform_table = False
        in_table_header = False
        header_indices = {}
        
        if not self.table_name.strip():
            self.table_name = "GEO Expression Data"
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        try:
            with self.open_file(filename) as f:
                lines = f.readlines()
                total_lines = len(lines)
                
                for line_idx, line in enumerate(lines):
                    # Update progress every 1000 lines
                    if line_idx % 1000 == 0:
                        progress = int((line_idx / total_lines) * 100)
                        self.progress_bar.setValue(progress)
                        self.progress_bar.repaint()
                    
                    line = line.strip()
                    
                    if line.startswith('^SERIES'):
                        self.table_name = line.split('=')[1].strip() if '=' in line else None
    
                    # Check for platform start
                    if line.startswith('^PLATFORM'):
                        current_platform = line.split('=')[1].strip() if '=' in line else None
                        in_platform_table = False
                        in_table_header = False
                        header_indices = {}
                        self.log_message(f"Found platform: {current_platform}")
                        
                    if line.startswith('!Series_platform_taxid') and not getattr(self, "taxonomy_id_setting", None):
                        self.taxonomy_id_setting = line.split('=')[1].strip() if '=' in line else self.taxonomy_id_setting

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

                            platform_data[probe_id] = {'entrez': '', 'symbol': ''}

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
                                platform_data[probe_id]['entrez'] = entrez_id

                            # Try to find gene symbol in common fields
                            possible_symbol_fields = ['gene symbol', 'gene_symbol', 'symbol', 'gene', 'gene_assignment', 'gene_name', 'geneid', 'gene_id', 'gene_title']
                            gene_symbol = None
                            for symbol_field in possible_symbol_fields:
                                if symbol_field in header_indices:
                                    col_idx = header_indices[symbol_field]
                                    if col_idx < len(parts) and parts[col_idx].strip():
                                        value = parts[col_idx].strip()
                                        # For gene_assignment, symbol is often first part before //
                                        if symbol_field == 'gene_assignment':
                                            assignment_parts = value.split('//')
                                            if assignment_parts:
                                                gene_symbol = assignment_parts[0].strip()
                                        else:
                                            if '///' in value:
                                                candidates = value.split('///')
                                            elif '//' in value:
                                                candidates = value.split('//')
                                            else:
                                                candidates = [value]
                                            gene_symbol = candidates[0].strip()
                                        break
                            # You can store or use gene_symbol as needed
                            if gene_symbol:
                                platform_data[probe_id]['symbol'] = gene_symbol
                
                self.progress_bar.setValue(100)
                                
        except Exception as e:
            self.log_message(f"Error parsing platform data: {str(e)}")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}")
        
        finally:
            self.progress_bar.setVisible(False)

        return platform_data

    def parse_soft_file_directly(self, filename, substring_input):
        """Parse SOFT file directly to extract sample info and expression data (handles .soft and .soft.gz)"""
        # Parse the comma-separated substrings
        substrings = self.parse_substrings(substring_input)
        
        if not substrings:
            return {}, {}

        matching_samples = {}
        sample_characteristics = {}
        current_sample = None
        current_sample_title = None
        in_sample_table = False
        sample_data = defaultdict(dict)
        
        try:
            with self.open_file(filename) as f:
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
                        # Check if any substring matches this title
                        title_lower = title.lower()
                        for substring in substrings:
                            if substring.lower() in title_lower:
                                current_sample_title = title
                                self.log_message(f"Found matching sample: {current_sample} - {title}")
                                break
                            
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
        file_path = self.get_absolute_path(self.soft_file_path)
        if not self.soft_file_path:
            self.log_message("Please select a valid SOFT file")
            return
        
        # Check if it's a URL or local file
        if not (file_path.startswith('http://') or file_path.startswith('https://') or file_path.startswith('ftp://')):
            if not os.path.exists(file_path):
                self.log_message("Please select a valid SOFT file")
                return
            
        substrings = self.parse_substrings(self.sample_substring)
        if not substrings:
            self.log_message("Please enter one or more sample substrings")
            return

        # Clear previous results
        self.log_area.clear()
        
        if len(substrings) == 1:
            self.log_message(f"Parsing SOFT file for samples containing '{substrings[0]}'...")
        else:
            substring_list = "', '".join(substrings)
            self.log_message(f"Parsing SOFT file for samples containing any of: '{substring_list}'...")
        
        # Detect if file is gzipped
        if file_path.endswith('.gz'):
            self.log_message("Detected gzipped file, extracting...")
        
        # First, parse platform data for Entrez IDs and Gene Symbols
        self.log_message("Parsing platform annotation data...")
        self.gene_info = self.parse_platform_data(file_path)

        entrez_count = sum(1 for info in self.gene_info.values() if info['entrez'])
        symbol_count = sum(1 for info in self.gene_info.values() if info['symbol'])
        self.log_message(f"Found Entrez IDs for {entrez_count} probes")
        self.log_message(f"Found Gene Symbols for {symbol_count} probes")
        
        # Highlight matching samples in the list
        self.highlight_matching_samples()
        
        # Parse the file for expression data
        self.log_message("Extracting expression data...")
        expression_data, sample_characteristics = self.parse_soft_file_directly(file_path, self.sample_substring)
        
        if not expression_data:
            if len(substrings) == 1:
                self.log_message(f"No samples found containing substring '{substrings[0]}'")
            else:
                substring_list = "', '".join(substrings)
                self.log_message(f"No samples found containing any of: '{substring_list}'")
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
        
        # Get selected characteristics
        if self.characteristics_list.count() > 0:
            selected_characteristics = []
            for i in range(self.characteristics_list.count()):
                item = self.characteristics_list.item(i)
                if item.checkState() == Qt.Checked:
                    selected_characteristics.append(item.text())
        else:
            selected_characteristics = None
                
        # Create Orange Table
        self.create_orange_table(expression_data, all_genes, sample_characteristics, selected_characteristics)

    def highlight_matching_samples(self):
        """Highlight samples in the list that match any of the current substrings"""
        substrings = self.parse_substrings(self.sample_substring)
        
        if not substrings:
            return
        
        for i in range(self.sample_list.count()):
            item = self.sample_list.item(i)
            item_text_lower = item.text().lower()
            
            # Check if any substring matches
            matches = False
            for substring in substrings:
                if substring.lower() in item_text_lower:
                    matches = True
                    break
            
            if matches:
                item.setBackground(item.listWidget().palette().highlight())
                item.setForeground(item.listWidget().palette().highlightedText())
            else:
                item.setBackground(item.listWidget().palette().base())
                item.setForeground(item.listWidget().palette().text())

    def create_orange_table(self, expression_data, all_genes, sample_characteristics, selected_characteristics=None):
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
                
                if selected_characteristics is not None:
                    # Filter attributes and reconstruct class
                    filtered_chars = {k: v for k, v in parsed_chars.items() if k in selected_characteristics}
                    if filtered_chars:
                        filtered_chars['class'] = '|'.join([filtered_chars[k] for k in sorted(filtered_chars.keys())])
                    parsed_chars = filtered_chars
                
                # Set each characteristic as a separate variable attribute
                if parsed_chars:
                    var.attributes = parsed_chars
                    self.log_message(f"Sample {sample_name} characteristics: {list(parsed_chars.keys())}")
            
            attributes.append(var)
        
        # Gene ID as "genes", Gene Symbol, and Entrez ID as meta attributes
        metas = [StringVariable("genes"), StringVariable("Gene Symbol"), StringVariable("Entrez ID")]
        
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
        
        # Create meta data (gene IDs, Gene Symbols, and Entrez IDs)
        gene_ids = []
        gene_symbol_list = []
        entrez_ids = []
        
        for gene_id in all_genes:
            gene_ids.append(gene_id)
            
            # Get gene info from the dictionary
            if gene_id in self.gene_info:
                gene_symbol_list.append(self.gene_info[gene_id]['symbol'])
                entrez_ids.append(self.gene_info[gene_id]['entrez'])
            else:
                gene_symbol_list.append("")
                entrez_ids.append("")
        
        gene_ids = np.array(gene_ids).reshape(-1, 1)
        gene_symbol_array = np.array(gene_symbol_list).reshape(-1, 1)
        entrez_ids_array = np.array(entrez_ids).reshape(-1, 1)
        metas_data = np.hstack([gene_ids, gene_symbol_array, entrez_ids_array])
        
        # Create Orange Table
        table = Table.from_numpy(domain, X, metas=metas_data)
        
        # Set table attributes (table-level metadata)
        table.attributes["taxonomy_id"] = str(self.taxonomy_id_setting)
        table.attributes["gene_as_attribute_name"] = bool(getattr(self, "gene_as_attribute_name", False))
        
        meta_options = ["genes", "Gene Symbol", "Entrez ID"]
        col_idx = getattr(self, "gene_id_column", 0)
        if col_idx >= 0 and col_idx < len(meta_options):
            table.attributes["gene_id_column"] = meta_options[col_idx]
        else:
            table.attributes["gene_id_column"] = "genes"
        
        # Set the table name
        if self.table_name.strip():
            table.name = self.table_name.strip()
        else:
            table.name = "GEO Expression Data"
        
        self.log_message(f"Created Orange Table '{table.name}': {n_genes} genes x {n_samples} samples")
        self.log_message(f"Non-missing values: {np.count_nonzero(~np.isnan(X))}")
        entrez_count = np.count_nonzero([e for e in entrez_ids if e])
        self.log_message(f"Genes with Entrez IDs in output: {entrez_count}")
        symbol_count = np.count_nonzero([s for s in gene_symbol_list if s])
        self.log_message(f"Genes with Symbols in output: {symbol_count}")
        if self.transform_log2:
            self.log_message("Applied log2 to actual value transformation (2^x)")
        
        # Send the table to output
        self.Outputs.data.send(table)


# For testing the widget
if __name__ == "__main__":
    WidgetPreview(OWGeoSoftExtractor).run()
