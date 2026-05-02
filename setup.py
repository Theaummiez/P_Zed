from setuptools import setup, find_packages

setup(
    name="jarvis",
    version="0.1.0",
    description="Local AI assistant — JARVIS-style, runs entirely on your machine.",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.27.0",
        "rich>=13.7.0",
        "prompt_toolkit>=3.0.43",
        "chromadb>=0.5.0",
        "duckduckgo-search>=6.1.0",
        "PyYAML>=6.0.1",
    ],
    entry_points={
        "console_scripts": [
            "jarvis=jarvis.main:main",
        ],
    },
)
