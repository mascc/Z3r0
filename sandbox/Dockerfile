FROM golang:1.26-trixie AS go-builder

ENV CGO_ENABLED=0

WORKDIR /build/proxy

COPY proxy/go.mod ./
COPY proxy/main.go ./
RUN go build -trimpath -ldflags="-s -w" -o /out/sandbox-proxy .

FROM debian:trixie-slim AS novnc-assets

ARG DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends novnc; \
    mkdir -p /out; \
    cp -a /usr/share/novnc /out/novnc; \
    ln -sf vnc.html /out/novnc/index.html; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/* /var/tmp/*

FROM debian:trixie-slim AS dev-browser-assets

ARG DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    apt-get update; \
    apt-get install -y \
      --no-install-recommends \
      ca-certificates \
      nodejs \
      npm; \
    npm install -g --no-audit --no-fund dev-browser@latest; \
    dev-browser install; \
    npm cache clean --force; \
    mkdir -p /out/root /out/usr/local/bin /out/usr/local/lib/node_modules; \
    cp -a /root/.dev-browser /out/root/.dev-browser; \
    cp -a /root/.cache /out/root/.cache; \
    cp -a /usr/local/bin/dev-browser /out/usr/local/bin/dev-browser; \
    cp -a /usr/local/lib/node_modules/dev-browser /out/usr/local/lib/node_modules/dev-browser; \
    rm -rf /root/.npm /var/lib/apt/lists/* /var/cache/apt/* /tmp/* /var/tmp/*

FROM debian:trixie-slim

ENV HOME=/root \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DISPLAY=:0

ARG DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    printf '%s\n' \
      'path-exclude=/usr/share/doc/*' \
      'path-exclude=/usr/share/man/*' \
      'path-exclude=/usr/share/info/*' \
      'path-exclude=/usr/share/lintian/*' \
      'path-exclude=/usr/share/locale/*' \
      'path-include=/usr/share/locale/locale.alias' \
      > /etc/dpkg/dpkg.cfg.d/01_nodoc; \
    apt-get update; \
    apt-get install -y \
      --no-install-recommends \
      ca-certificates \
      curl \
      libasound2t64 \
      libatk-bridge2.0-0t64 \
      libatk1.0-0t64 \
      libcairo2 \
      libcups2t64 \
      libdbus-1-3 \
      libdrm2 \
      libgbm1 \
      libglib2.0-0t64 \
      libgtk-3-0t64 \
      libnspr4 \
      libnss3 \
      libpango-1.0-0 \
      libx11-6 \
      libxcb1 \
      libxcomposite1 \
      libxdamage1 \
      libxext6 \
      libxfixes3 \
      libxkbcommon0 \
      libxrandr2 \
      nodejs \
      npm \
      python3 \
      python3-pip \
      supervisor \
      websockify \
      wget \
      x11vnc \
      xvfb \
      fonts-droid-fallback; \
    mkdir -p /data; \
    apt-get clean; \
    rm -rf /root/.npm /var/lib/apt/lists/* /var/cache/apt/* /tmp/* /var/tmp/*

EXPOSE 8000

COPY --from=novnc-assets /out/novnc /usr/share/novnc
COPY --from=dev-browser-assets /out/root/.dev-browser /root/.dev-browser
COPY --from=dev-browser-assets /out/root/.cache /root/.cache
COPY --from=dev-browser-assets /out/usr/local/bin/dev-browser /usr/local/bin/dev-browser
COPY --from=dev-browser-assets /out/usr/local/lib/node_modules/dev-browser /usr/local/lib/node_modules/dev-browser
RUN set -eux; \
    chromium_binary="$(find /root/.cache /root/.dev-browser -type f \( -path '*/chrome-linux/chrome' -o -path '*/chrome-linux64/chrome' -o -name chromium -o -name chrome \) -perm /111 | sort | head -n 1)"; \
    if [ -z "$chromium_binary" ]; then \
      echo 'No Chromium binary found from dev-browser install. Executable candidates:'; \
      find /root/.cache /root/.dev-browser -maxdepth 6 -type f -perm /111 -print | sort; \
      exit 1; \
    fi; \
    "$chromium_binary" --version; \
    ln -sf "$chromium_binary" /usr/local/bin/dev-browser-chromium
COPY --from=go-builder --chmod=755 /out/sandbox-proxy /usr/local/bin/sandbox-proxy
COPY --chmod=755 entrypoint.sh /entrypoint.sh
COPY supervisord.conf /supervisord.conf
COPY .agents /root/.agents

ENTRYPOINT [ "/entrypoint.sh" ]
