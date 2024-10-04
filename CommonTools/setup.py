from setuptools import setup, find_packages

setup(
    name='common_tools',
    version='0.1',
    description='Common tools for AI and generic needs on file, console, json, ...',
    author='Etienne Millerioux',
    author_email='eemillerioux@gmail.com',  # Replace with your email
    url='https://github.com/festnoze/common_tools',
    packages=find_packages(),
    install_requires=[
        'requests',
        'pydantic',
        'langchain',
        'langchain-experimental',
        'langchain-openai',
        'langchain-community',
        'langchain-groq',
        'langchain-chroma',
        'langgraph',
        'langsmith',
        'openai',
        'groq',
        'yaml'
        #'prefect',
        #'sentence-transformers',
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    include_package_data=True,
    package_data={
        'common_prompts': ['prompts/*.txt'],  # Include all prompts files as ressources
    },
)