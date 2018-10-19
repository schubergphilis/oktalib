#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
try:
    from pipenv.project import Project
    from pipenv.utils import convert_deps_to_pip

    pfile = Project().parsed_pipfile
    requirements = convert_deps_to_pip(pfile['packages'], r=False)
    test_requirements = convert_deps_to_pip(pfile['dev-packages'], r=False)
except ImportError:
    # get the requirements from the requirements.txt
    requirements = [line.strip()
                    for line in open('requirements.txt').readlines()
                    if line.strip() and not line.startswith('#')]
    # get the test requirements from the test_requirements.txt
    test_requirements = [line.strip()
                         for line in
                         open('dev-requirements.txt').readlines()
                         if line.strip() and not line.startswith('#')]

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')
version = open('.VERSION').read()


setup(
    name='''oktalib''',
    version=version,
    description='''A library to interface with okta through it's restful api''',
    long_description=readme + '\n\n' + history,
    author='''Costas Tyfoxylos''',
    author_email='''ctyfoxylos@schubergphilis.com''',
    url='''https://github.com/schubergphilis/oktalib.git''',
    packages=find_packages(where='.', exclude=('tests', 'hooks')),
    package_dir={'''oktalib''':
                 '''oktalib'''},
    include_package_data=True,
    install_requires=requirements,
    license='MIT',
    zip_safe=False,
    keywords='''oktalib okta api python rest''',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    data_files=[('', ['.VERSION',
                      'LICENSE',
                      'AUTHORS.rst',
                      'CONTRIBUTING.rst',
                      'HISTORY.rst',
                      'README.rst',
                      'USAGE.rst',
                      'Pipfile',
                      'Pipfile.lock',
                      'requirements.txt',
                      'dev-requirements.txt']),
                ]
)
