from setuptools import setup, find_packages

######################################################################
## To install/update the below listed dependencies globally,
#  run the following command as admin in a python terminal:
# senv\Scripts\activate
# pip install -e . --upgrade
######################################################################

setup(
    name='common_tools',
    version='0.4.0',
    description='Common tools for AI and generic needs on file, console, json, ...',
    author='Etienne Millerioux',
    author_email='eemillerioux@gmail.com',  # Replace with your email
    url='https://github.com/festnoze/common_tools',
    packages=find_packages(),
    install_requires=[
        'python-dotenv',
        'requests',
        'pandas',
        'pydantic',
        'rank-bm25',
        'langchain>=0.3.3',
        'langchain-core>=0.3.12',
        'langchain-community>=0.3.2',
        'langchain-experimental>=0.3.2',
        'langchain-openai>=0.2.2',
        'langchain-groq>=0.2.0',
        'protobuf==4.25.1',
        'langchain-chroma>=0.1.4',
        'langchain-ollama>=0.1.0',
        'langchain-anthropic>=0.2.4',
        'langchain-qdrant>=0.1.0',
        'qdrant-client',
        'pinecone-client==5.0.1',
        'pinecone-plugin-inference==1.1.0',
        'pinecone==5.0.1',
        'langgraph>=0.2.38',
        'langsmith>=0.1.136',
        'ragas>=0.2.5',
        'openai>=1.52.0',
        'ollama',
        'groq',
        'pyyaml',
        'lark',  # needed for langchain 'self-querying' retriever
        'scikit-learn',
        'scipy',
        # 'prefect',  # Uncomment if needed for advanced workflows management
        # 'sentence-transformers>=3.2.0',  # Uncomment to add as new LLM models' provider
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    include_package_data=True,
    package_data={        
        # If any folder contains ressources files (which are not python files, like *.txt files), reference those folders here to include them into the 'common_tools' package:
        'common_tools.prompts': ['**/*'],
        'common_tools.rag.configs': ['**/*']
    }
)