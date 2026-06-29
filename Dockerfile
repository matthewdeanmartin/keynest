FROM python:3.12-slim

LABEL maintainer="matthewdeanmartin@gmail.com"
LABEL description="Developer secret workbench: a pure-Python keystore with GUI and CLI for OS keyring and AWS Secrets Manager"

WORKDIR /app

# Non-root user for runtime isolation
RUN useradd --create-home --shell /bin/bash appuser

# Install the package as root so the venv is system-wide, then drop to appuser
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir keynest

# Drop privileges
USER appuser

# Default: show help.  Override CMD or pass arguments after the image name.
ENTRYPOINT ["keynest"]
CMD ["--help"]
