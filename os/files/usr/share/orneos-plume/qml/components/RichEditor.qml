// Formatted text: a light toolbar (bold, italic, underline, lists, link, clear) over a rich TextArea.
// Bold, italic and underline go through the cursorSelection; lists and links through `rich` (Python).
// pictures: a picture of the clipboard is pasted into the text (the composer); files copied in the file
// manager come out as filesPasted (attachments). Right click: cut, copy, paste, select all, link.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: editor
    readonly property var c: theme.c
    property alias area: area
    property alias below: below.data
    property alias placeholder: area.placeholderText
    property bool toolbar: true
    property int padding: 24
    property int fontSize: 15
    property int minTextHeight: 160
    property bool pictures: false
    // a signature with a layout (tables, pictures) comes out as designedPasted, never into the text
    property bool keepDesigned: false
    signal filesPasted(var urls)
    signal designedPasted(string html)
    readonly property string listAt: { area.cursorPosition; area.text; return rich.listAt(area.textDocument, area.cursorPosition) }
    spacing: 0

    function load(html) {
        area.text = pictures ? rich.prepare(html || "") : (html || "")
    }
    function paste() {
        area.forceActiveFocus()
        const designed = keepDesigned ? rich.designedClipboard() : ""
        if (designed !== "") {
            editor.designedPasted(designed)
            return
        }
        if (pictures && rich.pasteImage(area.textDocument, area.selectionStart, area.selectionEnd))
            return
        const files = pictures ? rich.clipboardFiles() : []
        if (files.length > 0)
            editor.filesPasted(files)
        else
            area.paste()
    }
    function exported() {
        return rich.export(area.textDocument)
    }
    function isEmpty() {
        return area.length === 0
    }
    function toggle(what) {
        const f = area.cursorSelection.font
        if (what === "bold") f.bold = !f.bold
        else if (what === "italic") f.italic = !f.italic
        else f.underline = !f.underline
        area.cursorSelection.font = f
        area.forceActiveFocus()
    }
    function openLink() {
        linkPopup.start = area.selectionStart
        linkPopup.end = area.selectionEnd
        linkField.text = rich.linkAt(area.textDocument, area.selectionStart) || ""
        linkLabel.text = area.selectedText
        linkPopup.open()
        linkField.forceActiveFocus()
    }

    component Tool: AbstractButton {
        id: tool
        property string glyph
        property string iconName
        property bool active
        property bool bold
        property bool italic
        property bool underline
        implicitWidth: 32; implicitHeight: 30
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        ToolTip.visible: hovered && ToolTip.text !== ""
        ToolTip.delay: 500
        Accessible.name: ToolTip.text
        background: Rectangle { radius: 6; color: tool.active ? editor.c.tint : tool.hovered ? editor.c.hover : "transparent" }
        contentItem: Item {
            Text {
                visible: tool.glyph !== ""
                anchors.centerIn: parent
                text: tool.glyph
                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                font.bold: tool.bold
                font.italic: tool.italic
                font.underline: tool.underline
                color: tool.active ? editor.c.accent : editor.c.text
            }
            Icon { visible: tool.iconName !== ""; anchors.centerIn: parent; name: tool.iconName; size: 17; color: tool.active ? editor.c.accent : editor.c.text }
        }
    }

    Row {
        visible: editor.toolbar
        Layout.leftMargin: editor.padding - 8
        Layout.topMargin: 6
        spacing: 2
        Tool { glyph: plume.t.fmt_bold_key; bold: true; active: area.cursorSelection.font.bold; ToolTip.text: plume.t.fmt_bold + "  (Ctrl+B)"; onClicked: editor.toggle("bold") }
        Tool { glyph: plume.t.fmt_italic_key; italic: true; active: area.cursorSelection.font.italic; ToolTip.text: plume.t.fmt_italic + "  (Ctrl+I)"; onClicked: editor.toggle("italic") }
        Tool { glyph: plume.t.fmt_underline_key; underline: true; active: area.cursorSelection.font.underline; ToolTip.text: plume.t.fmt_underline + "  (Ctrl+U)"; onClicked: editor.toggle("underline") }
        Rectangle { width: 1; height: 18; anchors.verticalCenter: parent.verticalCenter; color: editor.c.line }
        Tool { iconName: "listBullet"; active: editor.listAt === "bullet"; ToolTip.text: plume.t.fmt_bullets; onClicked: { rich.toggleList(area.textDocument, area.selectionStart, area.selectionEnd, "bullet"); area.forceActiveFocus() } }
        Tool { iconName: "listNumber"; active: editor.listAt === "number"; ToolTip.text: plume.t.fmt_numbers; onClicked: { rich.toggleList(area.textDocument, area.selectionStart, area.selectionEnd, "number"); area.forceActiveFocus() } }
        Tool { iconName: "link"; ToolTip.text: plume.t.fmt_link + "  (Ctrl+K)"; onClicked: editor.openLink() }
        Tool { iconName: "clearFormat"; ToolTip.text: plume.t.fmt_clear; onClicked: { rich.clearFormat(area.textDocument, area.selectionStart, area.selectionEnd); area.forceActiveFocus() } }
    }

    ScrollView {
        id: scroller
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        Column {
            width: scroller.availableWidth
            TextArea {
                id: area
                width: parent.width
                // the signature and the quote follow the text closely, like in the message sent
                height: Math.max(implicitHeight, editor.minTextHeight)
                // keep the caret in sight while typing (the area is not the ScrollView's direct child)
                onCursorRectangleChanged: {
                    const flick = scroller.contentItem
                    const top = cursorRectangle.y, bottom = top + cursorRectangle.height + 12
                    if (!activeFocus)
                        return
                    if (top < flick.contentY)
                        flick.contentY = Math.max(0, top - 12)
                    else if (bottom > flick.contentY + flick.height)
                        flick.contentY = bottom - flick.height
                }
                textFormat: TextEdit.RichText
                leftPadding: editor.padding; rightPadding: editor.padding; topPadding: 12; bottomPadding: 12
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                persistentSelection: true
                color: editor.c.text
                placeholderTextColor: editor.c.faint
                selectionColor: editor.c.tint
                selectedTextColor: editor.c.text
                font.family: "Schibsted Grotesk"; font.pixelSize: editor.fontSize
                background: null
                // our own menu (the style's one would paste around the pictures)
                ContextMenu.menu: null
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: point => editMenu.openAt(point.position.x, point.position.y)
                }
                Keys.onPressed: event => {
                    if (event.matches(StandardKey.Paste)) { editor.paste(); event.accepted = true; return }
                    if (!(event.modifiers & Qt.ControlModifier))
                        return
                    if (event.key === Qt.Key_B) { editor.toggle("bold"); event.accepted = true }
                    else if (event.key === Qt.Key_I) { editor.toggle("italic"); event.accepted = true }
                    else if (event.key === Qt.Key_U) { editor.toggle("underline"); event.accepted = true }
                    else if (event.key === Qt.Key_K) { editor.openLink(); event.accepted = true }
                }
            }
            Column { id: below; width: parent.width }
            // the empty space under it all still writes in the message
            MouseArea {
                width: parent.width
                height: Math.max(0, scroller.availableHeight - area.height - below.height)
                cursorShape: Qt.IBeamCursor
                onClicked: { area.forceActiveFocus(); area.cursorPosition = area.length }
            }
        }
    }

    OMenu {
        id: editMenu
        parent: area
        function openAt(px, py) {
            x = px; y = py
            open()
        }
        OMenuItem { visible: area.selectedText !== ""; text: plume.t.cut; iconName: "draft"; onTriggered: { area.cut(); area.forceActiveFocus() } }
        OMenuItem { visible: area.selectedText !== ""; text: plume.t.copy; iconName: "draft"; onTriggered: { area.copy(); area.forceActiveFocus() } }
        OMenuItem { text: plume.t.paste; iconName: "import"; onTriggered: editor.paste() }
        OMenuItem { text: plume.t.select_all; iconName: "check"; onTriggered: { area.forceActiveFocus(); area.selectAll() } }
        OMenuItem { text: plume.t.fmt_link; iconName: "link"; onTriggered: editor.openLink() }
    }

    Popup {
        id: linkPopup
        property int start
        property int end
        parent: area
        x: Math.min(Math.max(0, area.cursorRectangle.x), area.width - width)
        y: area.cursorRectangle.y + area.cursorRectangle.height + 6
        width: 340
        padding: 12
        focus: true
        background: Rectangle { radius: 10; color: editor.c.overlay; border.width: 1; border.color: editor.c.overlayLine }
        function apply(url) {
            rich.setLink(area.textDocument, start, end, url, linkLabel.text)
            close()
            area.forceActiveFocus()
        }
        contentItem: ColumnLayout {
            spacing: 8
            OTextField { id: linkLabel; Layout.fillWidth: true; visible: linkPopup.start === linkPopup.end; placeholderText: plume.t.fmt_link_text }
            OTextField { id: linkField; Layout.fillWidth: true; placeholderText: "https://…"; onAccepted: linkPopup.apply(text) }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                OButton { visible: linkField.text !== ""; kind: "quiet"; height_: 30; text: plume.t.fmt_unlink; onClicked: linkPopup.apply("") }
                Item { Layout.fillWidth: true }
                OButton { kind: "primary"; height_: 30; text: plume.t.ok; onClicked: linkPopup.apply(linkField.text) }
            }
        }
    }
}
