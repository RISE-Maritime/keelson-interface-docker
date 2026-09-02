#!/usr/bin/env bash
#
# Regenerate the committed protobuf bindings for interfaces/ContainerControl.proto.
#
# The generated *_pb2.py / *_pb2.pyi are COMMITTED. This repo has no generation
# step between the working tree and its artifact -- the artifact is a `docker
# build` of the tree, and a dev checkout is `uv pip install -e .` -- so
# gitignoring them would mean either putting protoc in the image build or a repo
# that does not run after `git clone`. CI runs this script and then
# `git diff --exit-code` to catch drift from the .proto.
#
# No peer-import rewriting is needed here (cf. keelson's own
# sdks/python/generate_python.sh, whose portable GNU/BSD sed_inplace exists for
# exactly that): ContainerControl.proto imports only google/protobuf/timestamp.proto,
# which protoc emits as an absolute `from google.protobuf import timestamp_pb2`
# that already resolves.
set -euo pipefail

cd "$(dirname "$0")/.."

# Pinned exactly, and deliberately to the same generator keelson itself uses
# (its shipped stubs declare "Protobuf Python Version: 6.30.2"). protoc >= 5.27
# embeds its own version into the generated module's runtime-version gate, so an
# unpinned generator would make the CI drift check flap on every protoc release.
PROTOC_WHEEL="protoc-wheel-0==30.2"

OUT=src/keelson_interface_docker/interfaces
rm -f "$OUT"/ContainerControl_pb2.py "$OUT"/ContainerControl_pb2.pyi

# The registry has to travel inside the installed package -- app.py loads it
# with keelson.add_well_known_interfaces() at startup, and interfaces/ at the
# repo root does not exist in the image. Same move keelson's own
# generate_python.sh makes with subjects.yaml.
cp -f interfaces/interfaces.yaml "$OUT"/interfaces.yaml

uv run --no-project --with "$PROTOC_WHEEL" protoc \
    --python_out="$OUT" \
    --pyi_out="$OUT" \
    --proto_path=interfaces \
    interfaces/ContainerControl.proto

echo "Generated $OUT/ContainerControl_pb2.py"
