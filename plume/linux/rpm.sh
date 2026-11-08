#!/bin/sh
# The .rpm of Plume (noarch, Fedora's Qt): from the staged tree of stage.py.
# Usage: sh plume/linux/rpm.sh <stage dir> <out dir>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
stage=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
version=$(cat "$stage/version")
top=$(mktemp -d)
trap 'rm -rf "$top"' EXIT
rpmbuild -bb --quiet --define "_topdir $top" --define "plume_version $version" --define "plume_stage $stage" \
    --define "plume_desktop $here/eu.orneos.plume.desktop" "$here/orneos-plume.spec"
cp "$top"/RPMS/noarch/*.rpm "$out/"
ls -la "$out"/*.rpm
