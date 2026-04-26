FROM python:3.11-slim

# Install tkinter and other dependencies
RUN apt-get update && apt-get install -y \
    python3-tk \
    curl \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Download the Cloudflare speed test CLI binary for Linux x86_64
RUN curl -L -o /tmp/cloudflare-speed-cli.tar.xz \
    https://github.com/kavehtehrani/cloudflare-speed-cli/releases/download/v0.6.6/cloudflare-speed-cli-x86_64-unknown-linux-musl.tar.xz \
    && tar -xJf /tmp/cloudflare-speed-cli.tar.xz -C /usr/local/bin --strip-components=1 \
    && chmod +x /usr/local/bin/cloudflare-speed-cli \
    && rm -rf /tmp/cloudflare-speed-cli.tar.xz

# Copy your script
COPY speed_test_gui.py .

# Run the Python script
CMD ["python", "speed_test_gui.py"]