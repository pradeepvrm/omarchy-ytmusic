import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

import "Api.js" as Api

BarWidget {
  id: root

  moduleName: "quickshell.ytmusic"

  readonly property var service: bar && bar.shell
    ? bar.shell.serviceFor("quickshell.ytmusic") : null
  readonly property color foreground: bar ? bar.barForeground : Color.foreground

  readonly property string title: service ? service.title : ""
  readonly property string artist: service ? service.artist : ""
  readonly property bool hasMedia: service ? service.hasMedia : false
  readonly property bool playing: service ? service.playing : false
  readonly property string setupState: service ? service.setupState : "checking"
  readonly property string setupError: service ? service.setupError : ""
  readonly property bool signedIn: service ? service.signedIn : false
  readonly property bool showPausedTrack: service ? service.showPausedTrack : true
  readonly property bool showTrackTitle: service ? service.showTrackTitle : true
  readonly property bool showArtistName: service ? service.showArtistName : true
  readonly property bool scrollBarText: service ? service.scrollBarText : true
  readonly property real maxBarTextWidth: service ? service.maxBarTextWidth : 260

  readonly property string barText: Api.barTrackText(title, artist,
    showTrackTitle ? "On" : "Off", showArtistName ? "On" : "Off")
  readonly property string playIcon: playing ? "󰏤" : "󰐊"
  readonly property bool settingUp: setupState === "checking" || setupState === "running"
  readonly property bool setupFailed: setupState === "failed"

  // Collapse to the icon while paused when the user asked for that, and on
  // vertical bars where there is no room for text.
  readonly property bool textVisible: !vertical && barText !== ""
    && (playing || showPausedTrack)
  readonly property bool iconOnly: !textVisible

  property bool popupOpen: false

  // Interface the shell's bar looks for to open panel-like widgets from
  // shortcuts (`omarchy-shell shell toggle <id>`, same as Bluetooth and
  // Network): findPanelWidget requires open()/close() functions and an
  // `opened` property on the widget item.
  readonly property bool opened: popupOpen
  function open() { popupOpen = true }
  function close() { popupOpen = false }

  function syncSettings() {
    if (service) service.applySettings(settings)
  }

  onSettingsChanged: syncSettings()
  onServiceChanged: syncSettings()

  implicitWidth: row.implicitWidth + Style.space(14)
  implicitHeight: barSize

  Row {
    id: row
    anchors.centerIn: parent
    spacing: Style.space(6)

    Text {
      id: glyph
      textFormat: Text.PlainText
      anchors.verticalCenter: parent.verticalCenter
      text: root.settingUp ? "󰥔" : (root.setupFailed ? "󰀍" : "󰗃")
      color: Color.urgent
      opacity: root.hasMedia ? 1.0 : (root.settingUp ? 0.9 : 0.75)
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.body
      Behavior on color {
        enabled: !root.bar || root.bar.foregroundAnimationEnabled
        ColorAnimation { duration: 160 }
      }
    }

    Text {
      id: stateGlyph
      textFormat: Text.PlainText
      anchors.verticalCenter: parent.verticalCenter
      text: root.playIcon
      visible: root.hasMedia
      color: root.playing ? root.foreground : Qt.darker(root.foreground, 1.5)
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.body
      Behavior on color {
        enabled: !root.bar || root.bar.foregroundAnimationEnabled
        ColorAnimation { duration: 160 }
      }
    }

    Item {
      id: scrollClip
      width: root.iconOnly ? 0 : Math.min(
        root.maxBarTextWidth > 0 ? root.maxBarTextWidth : labelText.implicitWidth,
        labelText.implicitWidth)
      height: glyph.height
      clip: true
      visible: root.textVisible

      Text {
        id: labelText
        textFormat: Text.PlainText
        text: root.barText
        color: root.foreground
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.body
        anchors.verticalCenter: parent.verticalCenter

        property bool needsScroll: implicitWidth > scrollClip.width

        NumberAnimation on x {
          id: scrollAnim
          running: labelText.needsScroll && root.scrollBarText && !root.popupOpen
            && !root.vertical && root.textVisible
          loops: Animation.Infinite
          duration: Math.max(6000, labelText.implicitWidth * 25)
          from: scrollClip.width
          to: -labelText.implicitWidth
          easing.type: Easing.Linear
        }

        onXChanged: {
          if (!scrollAnim.running) x = 0
        }

        onNeedsScrollChanged: {
          if (!needsScroll) x = 0
        }
      }
    }
  }

  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

    onClicked: function(mouse) {
      if (mouse.button === Qt.RightButton) {
        if (root.service) root.service.launchTui()
      } else if (mouse.button === Qt.MiddleButton) {
        if (root.service) root.service.toggle()
      } else {
        root.popupOpen = !root.popupOpen
      }
    }

    onWheel: function(wheel) {
      if (!root.service) return
      var shift = (wheel.modifiers & Qt.ShiftModifier) !== 0
      if (shift) {
        if (wheel.angleDelta.y > 0) root.service.previous()
        else root.service.next()
      } else {
        if (wheel.angleDelta.y > 0) root.service.volumeUp()
        else root.service.volumeDown()
      }
    }

    onEntered: if (root.bar) root.bar.showTooltip(root, root.tooltipText())
    onExited: if (root.bar) root.bar.hideTooltip(root)
  }

  function tooltipText() {
    if (settingUp) return "YouTube Music — setting up…"
    if (setupFailed) return "YouTube Music — setup failed: " + setupError
    if (hasMedia) {
      var parts = []
      if (title) parts.push(title)
      if (artist) parts.push(artist)
      return parts.join(" — ")
    }
    return "YouTube Music — click to open the player"
  }

  PopupCard {
    id: popup
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.popupOpen
    contentWidth: popup.fittedContentWidth(Style.space(330))
    contentHeight: popup.fittedContentHeight(column.implicitHeight)

    onOpenChanged: if (!open) root.popupOpen = false

    Column {
      id: column
      anchors.fill: parent
      spacing: Style.space(10)

      Row {
        spacing: Style.space(10)
        width: parent.width
        layoutDirection: Qt.LeftToRight

        BorderSurface {
          width: Style.space(84)
          height: Style.space(84)
          radius: Style.spacing.labelGap
          color: Style.normalFillFor(root.foreground, Color.accent)
          borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

          Image {
            id: art
            anchors.fill: parent
            anchors.margins: Style.space(2)
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            source: root.service && root.service.artUrl ? root.service.artUrl : ""
            visible: source !== "" && status === Image.Ready
          }

          Text {
            anchors.centerIn: parent
            visible: !art.visible
            text: "󰝚"
            color: root.foreground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.display
          }
        }

        Column {
          spacing: Style.space(4)
          width: parent.width - Style.space(94)

          Text {
            textFormat: Text.PlainText
            text: root.title || "YouTube Music"
            color: root.foreground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
            elide: Text.ElideRight
            width: parent.width
          }

          Text {
            textFormat: Text.PlainText
            text: root.artist
            color: Qt.darker(root.foreground, 1.3)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
            width: parent.width
            visible: text !== ""
          }

          Text {
            textFormat: Text.PlainText
            text: root.service && root.service.sourceLabel ? root.service.sourceLabel : ""
            color: Qt.darker(root.foreground, 1.6)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
            width: parent.width
            visible: text !== ""
          }

          Text {
            textFormat: Text.PlainText
            text: root.service ? root.service.positionText : ""
            color: Qt.darker(root.foreground, 1.45)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.caption
            visible: root.hasMedia
          }
        }
      }

      // Progress bar
      Item {
        width: parent.width
        height: Style.space(6)
        visible: root.hasMedia

        BorderSurface {
          id: progressTrack
          anchors.fill: parent
          radius: Style.spacing.labelGap
          color: Style.normalFillFor(root.foreground, Color.accent)
          borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

          Rectangle {
            readonly property real fraction: root.service && root.service.mpvDuration > 0
              ? Math.min(1, Math.max(0, root.service.playbackPosition / root.service.mpvDuration))
              : 0
            x: parent.borderLeft
            y: parent.borderTop
            width: fraction * Math.max(0, parent.width - parent.borderLeft - parent.borderRight)
            height: Math.max(0, parent.height - parent.borderTop - parent.borderBottom)
            radius: Style.spacing.labelGap
            color: Color.accent
            Behavior on width {
                NumberAnimation { duration: 900; easing.type: Easing.Linear }
            }
          }
        }
      }

      Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(6)

        Button {
          iconText: "󰒮"
          foreground: root.foreground
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY
          enabled: root.service && root.service.canGoPrevious
          opacity: enabled ? 1.0 : 0.4
          onClicked: if (root.service) root.service.previous()
        }

        Button {
          iconText: root.playIcon
          foreground: root.foreground
          horizontalPadding: Style.spacing.panelGap
          verticalPadding: Style.spacing.controlPaddingY
          iconSize: Style.font.iconLarge
          enabled: root.service && root.service.playerAlive
          opacity: enabled ? 1.0 : 0.4
          onClicked: if (root.service) root.service.toggle()
        }

        Button {
          iconText: "󰒭"
          foreground: root.foreground
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY
          enabled: root.service && root.service.canGoNext
          opacity: enabled ? 1.0 : 0.4
          onClicked: if (root.service) root.service.next()
        }

        Button {
          iconText: "󰓥"
          foreground: root.foreground
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY
          enabled: root.service && root.service.hasMedia
          opacity: enabled ? 1.0 : 0.4
          onClicked: if (root.service) root.service.stopPlayback()
        }
      }

      Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(6)

        Button {
          iconText: "󰕾"
          foreground: root.foreground
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY
          onClicked: if (root.service) root.service.volumeUp()
        }

        Text {
          textFormat: Text.PlainText
          anchors.verticalCenter: parent.verticalCenter
          text: root.service ? Math.round(root.service.mpvVolume) + "%" : "100%"
          color: Qt.darker(root.foreground, 1.3)
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.pixelSize: Style.font.bodySmall
        }

        Button {
          iconText: "󰕿"
          foreground: root.foreground
          horizontalPadding: Style.spacing.controlPaddingX
          verticalPadding: Style.spacing.controlPaddingY
          onClicked: if (root.service) root.service.volumeDown()
        }
      }

      PanelSeparator {
        foreground: root.foreground
        visible: !root.signedIn || root.setupFailed
      }

      Text {
        textFormat: Text.PlainText
        text: root.setupFailed
          ? ("Setup failed: " + (root.setupError || "unknown error"))
          : (!root.signedIn
            ? "Sign in with your YouTube account to get your homepage and recommendations."
            : "")
        color: Qt.darker(root.foreground, 1.45)
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
        width: parent.width
        visible: text !== ""
      }

      Button {
        text: root.setupFailed ? "Retry setup" : "Open YouTube Music"
        iconText: root.setupFailed ? "󰑐" : "󰆍"
        foreground: root.foreground
        horizontalPadding: Style.spacing.panelGap
        verticalPadding: Style.spacing.controlPaddingY
        anchors.horizontalCenter: parent.horizontalCenter
        onClicked: {
          root.popupOpen = false
          if (root.service) root.service.launchTui()
        }
      }
    }
  }
}
