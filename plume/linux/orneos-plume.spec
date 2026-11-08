# Plume for Fedora and Orneos OS: the apps as they are (Python + QML, noarch), on Fedora's Qt and libraries.
# Built by rpm.sh from the staged tree (stage.py); not PyInstaller.
%global __os_install_post %{nil}

Name:           orneos-plume
Version:        %{plume_version}
Release:        1
Summary:        Mail, calendar, contacts, notes, tasks and Ornis of your Orneos account
License:        Proprietary
URL:            https://orneos.eu
BuildArch:      noarch
Requires:       python3 >= 3.10
Requires:       python3-pyside6
Requires:       python3-keyring
Requires:       python3-cryptography
Requires:       python3-icalendar
Requires:       python3-dateutil
Requires:       python3-qrcode
# Meet: the calls (Chromium's WebRTC), the signaling server, voice messages
Requires:       qt6-qtwebengine
Requires:       qt6-qtwebchannel
Requires:       qt6-qtwebsockets
Requires:       qt6-qtmultimedia

%description
Plume brings together the mail, calendar, contacts, notes, tasks and Ornis assistant of an Orneos account in
one native app, with the other apps of the Orneos cloud one click away.

%install
mkdir -p %{buildroot}/usr/lib/orneos-plume %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
cp -a %{plume_stage}/share/. %{buildroot}/usr/lib/orneos-plume/
echo rpm > %{buildroot}/usr/lib/orneos-plume/orneos/package
cat > %{buildroot}%{_bindir}/plume <<'RUN'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/orneos-plume/orneos-plume/plume.py "$@"
RUN
chmod 755 %{buildroot}%{_bindir}/plume
install -m 644 %{plume_desktop} %{buildroot}%{_datadir}/applications/eu.orneos.plume.desktop
install -m 644 %{plume_stage}/share/icons/hicolor/scalable/apps/eu.orneos.plume.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/eu.orneos.plume.svg

%files
/usr/lib/orneos-plume
%{_bindir}/plume
%{_datadir}/applications/eu.orneos.plume.desktop
%{_datadir}/icons/hicolor/scalable/apps/eu.orneos.plume.svg
