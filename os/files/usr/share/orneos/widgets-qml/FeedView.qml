// SPDX-License-Identifier: GPL-2.0-or-later
// Favoris and team activity on the desktop: a short list (bookmarks with their folder, the team's latest
// documents with their time). Small: the first item. The folder and the count are in the widget's settings.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S

Frame {
    id: root
    required property string kind
    property string folder: ""
    property int limit: 8
    readonly property var feed: bridge
    readonly property var rows: (bridge.result.items || []).slice(0, Math.max(1, Math.min(20, limit)))
    readonly property bool team: kind === "team"

    family: team ? "space" : "tools"
    context: S.tr(kind) + (team && folder ? " · " + folder : "")
    onOpened: if (rows.length) root.openItem(rows[0])

    function openItem(item) {
        if (/^https?:\/\//i.test(item.url || "")) bridge.launch("xdg-open " + bridge.quote(item.url));
    }
    function detail(item) {
        if (!team) return item.subtitle || "";
        const ts = Date.parse(item.subtitle || "");
        return isNaN(ts) ? "" : S.stamp(ts / 1000);
    }

    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget " + root.kind + " --folder=" + quote(root.folder)
        interval: 60000
    }

    PC3.Label {
        visible: !bridge.result.ready || root.rows.length === 0
        Layout.fillWidth: true
        text: S.tr(!bridge.result.ready ? bridge.result.state || "loading" : "emptyFeed")
        wrapMode: Text.WordWrap
        opacity: 0.7
        font: Kirigami.Theme.smallFont
    }
    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        interactive: contentHeight > height
        model: root.roomy ? root.rows : root.rows.slice(0, 2)
        delegate: Item {
            id: row
            required property var modelData
            width: list.width
            height: line.implicitHeight + Kirigami.Units.smallSpacing * 2
            Rectangle {
                anchors.fill: parent
                radius: 6
                color: mouse.containsMouse ? Qt.alpha(Kirigami.Theme.textColor, 0.07) : "transparent"
            }
            RowLayout {
                id: line
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 4; rightMargin: 4 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        Layout.fillWidth: true
                        text: row.modelData.title
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        visible: !root.team && text !== ""
                        text: root.detail(row.modelData)
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        opacity: 0.7
                        font: Kirigami.Theme.smallFont
                    }
                }
                PC3.Label {
                    visible: root.team
                    Layout.alignment: Qt.AlignTop
                    text: root.detail(row.modelData)
                    opacity: 0.65
                    font: Kirigami.Theme.smallFont
                }
            }
            MouseArea {
                id: mouse
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
