from setuptools import setup, find_packages

setup(
    name='common_tools',
    version='0.1',
    description='Common tools for AI and generic needs on file, console, json, ...',
    author='Etienne Millerioux',
    author_email='eemillerioux@gmail.com',  # Replace with your email
    url='https://github.com/festnoze/common_tools',  # Replace with your project URL
    packages=find_packages(),
    install_requires=[
        'requests',
        'pydantic',
        'langchain',
        'langchain-experimental',
        'langgraph',
        'langsmith',
        'openai',
        'groq'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    include_package_data=True,
)