"""
Stellar DEX Connector for Hummingbot
====================================
A fully integrated connector enabling algorithmic trading on the Stellar
Decentralized Exchange (DEX) through the Hummingbot framework.

Uses Stellar RPC for network interactions.
Supports channel accounts for parallel transaction submission.
"""

from setuptools import find_packages, setup

setup(
    name="hummingbot-stellar-connector",
    version="1.0.0",
    description="Stellar DEX connector for Hummingbot algorithmic trading framework",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Stellar Hummingbot Integration Team",
    license="Apache-2.0",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "hummingbot>=2.0.0",
        "stellar-sdk>=10.0.0",
        "aiohttp>=3.9.0",
        "pydantic>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "pytest-cov>=4.0",
            "aioresponses>=0.7",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
)
