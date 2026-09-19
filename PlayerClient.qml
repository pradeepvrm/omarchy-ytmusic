import QtQuick
import Quickshell.Io

// Private Unix-socket client for the plugin's mpv player. The service and the
// TUI share the same mpv JSON IPC socket; this side keeps the bar widget's
// view of the world fresh through property observation, while the TUI drives
// queueing directly. Modeled on the proven reconnect pattern from
// Omarchy-Spotify's BackendClient: a failed connect leaves Quickshell's Socket
// holding a dead QLocalSocket, so each retry recreates the Socket via Loader.
Item {
  id: root

  visible: false
  width: 0
  height: 0

  // The service sets this while a player should exist. It keeps the reconnect
  // loop alive across slow mpv starts but gives up after enough misses until
  // kick() re-arms it.
  property bool wanted: false
  property string socketPath: ""
  property int maxReconnectAttempts: 30

  readonly property var activeSocket: socketLoader.item
  readonly property bool connected: !!(activeSocket && activeSocket.connected)
  property int reconnectAttempt: 0
  property int nextRequestId: 1
  property var pending: ({})

  signal eventReceived(var message)
  signal responseReceived(var message)
  signal observationsStarted()

  function resetPending(reason) {
    var waiters = pending
    pending = ({})
    for (var id in waiters) {
      var callback = waiters[id]
      if (typeof callback === "function") callback(false, undefined, String(reason || "player unavailable"))
    }
  }

  // command: array such as ["set_property", "pause", true]
  function sendCommand(command, callback) {
    var socket = activeSocket
    if (!socket || !socket.connected) {
      if (typeof callback === "function") callback(false, undefined, "player is not running")
      return 0
    }
    var id = nextRequestId++
    var payload = { command: command, request_id: id }
    var nextPending = ({})
    for (var existing in pending) nextPending[existing] = pending[existing]
    nextPending[String(id)] = typeof callback === "function" ? callback : null
    pending = nextPending
    socket.write(JSON.stringify(payload) + "\n")
    socket.flush()
    return id
  }

  function setProperty(name, value, callback) {
    return sendCommand(["set_property", name, value], callback)
  }

  function getProperty(name, callback) {
    return sendCommand(["get_property", name], callback)
  }

  function observeProperty(id, name) {
    return sendCommand(["observe_property", id, name], null)
  }

  // Re-arm the reconnect loop, used right after spawning mpv.
  function kick() {
    reconnectAttempt = 0
    if (wanted && !connected) reconnectTimer.restart()
  }

  function handleLine(line) {
    var message = null
    try {
      message = JSON.parse(String(line || ""))
    } catch (e) {
      return
    }
    if (!message || typeof message !== "object") return
    if (message.event !== undefined) {
      eventReceived(message)
      return
    }
    if (message.request_id === undefined) return
    var id = String(message.request_id)
    var callback = pending[id]
    if (callback === undefined) return
    var nextPending = ({})
    for (var key in pending) if (key !== id) nextPending[key] = pending[key]
    pending = nextPending
    responseReceived(message)
    if (typeof callback !== "function") return
    if (message.error === "success") callback(true, message.data, "")
    else callback(false, undefined, String(message.error || "command failed"))
  }

  onWantedChanged: {
    if (wanted) return
    reconnectTimer.stop()
    socketLoader.active = false
    reconnectAttempt = 0
    resetPending("player stopped")
  }

  onConnectedChanged: if (connected) reconnectAttempt = 0

  Component {
    id: socketComponent
    Socket {
      path: root.socketPath
      parser: SplitParser {
        splitMarker: "\n"
        onRead: function(line) { root.handleLine(line) }
      }
      connected: true
      onConnectionStateChanged: {
        if (connected) settleTimer.restart()
        else settleTimer.stop()
      }
    }
  }

  // Grace period between socket connect and the first writes: commands
  // flushed in the same tick as connection establishment are silently
  // swallowed, which starves mpv of observe_property and leaves the
  // service blind with zero errors.
  Timer {
    id: settleTimer
    interval: 400
    repeat: false
    onTriggered: {
      if (root.connected) {
        root.observeAll()
        observationsStarted()
      }
    }
  }

  Loader {
    id: socketLoader
    active: false
    sourceComponent: socketComponent
  }

  Timer {
    id: reconnectTimer
    interval: Math.min(1500, 180 + root.reconnectAttempt * 120)
    repeat: true
    triggeredOnStart: true
    running: root.wanted && !root.connected
    onTriggered: {
      root.reconnectAttempt++
      if (root.reconnectAttempt > root.maxReconnectAttempts) {
        root.reconnectAttempt = 0
        reconnectTimer.stop()
        return
      }
      socketLoader.active = false
      socketLoader.active = true
    }
  }

  // Stable observation ids shared with the service.
  function observeAll() {
    observeProperty(1, "pause")
    observeProperty(2, "idle-active")
    observeProperty(3, "playlist-pos")
    observeProperty(4, "playlist-count")
    observeProperty(5, "duration")
    observeProperty(6, "volume")
    observeProperty(7, "metadata")
    observeProperty(8, "path")
    observeProperty(9, "media-title")
  }
}
