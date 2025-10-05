import pandas as pd
from Orange.data import Table, Domain, ContinuousVariable, StringVariable, DiscreteVariable
from Orange.data.pandas_compat import table_to_frame as table_to_pandas
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import OWWidget, Input, Output
from AnyQt.QtWidgets import QVBoxLayout
from pkg_resources import resource_filename

class OWCustomPivot(OWWidget):
    name = "Pivot Alternative"
    description = "Pivot table transformation with configurable rows, columns, and values"
    icon = resource_filename(__name__, "../icons/Pivot-alternative.svg")
    priority = 10

    class Inputs:
        data = Input("Data", Table)

    class Outputs:
        data = Output("Data", Table)

    want_main_area = False
    resizing_enabled = False

    # Settings - use ContextSetting for variable-dependent settings
    row_var_index = Setting(0)
    col_var_index = Setting(0)
    val_var_index = Setting(0)
    aggregation = Setting(0)
    
    # Store variable names to restore selection
    row_var_name = Setting("")
    col_var_name = Setting("")
    val_var_name = Setting("")

    def __init__(self):
        super().__init__()
        self.data = None
        self.var_names = []
        
        # GUI
        box = gui.widgetBox(self.controlArea, "Pivot Configuration")
        
        self.row_combo = gui.comboBox(
            box, self, "row_var_index",
            label="Rows:",
            orientation="horizontal",
            callback=self.on_selection_changed
        )
        
        self.col_combo = gui.comboBox(
            box, self, "col_var_index",
            label="Columns:",
            orientation="horizontal",
            callback=self.on_selection_changed
        )
        
        self.val_combo = gui.comboBox(
            box, self, "val_var_index",
            label="Values:",
            orientation="horizontal",
            callback=self.on_selection_changed
        )
        
        self.agg_combo = gui.comboBox(
            box, self, "aggregation",
            label="Aggregation:",
            orientation="horizontal",
            items=["Mean", "Sum", "Count", "Min", "Max", "First", "Last"],
            callback=self.on_selection_changed
        )
        
        gui.button(box, self, "Apply Pivot", callback=self.apply_pivot)
        
        # Info box
        self.info_label = gui.widgetLabel(
            gui.widgetBox(self.controlArea, "Info"),
            "No data on input."
        )

    @Inputs.data
    def set_data(self, data):
        self.data = data
        if data is not None:
            # Include all variables: attributes, class_vars, and metas
            all_vars = list(data.domain.variables) + list(data.domain.metas)
            self.var_names = [var.name for var in all_vars]
            self.update_combos()
            
            # Restore previous selections if variable names match
            if self.row_var_name in self.var_names:
                self.row_var_index = self.var_names.index(self.row_var_name)
            if self.col_var_name in self.var_names:
                self.col_var_index = self.var_names.index(self.col_var_name)
            if self.val_var_name in self.var_names:
                self.val_var_index = self.var_names.index(self.val_var_name)
            
            self.info_label.setText(f"Input: {len(data)} rows, {len(self.var_names)} columns")
        else:
            self.var_names = []
            self.update_combos()
            self.info_label.setText("No data on input.")
            self.Outputs.data.send(None)

    def update_combos(self):
        self.row_combo.clear()
        self.col_combo.clear()
        self.val_combo.clear()
        
        if self.var_names:
            self.row_combo.addItems(self.var_names)
            self.col_combo.addItems(self.var_names)
            self.val_combo.addItems(self.var_names)
            
            # Set default indices if valid
            if self.row_var_index >= len(self.var_names):
                self.row_var_index = 0
            if self.col_var_index >= len(self.var_names):
                self.col_var_index = min(1, len(self.var_names) - 1)
            if self.val_var_index >= len(self.var_names):
                self.val_var_index = min(2, len(self.var_names) - 1)

    def on_selection_changed(self):
        # Save variable names when selection changes
        if self.var_names:
            if 0 <= self.row_var_index < len(self.var_names):
                self.row_var_name = self.var_names[self.row_var_index]
            if 0 <= self.col_var_index < len(self.var_names):
                self.col_var_name = self.var_names[self.col_var_index]
            if 0 <= self.val_var_index < len(self.var_names):
                self.val_var_name = self.var_names[self.val_var_index]

    def apply_pivot(self):
        if self.data is None:
            return

        try:
            # Get selected variable names
            row_var = self.var_names[self.row_var_index]
            col_var = self.var_names[self.col_var_index]
            val_var = self.var_names[self.val_var_index]
            
            # Map aggregation
            agg_map = {
                0: 'mean',
                1: 'sum',
                2: 'count',
                3: 'min',
                4: 'max',
                5: 'first',
                6: 'last'
            }
            agg_func = agg_map[self.aggregation]
            
            # Convert to pandas - include all attributes and metas
            df = table_to_pandas(self.data, include_metas=True)
            
            # Perform pivot with aggregation
            if agg_func in ['first', 'last']:
                pivoted = df.pivot_table(
                    index=row_var,
                    columns=col_var,
                    values=val_var,
                    aggfunc=agg_func
                )
            else:
                pivoted = df.pivot_table(
                    index=row_var,
                    columns=col_var,
                    values=val_var,
                    aggfunc=agg_func
                )
            
            # Reset index to make row variable a column
            pivoted = pivoted.reset_index()
            
            # Flatten column names (remove multi-index if present)
            pivoted.columns = [str(col) for col in pivoted.columns]
            
            # Create Orange Domain manually
            attributes = []
            metas = []
            
            # Check each column's data type
            meta_indices = []
            attr_indices = []
            
            for idx, col in enumerate(pivoted.columns):
                if pivoted[col].dtype == 'object' or pivoted[col].dtype.name == 'category':
                    # String or categorical column - store as meta
                    metas.append(StringVariable(col))
                    meta_indices.append(idx)
                else:
                    # Numerical column - store as attribute
                    attributes.append(ContinuousVariable(col))
                    attr_indices.append(idx)
            
            domain = Domain(attributes, metas=metas)
            
            # Separate numerical and meta data
            if metas:
                X = pivoted.iloc[:, attr_indices].values.astype(float)
                M = pivoted.iloc[:, meta_indices].values.astype(str)
                out_data = Table.from_numpy(domain, X, metas=M)
            else:
                # All columns are numerical
                X = pivoted.values.astype(float)
                out_data = Table.from_numpy(domain, X)
            
            self.Outputs.data.send(out_data)
            self.info_label.setText(
                f"Output: {len(out_data)} rows, {len(out_data.domain.variables)} columns"
            )
            
        except Exception as e:
            import traceback
            print(f"Error transposing data: {e}")
            print(traceback.format_exc())
            self.info_label.setText(f"Error: {str(e)}")
            self.Outputs.data.send(None)


if __name__ == "__main__":
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWCustomPivot).run()
