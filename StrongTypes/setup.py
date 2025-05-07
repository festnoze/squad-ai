import os
from setuptools import setup, find_packages

setup(
    name="strong-types",
    # HOW TO USE: in cmd, u can do: 'set BUILD_VERSION=0.x.xx' to override the version to be built.
    version=os.environ.get('BUILD_VERSION', '0.1.0'), 
    description="Static and dynamic type checker for Python using enforce and AST analysis",
    author="Étienne Millerioux",    
    author_email='eemillerioux@gmail.com',
    license="MIT",
    python_requires=">=3.9",
    install_requires=[
        "enforce>=0.5.4",
        "pytest>=7.0"
    ],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    url="https://github.com/festnoze/strong-types",
    project_urls={
        "Homepage": "https://github.com/festnoze/strong-types",
        "Repository": "https://github.com/festnoze/strong-types"
    },
    readme="README.md",
)
