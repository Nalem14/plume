#!/bin/sh
# Plume for Linux, from the PyInstaller folder (plume.spec): the AppImage (any distribution, updates itself) and
# the .deb (Debian, Ubuntu; updates offered to the system's installer). The .rpm is rpm.sh (Fedora's Qt).
# Usage: sh plume/linux/build.sh <dist/Plume> <out dir> <version>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
bundle=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
version=$3
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
svg="$bundle/_internal/icons/hicolor/scalable/apps/eu.orneos.plume.svg"

# ---- AppImage (appimagetool pinned by its checksum; our mirror first — GitHub often 504s on CI)
tool="$work/appimagetool"
sum=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
fetch() { curl -fsSL --retry 5 --retry-all-errors --retry-delay 3 -o "$tool" "$1"; }
fetch https://orneos.eu/downloads/tools/appimagetool-x86_64.AppImage \
  || fetch https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
echo "$sum  $tool" | sha256sum -c --quiet
chmod +x "$tool"
app="$work/Plume.AppDir"
mkdir -p "$app/usr/lib" "$app/usr/share/icons/hicolor/scalable/apps" "$app/usr/share/applications"
cp -a "$bundle" "$app/usr/lib/plume"
cp "$svg" "$app/usr/share/icons/hicolor/scalable/apps/"
cp "$svg" "$app/eu.orneos.plume.svg"
cp "$svg" "$app/.DirIcon"
cp "$here/eu.orneos.plume.desktop" "$app/"
cp "$here/eu.orneos.plume.desktop" "$app/usr/share/applications/"
cat > "$app/AppRun" <<'RUN'
#!/bin/sh
here=$(dirname "$(readlink -f "$0")")
exec "$here/usr/lib/plume/Plume" "$@"
RUN
chmod +x "$app/AppRun"
ARCH=x86_64 "$tool" --appimage-extract-and-run --no-appstream "$app" "$out/Plume-$version-x86_64.AppImage"

# ---- .deb: the same folder in /opt/plume, marked so the updater hands new versions to the system
deb="$work/deb"
mkdir -p "$deb/opt" "$deb/usr/bin" "$deb/usr/share/applications" "$deb/usr/share/icons/hicolor/scalable/apps" "$deb/DEBIAN"
cp -a "$bundle" "$deb/opt/plume"
echo deb > "$deb/opt/plume/_internal/orneos/package"
ln -s /opt/plume/Plume "$deb/usr/bin/plume"
cp "$here/eu.orneos.plume.desktop" "$deb/usr/share/applications/"
cp "$svg" "$deb/usr/share/icons/hicolor/scalable/apps/"
size=$(du -sk "$deb" | cut -f1)
cat > "$deb/DEBIAN/control" <<CONTROL
Package: orneos-plume
Version: $version
Architecture: amd64
Maintainer: Orneos <contact@orneos.eu>
Installed-Size: $size
Depends: libc6 (>= 2.35), libegl1, libgl1, libgbm1, libfontconfig1, libxkbcommon0, libwayland-client0, libwayland-cursor0, libwayland-egl1, libwayland-server0
Section: mail
Priority: optional
Homepage: https://orneos.eu
Description: Plume, mail, calendar and contacts of your Orneos account
 Plume brings together the mail, calendar, contacts, notes, tasks and Ornis
 assistant of an Orneos account in one native app, with the other apps of the
 Orneos cloud one click away.
CONTROL
dpkg-deb --root-owner-group -Zxz --build "$deb" "$out/plume_${version}_amd64.deb" >/dev/null
ls -la "$out"
