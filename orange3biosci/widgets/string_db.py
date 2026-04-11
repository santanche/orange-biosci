"""
Orange3 Widget — STRING-DB Gene Network Query
==============================================
"""

import sys
import os
import gzip

import requests
from importlib.resources import files

from AnyQt.QtWidgets import (
    QLabel, QComboBox, QVBoxLayout, QFormLayout,
    QSizePolicy, QApplication, QRadioButton,
    QHBoxLayout, QPushButton, QFileDialog,
    QCheckBox, QListWidget
)

from AnyQt.QtCore import Qt, QThread, pyqtSignal

import Orange.data
from Orange.widgets import gui, settings
from Orange.widgets.widget import OWWidget, Input, Output, Msg


# ---------------------------------------------------------------------------
# Background worker – keeps the GUI responsive during API calls
# ---------------------------------------------------------------------------

class _Worker(QThread):
    """Queries the STRING-DB API in a background thread."""

    finished  = pyqtSignal(list)   # emits list[dict] on success
    errored   = pyqtSignal(str)    # emits error message on failure

    # STRING-DB REST endpoints
    _BASE = "https://string-db.org/api"

    def __init__(self, genes, species, network_type, parent=None):
        super().__init__(parent)
        self.genes        = genes          # list[str]
        self.species      = species        # int  (NCBI taxon id)
        self.network_type = network_type   # "full" | "physical"

    # ------------------------------------------------------------------
    def run(self):
        try:
            edges = self._fetch()
            self.finished.emit(edges)
        except Exception as exc:
            self.errored.emit(str(exc))

    # ------------------------------------------------------------------
    def _fetch(self):
        """
        1. Resolve identifiers → STRING IDs via /json/get_string_ids
        2. Fetch interactions              via /json/network
        Returns list of dicts with keys: stringId_A, stringId_B,
        preferredName_A, preferredName_B, score.
        """

        # ---- step 1: resolve gene symbols / Entrez IDs ----------------
        resolve_url = f"{self._BASE}/json/get_string_ids"
        resp = requests.post(
            resolve_url,
            data={
                "identifiers" : "\r".join(self.genes),
                "species"     : self.species,
                "limit"       : 1,           # best hit per query gene
                "echo_query"  : 1,
                "caller_identity": "orange3_stringdb_widget",
            },
            timeout=60,
        )
        resp.raise_for_status()
        resolved = resp.json()

        if not resolved:
            raise ValueError(
                "STRING-DB could not resolve any of the supplied gene IDs. "
                "Check that the correct organism is selected."
            )

        string_ids = [r["stringId"] for r in resolved]

        # ---- step 2: fetch interaction network ------------------------
        network_url = f"{self._BASE}/json/network"
        payload = {
            "identifiers"    : "\r".join(string_ids),
            "species"        : self.species,
            "network_type"   : self.network_type,
            "required_score" : 0,            # return all; user can filter downstream
            "caller_identity": "orange3_stringdb_widget",
        }
        resp2 = requests.post(network_url, data=payload, timeout=120)
        resp2.raise_for_status()
        return resp2.json()


# ---------------------------------------------------------------------------
# Orange widget
# ---------------------------------------------------------------------------

