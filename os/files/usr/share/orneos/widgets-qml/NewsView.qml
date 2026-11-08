// SPDX-License-Identifier: GPL-2.0-or-later
// Actualités on the desktop: the cloud's News. Small: one headline over its picture, the top five in turn.
// Wide: the headline beside its picture, then two more. Tall or large: the magazine (the headline over its
// picture, then the others with a thumbnail). No source yet: sources of the Explore catalogue to follow
// in one click. Source, unread only and count are in the widget's settings (NewsConfig, NewsSources).
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    property string source: "all"
    property bool unreadOnly: false
    property int limit: 8
    signal configureRequested()
    readonly property var feed: bridge

    readonly property var data: bridge.result
    readonly property var rows: (data.items || []).slice(0, Math.max(1, Math.min(20, limit)))
    readonly property bool magazine: tall
    readonly property bool strip: wide && !tall
    readonly property var lead: rows.length ? rows[Math.min(turn, rows.length - 1)] : null
    property int turn: 0
    readonly property string sourceName: {
        const [kind, id] = source.split(":");
        if (kind === "starred") return S.tr("starred");
        const list = kind === "folder" ? (data.folders || []) : kind === "feed" ? (data.feeds || []) : [];
        return (list.find(x => String(x.id) === id) || {}).name || "";
    }

    family: "tools"
    context: S.tr("news") + (sourceName ? " · " + sourceName : "")
    actionIcon: "internet-services"
    actionText: S.tr("openNews")
    onAction: bridge.launch("/usr/libexec/orneos-app news")
    onOpened: if (lead) openItem(lead); else bridge.launch("/usr/libexec/orneos-app news")

    function openItem(item) {
        if (!/^https?:\/\//i.test(item.url || "")) return;
        bridge.launch("xdg-open " + bridge.quote(item.url));
        // Read here = read everywhere, like the News app does when an article is opened.
        if (item.unread) bridge.run("/usr/libexec/orneos-widget news-read --key=" + item.id);
    }
    function follow(feed) { bridge.run("/usr/libexec/orneos-widget news-follow --url=" + bridge.quote(feed)); }
    function byline(item) { return [item.source, S.stamp(item.stamp)].filter(x => x).join(" · "); }
    // A source's mark: its initial on one of the family colours, the same for the same name.
    function mark(name) {
        const keys = ["communicate", "docs", "organize", "media", "space"];
        let h = 0;
        for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 997;
        return Ornis.family(keys[h % keys.length], false);
    }

    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget news --source=" + quote(root.source) + (root.unreadOnly ? " --unread" : "")
                 + " --lang=" + quote(Qt.locale().name.slice(0, 2))
        interval: 300000
    }
    // Small: the five first headlines in turn, never while the pointer is on the widget.
    Timer {
        interval: 9000
        repeat: true
        running: !root.roomy && root.rows.length > 1 && !hover.hovered
        onTriggered: root.turn = (root.turn + 1) % Math.min(5, root.rows.length)
    }
    HoverHandler { id: hover }

    // ── States: loading, signed out, offline, missing source ──
    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: root.roomy ? 4 : 2
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        Layout.fillWidth: true
        visible: text !== ""
        text: ["signed_out", "error", "missingSource"].indexOf(root.data.state) >= 0 ? S.tr(root.data.state)
              : root.data.state === "offline" ? S.tr("offline")
              : root.data.state === "ready" && root.rows.length === 0 ? S.tr("emptyNews") : ""
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }
    PC3.Button {
        visible: root.data.state === "signed_out" || root.data.state === "error"
        text: root.data.state === "signed_out" ? "Orneos Connect" : S.tr("retry")
        onClicked: root.data.state === "signed_out" ? bridge.launch("orneos-connect") : bridge.refresh()
    }

    // ── No source yet: the catalogue's best, one click to follow ──
    ColumnLayout {
        visible: root.data.state === "noSources"
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Kirigami.Units.smallSpacing
        PC3.Label {
            Layout.fillWidth: true
            text: S.tr("noSources")
            font.weight: Font.Bold
            font.pointSize: Kirigami.Theme.defaultFont.pointSize * (root.roomy ? 1.15 : 1)
            wrapMode: Text.WordWrap
        }
        PC3.Label {
            visible: root.roomy
            Layout.fillWidth: true
            text: S.tr("noSourcesHint")
            wrapMode: Text.WordWrap
            opacity: 0.7
            font: Kirigami.Theme.smallFont
        }
        Repeater {
            model: (root.data.suggestions || []).slice(0, root.tall ? 5 : root.wide ? 3 : 2)
            delegate: RowLayout {
                id: suggestion
                required property var modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing * 2
                Rectangle {
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 1.6
                    Layout.preferredHeight: Layout.preferredWidth
                    radius: Ornis.t.radius.control
                    color: root.mark(suggestion.modelData.title)
                    PC3.Label {
                        anchors.centerIn: parent
                        text: suggestion.modelData.title.slice(0, 1).toUpperCase()
                        color: "white"
                        font.weight: Font.Bold
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        Layout.fillWidth: true
                        text: suggestion.modelData.title
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        font.weight: Font.DemiBold
                    }
                    PC3.Label {
                        visible: root.roomy
                        Layout.fillWidth: true
                        text: suggestion.modelData.category
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        opacity: 0.65
                        font: Kirigami.Theme.smallFont
                    }
                }
                PC3.Button {
                    icon.name: "list-add"
                    text: root.roomy ? S.tr("follow") : ""
                    enabled: !bridge.actionBusy
                    Accessible.name: S.tr("follow") + " " + suggestion.modelData.title
                    onClicked: root.follow(suggestion.modelData.feed)
                }
            }
        }
        Item { Layout.fillHeight: true }
        PC3.ToolButton {
            text: S.tr("moreSources")
            icon.name: "search"
            onClicked: root.configureRequested()
        }
    }

    // ── The headline: its picture with the title over a veil, or the title alone on the family tint ──
    component Headline: Item {
        id: headline
        required property var view
        property var item: null
        property real titleScale: 1.2
        Kirigami.ShadowedImage {
            id: picture
            anchors.fill: parent
            visible: status === Image.Ready
            source: headline.item && headline.item.image ? "file://" + headline.item.image : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            radius: Ornis.t.radius.card
        }
        Rectangle {
            anchors.fill: parent
            radius: Ornis.t.radius.card
            gradient: Gradient {
                GradientStop { position: 0; color: picture.visible ? "transparent" : Qt.alpha(view.tint, 0.16) }
                GradientStop { position: 0.45; color: picture.visible ? Qt.rgba(0, 0, 0, 0.05) : Qt.alpha(view.tint, 0.1) }
                GradientStop { position: 1; color: picture.visible ? Qt.rgba(0.04, 0.08, 0.14, 0.86) : Qt.alpha(view.tint, 0.04) }
            }
        }
        ColumnLayout {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: Kirigami.Units.largeSpacing }
            spacing: 2
            PC3.Label {
                Layout.fillWidth: true
                text: headline.item ? headline.item.title : ""
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
                color: picture.visible ? "white" : Kirigami.Theme.textColor
                font.weight: Font.Bold
                font.pointSize: Kirigami.Theme.defaultFont.pointSize * headline.titleScale
            }
            PC3.Label {
                Layout.fillWidth: true
                text: headline.item ? view.byline(headline.item) : ""
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: picture.visible ? Qt.rgba(1, 1, 1, 0.8) : view.tint
                font: Kirigami.Theme.smallFont
            }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: if (headline.item) view.openItem(headline.item)
            Accessible.role: Accessible.Link
            Accessible.name: headline.item ? headline.item.title + " · " + view.byline(headline.item) : ""
        }
    }

    // ── Small: the headline in turn, and where we are in the five ──
    Headline {
        view: root
        visible: !root.roomy && root.lead !== null
        Layout.fillWidth: true
        Layout.fillHeight: true
        item: root.lead
        titleScale: 1.05
    }
    Row {
        visible: !root.roomy && root.rows.length > 1
        Layout.alignment: Qt.AlignHCenter
        spacing: 4
        Repeater {
            model: Math.min(5, root.rows.length)
            delegate: Rectangle {
                required property int index
                width: index === root.turn ? 12 : 5
                height: 5
                radius: 2.5
                color: index === root.turn ? root.tint : Qt.alpha(Kirigami.Theme.textColor, 0.25)
                Behavior on width { NumberAnimation { duration: Ornis.t.motion.fast_ms } }
            }
        }
    }

    // ── Wide: the headline beside its picture, then two more ──
    RowLayout {
        visible: root.strip && root.rows.length > 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Kirigami.Units.largeSpacing
        Headline {
            view: root
            Layout.fillHeight: true
            Layout.preferredWidth: Math.min(parent.width * 0.5, height * 1.5)
            item: root.rows[0] || null
            titleScale: 1
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumHeight: parent.height
            clip: true
            spacing: Kirigami.Units.smallSpacing
            Repeater {
                model: root.rows.slice(1, root.height >= Kirigami.Units.gridUnit * 10 ? 4 : 3)
                delegate: Line { view: root; Layout.fillWidth: true; thumb: false }
            }
            Item { Layout.fillHeight: true }
        }
    }

    // ── Tall or large: the magazine ──
    Headline {
        view: root
        visible: root.magazine && root.rows.length > 0
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(Math.max(width * 0.5, Kirigami.Units.gridUnit * 7), root.height * 0.48)
        item: root.rows[0] || null
        titleScale: root.wide ? 1.3 : 1.15
    }
    ListView {
        id: list
        visible: root.magazine
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: 2
        interactive: contentHeight > height
        model: root.rows.slice(1)
        delegate: Line { view: root; width: list.width; thumb: true }
    }

    // An article in a list: its thumbnail (magazine), title, source and time, a dot when unread.
    component Line: Item {
        id: line
        required property var view
        required property var modelData
        property bool thumb: true
        implicitHeight: Math.max(body.implicitHeight, thumb ? Kirigami.Units.gridUnit * 2.6 : 0) + Kirigami.Units.smallSpacing * 2
        Rectangle {
            anchors.fill: parent
            radius: Ornis.t.radius.control
            color: area.containsMouse ? Qt.alpha(Kirigami.Theme.textColor, 0.07) : "transparent"
        }
        RowLayout {
            anchors { fill: parent; leftMargin: 4; rightMargin: 4 }
            spacing: Kirigami.Units.smallSpacing * 2
            Kirigami.ShadowedImage {
                visible: line.thumb && line.modelData.image !== ""
                Layout.preferredWidth: Kirigami.Units.gridUnit * 3.4
                Layout.preferredHeight: Kirigami.Units.gridUnit * 2.6
                source: line.modelData.image ? "file://" + line.modelData.image : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                radius: Ornis.t.radius.control
            }
            Rectangle {
                visible: line.thumb && line.modelData.image === ""
                Layout.preferredWidth: Kirigami.Units.gridUnit * 3.4
                Layout.preferredHeight: Kirigami.Units.gridUnit * 2.6
                radius: Ornis.t.radius.control
                color: Qt.alpha(view.mark(line.modelData.source || "?"), 0.14)
                PC3.Label {
                    anchors.centerIn: parent
                    text: (line.modelData.source || "?").slice(0, 1).toUpperCase()
                    color: view.mark(line.modelData.source || "?")
                    font.weight: Font.Bold
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.3
                }
            }
            ColumnLayout {
                id: body
                Layout.fillWidth: true
                spacing: 1
                PC3.Label {
                    Layout.fillWidth: true
                    text: line.modelData.title
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    font.weight: line.modelData.unread ? Font.DemiBold : Font.Normal
                }
                RowLayout {
                    spacing: 4
                    Rectangle {
                        visible: line.modelData.unread
                        width: 6; height: 6; radius: 3
                        color: view.tint
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        text: view.byline(line.modelData)
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        opacity: 0.65
                        font: Kirigami.Theme.smallFont
                    }
                }
            }
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: view.openItem(line.modelData)
            Accessible.role: Accessible.Link
            Accessible.name: (line.modelData.unread ? S.tr("unread") + " · " : "") + line.modelData.title + " · " + view.byline(line.modelData)
        }
    }
}
