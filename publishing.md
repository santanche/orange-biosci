# Publishing

# Install build tools
~~~bash
pip install build twine
~~~

# Build the package
~~~bash
python3 -m build
~~~

# Upload to PyPI (for real)
~~~bash
twine upload dist/*
~~~

# Check the build
~~~bash
twine check dist/*
~~~
