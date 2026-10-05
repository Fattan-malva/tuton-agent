FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    ripgrep \
    libgl1 \
    libglib2.0-0 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000


# opencode dipasang via bind-mount /usr/lib/node_modules/@opencode/cli saat runtime;
# buat symlink-nya lebih awal supaya `which opencode` ketemu di dalam container.
RUN ln -sf /usr/lib/node_modules/@opencode/cli/bin/opencode.exe /usr/local/bin/opencode

CMD ["python", "-u", "server.py"]
