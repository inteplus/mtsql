#!/usr/bin/env python3

from setuptools import setup, find_packages, find_namespace_packages
from mt.sql.version import VERSION

setup(
    name='mtsql',
    version=VERSION,
    description="Extra Python modules to deal with the interaction between pandas dataframes and remote SQL servers, for Minh-Tri Pham",
    author=["Minh-Tri Pham"],
    packages=find_packages() + find_namespace_packages(include=['mt.*']),
    install_requires=[
        'sqlalchemy',  # for psql access
        'tzlocal',  # for getting the local timezone
        'tqdm',  # for a nice progress bar
        'psycopg2-binary',  # for psql access
        # 'mysql', # for mysql access
        'mtpandas>=0.2.1',
    ],
    url='https://github.com/inteplus/mtsql',
    project_urls={
        'Documentation': 'https://mtdoc.readthedocs.io/en/latest/mt.sql/mt.sql.html',
        'Source Code': 'https://github.com/inteplus/mtsql',
    }
)
