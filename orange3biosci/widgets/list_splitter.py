from typing import Optional
from AnyQt.QtWidgets import QComboBox, QLineEdit, QRadioButton, QButtonGroup, QVBoxLayout, QFormLayout, QLabel
from AnyQt.QtCore import Qt

from Orange.data import Table, Domain, StringVariable, DiscreteVariable, ContinuousVariable
from Orange.widgets import gui, widget
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output
import numpy as np


class OWListSplitter(widget.OWWidget):
    name = "List Splitter"
    description = "Split delimited values in a field into multiple rows or filter first/last occurrence"
    icon = "icons/mywidget.svg"
    priority = 10

    class Inputs:
        data = Input("Data", Table)

    class Outputs:
        data = Output("Data", Table)

    want_main_area = False
    resizing_enabled = False

    # Settings
    selected_field_name = Setting("", schema_only=True)
    delimiter = Setting(":", schema_only=True)
    split_mode = Setting(0, schema_only=True)  # 0: First, 1: Last, 2: Split All
    auto_apply = Setting(False, schema_only=True)

    def __init__(self):
        super().__init__()
        
        self.data = None
        self.field_names = []

        # GUI
        box = gui.widgetBox(self.controlArea, "List Field Selection")
        
        # Field selection
        form_layout = QFormLayout()
        self.field_combo = QComboBox()
        self.field_combo.currentIndexChanged.connect(self.on_field_changed)
        form_layout.addRow("Select field containing list:", self.field_combo)
        box.layout().addLayout(form_layout)

        # Delimiter input
        delimiter_box = gui.widgetBox(self.controlArea, "Delimiter")
        delimiter_layout = QFormLayout()
        self.delimiter_input = QLineEdit(self.delimiter)
        self.delimiter_input.textChanged.connect(self.on_delimiter_changed)
        delimiter_layout.addRow("Split character(s):", self.delimiter_input)
        delimiter_box.layout().addLayout(delimiter_layout)

        # Split mode selection
        mode_box = gui.widgetBox(self.controlArea, "Split Mode")
        self.mode_group = QButtonGroup()
        
        self.radio_first = QRadioButton("First occurrence only")
        self.radio_last = QRadioButton("Last occurrence only")
        self.radio_split = QRadioButton("Split all values")
        
        self.mode_group.addButton(self.radio_first, 0)
        self.mode_group.addButton(self.radio_last, 1)
        self.mode_group.addButton(self.radio_split, 2)
        
        mode_box.layout().addWidget(self.radio_first)
        mode_box.layout().addWidget(self.radio_last)
        mode_box.layout().addWidget(self.radio_split)
        
        # Set initial selection
        if self.split_mode == 0:
            self.radio_first.setChecked(True)
        elif self.split_mode == 1:
            self.radio_last.setChecked(True)
        else:
            self.radio_split.setChecked(True)
            
        self.mode_group.buttonClicked.connect(self.on_mode_changed)

        # Auto-apply checkbox and Apply button
        button_box = gui.widgetBox(self.controlArea, "")
        self.auto_apply_checkbox = gui.checkBox(
            button_box, self, "auto_apply", "Apply Automatically",
            callback=self.on_auto_apply_changed
        )
        self.apply_button = gui.button(button_box, self, "Apply", callback=self.apply)
        
        # Set initial button state
        self.apply_button.setEnabled(not self.auto_apply)

        # Info label
        self.info_label = QLabel("No data loaded")
        self.controlArea.layout().addWidget(self.info_label)

    @Inputs.data
    def set_data(self, data):
        print('=== data')
        print(data)
        self.data = data
        self.field_combo.clear()
        self.field_names = []
        
        if self.data is None:
            self.info_label.setText("No data loaded")
            self.Outputs.data.send(None)
            return
        
        # Get all attributes (features)
        for var in self.data.domain.attributes:
            self.field_names.append(var.name)
            
        # Get class variables
        if self.data.domain.class_vars:
            for var in self.data.domain.class_vars:
                self.field_names.append(var.name)
        
        # Get meta attributes
        for var in self.data.domain.metas:
            self.field_names.append(var.name)
        
        if not self.field_names:
            self.info_label.setText("No fields found in data")
            self.Outputs.data.send(None)
            return
        
        # Populate combo box
        self.field_combo.addItems(self.field_names)
        print('=== combo fields and selection')
        print(self.selected_field_name)
        print(self.field_names)
        
        # Restore previous selection by name
        if self.selected_field_name and self.selected_field_name in self.field_names:
            index = self.field_names.index(self.selected_field_name)
            self.field_combo.setCurrentIndex(index)
        else:
            self.field_combo.setCurrentIndex(0)
            self.selected_field_name = self.field_names[0] if self.field_names else ""
        
        self.info_label.setText(f"Loaded {len(self.data)} rows, {len(self.field_names)} fields")
        
        # Auto-apply if enabled
        if self.auto_apply:
            self.apply()

    def on_field_changed(self, index):
        if 0 <= index < len(self.field_names):
            self.selected_field_name = self.field_names[index]
            if self.auto_apply:
                self.apply()

    def on_delimiter_changed(self, text):
        self.delimiter = text
        if self.auto_apply:
            self.apply()

    def on_mode_changed(self):
        self.split_mode = self.mode_group.checkedId()
        if self.auto_apply:
            self.apply()
    
    def on_auto_apply_changed(self):
        self.apply_button.setEnabled(not self.auto_apply)
        if self.auto_apply:
            self.apply()

    def apply(self):
        if self.data is None:
            self.info_label.setText("No data to process")
            self.Outputs.data.send(None)
            return

        if not self.field_names:
            self.info_label.setText("No fields available")
            self.Outputs.data.send(None)
            return
        
        # Get currently selected field
        current_index = self.field_combo.currentIndex()
        if current_index < 0 or current_index >= len(self.field_names):
            self.info_label.setText("Invalid field selection")
            self.Outputs.data.send(None)
            return
        
        print('=== index and field')
        print(current_index)
        print(self.field_names)
        selected_field = self.field_names[current_index]
        self.selected_field_name = selected_field  # Update setting

        if not self.delimiter:
            self.info_label.setText("Delimiter cannot be empty")
            self.Outputs.data.send(None)
            return
        
        try:
            result = self.process_data(selected_field)
            self.Outputs.data.send(result)
            self.info_label.setText(f"Success! Output: {len(result)} rows")
        except Exception as e:
            self.info_label.setText(f"Error: {str(e)}")
            self.Outputs.data.send(None)

    def process_data(self, field_name):
        # Find the field in domain (could be in attributes, class_vars, or metas)
        field_var = None
        field_location = None  # 'attributes', 'class_vars', or 'metas'
        field_idx = None
        
        # Check attributes
        for idx, var in enumerate(self.data.domain.attributes):
            if var.name == field_name:
                field_var = var
                field_location = 'attributes'
                field_idx = idx
                break
        
        # Check class variables
        if field_var is None and self.data.domain.class_vars:
            for idx, var in enumerate(self.data.domain.class_vars):
                if var.name == field_name:
                    field_var = var
                    field_location = 'class_vars'
                    field_idx = idx
                    break
        
        # Check metas
        if field_var is None:
            for idx, var in enumerate(self.data.domain.metas):
                if var.name == field_name:
                    field_var = var
                    field_location = 'metas'
                    field_idx = idx
                    break
        
        if field_var is None:
            raise ValueError(f"Field {field_name} not found")

        # Collect all rows for the output
        output_rows = []
        
        for row in self.data:
            # Get the value of the field to split based on location
            if field_location == 'attributes':
                raw_value = row.x[field_idx]
            elif field_location == 'class_vars':
                raw_value = row.y[field_idx] if len(self.data.domain.class_vars) > 1 else row.y
            else:  # metas
                raw_value = row.metas[field_idx]
            
            # Convert to string
            if isinstance(field_var, ContinuousVariable):
                if isinstance(raw_value, float) and np.isnan(raw_value):
                    field_value = ""
                else:
                    field_value = str(raw_value)
            elif isinstance(field_var, DiscreteVariable):
                field_value = str(field_var.values[int(raw_value)]) if not np.isnan(raw_value) else ""
            else:  # StringVariable
                field_value = str(raw_value) if raw_value else ""
            
            # Split the value
            split_values = field_value.split(self.delimiter) if field_value else [""]
            
            # Apply the selected mode
            if self.split_mode == 0:  # First occurrence
                values_to_use = [split_values[0]] if split_values else [""]
            elif self.split_mode == 1:  # Last occurrence
                values_to_use = [split_values[-1]] if split_values else [""]
            else:  # Split all
                values_to_use = split_values
            
            # Create output rows
            for value in values_to_use:
                output_rows.append((row, value.strip()))
        
        # Create output domain - keep structure but convert selected field to StringVariable
        new_attributes = []
        new_class_vars = []
        new_metas = []
        
        for var in self.data.domain.attributes:
            if var.name == field_name:
                new_attributes.append(StringVariable(var.name))
            else:
                new_attributes.append(var)
        
        if self.data.domain.class_vars:
            for var in self.data.domain.class_vars:
                if var.name == field_name:
                    new_class_vars.append(StringVariable(var.name))
                else:
                    new_class_vars.append(var)
        
        for var in self.data.domain.metas:
            if var.name == field_name:
                new_metas.append(StringVariable(var.name))
            else:
                new_metas.append(var)
        
        new_domain = Domain(new_attributes, new_class_vars, new_metas)
        
        # Build output table
        X = np.empty((len(output_rows), len(new_attributes)), dtype=object)
        Y = np.empty((len(output_rows), len(new_class_vars)), dtype=object) if new_class_vars else None
        metas = np.empty((len(output_rows), len(new_metas)), dtype=object) if new_metas else None
        
        for row_idx, (original_row, new_value) in enumerate(output_rows):
            # Handle attributes
            for col_idx, var in enumerate(new_domain.attributes):
                if var.name == field_name:
                    X[row_idx, col_idx] = new_value
                else:
                    X[row_idx, col_idx] = original_row.x[col_idx]
            
            # Handle class variables
            if Y is not None:
                for col_idx, var in enumerate(new_domain.class_vars):
                    if var.name == field_name:
                        Y[row_idx, col_idx] = new_value
                    else:
                        if len(self.data.domain.class_vars) > 1:
                            Y[row_idx, col_idx] = original_row.y[col_idx]
                        else:
                            Y[row_idx, col_idx] = original_row.y
            
            # Handle metas
            if metas is not None:
                for col_idx, var in enumerate(new_domain.metas):
                    if var.name == field_name:
                        metas[row_idx, col_idx] = new_value
                    else:
                        metas[row_idx, col_idx] = original_row.metas[col_idx]
        
        # Create Orange Table
        result_table = Table.from_numpy(new_domain, X, Y, metas)
        
        return result_table


if __name__ == "__main__":
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWListSplitter).run()
