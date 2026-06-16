# Controller image: runs bbctl, tmux, Pi, and can launch Exegol containers via mounted Docker socket.
# Build: docker build -f docker/controller.Dockerfile -t bounty-pi-controller .
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git nodejs npm tmux docker-cli \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent

WORKDIR /workspace
COPY pyproject.toml README.md ./
COPY bbagent ./bbagent
COPY configs ./configs
COPY tasks ./tasks
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .

CMD ["bash"]
