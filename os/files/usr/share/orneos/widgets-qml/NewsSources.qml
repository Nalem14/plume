// Actualités, sources: the Explore catalogue of the cloud's News (chosen by Orneos), by category, each
// followed in one click; or the address of any feed. A followed source is added to the cloud's News.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "strings.js" as S

ColumnLayout {
    id: root
    spacing: Kirigami.Units.largeSpacing
    readonly property var categories: bridge.result.categories || []
    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget news-catalog --lang=" + quote(Qt.locale().name.slice(0, 2))
        interval: 600000
        onActionFinished: ok => failed.visible = !ok
    }
    function follow(url) { bridge.run("/usr/libexec/orneos-widget news-follow --url=" + bridge.quote(url)); }

    QQC2.Label {
        Layout.fillWidth: true
        text: S.tr("exploreHint")
        wrapMode: Text.WordWrap
    }
    RowLayout {
        Layout.fillWidth: true
        QQC2.TextField {
            id: address
            Layout.fillWidth: true
            placeholderText: S.tr("feedAddress")
            inputMethodHints: Qt.ImhUrlCharactersOnly
            onAccepted: add.clicked()
        }
        QQC2.Button {
            id: add
            text: S.tr("add")
            icon.name: "list-add"
            enabled: /^https?:\/\/\S+\.\S+/i.test(address.text) && !bridge.actionBusy
            onClicked: { root.follow(address.text.trim()); address.text = ""; }
        }
    }
    Kirigami.InlineMessage {
        id: failed
        Layout.fillWidth: true
        type: Kirigami.MessageType.Error
        text: S.tr("actionError")
        visible: false
    }
    QQC2.Label {
        visible: !bridge.result.ready
        text: S.tr(bridge.result.state || "loading")
        opacity: 0.7
    }
    Repeater {
        model: root.categories
        delegate: ColumnLayout {
            id: category
            required property var modelData
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Heading {
                level: 4
                text: category.modelData.name
                Layout.topMargin: Kirigami.Units.smallSpacing
            }
            Repeater {
                model: category.modelData.sources
                delegate: RowLayout {
                    id: entry
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: entry.modelData.title
                            textFormat: Text.PlainText
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: entry.modelData.description
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            opacity: 0.7
                            font: Kirigami.Theme.smallFont
                        }
                    }
                    QQC2.Button {
                        text: S.tr(entry.modelData.followed ? "followed" : "follow")
                        icon.name: entry.modelData.followed ? "checkmark" : "list-add"
                        enabled: !entry.modelData.followed && !bridge.actionBusy
                        Accessible.name: text + " " + entry.modelData.title
                        onClicked: root.follow(entry.modelData.feed)
                    }
                }
            }
        }
    }
    Item { Layout.fillHeight: true }
}
