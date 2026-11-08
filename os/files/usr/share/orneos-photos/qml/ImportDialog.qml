// « Importer » (Ctrl+I): photos and videos of the computer into the library, sorted by year and month in its
// first folder. They show as soon as the cloud has them; the sidebar counts what is still on its way.
import QtQuick
import QtQuick.Dialogs

FileDialog {
    title: app.t.import_title
    fileMode: FileDialog.OpenFiles
    nameFilters: [app.t.import_filter + " (*.jpg *.jpeg *.png *.heic *.heif *.webp *.gif *.tif *.tiff *.avif *.dng *.mp4 *.mov *.m4v *.webm *.mkv)",
                  app.t.import_all + " (*)"]
    onAccepted: photos.importFiles(selectedFiles.map(u => u.toString()))
}
