# This deliverable is considered developed content as defined in contract between BDF parties.


"""Setup script for fix_values package."""

from pathlib import Path

from setuptools import find_namespace_packages, setup

# Read requirements
REQUIREMENTS = Path(__file__).parent / "requirements.txt"
with open(REQUIREMENTS) as f:
    required = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read long description
README = Path(__file__).parent / "README.md"
with open(README, encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="genai-curator-fix-values",
    version="0.1.0",
    description="Metadata correction pipeline using ML/NLP techniques",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Sage Bionetworks BDF Curator Team",
    url="https://github.com/sage-bdf/genai-curator/genai-curator",
    packages=find_namespace_packages(include=["genai_curator.*"]),
    package_data={"fix_values": ["py.typed"]},
    python_requires=">=3.9",
    install_requires=required,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "mypy>=1.0.0",
            "pandas-stubs>=2.0.0.230412",
            "types-PyYAML>=6.0.0",
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Typing :: Typed",
    ],
)
