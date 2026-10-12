FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev libcmocka-dev python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 runner

COPY executor.py /opt/runner/executor.py
COPY entrypoint.sh /opt/runner/entrypoint.sh
COPY cmocka_compat.h /opt/runner/cmocka_compat.h
RUN chmod 0555 /opt/runner/entrypoint.sh /opt/runner/executor.py /opt/runner/cmocka_compat.h
USER runner
ENTRYPOINT ["/opt/runner/entrypoint.sh"]

