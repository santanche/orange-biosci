import numpy as np
from collections import defaultdict
from itertools import combinations
from pkg_resources import resource_filename

from AnyQt.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QWidget
from AnyQt.QtCore import Qt

import Orange
from Orange.data import Table, Domain, DiscreteVariable, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui, settings
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import OWWidget, Input, Output, Msg


class OWElementsPairing(OWWidget):
    name = "Elements Pairing"
    description = "Generate pairs of sources that share the same target"
    icon = resource_filename(__name__, "../icons/ElementsPairing.svg")
    priority = 10
    
    class Inputs:
        data = Input("Data", Table)
    
    class Outputs:
        data = Output("Paired Sources", Table)
    
    want_main_area = False
    
    # Settings
    source_column = settings.Setting("")
    target_column = settings.Setting("")
    
    class Error(OWWidget.Error):
        no_data = Msg("No data on input")
        no_columns = Msg("Data must have at least 2 columns")
        same_column = Msg("Source and target columns must be different")
        no_pairs = Msg("No pairs found with selected columns")
    
    def __init__(self):
        super().__init__()
        
        self.data = None
        
        # GUI
        box = gui.widgetBox(self.controlArea, "Column Selection")
        
        # Source column selection
        self.source_combo = gui.comboBox(
            box, self, "source_column", 
            label="Source column:",
            callback=self.on_column_changed,
            sendSelectedValue=True
        )
        
        # Target column selection
        self.target_combo = gui.comboBox(
            box, self, "target_column",
            label="Target column:",
            callback=self.on_column_changed,
            sendSelectedValue=True
        )
        
        # Info box
        info_box = gui.widgetBox(self.controlArea, "Info")
        self.info_label = gui.widgetLabel(info_box, "No data loaded")
        
        # Process button
        self.process_button = gui.button(
            self.controlArea, self, "Generate Pairs", 
            callback=self.process_data
        )
        self.process_button.setEnabled(False)
    
    @Inputs.data
    def set_data(self, data):
        self.Error.clear()
        self.data = data
        
        if data is None:
            self.Error.no_data()
            self.clear_combos()
            self.info_label.setText("No data loaded")
            self.process_button.setEnabled(False)
            self.Outputs.data.send(None)
            return
        
        if len(data.domain.attributes) + len(data.domain.metas) < 2:
            self.Error.no_columns()
            self.clear_combos()
            self.info_label.setText("Need at least 2 columns")
            self.process_button.setEnabled(False)
            self.Outputs.data.send(None)
            return
        
        self.update_combos()
        self.update_info()
        self.process_button.setEnabled(True)
    
    def clear_combos(self):
        self.source_combo.clear()
        self.target_combo.clear()
    
    def update_combos(self):
        self.clear_combos()
        
        if self.data is None:
            return
        
        # Get all columns (attributes + metas)
        columns = []
        for attr in self.data.domain.attributes:
            columns.append(attr.name)
        for meta in self.data.domain.metas:
            columns.append(meta.name)
        
        # Add class variable if exists
        if self.data.domain.class_var:
            columns.append(self.data.domain.class_var.name)
        
        self.source_combo.addItems(columns)
        self.target_combo.addItems(columns)
        
        # Set default selections if settings exist
        if self.source_column and self.source_column in columns:
            self.source_combo.setCurrentText(self.source_column)
        
        if self.target_column and self.target_column in columns:
            self.target_combo.setCurrentText(self.target_column)
    
    def update_info(self):
        if self.data is None:
            self.info_label.setText("No data loaded")
            return
        
        rows = len(self.data)
        cols = len(self.data.domain.attributes) + len(self.data.domain.metas)
        if self.data.domain.class_var:
            cols += 1
        
        self.info_label.setText(f"Data: {rows} rows, {cols} columns")
    
    def on_column_changed(self):
        if self.data is not None:
            self.process_data()
    
    def get_column_data(self, column_name):
        """Get data from a column by name"""
        if not column_name:
            return None
        
        # Check attributes
        for i, attr in enumerate(self.data.domain.attributes):
            if attr.name == column_name:
                return self.data.X[:, i]
        
        # Check metas
        for i, meta in enumerate(self.data.domain.metas):
            if meta.name == column_name:
                return self.data.metas[:, i]
        
        # Check class variable
        if self.data.domain.class_var and self.data.domain.class_var.name == column_name:
            return self.data.Y
        
        return None
    
    def process_data(self):
        self.Error.clear()
        
        if self.data is None:
            self.Outputs.data.send(None)
            return
        
        if not self.source_column or not self.target_column:
            self.Outputs.data.send(None)
            return
        
        if self.source_column == self.target_column:
            self.Error.same_column()
            self.Outputs.data.send(None)
            return
        
        # Get column data
        source_data = self.get_column_data(self.source_column)
        target_data = self.get_column_data(self.target_column)
        
        if source_data is None or target_data is None:
            self.Outputs.data.send(None)
            return
        
        # Group sources by target
        target_to_sources = defaultdict(list)
        
        for i in range(len(self.data)):
            source_val = source_data[i]
            target_val = target_data[i]
            
            # Skip missing values
            if np.isnan(source_val) if isinstance(source_val, (int, float)) else source_val == "" or source_val is None:
                continue
            if np.isnan(target_val) if isinstance(target_val, (int, float)) else target_val == "" or target_val is None:
                continue
            
            target_to_sources[target_val].append(source_val)
        
        # Generate pairs
        pairs = []
        for target_val, sources in target_to_sources.items():
            if len(sources) > 1:
                # Remove duplicates while preserving order
                unique_sources = []
                seen = set()
                for source in sources:
                    if source not in seen:
                        unique_sources.append(source)
                        seen.add(source)
                
                # Generate all combinations of unique sources
                if len(unique_sources) > 1:
                    for source1, source2 in combinations(unique_sources, 2):
                        pairs.append([source1, source2])
        
        if not pairs:
            self.Error.no_pairs()
            self.Outputs.data.send(None)
            return
        
        # Create output table
        pairs_array = np.array(pairs, dtype=object)
        
        # Determine variable types based on source column
        source_var = None
        for attr in self.data.domain.attributes:
            if attr.name == self.source_column:
                source_var = attr
                break
        if source_var is None:
            for meta in self.data.domain.metas:
                if meta.name == self.source_column:
                    source_var = meta
                    break
        if source_var is None and self.data.domain.class_var and self.data.domain.class_var.name == self.source_column:
            source_var = self.data.domain.class_var
        
        # Create variables for the output table
        if isinstance(source_var, DiscreteVariable):
            source1_var = DiscreteVariable("Source1", values=source_var.values)
            source2_var = DiscreteVariable("Source2", values=source_var.values)
        elif isinstance(source_var, ContinuousVariable):
            source1_var = ContinuousVariable("Source1")
            source2_var = ContinuousVariable("Source2")
        else:
            # String or other type
            source1_var = StringVariable("Source1")
            source2_var = StringVariable("Source2")
        
        # Create domain and table
        domain = Domain([], metas=[source1_var, source2_var])
        
        # Convert data based on variable types
        if isinstance(source_var, StringVariable) or source_var is None:
            # String data goes to metas
            output_table = Table.from_numpy(
                domain=domain,
                X=np.empty((len(pairs), 0)),
                metas=pairs_array
            )
        else:
            # Numeric data
            if isinstance(source_var, DiscreteVariable):
                # Convert string values to indices for discrete variables
                pairs_numeric = []
                for pair in pairs:
                    pair_indices = []
                    for val in pair:
                        try:
                            idx = source_var.values.index(str(val))
                            pair_indices.append(idx)
                        except ValueError:
                            pair_indices.append(np.nan)
                    pairs_numeric.append(pair_indices)
                pairs_array = np.array(pairs_numeric, dtype=float)
            
            output_table = Table.from_numpy(
                domain=domain,
                X=np.empty((len(pairs), 0)),
                metas=pairs_array
            )
        
        self.Outputs.data.send(output_table)


# For testing purposes
def main():
    from AnyQt.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Create test data
    data = Table("iris")  # You can replace this with your own test data
    
    widget = OWElementsPairing()
    widget.set_data(data)
    widget.show()
    
    app.exec_()


if __name__ == "__main__":
    main()