class OWStringDB(OWWidget):
    name        = "STRING-DB Network"
    description = (
        "Query the STRING-DB database for gene–gene interactions and "
        "return a network edge table (source, target, score)."
    )
    icon = str(files("orange3biosci") / "icons/StringDB.svg")
    priority    = 100
    keywords    = ["string", "stringdb", "gene", "network", "interaction", "PPI"]

    want_main_area = True

    # ------------------------------------------------------------------ I/O
    class Inputs:
        data = Input("Data", Orange.data.Table)

    class Outputs:
        network = Output("Network", Orange.data.Table, default=True)

    # ------------------------------------------------------------------ msgs
    class Warning(OWWidget.Warning):
        no_genes = Msg("No valid gene IDs found in the selected column.")
        limit_exceeded = Msg("STRING-DB API limits queries to 2,000 genes. The input has been truncated.")

    class Error(OWWidget.Error):
        api_error   = Msg("STRING-DB API error: {}")
        no_data     = Msg("No input data.")
        no_column   = Msg("Selected column not found in the input table.")

    # ---------------------------------------------------------------- settings
    # Persistent user choices saved between sessions
    gene_col_name   = settings.Setting("")           # name of the gene-ID column
    network_type    = settings.Setting("full")       # "full" | "physical"
    species_taxid   = settings.Setting(9606)         # Homo sapiens by default

    data_source = settings.Setting("api")  # "api" | "file"
    file_path = settings.Setting("")
    path_mode = settings.Setting("absolute")  # "absolute" | "relative"
    selected_fields = settings.Setting([])
    strip_protein_prefix = settings.Setting(False)

    # ---------------------------------------------------------------- species catalogue
    # (taxid, display name) — extend freely
    SPECIES = [
        (9606,   "Homo sapiens (human)"),
        (10090,  "Mus musculus (mouse)"),
        (10116,  "Rattus norvegicus (rat)"),
        (7955,   "Danio rerio (zebrafish)"),
        (7227,   "Drosophila melanogaster (fruit fly)"),
        (6239,   "Caenorhabditis elegans (nematode)"),
        (4932,   "Saccharomyces cerevisiae (yeast)"),
        (3702,   "Arabidopsis thaliana (thale cress)"),
        (83333,  "Escherichia coli K-12"),
        (9031,   "Gallus gallus (chicken)"),
        (9913,   "Bos taurus (cattle)"),
        (9823,   "Sus scrofa (pig)"),
        (9615,   "Canis lupus familiaris (dog)"),
        (9986,   "Oryctolagus cuniculus (rabbit)"),
    ]

    NETWORK_TYPES = [
        ("full",     "Full STRING network"),
        ("physical", "Physical subnetwork"),
    ]

    # ---------------------------------------------------------------- GUI
    def __init__(self):
        super().__init__()
        self._data       = None
        self._worker     = None

        # ---- Control area -----------------------------------------------
        box = gui.widgetBox(self.controlArea, "Query Parameters")
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignRight)
        box.layout().addLayout(form)

        # --- Data source selector ---
        self._api_radio = QRadioButton("STRING API")
        self._file_radio = QRadioButton("Local file")

        self._api_radio.setChecked(self.data_source == "api")
        self._file_radio.setChecked(self.data_source == "file")

        self._api_radio.toggled.connect(self._on_source_changed)

        src_layout = QHBoxLayout()
        src_layout.addWidget(self._api_radio)
        src_layout.addWidget(self._file_radio)

        form.addRow("Data source:", src_layout)

        # --- File selector (shown only if "Local file" is selected) ---
        self._file_edit = gui.lineEdit(self.controlArea, self, "file_path")
        self._browse_btn = QPushButton("Browse")

        def browse():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select STRING file", "", "STRING files (*.gz *.txt)"
            )
            if path:
                self.file_path = path
                self._file_edit.setText(path)

        self._browse_btn.clicked.connect(browse)

        file_layout = QHBoxLayout()
        file_layout.addWidget(self._file_edit)
        file_layout.addWidget(self._browse_btn)

        form.addRow("File:", file_layout)

        # Path mode selector (absolute vs relative) — only relevant if file input is used
        self._path_cb = QComboBox()
        self._path_cb.addItems(["Absolute", "Relative to workflow"])
        self._path_cb.setCurrentIndex(0 if self.path_mode == "absolute" else 1)
        self._path_cb.currentIndexChanged.connect(
            lambda i: setattr(self, "path_mode", "absolute" if i == 0 else "relative")
        )

        form.addRow("Path mode:", self._path_cb)

        # Fields selector (for file input) — user can pick which columns to import
        self._fields_list = QListWidget()
        self._fields_list.setSelectionMode(QListWidget.MultiSelection)

        form.addRow("Fields:", self._fields_list)

        # Gene column selector
        self._col_cb = QComboBox()
        self._col_cb.setMinimumWidth(160)
        self._col_cb.currentIndexChanged.connect(self._on_col_changed)
        form.addRow("Gene ID column:", self._col_cb)

        self._strip_cb = QCheckBox("Extract only protein_id (remove Taxon.ENSP...)")
        self._strip_cb.setChecked(self.strip_protein_prefix)
        self._strip_cb.stateChanged.connect(
            lambda s: setattr(self, "strip_protein_prefix", bool(s))
        )

        form.addRow("", self._strip_cb)

        # Network type selector
        self._net_cb = QComboBox()
        for value, label in self.NETWORK_TYPES:
            self._net_cb.addItem(label, value)
        idx = next(
            (i for i, (v, _) in enumerate(self.NETWORK_TYPES) if v == self.network_type),
            0,
        )
        self._net_cb.setCurrentIndex(idx)
        self._net_cb.currentIndexChanged.connect(self._on_net_changed)
        form.addRow("Network type:", self._net_cb)

        # Species selector
        self._sp_cb = QComboBox()
        for taxid, name in self.SPECIES:
            self._sp_cb.addItem(name, taxid)
        sp_idx = next(
            (i for i, (t, _) in enumerate(self.SPECIES) if t == self.species_taxid),
            0,
        )
        self._sp_cb.setCurrentIndex(sp_idx)
        self._sp_cb.currentIndexChanged.connect(self._on_species_changed)
        form.addRow("Organism:", self._sp_cb)

        gui.separator(self.controlArea)

        # Query button
        self._query_btn = gui.button(
            self.controlArea, self, "Query STRING-DB",
            callback=self._run_query,
        )
        self._query_btn.setEnabled(False)

        gui.rubber(self.controlArea)

        # ---- Main area (status / summary) --------------------------------
        self._status_label = QLabel(
            "Connect a data table to get started.\n\n"
            "The widget will query STRING-DB and output\n"
            "an edge table: Source | Target | Score."
        )
        self._status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("padding: 12px; font-size: 13px;")
        self.mainArea.layout().addWidget(self._status_label)

        self._on_source_changed()

    # file resolution helper — returns absolute path based on current path mode
    def _resolve_path(self):
        path = self.file_path
        if self.path_mode == "relative":
            # relative to workflow (Orange stores cwd as workflow dir)
            return os.path.abspath(path)
        return path
    
    # helper to open files, transparently handling gzip if needed
    def _open_file(self, path):
        if path.endswith(".gz"):
            return gzip.open(path, "rt")
        return open(path, "r")
    
    # helper to parse STRING-DB space-delimited files
    def _parse_string_file(self, path):
        with self._open_file(path) as f:
            header = f.readline().strip().split()
            rows = []

            for line in f:
                parts = line.strip().split()
                if len(parts) != len(header):
                    continue
                rows.append(dict(zip(header, parts)))

        return header, rows
    
    def _load_file_schema(self):
        path = self._resolve_path()
        header, _ = self._parse_string_file(path)

        self._fields_list.clear()
        for h in header:
            self._fields_list.addItem(h)

    def _get_selected_fields(self):
        return [item.text() for item in self._fields_list.selectedItems()]
    
    def _strip_protein(self, pid):
        # 9606.ENSP00000000233 → 233
        try:
            return pid.split("ENSP")[-1].lstrip("0")
        except:
            return pid

    # ---------------------------------------------------------------- input handler
    @Inputs.data
    def set_data(self, data):
        self.Error.no_data.clear()
        self.Error.no_column.clear()
        self.Warning.no_genes.clear()

        self._data = data
        self._col_cb.blockSignals(True)
        self._col_cb.clear()

        if data is None:
            self._query_btn.setEnabled(False)
            self._status_label.setText("No input data.")
            self._col_cb.blockSignals(False)
            return

        # Populate column selector with string / categorical variables
        candidates = [
            var.name for var in data.domain.variables + data.domain.metas
            if isinstance(var, (Orange.data.StringVariable, Orange.data.DiscreteVariable))
        ]
        if not candidates:
            # Fall back to all variables
            candidates = [var.name for var in data.domain.variables + data.domain.metas]

        for name in candidates:
            self._col_cb.addItem(name, name)

        # Restore saved column or pick sensible default
        default_names = ["Gene Symbol", "Gene symbol", "gene_symbol",
                         "Symbol", "Entrez ID", "entrez_id", "GeneID"]
        restore_idx = 0
        if self.gene_col_name in candidates:
            restore_idx = candidates.index(self.gene_col_name)
        else:
            for d in default_names:
                if d in candidates:
                    restore_idx = candidates.index(d)
                    break

        self._col_cb.setCurrentIndex(restore_idx)
        self._col_cb.blockSignals(False)
        self.gene_col_name = candidates[restore_idx] if candidates else ""

        self._query_btn.setEnabled(bool(candidates))
        self._status_label.setText(
            f"Input table: {len(data)} rows × "
            f"{len(data.domain.variables) + len(data.domain.metas)} columns.\n"
            "Configure parameters and press 'Query STRING-DB'."
        )

    # ---------------------------------------------------------------- combo slots
    def _on_col_changed(self, idx):
        if idx >= 0:
            self.gene_col_name = self._col_cb.itemData(idx)

    def _on_net_changed(self, idx):
        if idx >= 0:
            self.network_type = self._net_cb.itemData(idx)

    def _on_species_changed(self, idx):
        if idx >= 0:
            self.species_taxid = self._sp_cb.itemData(idx)

    # ---------------------------------------------------------------- query
    def _run_query(self):
        self.Error.clear()
        self.Warning.clear()

        if self._data is None:
            self.Error.no_data()
            return

        # --- extract gene list -------------------------------------------
        domain = self._data.domain
        col_var = domain[self.gene_col_name] if self.gene_col_name in domain else None
        if col_var is None:
            self.Error.no_column()
            return

        col_idx = domain.index(col_var)
        if col_var in domain.metas:
            raw_col = self._data.metas[:, domain.metas.index(col_var)]
        else:
            raw_col = self._data.X[:, col_idx] if col_var in domain.attributes else \
                      self._data.Y[:, domain.class_vars.index(col_var)]

        genes = []
        for val in raw_col:
            if isinstance(val, float):
                # Discrete/numeric encoded — convert back via var.values
                if not (val != val):  # skip NaN
                    genes.append(col_var.values[int(val)] if hasattr(col_var, 'values') else str(int(val)))
            else:
                s = str(val).strip()
                if s and s.lower() not in ("nan", "?", ""):
                    genes.append(s)

        genes = list(dict.fromkeys(genes))  # deduplicate, preserve order

        if not genes:
            self.Warning.no_genes()
            return

        self._status_label.setText(
            f"Querying STRING-DB for {len(genes)} gene(s)…\n"
            f"Network: {self.network_type} | "
            f"Taxon: {self.species_taxid}"
        )
        self._query_btn.setEnabled(False)

        if self.data_source == "api":
            self._run_api_query(genes)
        else:
            self._run_file_query(genes)
        
    def _run_api_query(self, genes=None):
        if len(genes) > 2000:
            self.Warning.limit_exceeded()
            genes = genes[:2000]

        # --- start background worker ------------------------------------
        self._worker = _Worker(genes, self.species_taxid, self.network_type)
        self._worker.finished.connect(self._on_query_done)
        self._worker.errored.connect(self._on_query_error)
        self._worker.start()

    def _run_file_query(self, genes=None):
        path = self._resolve_path()

        if not path or not os.path.exists(path):
            self.Error.api_error("Invalid file path")
            return

        header, rows = self._parse_string_file(path)

        selected = self._get_selected_fields()
        if not selected:
            selected = header  # fallback

        # Build Orange domain dynamically
        metas = []
        for h in selected:
            metas.append(Orange.data.StringVariable(h))

        domain = Orange.data.Domain([], metas=metas)

        import numpy as np

        data = []
        for row in rows:
            entry = []
            for h in selected:
                val = row[h]

                if self.strip_protein_prefix and h in ("protein1", "protein2"):
                    val = self._strip_protein(val)

                entry.append(val)

            data.append(entry)

        table = Orange.data.Table.from_numpy(
            domain,
            X=np.empty((len(data), 0)),
            metas=np.array(data, dtype=object),
        )

        self.Outputs.network.send(table)
        self._status_label.setText(f"Loaded {len(data)} interactions from file.")    

    # ---------------------------------------------------------------- callbacks
    def _on_query_done(self, edges):
        self._query_btn.setEnabled(True)

        if not edges:
            self._status_label.setText("Query complete — no interactions found.")
            self.Outputs.network.send(None)
            return

        # Build Orange Table: source_name, target_name, combined_score
        domain = Orange.data.Domain(
            [],
            metas=[
                Orange.data.StringVariable("Source"),
                Orange.data.StringVariable("Target"),
                Orange.data.ContinuousVariable("Score"),
            ],
        )

        metas = []
        for edge in edges:
            src   = edge.get("preferredName_A", edge.get("stringId_A", ""))
            tgt   = edge.get("preferredName_B", edge.get("stringId_B", ""))
            score = float(edge.get("score", edge.get("escore", 0)))
            metas.append([src, tgt, score])

        import numpy as np
        table = Orange.data.Table.from_numpy(
            domain,
            X     = np.empty((len(metas), 0)),
            metas = np.array(metas, dtype=object),
        )

        self._status_label.setText(
            f"Done!  {len(edges)} interaction(s) found for "
            f"{len(set([e.get('preferredName_A','') for e in edges] + [e.get('preferredName_B','') for e in edges]))} "
            f"unique proteins.\n\n"
            f"Output columns: Source | Target | Score (0–1)"
        )
        self.Outputs.network.send(table)

    def _on_query_error(self, msg):
        self._query_btn.setEnabled(True)
        self.Error.api_error(msg)
        self._status_label.setText(f"Error:\n{msg}")
        self.Outputs.network.send(None)

    # ---------------------------------------------------------------- cleanup
    def onDeleteWidget(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        super().onDeleteWidget()

    def _on_source_changed(self):
        self.data_source = "api" if self._api_radio.isChecked() else "file"

        is_file = self.data_source == "file"

        self._file_edit.setEnabled(is_file)
        self._browse_btn.setEnabled(is_file)
        self._fields_list.setEnabled(is_file)
        self._strip_cb.setEnabled(is_file)

        if is_file and self.file_path:
            self._load_file_schema()

# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Build a tiny test table with gene symbols
    domain = Orange.data.Domain(
        [],
        metas=[Orange.data.StringVariable("Gene Symbol")],
    )
    import numpy as np
    demo_genes = [["TP53"], ["BRCA1"], ["EGFR"], ["MYC"], ["CDK2"]]
    table = Orange.data.Table.from_numpy(
        domain,
        X=np.empty((len(demo_genes), 0)),
        metas=np.array(demo_genes, dtype=object),
    )

    w = OWStringDB()
    w.set_data(table)
    w.show()
    sys.exit(app.exec_())
