FROM postgres:17-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV GIT_CONFIG_COUNT=1
ENV GIT_CONFIG_KEY_0="safe.directory"
ENV GIT_CONFIG_VALUE_0="*"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        ca-certificates \
        flex \
        bison \
        postgresql-server-dev-17 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git /tmp/pgvector && \
    cd /tmp/pgvector && \
    make && \
    make install && \
    rm -rf /tmp/pgvector

RUN git clone --branch PG17/v1.6.0-rc0 https://github.com/apache/age.git /tmp/age && \
    cd /tmp/age && \
    make && \
    make install && \
    rm -rf /tmp/age

FROM postgres:17-bookworm

COPY --from=builder /usr/lib/postgresql/17/lib/vector.so /usr/lib/postgresql/17/lib/vector.so
COPY --from=builder /usr/lib/postgresql/17/lib/age.so /usr/lib/postgresql/17/lib/age.so
COPY --from=builder /usr/lib/postgresql/17/lib/bitcode/ /usr/lib/postgresql/17/lib/bitcode/
COPY --from=builder /usr/share/postgresql/17/extension/vector* /usr/share/postgresql/17/extension/
COPY --from=builder /usr/share/postgresql/17/extension/age* /usr/share/postgresql/17/extension/

COPY init-extensions.sh /docker-entrypoint-initdb.d/

LABEL maintainer="Voproshalych" \
      description="PostgreSQL 17 with pgvector and Apache AGE extensions" \
      pgvector="0.8.1" \
      apache_age="1.6.0"

EXPOSE 5432