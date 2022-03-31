from setuptools import setup

setup(
    name='lektor-simple',
    py_modules=['lektor_simple'],
    version='1.0',
    entry_points={
        'lektor.plugins': [
            'simple = lektor_simple:SimpleGroupByPlugin',
        ]
    }
)
