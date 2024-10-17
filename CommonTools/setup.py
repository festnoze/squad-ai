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
        'python-dotenv',
        'requests',
        'pydantic',
        'langchain>=0.3.3',
        'langchain-core>=0.3.12',
        'langchain-community>=0.3.2',
        'langchain-experimental>=0.3.2',
        'langchain-openai>=0.2.2',
        'langchain-groq>=0.2.0',
        'langchain-chroma>=0.1.4',
        'langgraph>=0.2.38',
        'langsmith>=0.1.136',
        'openai>=1.52.0',
        'ollama',
        'groq',
        'pyyaml',
        'ragas>=0.2.1',
        'lark',  # needed for langchain self-querying retriever
        # 'prefect',  # Uncomment if needed
        # 'sentence-transformers>=3.2.0',  # Uncomment if needed
        'rank-bm25'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    include_package_data=True,
    package_data={
    },
)