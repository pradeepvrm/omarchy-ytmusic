import QtQuick
import Quickshell
import Quickshell.Io

import "Api.js" as Api

// Shared state for the bar widget and the IPC surface. Audio runs in a
// detached mpv process (idle, audio-only) supervised here; both this service
// and the Python TUI speak mpv's JSON IPC on the same Unix socket. The TUI
// additionally writes a snapshot of its queue metadata next to the socket,
// which this service watches so the widget keeps showing clean titles after
// the TUI is closed.
Item {
  id: root

  visible: false
  width: 0
  height: 0

  // ------------------------------------------------------ injected context
  property var shell: null
  property var manifest: null

  readonly property string pluginId: manifest && manifest.id
    ? String(manifest.id) : "quickshell.ytmusic"
  // NOTE: do NOT read the plugin path from manifest.__sourceDir — the shell
  // strips private __ fields before injecting the manifest into third-party
  // plugins (see shell.qml publicPluginManifest), so that is always empty
  // here. Qt.resolvedUrl(".") resolves against this file's location instead.
  readonly property string pluginDir: String(Qt.resolvedUrl(".")).replace(/^file:\/\//, "").replace(/\/$/, "")

  // ------------------------------------------------------ paths
  readonly property string homeDirectory: Quickshell.env("HOME") || ""
  readonly property string runtimeBase: String(Quickshell.env("XDG_RUNTIME_DIR") || "/tmp")
  readonly property string runtimeDir: runtimeBase + "/omarchy-ytmusic"
  readonly property string socketPath: runtimeDir + "/mpv.sock"
  readonly property string tuiStatePath: runtimeDir + "/state.json"
  readonly property string dataHome: String(Quickshell.env("XDG_DATA_HOME")
    || (homeDirectory ? homeDirectory + "/.local/share" : ".local/share"))
  readonly property string dataDir: dataHome + "/omarchy-ytmusic"
  readonly property string launcherPath: pluginDir ? pluginDir + "/scripts/run-tui.sh" : ""
  readonly property string setupScriptPath: pluginDir ? pluginDir + "/scripts/setup.sh" : ""

  // ------------------------------------------------------ settings
  property var settings: Api.shallowCopy(Api.defaultSettingValues)

  readonly property bool showTrackTitle: String(settings.showTrackTitle) !== "Off"
  readonly property bool showArtistName: String(settings.showArtistName) !== "Off"
  readonly property bool showPausedTrack: String(settings.showPausedTrack) !== "Off"
  readonly property bool scrollBarText: String(settings.scrollBarText) !== "Off"
  readonly property real maxBarTextWidth: Number(settings.maxBarTextWidth) || 0
  readonly property string audioQuality: String(settings.audioQuality || "Best available")
  readonly property int idleShutdownMinutes: Math.max(0, Math.min(1440,
    Math.floor(Number(settings.idleShutdownMinutes) || 0)))

  function applySettings(values) {
    var next = Api.normalizedSettings(values)
    var previousQuality = audioQuality
    if (JSON.stringify(next) !== JSON.stringify(settings)) settings = next
    if (previousQuality !== next.audioQuality) quitIdlePlayerForSettingsChange()
  }

  // A quality change only matters for future yt-dlp extractions, so an idle
  // player is stopped now and will respawn with the new format on demand.
  function quitIdlePlayerForSettingsChange() {
    if (!playerClient.connected) return
    if (!mpvIdleActive && mpvQueueCount > 0) return
    playerClient.wanted = false
    playerClient.sendCommand(["quit"], null)
  }

  // ------------------------------------------------------ setup lifecycle
  // checking -> (ready | needed -> running -> ready | failed)
  property string setupState: "checking"
  property string setupError: ""
  property string setupLogTail: ""

  function notify(headline, description) {
    notifyProcess.command = [
      "omarchy-notification-send", "-g", "󰗃",
      "--app-name", "Omarchy YouTube Music", headline, description
    ]
    notifyProcess.running = true
  }

  function startSetupCheck() {
    if (!pluginDir) return
    setupState = "checking"
    setupCheckProcess.running = true
  }

  function runSetup() {
    if (!pluginDir || setupState === "running") return
    setupState = "running"
    setupError = ""
    setupLogTail = ""
    setupProcess.running = true
  }

  function retrySetup() {
    if (setupState === "running" || setupState === "checking") return
    runSetup()
  }

  property Process notifyProcess: Process { }

  property Process setupCheckProcess: Process {
    command: [root.setupScriptPath, "--status"]
    stdout: StdioCollector { id: setupCheckOut; waitForEnd: true }
    stderr: StdioCollector { id: setupCheckErr; waitForEnd: true }
    onExited: function(exitCode) {
      var text = String(setupCheckOut.text || "").trim()
      var errText = String(setupCheckErr.text || "").trim()
      if (exitCode === 0 && text.indexOf("ready") === 0) {
        root.setupState = "ready"
        return
      }
      if (text.indexOf("needed") === 0) {
        root.setupState = "needed"
        root.runSetup()
        return
      }
      root.setupState = "failed"
      root.setupError = text.indexOf("failed:") === 0
        ? text.substring(7).trim() : (errText || "setup check failed")
      root.notify("YouTube Music setup failed", root.setupError)
    }
  }

  property Process setupProcess: Process {
    command: [root.setupScriptPath]
    stdout: SplitParser {
      onRead: function(line) {
        var text = String(line || "")
        if (text.indexOf("failed:") === 0) root.setupError = text.substring(7).trim()
        else if (text.length > 0) root.setupLogTail = text
      }
    }
    stderr: SplitParser {
      onRead: function(line) {
        var text = String(line || "")
        if (text.length > 0) root.setupLogTail = text
      }
    }
    onExited: function(exitCode) {
      if (exitCode === 0) {
        root.setupState = "ready"
        root.notify("YouTube Music is ready",
          "Sign in from the terminal player with omarchy-ytmusic, then play something.")
      } else {
        root.setupState = "failed"
        if (!root.setupError) root.setupError = root.setupLogTail || "setup exited with code " + exitCode
        root.notify("YouTube Music setup failed", root.setupError)
      }
    }
  }

  // ------------------------------------------------------ player state
  property bool mpvIdleActive: true
  property bool mpvPaused: true
  property int mpvQueueIndex: -1
  property int mpvQueueCount: 0
  property real mpvDuration: 0
  property real mpvVolume: 100
  property string mpvPath: ""
  property string mpvMediaTitle: ""
  property var mpvMetadata: ({})
  property real playbackPosition: 0
  property double idleSince: 0
  property bool playerSpawnPending: false

  readonly property bool playerAlive: playerClient.connected

  // Snapshot written by the TUI: { tracks: [...], signedIn, source }.
  property var tuiState: null
  readonly property bool signedIn: tuiState ? tuiState.signedIn === true : false

  // Resolve display metadata for the current queue position. The TUI snapshot
  // wins; mpv's yt-dlp metadata and media title are the fallbacks so the
  // widget still shows something if state.json is missing or stale.
  readonly property var displayTrack: {
    var track = Api.trackAt(tuiState, mpvQueueIndex)
    if (track && (track.title || track.artist)) return track
    var metaTitle = Api.metaValue(mpvMetadata, ["Title", "title"])
    var metaArtist = Api.metaValue(mpvMetadata,
      ["Artist", "artist", "Uploader", "uploader", "channel"])
    var videoId = Api.parseVideoId(mpvPath)
    if (metaTitle || metaArtist) {
      return { title: metaTitle, artist: metaArtist, videoId: videoId }
    }
    if (mpvMediaTitle) return { title: mpvMediaTitle, artist: "", videoId: videoId }
    return null
  }

  readonly property string title: displayTrack ? String(displayTrack.title || "") : ""
  readonly property string artist: displayTrack ? String(displayTrack.artist || "") : ""
  readonly property string videoId: displayTrack ? String(displayTrack.videoId || "") : ""
  readonly property string artUrl: Api.thumbnailUrl(videoId)
  readonly property bool hasMedia: playerAlive && !mpvIdleActive && (title !== "" || mpvPath !== "")
  readonly property bool playing: hasMedia && !mpvPaused
  readonly property bool canGoPrevious: hasMedia && mpvQueueIndex > 0
  readonly property bool canGoNext: hasMedia && mpvQueueIndex < mpvQueueCount - 1
  readonly property string positionText: Api.formatTime(playbackPosition)
    + (mpvDuration > 0 ? " / " + Api.formatTime(mpvDuration) : "")
  readonly property string sourceLabel: tuiState && tuiState.source
    ? String(tuiState.source) : ""

  PlayerClient {
    id: playerClient
    socketPath: root.socketPath

    onEventReceived: function(message) {
      if (!message || message.event !== "property-change") return
      root.applyObserved(message.id, message.data)
    }

    onObservationsStarted: root.seedPlayerState()
  }

  // Shared by push events and the seeding reads below: observation ids
  // match PlayerClient._observed_ids.
  function applyObserved(id, value) {
    switch (id) {
      case 1:
        root.mpvPaused = value === true
        break
      case 2:
        root.mpvIdleActive = value === true
        if (value) {
          root.playbackPosition = 0
          root.mpvDuration = 0
        }
        break
      case 3:
        root.mpvQueueIndex = value === undefined || value === null ? -1 : value
        root.playbackPosition = 0
        break
      case 4:
        root.mpvQueueCount = value === undefined || value === null ? 0 : value
        break
      case 5:
        root.mpvDuration = value === undefined || value === null ? 0 : value
        break
      case 6:
        root.mpvVolume = value === undefined || value === null ? 100 : value
        break
      case 7:
        root.mpvMetadata = Api.isPlainObject(value) ? value : ({})
        break
      case 8:
        root.mpvPath = value === undefined || value === null ? "" : String(value)
        break
      case 9:
        root.mpvMediaTitle = value === undefined || value === null ? "" : String(value)
        break
    }
  }

  // Explicit initial reads after (re)subscribing: mpv only pushes changes,
  // so without these the widget shows stale initials until the next change.
  // Responses also prove the read path is alive.
  function seedPlayerState() {
    var seeds = [
      [1, "pause"], [2, "idle-active"], [3, "playlist-pos"],
      [4, "playlist-count"], [5, "duration"], [6, "volume"],
      [7, "metadata"], [8, "path"], [9, "media-title"]
    ]
    for (var i = 0; i < seeds.length; i++) {
      (function(id, name) {
        playerClient.getProperty(name, function(ok, value) {
          if (ok) root.applyObserved(id, value)
        })
      })(seeds[i][0], seeds[i][1])
    }
  }

  // ------------------------------------------------------ player lifecycle
  function mpvArguments() {
    return [
      "mpv",
      "--idle",
      "--no-terminal",
      "--no-video",
      "--audio-display=no",
      "--force-window=no",
      "--keep-open=no",
      "--gapless-audio=weak",
      "--prefetch-playlist=yes",
      "--input-ipc-server=" + socketPath,
      "--ytdl-format=" + Api.ytdlFormat(audioQuality),
      "--title=Omarchy YouTube Music",
      "--volume=" + Math.round(mpvVolume)
    ]
  }

  function ensurePlayer() {
    if (setupState !== "ready") {
      if (setupState === "needed" || setupState === "failed") runSetup()
      return false
    }
    if (playerClient.connected) return true
    spawnPlayer()
    return true
  }

  function spawnPlayer() {
    if (playerSpawnPending) return
    playerSpawnPending = true
    playerClient.wanted = true
    mkdirProcess.running = true
  }

  property Process mkdirProcess: Process {
    command: ["mkdir", "-p", root.runtimeDir]
    onExited: function(exitCode) {
      root.playerSpawnPending = false
      if (exitCode !== 0) {
        root.notify("YouTube Music player failed to start",
          "Could not create " + root.runtimeDir)
        return
      }
      Quickshell.execDetached(root.mpvArguments())
      playerClient.kick()
    }
  }

  // ------------------------------------------------------ controls
  function toggle() {
    if (!playerClient.connected) {
      launchTui()
      return
    }
    if (mpvIdleActive) {
      launchTui()
      return
    }
    playerClient.setProperty("pause", !mpvPaused, null)
  }

  function next() {
    if (hasMedia) playerClient.sendCommand(["playlist-next", "force"], null)
    else launchTui()
  }

  function previous() {
    if (hasMedia) playerClient.sendCommand(["playlist-prev", "force"], null)
    else launchTui()
  }

  function stopPlayback() {
    if (!playerClient.connected) return
    playerClient.sendCommand(["stop"], null)
  }

  function adjustVolume(step) {
    if (!playerClient.connected) return
    var target = Api.clamp(Math.round((mpvVolume + step) * 10) / 10, 0, 130)
    playerClient.setProperty("volume", target, null)
  }

  function volumeUp() { adjustVolume(5) }
  function volumeDown() { adjustVolume(-5) }

  function jumpToQueueIndex(index) {
    var i = Math.floor(Number(index))
    if (!playerClient.connected || i < 0 || i >= mpvQueueCount) return
    playerClient.sendCommand(["playlist-play-index", i], null)
  }

  // ------------------------------------------------------ idle supervision
  Timer {
    id: supervisionTimer
    interval: 20000
    repeat: true
    running: true
    onTriggered: {
      // Periodic re-seed: local socket writes/reads occasionally get lost
      // (swallowed at connect time, dropped events), which used to leave
      // the widget blind for hours. Nine tiny round-trips every 20 s keep
      // the widget's view of mpv honest no matter what was missed.
      if (playerClient.connected) root.seedPlayerState()
      if (!playerClient.connected) {
        root.idleSince = 0
        return
      }
      var idleNow = root.mpvIdleActive || root.mpvQueueCount === 0
      if (!idleNow) {
        root.idleSince = 0
        return
      }
      if (root.idleSince === 0) {
        root.idleSince = Date.now()
        return
      }
      if (root.idleShutdownMinutes <= 0) return
      if (Date.now() - root.idleSince >= root.idleShutdownMinutes * 60000) {
        root.idleSince = 0
        playerClient.wanted = false
        playerClient.sendCommand(["quit"], null)
      }
    }
  }

  // Poll the position once per second while something plays; the queue and
  // metadata arrive through property observation instead.
  Timer {
    id: positionTimer
    interval: 1000
    repeat: true
    running: playerClient.connected && root.hasMedia && !root.mpvPaused
    onTriggered: {
      playerClient.getProperty("playback-time", function(ok, value) {
        if (ok && typeof value === "number") root.playbackPosition = value
      })
    }
  }

  // ------------------------------------------------------ TUI state mirror
  function applyTuiState(text) {
    var parsed = Api.parseJson(text, null)
    if (!Api.isPlainObject(parsed)) return
    if (!Array.isArray(parsed.tracks)) parsed.tracks = []
    root.tuiState = parsed
  }

  property FileView tuiStateFile: FileView {
    path: root.tuiStatePath
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyTuiState(text())
    onLoadFailed: {
      if (root.tuiState !== null) root.tuiState = null
    }
  }

  // The first read can race runtime-dir creation; one delayed reload
  // self-corrects (mirrors the weather panel's pattern).
  Timer {
    interval: 1500
    running: true
    onTriggered: tuiStateFile.reload()
  }

  // ------------------------------------------------------ TUI launching
  property string terminalCommand: ""
  property bool terminalResolved: false

  function terminalLaunchArgs() {
    var configured = String(settings.launchTerminal || "").trim()
    if (configured) {
      var argv = configured.split(/\s+/).filter(function(part) { return part.length > 0 })
      argv.push(launcherPath)
      return argv
    }
    if (terminalCommand) {
      var args = [terminalCommand]
      if (terminalCommand === "alacritty" || terminalCommand === "ghostty"
        || terminalCommand === "konsole") args.push("-e")
      if (terminalCommand === "wezterm") args.push("start", "--")
      args.push(launcherPath)
      return args
    }
    // Empty (no resolved terminal yet) means the async detectTerminal()
    // hasn't finished: fall back to the Omarchy default terminal launcher
    // instead of hardcoding foot, which may not be installed.
    return ["xdg-terminal-exec", launcherPath]
  }

  function launchTui() {
    if (!launcherPath) return
    if (setupState === "checking" || setupState === "needed") {
      runSetup()
      notify("YouTube Music is still setting up",
        "The terminal player opens as soon as setup finishes.")
      return
    }
    if (setupState === "failed") {
      retrySetup()
      notify("Retrying YouTube Music setup", setupError)
      return
    }
    if (!terminalResolved) {
      detectTerminal()
    }
    Quickshell.execDetached(terminalLaunchArgs())
  }

  function detectTerminal() {
    terminalResolved = true
    var script = 'for t in "$TERMINAL" foot kitty alacritty ghostty wezterm; do '
      + '[ -n "$t" ] && command -v "$t" >/dev/null 2>&1 && { basename "$t"; exit 0; }; '
      + 'done; exit 1'
    terminalDetectProcess.command = ["sh", "-c", script]
    terminalDetectProcess.running = true
  }

  property Process terminalDetectProcess: Process {
    stdout: StdioCollector { id: terminalOut; waitForEnd: true }
    onExited: function(exitCode) {
      var name = String(terminalOut.text || "").trim()
      if (exitCode === 0 && name) root.terminalCommand = name
    }
  }

  // ------------------------------------------------------ IPC surface
  IpcHandler {
    target: "quickshell.ytmusic.player"

    function launchTui(): string { root.launchTui(); return "ok" }
    function toggle(): string { root.toggle(); return "ok" }
    function next(): string { root.next(); return "ok" }
    function previous(): string { root.previous(); return "ok" }
    function stop(): string { root.stopPlayback(); return "ok" }
    function volumeUp(): string { root.volumeUp(); return "ok" }
    function volumeDown(): string { root.volumeDown(); return "ok" }
    function ensurePlayer(): string { return root.ensurePlayer() ? "ok" : "busy" }

    function setupStatus(): string {
      return root.setupState + (root.setupError ? ": " + root.setupError : "")
    }

    function retrySetup(): string { root.retrySetup(); return "ok" }

    // Read-only diagnostics (and recovery) for the player link. The link
    // fails silently when it fails, so this is the support tool: check
    // `status`, and if `connected` is true but nothing ever arrives,
    // `reconnect` cycles the socket without touching mpv.
    function status(): string {
      return JSON.stringify({
        connected: playerClient.connected,
        paused: root.mpvPaused, idle: root.mpvIdleActive,
        pos: root.mpvQueueIndex, count: root.mpvQueueCount,
        title: root.title, artist: root.artist,
        volume: Math.round(root.mpvVolume), hasMedia: root.hasMedia,
        setup: root.setupState,
        linkLines: playerClient.linesSeenThisLink,
        linkHeals: playerClient.linkHealAttempts
      })
    }

    function reconnect(): string {
      playerClient.wanted = false
      playerClient.wanted = true
      playerClient.kick()
      return "ok"
    }
  }

  // ------------------------------------------------------ bootstrap
  // The shell injects `manifest` right after object creation, so setup must
  // be kicked off from the property change (not Component.onCompleted, which
  // fires before the injection and would run with an empty plugin path).
  property bool didBootstrap: false

  // Attach to a player that is already running (started before this service
  // instance loaded, e.g. across a shell restart). Without this the service
  // stays blind: `wanted` defaults to false, so the reconnect loop never
  // runs and the widget shows nothing while music plays.
  function attachToPlayer() {
    playerClient.wanted = true
    playerClient.kick()
  }

  onManifestChanged: {
    if (manifest && !didBootstrap) {
      didBootstrap = true
      startSetupCheck()
      attachToPlayer()
    }
  }

  Component.onCompleted: {
    detectTerminal()
  }
}
