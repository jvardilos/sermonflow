.PHONY: proto setup run clean

# Compile ProPresenter7 and Google wrapper proto files into Python classes.
# Must be run once after cloning, inside the activated venv.
proto:
	mkdir -p pco_types/google/protobuf
	python -m grpc_tools.protoc \
		--proto_path=ProPresenter7-Proto/proto \
		--python_out=. \
		ProPresenter7-Proto/proto/*.proto
	python -m grpc_tools.protoc \
		--proto_path=ProPresenter7-Proto/proto \
		--python_out=./pco_types \
		ProPresenter7-Proto/proto/google/protobuf/wrappers.proto

# Create venv and install all dependencies.
setup:
	python3 -m venv deps
	deps/bin/pip install --upgrade pip
	deps/bin/pip install -r requirements.txt

# Run the full pipeline (edit SERVICE_TYPE to match your PCO service type name).
SERVICE_TYPE ?= Weekend
run:
	deps/bin/python pipeline.py --skip-review --service-type "$(SERVICE_TYPE)"

# Run without Google Docs (no sermon slides).
run-no-gdocs:
	deps/bin/python pipeline.py --skip-review --skip-gdocs --service-type "$(SERVICE_TYPE)"

# Generate review PDF from the last fetched schema without re-running the pipeline.
pdf:
	deps/bin/python pipeline.py --pdf-only --schema service_schema.json

# Remove generated protobuf Python files and cached token.
clean:
	rm -f propresenter_pb2*.py
	rm -rf pco_types
	rm -f token.json
