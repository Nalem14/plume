// SPDX-License-Identifier: GPL-2.0-or-later
// Fichiers récents on the desktop: the latest documents changed in the Drive, opened from ~/Orneos when the
// file is already on this computer, else in the cloud. Files dropped on the widget are copied into ~/Orneos
// (the files client sends them). Small: the latest document; wide: a grid of tiles; tall: the list.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    property int limit: 8
    readonly property var feed: bridge
    readonly property var rows: (bridge.result.items || []).slice(0, Math.max(1, Math.min(20, limit)))
    readonly property bool grid: wide && !tall
    property bool dropped: false

    family: "docs"
    context: S.tr("files")
    actionIcon: "folder-cloud"
    actionText: S.tr("openDrive")
    onAction: bridge.launch("/usr/libexec/orneos-app files")
    onOpened: if (rows.length) openItem(rows[0]); else bridge.launch("/usr/libexec/orneos-app files")

    function openItem(item) {
        if (item.local) bridge.launch("xdg-open " + bridge.quote(item.local));
        else if (/^https:\/\//.test(item.url)) bridge.launch("xdg-open " + bridge.quote(item.url));
    }
    function icon(mime) {
        const m = String(mime);
        return m.startsWith("image/") ? "image-x-generic" : m === "application/pdf" ? "application-pdf"
             : /spreadsheet|excel|csv/.test(m) ? "x-office-spreadsheet" : /presentation|powerpoint/.test(m) ? "x-office-presentation"
             : /word|opendocument.text|rtf/.test(m) ? "x-office-document" : m.startsWith("text/") ? "text-x-generic"
             : m.startsWith("audio/") ? "audio-x-generic" : m.startsWith("video/") ? "video-x-generic" : "unknown";
    }

    Bridge { id: bridge; command: "/usr/libexec/orneos-widget files"; interval: 120000 }
    Timer { id: done; interval: 4000; onTriggered: { root.dropped = false; bridge.refresh(); } }

    // Anything dropped here goes to ~/Orneos (local files only).
    DropArea {
        id: drop
        parent: root
        anchors.fill: parent
        keys: ["text/uri-list"]
        onDropped: event => {
            const paths = event.urls.map(u => String(u)).filter(u => u.startsWith("file:///"))
                .map(u => decodeURIComponent(u.slice(7)));
            if (!paths.length) return;
            bridge.launch("/usr/libexec/orneos-share drop " + paths.map(p => bridge.quote(p)).join(" "));
            root.dropped = true;
            done.restart();
            event.accept(Qt.CopyAction);
        }
    }
    Rectangle {
        parent: root
        anchors.fill: parent
        z: 10
        visible: drop.containsDrag || root.dropped
        radius: Ornis.t.radius.card
        color: Qt.alpha(root.tint, 0.14)
        border.color: root.tint
        border.width: 2
        ColumnLayout {
            anchors.centerIn: parent
            Kirigami.Icon {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Kirigami.Units.iconSizes.large
                Layout.preferredHeight: Kirigami.Units.iconSizes.large
                source: root.dropped ? "checkmark" : "folder-cloud"
            }
            PC3.Label {
                Layout.alignment: Qt.AlignHCenter
                text: S.tr(root.dropped ? "copied" : "dropHere")
                font.weight: Font.DemiBold
            }
        }
    }

    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: root.roomy ? 4 : 2
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        visible: text !== ""
        Layout.fillWidth: true
        text: bridge.result.state === "signed_out" || bridge.result.state === "error" ? S.tr(bridge.result.state)
              : bridge.result.ready && root.rows.length === 0 ? S.tr("emptyFiles") : ""
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }

    // ── Small: the latest document ──
    ColumnLayout {
        visible: !root.roomy && root.rows.length > 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        Kirigami.Icon {
            Layout.preferredWidth: Kirigami.Units.iconSizes.huge
            Layout.preferredHeight: Kirigami.Units.iconSizes.huge
            source: root.rows.length ? root.icon(root.rows[0].mime) : ""
        }
        Item { Layout.fillHeight: true }
        PC3.Label {
            Layout.fillWidth: true
            text: root.rows.length ? root.rows[0].title : ""
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            font.weight: Font.DemiBold
        }
        PC3.Label {
            Layout.fillWidth: true
            text: root.rows.length ? S.stamp(root.rows[0].stamp) : ""
            opacity: 0.65
            font: Kirigami.Theme.smallFont
        }
    }

    // ── Wide: tiles ──
    GridView {
        id: tiles
        visible: root.grid
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        interactive: contentHeight > height
        readonly property int columns: Math.max(3, Math.floor(width / (Kirigami.Units.gridUnit * 5.5)))
        cellWidth: width / columns
        cellHeight: Math.min(height, Kirigami.Units.gridUnit * 6.5)
        model: root.rows
        delegate: Item {
            id: tile
            required property var modelData
            width: tiles.cellWidth
            height: tiles.cellHeight
            Rectangle {
                anchors { fill: parent; margins: 3 }
                radius: Ornis.t.radius.card
                color: tileArea.containsMouse ? Qt.alpha(root.tint, 0.12) : Qt.alpha(Kirigami.Theme.textColor, 0.05)
            }
            ColumnLayout {
                anchors { fill: parent; margins: Kirigami.Units.smallSpacing * 2 }
                spacing: 2
                Kirigami.Icon {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Kirigami.Units.iconSizes.large
                    Layout.preferredHeight: Kirigami.Units.iconSizes.large
                    source: root.icon(tile.modelData.mime)
                }
                PC3.Label {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: tile.modelData.title
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideMiddle
                    font: Kirigami.Theme.smallFont
                }
            }
            MouseArea {
                id: tileArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openItem(tile.modelData)
                Accessible.role: Accessible.Button
                Accessible.name: tile.modelData.title
            }
        }
    }

    // ── Tall: the list, with the folder and the time ──
    ListView {
        id: list
        visible: root.tall
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: 2
        interactive: contentHeight > height
        model: root.rows
        delegate: Item {
            id: row
            required property var modelData
            width: list.width
            height: line.implicitHeight + Kirigami.Units.smallSpacing * 2
            Rectangle {
                anchors.fill: parent
                radius: Ornis.t.radius.control
                color: area.containsMouse ? Qt.alpha(Kirigami.Theme.textColor, 0.07) : "transparent"
            }
            RowLayout {
                id: line
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 4; rightMargin: 4 }
                spacing: Kirigami.Units.smallSpacing * 2
                Kirigami.Icon {
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                    source: root.icon(row.modelData.mime)
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        Layout.fillWidth: true
                        text: row.modelData.title
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: row.modelData.folder
                        textFormat: Text.PlainText
                        elide: Text.ElideLeft
                        opacity: 0.65
                        font: Kirigami.Theme.smallFont
                    }
                }
                PC3.Label {
                    Layout.alignment: Qt.AlignTop
                    text: S.stamp(row.modelData.stamp)
                    opacity: 0.65
                    font: Kirigami.Theme.smallFont
                }
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openItem(row.modelData)
                Accessible.role: Accessible.Button
                Accessible.name: row.modelData.title
            }
        }
    }
}
