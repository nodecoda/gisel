# syntax=docker/dockerfile:1
# The image is built from this checkout, so its `gisel` is always the commit
# that built it.  The companions come from PyPI: they are versioned
# independently and the arm's length dependency is what a user gets.
FROM python:3.12-slim

# Bump these two together with the cohort that publishes them; `gisel-ab`
# 0.9.0 requires `gisel>=0.3,<0.4`, which the local install satisfies.
ARG ANCHOR_VERSION=0.2.0
ARG AB_VERSION=0.9.0

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY gisel ./gisel
RUN python -m pip install --no-cache-dir . \
 && python -m pip install --no-cache-dir \
        "gisel-anchor==${ANCHOR_VERSION}" "gisel-ab==${AB_VERSION}" \
 && gisel --version \
 && gisel-anchor --version \
 && gisel-ab --version \
 && gisel doctor

WORKDIR /work
# `doctor` at build time already proves the data files shipped; the default
# command repeats it for whoever runs the image, in one screen.
CMD ["gisel", "doctor"]
