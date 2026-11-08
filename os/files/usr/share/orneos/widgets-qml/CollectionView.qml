// SPDX-License-Identifier: GPL-2.0-or-later
// Courrier and Notes on the desktop. Courrier: the unread count, then the latest messages (sender, subject,
// time). Notes: the pinned or latest note, then the others. Small: one thing; wide or tall: the list. View,
// mailbox or folder are chosen in the widget's settings (CollectionConfig.qml), not in the widget.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    required property string kind
    required property string view
    required property string group
    property int limit: 8
    signal viewPicked(string value)
    signal groupPicked(string value)
    readonly property bool mail: kind === "mail"
    readonly property var groups: [{id: "", name: S.tr(mail ? "allBoxes" : "allFolders")}].concat(bridge.result.groups || [])
    readonly property bool missingGroup: group !== "" && !groups.some(g => g.id === group)
    readonly property var inGroup: (bridge.result.items || []).filter(item => !group || item.group === group)
    readonly property var matching: inGroup.filter(item => view === "recent" || (mail ? item.unread : item.favorite))
    readonly property var rows: matching.slice(0, Math.max(1, Math.min(20, limit)))
    readonly property int unread: inGroup.filter(item => item.unread).length
    // Notes, small: the pinned note first (the one people keep in view), else the latest.
    readonly property var lead: mail ? (inGroup.find(item => item.unread) || inGroup[0] || null)
                                     : (inGroup.find(item => item.favorite) || inGroup[0] || null)
    readonly property string groupName: group ? ((groups.find(g => g.id === group) || {}).name || "") : ""

    family: mail ? "communicate" : "organize"
    context: S.tr(kind) + (groupName ? " · " + groupName : "") + (mail && roomy && unread ? " · " + unread + " " + S.tr(root.unread === 1 ? "unreadOne" : "unreadCount") : "")
    actionIcon: mail ? "mail-message-new" : "document-new"
    actionText: S.tr(mail ? "newMessage" : "quickNote")
    onAction: bridge.launch(mail ? "orneos-mail --new-message" : "orneos-notes --quick")
    onOpened: bridge.launch(mail ? "orneos-mail" : "orneos-notes")

    function openItem(item) {
        if (mail) bridge.launch(item.id ? "orneos-mail --message-id=" + bridge.quote(item.id) : "orneos-mail");
        else bridge.launch("orneos-notes --show=" + bridge.quote(item.id));
    }
    // A sender's colour: one of the family colours, the same for the same name.
    function senderColor(name) {
        const keys = ["communicate", "docs", "organize", "media", "space"];
        let h = 0;
        for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 997;
        return Ornis.family(keys[h % keys.length], false);
    }
    function initials(name) {
        const parts = String(name || "?").replace(/[<>"]/g, "").trim().split(/\s+/);
        return ((parts[0] || "?")[0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
    }

    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget " + root.kind
        interval: 10000
        onActionFinished: ok => {
            if (!capture.pending) return;
            capture.pending = false;
            capture.ok = ok;
            if (ok) capture.text = "";
            capture.shown = true;
            told.restart();
        }
    }
    Timer { id: told; interval: 4000; onTriggered: capture.shown = false }

    PC3.Label {
        Layout.fillWidth: true
        visible: !bridge.result.ready || root.missingGroup
        text: root.missingGroup ? S.tr("missingGroup") : S.tr(bridge.result.state || "loading")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        font: Kirigami.Theme.smallFont
        opacity: 0.8
    }
    PC3.Button {
        visible: !bridge.result.ready && bridge.result.state !== "loading"
        text: bridge.result.state === "signed_out" ? "Orneos Connect" : S.tr("open")
        onClicked: bridge.launch(bridge.result.state === "signed_out" ? "orneos-connect" : root.mail ? "orneos-mail" : "orneos-notes")
    }

    // ── Small: Courrier = the unread count and the latest unread; Notes = the pinned note ──
    ColumnLayout {
        visible: !root.roomy && bridge.result.ready
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 2
        RowLayout {
            visible: root.mail
            spacing: Kirigami.Units.smallSpacing
            PC3.Label {
                text: String(root.unread)
                color: root.tint
                font.pixelSize: Kirigami.Units.gridUnit * 2.2
                font.weight: Font.Bold
                font.features: {"tnum": 1}
            }
            PC3.Label {
                Layout.alignment: Qt.AlignBottom
                bottomPadding: Kirigami.Units.smallSpacing
                text: root.unread ? S.tr(root.unread === 1 ? "unreadOne" : "unreadCount") : S.tr("allRead")
                opacity: 0.7
            }
        }
        RowLayout {
            visible: !root.mail && root.lead !== null
            spacing: 4
            opacity: 0.7
            Kirigami.Icon {
                visible: !!(root.lead && root.lead.favorite)
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                source: "pin"
            }
            PC3.Label {
                text: root.lead && root.lead.favorite ? S.tr("pinnedNote") : S.tr("recentNote")
                font: Kirigami.Theme.smallFont
            }
        }
        PC3.Label {
            visible: !root.mail
            Layout.fillWidth: true
            text: root.lead ? (root.lead.title || S.tr("untitled")) : S.tr("noNotes")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.25
            font.weight: Font.Bold
        }
        Item { Layout.fillHeight: true }
        PC3.Label {
            visible: root.lead !== null
            Layout.fillWidth: true
            text: root.lead ? (root.mail ? root.lead.subtitle : root.lead.subtitle || "") : ""
            textFormat: Text.PlainText
            elide: Text.ElideRight
            font.weight: root.mail ? Font.DemiBold : Font.Normal
            opacity: root.mail ? 1 : 0.7
        }
        PC3.Label {
            visible: root.lead !== null
            Layout.fillWidth: true
            text: root.lead ? (root.mail ? (root.lead.title || S.tr("noSubject")) : S.stamp(root.lead.stamp)) : ""
            textFormat: Text.PlainText
            elide: Text.ElideRight
            opacity: 0.7
            font: Kirigami.Theme.smallFont
        }
    }

    // ── Wide or tall: the list ──
    PC3.Label {
        visible: root.roomy && bridge.result.ready && !root.missingGroup && root.rows.length === 0
        text: S.tr(root.mail ? (root.view === "unread" ? "allRead" : "emptyMail") : "emptyNotes")
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        opacity: 0.65
    }
    ListView {
        id: list
        visible: root.roomy
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        interactive: contentHeight > height
        model: root.rows
        spacing: 2
        delegate: Item {
            id: row
            required property var modelData
            readonly property bool strong: !!(root.mail ? modelData.unread : modelData.favorite)
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
                spacing: Kirigami.Units.smallSpacing * 2
                // Courrier: the sender's initials on a family colour; Notes: a pin on pinned notes.
                Rectangle {
                    visible: root.mail
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 1.6
                    Layout.preferredHeight: Layout.preferredWidth
                    radius: 6
                    color: root.senderColor(row.modelData.subtitle || "")
                    PC3.Label {
                        anchors.centerIn: parent
                        text: root.initials(row.modelData.subtitle)
                        color: "white"
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        font.weight: Font.Bold
                    }
                }
                Kirigami.Icon {
                    visible: !root.mail
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    source: row.modelData.favorite ? "pin" : "text-plain"
                    opacity: row.modelData.favorite ? 1 : 0.5
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        Layout.fillWidth: true
                        text: root.mail ? (row.modelData.subtitle || "?") : (row.modelData.title || S.tr("untitled"))
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        font.weight: row.strong ? Font.DemiBold : Font.Normal
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        text: root.mail ? (row.modelData.title || S.tr("noSubject")) : (row.modelData.subtitle || "")
                        visible: text !== ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        opacity: 0.7
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
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openItem(row.modelData)
                Accessible.role: Accessible.Button
                Accessible.name: (root.mail && row.modelData.unread ? S.tr("unread") + " · " : "") + row.modelData.title + " · " + row.modelData.subtitle
            }
        }
    }
    PC3.Label {
        visible: root.roomy && root.matching.length > root.rows.length
        text: S.tr("moreInApp")
        Layout.fillWidth: true
        opacity: 0.65
        font: Kirigami.Theme.smallFont
    }

    // ── Notes: write a note here (first line = title), straight to the cloud, in the widget's folder ──
    RowLayout {
        visible: !root.mail && root.roomy && bridge.result.ready
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        QQC2.TextField {
            id: capture
            property bool pending: false
            property bool ok: true
            property bool shown: false
            Layout.fillWidth: true
            placeholderText: shown ? S.tr(ok ? "noteAdded" : "noteFailed") : S.tr("writeNote")
            enabled: !pending
            background: Rectangle {
                radius: Ornis.t.radius.control
                color: Qt.alpha(Kirigami.Theme.backgroundColor, 0.85)
                border.width: capture.activeFocus ? 2 : 1
                border.color: capture.shown && !capture.ok ? Ornis.t.brand.vermillon
                              : capture.activeFocus ? root.tint : Qt.alpha(Kirigami.Theme.textColor, 0.18)
            }
            onTextEdited: shown = false
            onAccepted: save.clicked()
            Accessible.name: S.tr("writeNote")
        }
        PC3.ToolButton {
            id: save
            icon.name: "document-save"
            enabled: capture.text.trim() !== "" && !capture.pending
            Accessible.name: S.tr("saveNote")
            PC3.ToolTip.text: S.tr("saveNote")
            PC3.ToolTip.visible: hovered
            onClicked: {
                capture.pending = true;
                bridge.run("/usr/libexec/orneos-widget notes-add --text=" + bridge.quote(capture.text.trim())
                           + " --folder=" + bridge.quote(root.group));
            }
        }
    }
    PC3.Label {
        visible: capture.shown && !capture.ok && capture.text !== ""
        Layout.fillWidth: true
        text: S.tr("noteFailed")
        color: Ornis.t.brand.vermillon
        font: Kirigami.Theme.smallFont
        wrapMode: Text.WordWrap
    }
}
