# Controller image: runs bbctl, tmux, Pi, headless Ghidra + RE tooling, and can
# launch Exegol containers via mounted Docker socket.
# Build: docker build -f docker/controller.Dockerfile -t bounty-pi-controller .
# Self-contained agent: run this image and use `bbctl launch <task> --no-docker`
# so Pi runs here with Ghidra/gdb/binutils available in-container.
FROM python:3.12-slim

# uv is the default Python package manager for this project.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git nodejs npm tmux docker-cli \
    openjdk-17-jdk-headless unzip wget binutils file gdb \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent

# Headless Ghidra for scripts/ghidra-headless. Bump via build args; asset names
# live on https://github.com/NationalSecurityAgency/ghidra/releases
#   docker build --build-arg GHIDRA_VERSION=11.2.1 --build-arg GHIDRA_DATE=20241105 ...
ARG GHIDRA_VERSION=11.1.2
ARG GHIDRA_DATE=20240709
RUN wget -q -O /tmp/ghidra.zip \
      "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_DATE}.zip" \
 && unzip -q /tmp/ghidra.zip -d /opt \
 && rm /tmp/ghidra.zip \
 && ln -s "/opt/ghidra_${GHIDRA_VERSION}_PUBLIC" /opt/ghidra
ENV GHIDRA_HOME=/opt/ghidra
ENV PATH="/opt/ghidra/support:${PATH}"

WORKDIR /workspace
COPY pyproject.toml README.md ./
COPY bbagent ./bbagent
COPY configs ./configs
COPY tasks ./tasks
COPY scripts ./scripts
RUN uv pip install --system --no-cache -e .

CMD ["bash"]
