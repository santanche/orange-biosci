# setup.py
from setuptools import setup, find_packages

NAME = 'orange-biosci'
VERSION = '0.1.0'
DESCRIPTION = 'Custom Orange Bio Sci Widgets'
AUTHOR = 'André Santanchè'
URL = 'https://github.com/santanche/orange-biosci'
LICENSE = 'LGPL-2.1-or-later'

setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    author=AUTHOR,
    url=URL,
    license=LICENSE,
    packages=find_packages(),
    package_data={
        # Include any icons or other resources
        'orangewidgets': ['icons/*.svg', 'icons/*.png'],
    },
    entry_points={
        # This is the crucial part that tells Orange about your widgets
        'orange3.addon': (
            'mywidgets = orange3biosci',  # Replace 'orangewidgets' with your package name
        ),
        'orange.widgets': (
            # Point to your widget category definition
            'My Custom Widgets = orange3biosci.widgets',
        ),
    },
    install_requires=[
        'orange3>=3.32.0',  # Specify Orange version requirement
    ],
    classifiers=[
        'Framework :: Orange',
        'License :: OSI Approved :: GNU Lesser General Public License v2.1 or later (LGPLv2.1+)',
        'Programming Language :: Python :: 3',
        'Topic :: Scientific/Engineering :: Visualization',
        'Topic :: Scientific/Engineering :: Information Analysis',
    ],
    keywords=[
        'orange3',
        'bioinformatics',
        'geo',
        'gene expression'
    ],
)
