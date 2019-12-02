#!/usr/bin/env python

import os.path
from setuptools import setup

setup(
    name = 'NewTitleIndex',
    packages = ['newtitleindex'],
    version = '0.11.1',

    author = 'Telminov Ilya',
    author_email = 'boeing568@gmail.com',
    description = '',
    long_description = open(os.path.join(os.path.dirname(__file__), 'README')).read(),
    keywords = '0.11 newtitleindex telminov macro wiki',
    url = 'http://trac-hacks.org/wiki/NewTitleIndex',
    license = 'BSD',

    entry_points = { 'trac.plugins': [ 'newtitleindex.macro = newtitleindex.macro' ] },
    classifiers = ['Framework :: Trac'],
    install_requires = ['Trac'],
    zip_safe = False,
)
