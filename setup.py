from setuptools import setup, find_packages
import os

this_directory = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

with open(
    os.path.join(this_directory, "copilotexport", "version"), encoding="utf-8"
) as f:
    version = f.read().strip()

setup(
    name="copilotexport",
    version=version,
    description="Export all VS Code GitHub Copilot Chat conversations to JSON and Markdown.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Josh XT",
    author_email="josh@devxt.com",
    url="https://github.com/Josh-XT/copilotexport",
    packages=find_packages(),
    package_data={"copilotexport": ["version"]},
    python_requires=">=3.10",
    install_requires=[],
    entry_points={
        "console_scripts": ["copilotexport=copilotexport.cli:main"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Utilities",
    ],
)
