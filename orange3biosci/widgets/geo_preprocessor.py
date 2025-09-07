import numpy as np
from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui, settings
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import Msg
from pkg_resources import resource_filename

class OWGeoPreprocessor(widget.OWWidget):
    # Widget metadata
    name = "GEO Preprocessor"
    description = "Preprocess GEO gene differential expression data."
    icon = resource_filename(__name__, "../icons/preprocessing-icon.svg")
    priority = 100
    keywords = ["GEO", "gene", "expression", "preprocess"]

    # Input and Output definitions
    class Inputs:
        data = Input("GEO Data", Table)

    class Outputs:
        processed_data = Output("Processed Data", Table)

    # Settings (user-configurable parameters)
    split_delimiter = settings.Setting("///")  # Default delimiter for splitting
    select_first = settings.Setting(0)  # Radio button setting (0 = first, 1 = last)
    skip_empty_genes = settings.Setting(True)  # Option to skip rows with empty
    auto_apply = settings.Setting(True)

    # Warning messages
    class Warning(widget.OWWidget.Warning):
        no_gene_symbol = Msg("Some rows have empty Gene.symbol")
        multiple_genes_split = Msg("Some genes were split using '///'")

    def __init__(self):
        super().__init__()

        # Initialize variables
        self.data = None
        self.processed_data = None

        # Build the UI
        self.build_ui()

    def build_ui(self):
        # Settings box
        box = gui.widgetBox(self.controlArea, "Processing Settings")
        
        # Delimiter setting
        gui.lineEdit(box, self, 'split_delimiter',
                    label='Gene split delimiter:',
                    tooltip='Delimiter used to split multiple genes in one field',
                    callback=self._on_parameter_changed)
        
        # Select first or last
        button_group = gui.radioButtonsInBox(box, self, 'select_first',
                                             label='When multiple gene symbols are present:',
                                             callback=self._on_parameter_changed)

        gui.appendRadioButton(button_group, 'Select first')
        gui.appendRadioButton(button_group, 'Select last')

        # Empty Gene.symbol setting
        gui.checkBox(box, self, 'skip_empty_genes',
                     label='Skip rows with empty Gene.symbol',
                     callback=self._on_parameter_changed)

        # Auto-apply checkbox
        gui.checkBox(box, self, 'auto_apply',
                     label='Apply automatically on change',
                     callback=self._on_parameter_changed)

        # Apply button (only visible when auto_apply is False)
        self.apply_button = gui.button(box, self, "Apply", callback=self.apply, disabled=self.auto_apply)
        
        # Info/status area
        self.info_box = gui.widgetBox(self.controlArea, "Info")
        self.info_label = gui.label(self.info_box, self, "No data loaded")

    ###################################################################
    # CORE PROCESSING LOGIC (Your code integrated here)
    ###################################################################
    def process_data(self):
        """Process the GEO data using your algorithm"""
        self.Warning.clear()
        
        if self.data is None:
            self.processed_data = None
            self.info_label.setText("No data loaded")
            return

        gene = []
        logfc = []
        split_count = 0
        empty_symbol_count = 0

        inst_pre = self.data.domain.attributes + self.data.domain.metas
        inst_attrs = [attr.name for attr in inst_pre]
        print("first_last")
        print(self.select_first)
        first_last = 0 if self.select_first == 0 else -1

        # Your processing logic with enhancements
        if "Gene.symbol" not in inst_attrs and "Gene.ID" not in inst_attrs:
            self.Warning.no_gene_symbol("Input data must contain 'Gene.symbol' or 'Gene.ID' fields")
            self.processed_data = None
            self.info_label.setText("Invalid input data")
            return
        
        for inst in self.data:
            if len(inst["Gene.symbol"].value) == 0 and self.skip_empty_genes:
                empty_symbol_count += 1
            else:
                gene_symbol = inst["Gene.symbol"].value if "Gene.symbol" in inst_attrs else ""
                gene_id = inst["Gene.ID"].value if "Gene.ID" in inst_attrs else ""

                # Handle multiple genes separated by delimiter
                if self.split_delimiter in gene_symbol:
                    gene_symbol = gene_symbol.split(self.split_delimiter)[first_last].strip()
                    gene_id = gene_id.split(self.split_delimiter)[first_last].strip()
                    split_count += 1
                
                # Build gene metadata
                gene.append([
                    inst["ID"].value if "ID" in inst_attrs else "",
                    gene_symbol,
                    inst["Gene.title"].value if "Gene.title" in inst_attrs else "",
                    gene_id
                ])
                
                # Build expression data
                logfc_values = []
                for field in ["adj.P.Val", "P.Value", "t", "B", "logFC"]:
                    if field in inst_attrs:
                        logfc_values.append(inst[field].value)
                    else:
                        logfc_values.append(0.0)  # Default value if field missing
                
                logfc.append(logfc_values)

        info_msgs = []
        # Set warning messages
        if empty_symbol_count > 0:
            info_msgs.append(f"{empty_symbol_count} rows skipped due to empty Gene.symbol")
        if split_count > 0:
            info_msgs.append(f"Split {split_count} genes using '{self.split_delimiter}'")

        # Create output table
        if gene and logfc:
            # Define domain for the output table
            meta_attrs = [
                StringVariable("ID"),
                StringVariable("Gene.symbol"),
                StringVariable("Gene.title"), 
                StringVariable("Gene.ID")
            ]
            
            continuous_attrs = [
                ContinuousVariable("adj.P.Val"),
                ContinuousVariable("P.Value"),
                ContinuousVariable("t"),
                ContinuousVariable("B"), 
                ContinuousVariable("logFC")
            ]
            
            domain = Domain(continuous_attrs, metas=meta_attrs)
            
            # Convert to numpy arrays and create table
            logfc_array = np.array(logfc, dtype=float)
            gene_array = np.array(gene, dtype=object)
            
            self.processed_data = Table.from_numpy(domain, logfc_array, metas=gene_array)

            msg = f"Processed {len(gene)} genes"
            if info_msgs:
                msg += "\n" + "\n".join(info_msgs)
            self.info_label.setText(msg)
        else:
            self.processed_data = None
            self.info_label.setText("No valid data to process")

    ###################################################################
    # Widget Lifecycle Methods
    ###################################################################
    @Inputs.data
    def set_data(self, data):
        """Handle incoming data"""
        self.data = data
        if data is not None:
            self.info_label.setText(f"Loaded {len(data)} rows")
        else:
            self.info_label.setText("No data loaded")
        
        if self.auto_apply:
            self.process_data()
            self.commit()
        else:
            self.apply_button.setEnabled(True)

    def _on_parameter_changed(self):
        """Called when settings are changed"""
        if self.auto_apply:
            self.process_data()
            self.commit()
        else:
            self.apply_button.setEnabled(True)

    def apply(self):
        """Manual apply button handler"""
        self.process_data()
        self.commit()
        self.apply_button.setEnabled(False)

    def commit(self):
        """Send processed data to output"""
        self.Outputs.processed_data.send(self.processed_data)