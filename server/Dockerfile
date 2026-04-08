FROM python:3.11-slim

# Install git for cloning KiCad libraries
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Download KiCad symbol and footprint libraries (shallow clone to save space)
RUN git clone --depth 1 https://gitlab.com/kicad/libraries/kicad-symbols.git /opt/kicad/symbols && \
    git clone --depth 1 https://gitlab.com/kicad/libraries/kicad-footprints.git /opt/kicad/footprints && \
    rm -rf /opt/kicad/symbols/.git /opt/kicad/footprints/.git

ENV KICAD8_SYMBOL_DIR=/opt/kicad/symbols

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code - directory name must be ds2kicad for Python imports
COPY . /opt/ds2kicad/

WORKDIR /opt/ds2kicad

# Create cache directory
RUN mkdir -p /opt/ds2kicad/cache

ENV DS2KICAD_STANDALONE=1
ENV PORT=8000

EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
