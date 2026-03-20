from setuptools import setup, find_packages

setup(
    name="aidownloader",
    version="1.0.0",
    description="Batch download videos from TikTok, Douyin, Facebook Reels & YouTube Shorts via Excel input",
    author="donbach",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "yt-dlp>=2024.1.0",
        "openpyxl>=3.1.0",
        "rich>=13.7.0",
    ],
    entry_points={
        "console_scripts": [
            "aidownloader=downloader.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
