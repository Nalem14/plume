// SPDX-License-Identifier: GPL-2.0-or-later
// Recherche on the desktop: the bar of Orneos Search, and its AI mode. Opens the results in the browser;
// nothing is kept here (no history: Search never logs a query either).
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    readonly property string home: "https://search.orneos.eu/"

    family: "tools"
    context: S.tr("searchTitle")
    onOpened: field.forceActiveFocus()

    function go(ai) {
        const q = field.text.trim();
        if (!q && !ai) { bridge.launch("xdg-open " + bridge.quote(home)); return; }
        bridge.launch("xdg-open " + bridge.quote(home + "?q=" + encodeURIComponent(q) + (ai ? "&tab=ai" : "")));
        field.text = "";
    }

    // Only to launch the browser: no data to read.
    Bridge { id: bridge }

    Item { Layout.fillHeight: true; visible: root.tall }
    QQC2.TextField {
        id: field
        Layout.fillWidth: true
        placeholderText: S.tr("searchPlaceholder")
        leftPadding: Kirigami.Units.gridUnit * 1.8
        font.pointSize: Kirigami.Theme.defaultFont.pointSize * (root.roomy ? 1.1 : 1)
        background: Rectangle {
            radius: height / 2
            color: Qt.alpha(Kirigami.Theme.backgroundColor, 0.85)
            border.width: field.activeFocus ? 2 : 1
            border.color: field.activeFocus ? root.tint : Qt.alpha(Kirigami.Theme.textColor, 0.18)
        }
        Kirigami.Icon {
            anchors { left: parent.left; leftMargin: Kirigami.Units.smallSpacing * 2; verticalCenter: parent.verticalCenter }
            width: Kirigami.Units.iconSizes.small
            height: width
            source: "search"
            opacity: 0.7
        }
        onAccepted: root.go(false)
        Keys.onPressed: event => {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                root.go(true);
                event.accepted = true;
            }
        }
        Accessible.name: S.tr("searchPlaceholder")
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        PC3.Button {
            visible: root.roomy
            text: S.tr("searchTitle")
            icon.name: "search"
            onClicked: root.go(false)
        }
        PC3.Button {
            id: ai
            text: S.tr("aiMode")
            onClicked: root.go(true)
            contentItem: RowLayout {
                spacing: Kirigami.Units.smallSpacing
                OrnisStars {
                    color: Ornis.family("communicate", root.dark)
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: Kirigami.Units.iconSizes.small
                }
                PC3.Label { text: ai.text }
            }
        }
        Item { Layout.fillWidth: true }
    }
    PC3.Label {
        visible: root.tall
        Layout.fillWidth: true
        text: S.tr("searchHint")
        wrapMode: Text.WordWrap
        opacity: 0.6
        font: Kirigami.Theme.smallFont
    }
    Item { Layout.fillHeight: true }
}
