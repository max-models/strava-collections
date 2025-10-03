# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import shutil


def copy_html_files(app):
    src = os.path.abspath("source/")
    dst = os.path.abspath("source/_static")
    if os.path.exists(src):
        for fname in os.listdir(src):
            if fname.endswith(".html"):
                shutil.copy(os.path.join(src, fname), dst)


def setup(app):
    app.connect("builder-inited", copy_html_files)
    # app.add_stylesheet("my-styles.css")
    app.add_css_file("custom.css")


# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Max runs and rides"
copyright = "2025, Max"
author = "Max"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "nbsphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "myst_parser",  # enable Markdown support
]

exclude_patterns = []

# Recognize both .rst and .md
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Activate the theme.
html_theme = "sphinx_book_theme"


html_static_path = ["_static"]
templates_path = ["_templates"]


# html_sidebars = {"**": []}

html_theme_options = {
    "repository_branch": "devel",
    "show_toc_level": 3,
    "secondary_sidebar_items": ["page-toc"],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/max-models/strava-collections",
            "icon": "fab fa-github",
            "type": "fontawesome",
        },
    ],
}
