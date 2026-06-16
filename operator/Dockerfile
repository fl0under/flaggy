# Flaggy operator image: Exegol + Terminus/Harbor-friendly defaults.
#
# Build this ONCE and reuse it everywhere instead of rebuilding a ~30-50GB
# image per task:
#   - as the agent environment for Harbor runs, via task.toml
#     `[environment].docker_image` (flaggy export --docker-image),
#   - as the interactive workbench, via `flaggy interactive --image`.
#
# Reproducibility: `full` is a moving tag. For eval/RL runs pin a digest, e.g.
#   FROM nwodtuhs/exegol@sha256:<digest>
# and rebuild deliberately.
ARG EXEGOL_TAG=full
FROM nwodtuhs/exegol:${EXEGOL_TAG}

# --- Terminus / Harbor compatibility ----------------------------------------
# Exegol's default ENTRYPOINT is built for the `exegol` wrapper (spawn protocol,
# my-resources, tmux bootstrap). Harbor boots the container and `exec`s into it,
# so neutralise the wrapper entrypoint and keep PID 1 alive and quiet.
ENTRYPOINT []
CMD ["sleep", "infinity"]

# Terminus interacts purely by screen-scraping a tmux pane. Exegol defaults to
# zsh + a heavy Powerlevel10k prompt, which adds visual noise and non-determinism
# to the scraped screen. Force a clean bash shell with a minimal, fixed prompt.
ENV SHELL=/bin/bash \
    TERM=xterm-256color \
    DEBIAN_FRONTEND=noninteractive
RUN printf '\n# flaggy: deterministic prompt for Terminus screen-scraping\nexport PS1="$ "\n' >> /etc/bash.bashrc \
 && printf '\n# flaggy: deterministic prompt for Terminus screen-scraping\nexport PS1="$ "\n' >> /root/.bashrc

WORKDIR /app

# Fail the build loudly if the base ever stops shipping the tools Terminus needs.
RUN command -v tmux >/dev/null && command -v bash >/dev/null \
 || (echo "operator image missing tmux/bash" >&2; exit 1)

# --- Your extra tooling -----------------------------------------------------
# Layer task-specific tools on top of Exegol here. Examples:
#   RUN apt-get update && apt-get install -y --no-install-recommends <pkg> \
#       && rm -rf /var/lib/apt/lists/*
#   RUN pipx install <tool>
# Keep this block last so edits don't bust the cache for the heavy base layers.
