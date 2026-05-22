FROM python:3.12-slim

WORKDIR /app

# Install git (needed if pulling proto submodule at build time)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proto files and generated Python classes
COPY ProPresenter7-Proto/ ProPresenter7-Proto/
RUN mkdir -p pco_types/google/protobuf && \
    python -m grpc_tools.protoc \
        --proto_path=ProPresenter7-Proto/proto \
        --python_out=. \
        ProPresenter7-Proto/proto/*.proto && \
    python -m grpc_tools.protoc \
        --proto_path=ProPresenter7-Proto/proto \
        --python_out=./pco_types \
        ProPresenter7-Proto/proto/google/protobuf/wrappers.proto

# Application source
COPY pipeline.py pco.py ai.py gdocs.py pp7.py review.py ./

# Required — set these at runtime via -e flags or a .env file
ENV PCO_ID=""
ENV PCO_SECRET=""
ENV ANTHROPIC_API_KEY=""
ENV GDOCS_DOC_ID=""
ENV PP7_OUTPUT_DIR="/output"

# Optional email review
ENV REVIEW_EMAIL_TO=""
ENV SMTP_HOST=""
ENV SMTP_PORT="587"
ENV SMTP_USER=""
ENV SMTP_PASSWORD=""

# Mount /output to retrieve generated .pro files
VOLUME ["/output"]

# Google OAuth credentials must be mounted at runtime:
#   docker run -v ./credentials.json:/app/credentials.json ...
# token.json is written here on first run — mount a volume to persist it:
#   docker run -v ./token.json:/app/token.json ...

ENTRYPOINT ["python", "pipeline.py"]
CMD ["--skip-review", "--service-type", "Weekend"]
