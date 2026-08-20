FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        gcc \
        git \
        libc6-dev \
        libgmp10 \
        libmpc3 \
        libmpfr6 \
        libzstd1 \
        python3 \
        python3-venv \
        tzdata \
        zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /workspace \
    && git config --system core.autocrlf true

COPY toolchain /opt/ap01-toolchain
COPY python-wheels /opt/python-wheels
COPY licenses /usr/share/doc/ap01-build-tools/licenses
COPY toolchain.sha256 /opt/toolchain.sha256
COPY check-tools.sh /usr/local/bin/ap01-check-tools
COPY container-entrypoint.sh /usr/local/bin/ap01-container-entrypoint

ENV PATH=/opt/ap01-toolchain/bin:/opt/ap01-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV PYTHONUTF8=1

RUN chmod -R a+rX /opt/ap01-toolchain /opt/python-wheels \
    && chmod 755 /opt/ap01-toolchain/bin/* \
    && find /opt/ap01-toolchain/libexec -type f -exec chmod 755 {} + \
    && sed -i 's/\r$//' /usr/local/bin/ap01-check-tools /usr/local/bin/ap01-container-entrypoint \
    && chmod 755 /usr/local/bin/ap01-check-tools /usr/local/bin/ap01-container-entrypoint \
    && mkdir -p /opt/ap01-toolchain/riscv64-unknown-elf/bin \
    && ln -s ../../bin/riscv64-elf-as /opt/ap01-toolchain/riscv64-unknown-elf/bin/as \
    && ln -s ../../bin/riscv64-elf-ld /opt/ap01-toolchain/riscv64-unknown-elf/bin/ld \
    && cd /opt/ap01-toolchain \
    && sha256sum --check /opt/toolchain.sha256 \
    && python3 -m venv /opt/ap01-venv \
    && /opt/ap01-venv/bin/python -m pip install \
        --no-index \
        --find-links=/opt/python-wheels \
        Pillow==12.2.0 \
        requests==2.34.2 \
    && rm -rf /opt/python-wheels \
    && /usr/local/bin/ap01-check-tools >/dev/null

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/ap01-container-entrypoint"]
