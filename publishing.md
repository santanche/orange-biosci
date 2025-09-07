# Publishing

~~~bash
pip install build twine
~~~

# Install build tools
~~~bash
pip install build twine
~~~

# Build the package
~~~bash
python -m build
~~~

# Check the build
~~~bash
twine check dist/*
~~~

# Upload to PyPI (for real)
~~~bash
twine upload dist/*
~~~