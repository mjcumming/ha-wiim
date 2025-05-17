# .devcontainer/Dockerfile  – final version
FROM mcr.microsoft.com/devcontainers/python:1-3.13

# Create the venv as root, then hand ownership to uid 1000
RUN python -m venv /ha-venv && \
    chown -R 1000:1000 /ha-venv

# Switch to the regular (devcontainer default) user
USER 1000

# Now install everything as that user
RUN /ha-venv/bin/pip install --upgrade pip && \
    /ha-venv/bin/pip install \
        homeassistant \
        ruff pytest pytest-asyncio pytest-homeassistant-custom-component

ENV PATH="/ha-venv/bin:${PATH}"
WORKDIR /workspaces/ha-wiim
