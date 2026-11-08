// A picture of the library (thumbnail, large preview, cover), by its address in the cache (thumbs.py): the
// file at once when it is on disk, else asked from the cloud and shown when it arrives. Qt reads the file.
import QtQuick

Image {
    id: thumb
    property string address
    asynchronous: true
    cache: true
    function load() {
        if (!address) { source = ""; return }
        const url = thumbs.url(address)
        if (url) source = url
        else { source = ""; thumbs.want(address) }
    }
    onAddressChanged: load()
    Component.onCompleted: load()
    Connections {
        target: thumbs
        enabled: thumb.address !== "" && thumb.status === Image.Null
        function onReady(address, url) { if (address === thumb.address && url) thumb.source = url }
    }
}
