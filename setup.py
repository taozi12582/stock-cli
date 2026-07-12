from setuptools import setup, find_packages

setup(
    name="stock-cli",
    version="1.0.0",
    description="A股股票数据CLI - 行情+基本面上下文生成器",
    packages=find_packages(),
    install_requires=[
        "pymysql>=1.1.0",
    ],
    entry_points={
        "console_scripts": [
            "stock-cli=stock_cli.cli:main",
        ],
    },
    python_requires=">=3.8",
)
