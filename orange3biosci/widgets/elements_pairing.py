import numpy as np
from collections import defaultdict
from itertools import combinations
from pkg_resources import resource_filename

from AnyQt.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QWidget, QScrollArea
from AnyQt.QtCore import Qt

import Orange
from Orange.data import Table, Domain, DiscreteVariable, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui, settings
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import OWWidget, Input, Output, Msg


class OWElementsPairing(OWWidget):
    name = "Elements Pairing"
    description = "Generate pairs of sources that share the same target with aggregation support"
    icon = resource_filename(__name__, "../icons/ElementsPairing.svg")
    priority = 10
    
    class Inputs:
        data = Input("Data", Table)
    
    class Outputs:
        data = Output("Paired Sources", Table)
    
    want_main_area = False
    resizing_enabled = True
    
    # Settings - all will be persisted automatically
    source_column = settings.Setting("")
    target_column = settings.Setting("")
    aggregation_methods = settings.Setting({})  # Dict: column_name -> method
    
    # Available aggregation methods
    AGG_METHODS = [
        "first", "last", "mean", "sum", "count", 
        "max", "min", "median", "std", "var"
    ]
    
    class Error(OWWidget.Error):
        no_data = Msg("No data on input")
        no_columns = Msg("Data must have at least 2 columns")
        same_column = Msg("Source and target columns must be different")
        no_pairs = Msg("No pairs found with selected columns")
    
    def __init__(self):
        super().__init__()
        
        self.data = None
        self.numeric_columns = []
        self.aggregation_combos = {}
        
        # GUI
        box = gui.widgetBox(self.controlArea, "Column Selection")
        
        # Source column selection
        self.source_combo = gui.comboBox(
            box, self, "source_column", 
            label="Source column:",
            callback=self.on_source_target_changed,
            sendSelectedValue=True
        )
        
        # Target column selection
        self.target_combo = gui.comboBox(
            box, self, "target_column",
            label="Target column:",
            callback=self.on_source_target_changed,
            sendSelectedValue=True
        )
        
        # Aggregation settings box with scroll area
        self.agg_box = gui.widgetBox(self.controlArea, "Numeric Column Aggregations")
        
        # Create scroll area for aggregation controls
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.agg_widget = QWidget()
        self.agg_layout = QVBoxLayout()
        self.agg_widget.setLayout(self.agg_layout)
        scroll.setWidget(self.agg_widget)
        
        self.agg_box.layout().addWidget(scroll)
        self.agg_box.setMaximumHeight(300)
        
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
        self.update_numeric_columns()
        self.update_aggregation_controls()
        self.update_info()
        self.process_button.setEnabled(True)
    
    def clear_combos(self):
        self.source_combo.clear()
        self.target_combo.clear()
        self.clear_aggregation_controls()
    
    def clear_aggregation_controls(self):
        # Clear existing aggregation controls
        while self.agg_layout.count():
            item = self.agg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.aggregation_combos.clear()
    
    def update_combos(self):
        self.source_combo.clear()
        self.target_combo.clear()
        
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
    
    def update_numeric_columns(self):
        """Identify numeric columns (excluding source and target)"""
        self.numeric_columns = []
        
        if self.data is None:
            return
        
        # Get all numeric columns
        for attr in self.data.domain.attributes:
            if isinstance(attr, ContinuousVariable):
                if attr.name != self.source_column and attr.name != self.target_column:
                    self.numeric_columns.append(attr.name)
        
        for meta in self.data.domain.metas:
            if isinstance(meta, ContinuousVariable):
                if meta.name != self.source_column and meta.name != self.target_column:
                    self.numeric_columns.append(meta.name)
        
        if self.data.domain.class_var:
            if isinstance(self.data.domain.class_var, ContinuousVariable):
                if self.data.domain.class_var.name != self.source_column and \
                   self.data.domain.class_var.name != self.target_column:
                    self.numeric_columns.append(self.data.domain.class_var.name)
    
    def update_aggregation_controls(self):
        """Create combo boxes for each numeric column"""
        self.clear_aggregation_controls()
        
        if not self.numeric_columns:
            label = QLabel("No numeric columns to aggregate")
            self.agg_layout.addWidget(label)
            return
        
        # Initialize aggregation_methods dict if needed
        if not isinstance(self.aggregation_methods, dict):
            self.aggregation_methods = {}
        
        for col_name in self.numeric_columns:
            # Create horizontal layout for label and combo
            h_layout = QHBoxLayout()
            
            label = QLabel(f"{col_name}:")
            label.setMinimumWidth(100)
            h_layout.addWidget(label)
            
            combo = QComboBox()
            combo.addItems(self.AGG_METHODS)
            
            # Set saved value or default to 'mean'
            if col_name in self.aggregation_methods:
                idx = combo.findText(self.aggregation_methods[col_name])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText("mean")
                self.aggregation_methods[col_name] = "mean"
            
            # Connect to save settings
            combo.currentTextChanged.connect(
                lambda text, name=col_name: self.on_aggregation_changed(name, text)
            )
            
            h_layout.addWidget(combo)
            h_layout.addStretch()
            
            # Add to layout
            widget = QWidget()
            widget.setLayout(h_layout)
            self.agg_layout.addWidget(widget)
            
            self.aggregation_combos[col_name] = combo
        
        self.agg_layout.addStretch()
    
    def on_aggregation_changed(self, column_name, method):
        """Save aggregation method when changed"""
        self.aggregation_methods[column_name] = method
        if self.data is not None:
            self.process_data()
    
    def on_source_target_changed(self):
        """Handle source/target column change"""
        if self.data is not None:
            self.update_numeric_columns()
            self.update_aggregation_controls()
            self.process_data()
    
    def update_info(self):
        if self.data is None:
            self.info_label.setText("No data loaded")
            return
        
        rows = len(self.data)
        cols = len(self.data.domain.attributes) + len(self.data.domain.metas)
        if self.data.domain.class_var:
            cols += 1
        
        num_agg = len(self.numeric_columns)
        self.info_label.setText(
            f"Data: {rows} rows, {cols} columns\n"
            f"Numeric columns for aggregation: {num_agg}"
        )
    
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
    
    def apply_aggregation(self, values, method):
        """Apply aggregation method to list of values"""
        values = [v for v in values if not (isinstance(v, float) and np.isnan(v))]
        
        if not values:
            return np.nan
        
        if method == "first":
            return values[0]
        elif method == "last":
            return values[-1]
        elif method == "mean":
            return np.mean(values)
        elif method == "sum":
            return np.sum(values)
        elif method == "count":
            return len(values)
        elif method == "max":
            return np.max(values)
        elif method == "min":
            return np.min(values)
        elif method == "median":
            return np.median(values)
        elif method == "std":
            return np.std(values)
        elif method == "var":
            return np.var(values)
        else:
            return np.mean(values)  # Default
    
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
        
        # Get numeric column data
        numeric_data = {}
        for col_name in self.numeric_columns:
            numeric_data[col_name] = self.get_column_data(col_name)
        
        # Build structure: source -> target -> {numeric_col: values}
        source_target_data = defaultdict(lambda: defaultdict(lambda: {col: [] for col in self.numeric_columns}))
        
        for i in range(len(self.data)):
            source_val = source_data[i]
            target_val = target_data[i]
            
            # Skip missing values
            if isinstance(source_val, (int, float)) and np.isnan(source_val):
                continue
            if source_val == "" or source_val is None:
                continue
            if isinstance(target_val, (int, float)) and np.isnan(target_val):
                continue
            if target_val == "" or target_val is None:
                continue
            
            # Store numeric values for this source-target pair
            for col_name in self.numeric_columns:
                value = numeric_data[col_name][i]
                source_target_data[source_val][target_val][col_name].append(value)
        
        # Now build pairs: find sources that share targets
        # Structure: (source1, source2) -> list of shared targets -> numeric values
        pair_data = defaultdict(lambda: defaultdict(lambda: {col: [] for col in self.numeric_columns}))
        
        # Get all sources
        all_sources = list(source_target_data.keys())
        
        # For each pair of sources
        for source1, source2 in combinations(all_sources, 2):
            # Find shared targets
            targets1 = set(source_target_data[source1].keys())
            targets2 = set(source_target_data[source2].keys())
            shared_targets = targets1 & targets2
            
            if shared_targets:
                # For each shared target, aggregate the numeric values
                for target in shared_targets:
                    for col_name in self.numeric_columns:
                        values1 = source_target_data[source1][target][col_name]
                        values2 = source_target_data[source2][target][col_name]
                        
                        method = self.aggregation_methods.get(col_name, "mean")
                        
                        # Aggregate values for source1 and source2 at this target
                        agg1 = self.apply_aggregation(values1, method)
                        agg2 = self.apply_aggregation(values2, method)
                        
                        # Combine the two aggregated values (e.g., mean of the two means)
                        combined = self.apply_aggregation([agg1, agg2], method)
                        
                        # Store for this pair and target
                        pair_data[(source1, source2)][target][col_name] = combined
        
        if not pair_data:
            self.Error.no_pairs()
            self.Outputs.data.send(None)
            return
        
        # Now aggregate across all shared targets for each pair
        pairs = []
        aggregated_values = {col: [] for col in self.numeric_columns}
        
        for (source1, source2), targets_dict in pair_data.items():
            pairs.append([source1, source2])
            
            # For each numeric column, aggregate across all shared targets
            for col_name in self.numeric_columns:
                method = self.aggregation_methods.get(col_name, "mean")
                
                # Collect the combined values for each shared target
                target_values = [targets_dict[target][col_name] for target in targets_dict]
                
                # Aggregate across all shared targets
                final_agg = self.apply_aggregation(target_values, method)
                aggregated_values[col_name].append(final_agg)
        
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
        if source_var is None and self.data.domain.class_var and \
           self.data.domain.class_var.name == self.source_column:
            source_var = self.data.domain.class_var
        
        # Create variables for the output table
        metas = []
        attributes = []
        
        # Source columns
        if isinstance(source_var, DiscreteVariable):
            source1_var = DiscreteVariable("Source1", values=source_var.values)
            source2_var = DiscreteVariable("Source2", values=source_var.values)
            metas.extend([source1_var, source2_var])
        elif isinstance(source_var, ContinuousVariable):
            source1_var = ContinuousVariable("Source1")
            source2_var = ContinuousVariable("Source2")
            attributes.extend([source1_var, source2_var])
        else:
            # String or other type
            source1_var = StringVariable("Source1")
            source2_var = StringVariable("Source2")
            metas.extend([source1_var, source2_var])
        
        # Aggregated numeric columns
        for col_name in self.numeric_columns:
            method = self.aggregation_methods.get(col_name, "mean")
            var = ContinuousVariable(f"{col_name}_{method}")
            attributes.append(var)
        
        # Prepare data arrays
        X_data = []
        metas_data = []
        
        for i, pair in enumerate(pairs):
            row_attrs = []
            row_metas = []
            
            # Handle source columns
            if isinstance(source_var, StringVariable) or source_var is None:
                row_metas.extend(pair)
            elif isinstance(source_var, DiscreteVariable):
                try:
                    idx1 = source_var.values.index(str(pair[0]))
                    idx2 = source_var.values.index(str(pair[1]))
                    row_metas.extend([idx1, idx2])
                except ValueError:
                    row_metas.extend([np.nan, np.nan])
            else:
                row_attrs.extend(pair)
            
            # Add aggregated values
            for col_name in self.numeric_columns:
                row_attrs.append(aggregated_values[col_name][i])
            
            X_data.append(row_attrs)
            metas_data.append(row_metas)
        
        # Create domain and table
        domain = Domain(attributes, metas=metas)
        
        X_array = np.array(X_data, dtype=float) if X_data and X_data[0] else np.empty((len(pairs), 0))
        metas_array = np.array(metas_data, dtype=object) if metas_data and metas_data[0] else np.empty((len(pairs), 0))
        
        output_table = Table.from_numpy(
            domain=domain,
            X=X_array,
            metas=metas_array
        )
        
        self.Outputs.data.send(output_table)


# For testing purposes
def main():
    from AnyQt.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Create test data
    data = Table("iris")
    
    widget = OWElementsPairing()
    widget.set_data(data)
    widget.show()
    
    app.exec_()


if __name__ == "__main__":
    main()
