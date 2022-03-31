from setuptools import setup

setup(
    name='lektor-advanced',
    py_modules=['lektor_advanced'],
    version='1.0',
    entry_points={
        'lektor.plugins': [
            'advanced = lektor_advanced:AdvancedGroupByPlugin',
        ]
    }
)
