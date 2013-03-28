#!/usr/bin/python
import setuptools

setuptools.setup(
    name='papertrail',
    version='0.1.0',
    packages=setuptools.find_packages(),
    dependency_links=[
        'https://github.com/shlomozippel/django-apptemplates/tarball/master#egg=django-apptemplates-custom'
        ],
    install_requires=[
        'django-jsonfield>=0.8.11',
        'django-apptemplates==custom',
        ]
)
