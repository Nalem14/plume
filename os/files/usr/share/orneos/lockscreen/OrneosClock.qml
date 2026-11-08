/*
    The Ornis clock of the lock screen, in place of Breeze's (os/tools/lockscreen.py puts it in the desktop shell's
    lockscreen folder): the day in small capitals of JetBrains Mono with a saffron dot, as the headers of the Orneos
    apps, then the time in Schibsted Grotesk.

    SPDX-License-Identifier: GPL-2.0-or-later
*/
import QtQuick
import QtQuick.Layouts

import org.kde.plasma.clock as PlasmaClock
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    readonly property bool softwareRendering: GraphicsInfo.api === GraphicsInfo.Software
    readonly property color saffron: "#F0A202"           // design/tokens.json › brand.safran
    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        Layout.alignment: Qt.AlignHCenter
        spacing: Kirigami.Units.largeSpacing
        PlasmaComponents3.Label {
            text: timeSource.dateTime.toLocaleDateString(Qt.locale(), "dddd").toLocaleUpperCase()
            textFormat: Text.PlainText
            font.family: "JetBrains Mono"
            font.pointSize: Math.round(Kirigami.Theme.defaultFont.pointSize * 1.3)
            font.weight: Font.Medium
            font.letterSpacing: 3
            style: root.softwareRendering ? Text.Outline : Text.Normal
            styleColor: root.softwareRendering ? Kirigami.Theme.backgroundColor : "transparent"
        }
        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: Math.round(Kirigami.Units.gridUnit * 0.4)
            implicitHeight: implicitWidth
            radius: width / 2
            color: root.saffron
        }
        PlasmaComponents3.Label {
            text: timeSource.dateTime.toLocaleDateString(Qt.locale(), "d MMMM").toLocaleUpperCase()
            textFormat: Text.PlainText
            font.family: "JetBrains Mono"
            font.pointSize: Math.round(Kirigami.Theme.defaultFont.pointSize * 1.3)
            font.weight: Font.Medium
            font.letterSpacing: 3
            style: root.softwareRendering ? Text.Outline : Text.Normal
            styleColor: root.softwareRendering ? Kirigami.Theme.backgroundColor : "transparent"
        }
    }
    PlasmaComponents3.Label {
        Layout.alignment: Qt.AlignHCenter
        text: Qt.formatTime(timeSource.dateTime, Qt.locale(), Locale.ShortFormat)
        textFormat: Text.PlainText
        font.family: "Schibsted Grotesk"
        font.pointSize: Math.round(Kirigami.Theme.defaultFont.pointSize * 8)
        font.weight: Font.Medium
        font.letterSpacing: -3
        style: root.softwareRendering ? Text.Outline : Text.Normal
        styleColor: root.softwareRendering ? Kirigami.Theme.backgroundColor : "transparent"
        renderType: Text.NativeRendering
    }

    PlasmaClock.Clock {
        id: timeSource
        trackSeconds: Qt.locale().timeFormat(Locale.ShortFormat).includes("s")
    }
}
