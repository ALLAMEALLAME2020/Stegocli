from setuptools import setup, find_packages

setup(
    name="stegocli",
    version="1.0.0",
    description="Production-grade steganography: hide files inside PNG/BMP images",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["Pillow>=9.0", "cryptography>=38.0"],
    entry_points={
        "console_scripts": ["stegocli=stegocli.cli.main:main"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
