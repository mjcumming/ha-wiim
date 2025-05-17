# .devcontainer/Dockerfile  (your slim layer)
FROM mcr.microsoft.com/devcontainers/python:1-3.13 

# create and pre-install tools in an isolated venv
RUN python -m venv /ha-venv && \
    /ha-venv/bin/pip install --upgrade pip && \
    /ha-venv/bin/pip install \
        homeassistant \
        ruff pytest pytest-asyncio pytest-homeassistant-custom-component

ENV PATH="/ha-venv/bin:${PATH}"
WORKDIR /workspaces/ha-wiim
