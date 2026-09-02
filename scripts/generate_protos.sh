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
rm -f "$OUT"/ContainerControl_pb2.py "$OUT"/ContainerControl_pb2.pyi "$OUT"/ContainerControl.desc

# The registries have to travel inside the installed package -- app.py loads
# them with keelson.add_well_known_interfaces() and
# keelson.add_well_known_subjects_and_proto_definitions() at startup, and
# interfaces/ at the repo root does not exist in the image. Same move keelson's
# own generate_python.sh makes with subjects.yaml.
#
# Both are listed in pyproject.toml's [tool.setuptools.package-data]. A file
# copied here but not listed there is present in a dev checkout and ABSENT from
# the image, which fails at startup and nowhere earlier.
cp -f interfaces/interfaces.yaml "$OUT"/interfaces.yaml
cp -f interfaces/subjects.yaml "$OUT"/subjects.yaml

uv run --no-project --with "$PROTOC_WHEEL" protoc \
    --python_out="$OUT" \
    --pyi_out="$OUT" \
    --descriptor_set_out="$OUT/ContainerControl.desc" \
    --include_imports \
    --proto_path=interfaces \
    interfaces/ContainerControl.proto

# --include_imports is load-bearing, not tidiness.
# add_well_known_subjects_and_proto_definitions() builds a FRESH, EMPTY
# DescriptorPool (message_factory.GetMessages -> DescriptorPool()), so nothing
# is resolvable from the default pool. Without the imports embedded,
# google/protobuf/timestamp.proto is missing and building ContainerHostStatus
# raises at startup. The fresh pool is also why this does not clash with
# ContainerControl_pb2's own registration in the default pool -- and why the
# class it yields is a DIFFERENT object: publish with the _pb2 class, not the
# registry's.

echo "Generated $OUT/ContainerControl_pb2.py and $OUT/ContainerControl.desc"
