from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.data import Table, Domain, StringVariable, DiscreteVariable, ContinuousVariable
from Orange.widgets.widget import Input, Output
import numpy as np
from pkg_resources import resource_filename


class OWSimpleTransposeTable(widget.OWWidget):
    name = "Alternative Transpose"
    description = "Transpose a data table regardless of field types"
    icon = resource_filename(__name__, "../icons/Transpose-alternative.svg")
    priority = 10

    class Inputs:
        data = Input("Data", Table)

    class Outputs:
        transposed_data = Output("Transposed Data", Table)

    want_main_area = False
    resizing_enabled = False

    # Settings
    column_for_names = Setting(0)  # Index of column to use for names
    use_attribute_names_as_column = Setting(True)

    def __init__(self):
        super().__init__()
        self.data = None
        self.all_vars = []

        # GUI
        box = gui.widgetBox(self.controlArea, "Options")
        
        self.column_combo = gui.comboBox(
            box, self, "column_for_names",
            label="Column for new attribute names:",
            callback=self.transpose_data,
            sendSelectedValue=False
        )
        
        gui.checkBox(box, self, "use_attribute_names_as_column",
                     "Add original attribute names as first column",
                     callback=self.transpose_data)

        gui.rubber(self.controlArea)

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self.update_column_combo()
        self.transpose_data()

    def update_column_combo(self):
        self.column_combo.clear()
        if self.data is None:
            return
        
        # Get all variables
        self.all_vars = list(self.data.domain.attributes) + \
                       list(self.data.domain.class_vars) + \
                       list(self.data.domain.metas)
        
        # Add option for generic names
        self.column_combo.addItem("(Use generic names: V1, V2, ...)")
        
        # Add all variable names as options
        for var in self.all_vars:
            self.column_combo.addItem(var.name)
        
        # Reset selection if out of bounds
        if self.column_for_names > len(self.all_vars):
            self.column_for_names = 0

    def transpose_data(self):
        if self.data is None:
            self.Outputs.transposed_data.send(None)
            return

        try:
            # Get all variables (attributes, class vars, and metas)
            all_vars = list(self.data.domain.attributes) + \
                      list(self.data.domain.class_vars) + \
                      list(self.data.domain.metas)
            
            if not all_vars:
                self.Outputs.transposed_data.send(None)
                return
            
            # Get variable names
            attr_names = [var.name for var in all_vars]
            
            # Extract all data as strings
            n_rows = len(self.data)
            n_cols = len(all_vars)
            data_matrix = []
            
            for i in range(n_rows):
                row = []
                for var in all_vars:
                    try:
                        val = self.data[i][var]
                        if hasattr(val, 'value'):
                            if val.value is None or (isinstance(val.value, float) and np.isnan(val.value)):
                                row.append("")
                            else:
                                row.append(str(val.value))
                        else:
                            row.append(str(val) if val is not None else "")
                    except:
                        row.append("")
                data_matrix.append(row)
            
            if not data_matrix:
                self.Outputs.transposed_data.send(None)
                return
            
            # Transpose the matrix
            transposed = [list(row) for row in zip(*data_matrix)]
            
            # Determine which column to use for names
            # column_for_names: 0 = generic, 1+ = actual column index (index-1)
            if self.column_for_names == 0 or n_cols == 0:
                # Use generic names
                new_col_names = [f"V{i+1}" for i in range(n_cols)]
                transposed_data = transposed
            else:
                # Use specified column for names
                col_idx = self.column_for_names - 1  # Adjust for "generic" option
                if col_idx < len(transposed):
                    new_col_names = transposed[col_idx]
                    # Remove the column used for names from the data
                    transposed_data = transposed[:col_idx] + transposed[col_idx+1:]
                    # Remove the corresponding attribute name
                    attr_names = attr_names[:col_idx] + attr_names[col_idx+1:]
                else:
                    new_col_names = [f"V{i+1}" for i in range(n_cols)]
                    transposed_data = transposed
            
            # Ensure unique column names
            seen = {}
            unique_names = []
            for name in new_col_names:
                name_str = str(name) if name else "Column"
                if name_str in seen:
                    seen[name_str] += 1
                    unique_names.append(f"{name_str}_{seen[name_str]}")
                else:
                    seen[name_str] = 0
                    unique_names.append(name_str)
            new_col_names = unique_names
            
            # Add attribute names as first column if requested
            if self.use_attribute_names_as_column and transposed_data:
                for i, row in enumerate(transposed_data):
                    if i < len(attr_names):
                        row.insert(0, attr_names[i])
                    else:
                        row.insert(0, "")
                new_col_names.insert(0, "Attribute")
            
            if not transposed_data or not transposed_data[0]:
                self.Outputs.transposed_data.send(None)
                return
            
            # Create string variables as metas
            meta_vars = [StringVariable(col_name) for col_name in new_col_names]
            new_domain = Domain([], metas=meta_vars)
            
            # Prepare meta data array
            n_rows_new = len(transposed_data)
            n_cols_new = len(meta_vars)
            meta_data = np.empty((n_rows_new, n_cols_new), dtype=object)
            
            for i, row in enumerate(transposed_data):
                for j in range(min(len(row), n_cols_new)):
                    meta_data[i, j] = str(row[j]) if row[j] else ""
            
            # Create the table
            transposed_table = Table.from_numpy(
                new_domain,
                X=np.empty((n_rows_new, 0)),
                metas=meta_data
            )
            
            self.Outputs.transposed_data.send(transposed_table)
            
        except Exception as e:
            import traceback
            print(f"Error transposing data: {e}")
            print(traceback.format_exc())
            self.Outputs.transposed_data.send(None)


if __name__ == "__main__":
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWSimpleTransposeTable).run()
