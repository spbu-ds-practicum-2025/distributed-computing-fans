FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App files (includes static/ and templates/)
COPY . .

# Build a single-file Yjs bundle for the browser (no CDN at runtime).
# This produces /app/static/yjs.umd.js that exposes window.Y
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates     && rm -rf /var/lib/apt/lists/*     && mkdir -p /tmp/yjsbuild     && cd /tmp/yjsbuild     && npm init -y     && npm install yjs@13.6.28 rollup @rollup/plugin-node-resolve     && cat > rollup.config.mjs <<'EOF'
import resolve from '@rollup/plugin-node-resolve';

export default {
  input: 'node_modules/yjs/dist/yjs.mjs',
  plugins: [resolve({ browser: true })],
  output: {
    file: '/app/static/yjs.umd.js',
    format: 'umd',
    name: 'Y'
  }
};
EOF
RUN cd /tmp/yjsbuild && npx rollup -c rollup.config.mjs

ENV FLASK_APP=main.py
ENV FLASK_RUN_PORT=8080

CMD ["flask", "run", "--host", "0.0.0.0", "--port", "8080"]
