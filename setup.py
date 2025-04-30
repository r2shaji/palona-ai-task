from setuptools import setup, find_packages

setup(
    name="palona-ai",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'flask',
        'python-dotenv',
        'openai',
        'pillow',
        'numpy',
        'faiss-cpu'
    ],
) 