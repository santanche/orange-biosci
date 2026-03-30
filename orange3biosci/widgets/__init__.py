from importlib.resources import files

# Widgets are registered by category. Let's put it in "Transform"
NAME = "BioSci"
DESCRIPTION = "Collection of Bio Science processing widgets."
ICON = str(files(__name__).parent / "icons" / "biosci-category-icon.svg")
BACKGROUND = "#9FFFBD"

PRIORITY = 3

WIDGETS = [
    # The class name and a friendly name for its menu entry
    'OWGeoPreprocessor',
    'OWGeoSoftExtractor',
    'OWElementsPairing',
    'OWSimpleTransposeTable',
    'OWCustomPivot',
    'OWListSplitter'
]

# The .py file where each widget is implemented
WIDGET_HELP_PATH = (
    # You can link to documentation here
)
