"""Metadata for keynest."""

__all__ = [
    "__credits__",
    "__dependencies__",
    "__description__",
    "__keywords__",
    "__license__",
    "__readme__",
    "__requires_python__",
    "__status__",
    "__title__",
    "__version__",
]

__title__ = "keynest"
__version__ = "0.1.0"
__description__ = (
    "Developer secret workbench: a pure-Python keystore with GUI and CLI for OS keyring and AWS Secrets Manager"
)
__readme__ = "README.md"
__credits__ = [{"name": "Matthew Martin", "email": "matthewdeanmartin@gmail.com"}]
__keywords__ = [
    "secrets",
    "keyring",
    "aws",
    "secrets-manager",
    "credentials",
    "vault",
    "developer-tools",
    "cli",
    "gui",
    "tkinter",
]
__license__ = "MIT"
__requires_python__ = ">=3.11"
__status__ = "3 - Alpha"
__dependencies__ = ["keyring>=24.0.0", "boto3>=1.34.0"]
