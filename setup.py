from setuptools import setup

with open('README.md') as fp:
    longdesc = fp.read()

setup(
    name='lektor-groupby',
    packages=['lektor_groupby'],
    entry_points={
        'lektor.plugins': [
            'groupby = lektor_groupby:GroupByPlugin',
        ]
    },
    author='relikd',
    url='https://github.com/relikd/lektor-groupby-plugin',
    version='0.9.7',
    description='Cluster arbitrary records with field attribute keyword.',
    long_description=longdesc,
    long_description_content_type="text/markdown",
    license='MIT',
    python_requires='>=3.6',
    keywords=[
        'lektor',
        'plugin',
        'groupby',
        'grouping',
        'cluster',
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Environment :: Plugins',
        'Framework :: Lektor',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)
