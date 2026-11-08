// Avatar alongside a response, without changing the response's own controls or rich text.
import QtQuick
import QtQuick.Layouts

RowLayout {
    id: reply
    default property alias content: body.data
    Layout.fillWidth: true
    spacing: 10
    Icon { name: "ornis-mascot"; size: 28; Layout.alignment: Qt.AlignTop }
    ColumnLayout {
        id: body
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 8
    }
}
