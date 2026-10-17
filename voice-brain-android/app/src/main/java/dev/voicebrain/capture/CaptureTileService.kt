package dev.voicebrain.capture

import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/** Quick Settings tile — swipe down, tap 🎙️, speak. */
class CaptureTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        qsTile?.state = Tile.STATE_INACTIVE
        qsTile?.updateTile()
    }

    override fun onClick() {
        super.onClick()
        qsTile?.state = Tile.STATE_ACTIVE
        qsTile?.updateTile()
        startActivityAndCollapse(
            android.content.Intent(this, CaptureActivity::class.java)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
