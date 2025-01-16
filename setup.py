#!/usr/bin/env python3

import os
from setuptools import setup, find_packages, find_namespace_packages

VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION.txt")

setup(
    name="mtsql",
    description="Extra Python modules to deal with the interaction between pandas dataframes and remote SQL servers, for Minh-Tri Pham",
    author=["Minh-Tri Pham"],
    packages=find_packages() + find_namespace_packages(include=["mt.*"]),
    install_requires=[
        "sqlalchemy",  # for psql access
        "tzlocal",  # for getting the local timezone
        "tqdm",  # for a nice progress bar
        "psycopg[binary]",  # for psql access, and to upgrade to psycopg3
        # 'mysql', # for mysql access
        "mtbase>=4.27.4",  # to have mt.halo
        "mtpandas>=1.15",  # just updating
    ],
    url="https://github.com/inteplus/mtsql",
    project_urls={
        "Documentation": "https://mtdoc.readthedocs.io/en/latest/mt.sql/mt.sql.html",
        "Source Code": "https://github.com/inteplus/mtsql",
    },
    setup_requires=["setuptools-git-versioning<2"],
    setuptools_git_versioning={
        "enabled": True,
        "version_file": VERSION_FILE,
        "count_commits_from_version_file": True,
        "template": "{tag}",
        "dev_template": "{tag}.dev{ccount}+{branch}",
        "dirty_template": "{tag}.post{ccount}",
    },
)
