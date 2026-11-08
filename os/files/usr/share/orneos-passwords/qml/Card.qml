// A card of fields (hairlines between them), set on the page like the other cards of Orneos (Surface).
import QtQuick
import QtQuick.Layouts
import "components"

Surface {
    id: card
    default property alias fields: column.data
    Layout.fillWidth: true
    implicitHeight: column.implicitHeight
    ColumnLayout {
        id: column
        width: parent.width
        spacing: 0
    }
}
