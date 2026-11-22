import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "matthewjaybarr.git-tracker"
  ipcTarget: "matthewjaybarr.git-tracker"
  manageIpc: false

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  function tr(key, vars) {
    var s = strings.t(key)
    for (var k in (vars || {})) s = s.replace("{" + k + "}", vars[k])
    return s
  }

  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color urgent: bar ? bar.urgent : Commons.Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  readonly property var roots: Model.splitPaths(setting("roots", "~"))
  readonly property var excludes: Model.splitPaths(setting("exclude", ""))
  readonly property int depth: setting("depth", 4)
  readonly property int refreshIntervalSec: Math.max(30, setting("refreshIntervalSec", 300))
  readonly property bool autoFetch: setting("autoFetch", false)
  readonly property int fetchIntervalSec: Math.max(300, setting("fetchIntervalSec", 1800))
  readonly property string scriptPath: decodeURIComponent(String(Qt.resolvedUrl("gitscan.py")).replace(/^file:\/\//, ""))
  readonly property string actionPath: decodeURIComponent(String(Qt.resolvedUrl("gitaction.py")).replace(/^file:\/\//, ""))

  property var repos: []
  property string filter: "all"
  property string query: ""
  // Selection follows the repo's path, so a refresh that re-sorts the list keeps it.
  property string selectedPath: ""
  property bool scanning: false
  property bool fetching: false
  property bool pendingFetch: false
  property string error: ""
  property real scannedAt: 0
  property real fetchedAt: 0
  property real now: Date.now()

  readonly property var shown: Model.visible(repos, filter, query)
  readonly property int attentionCount: Model.count(repos, "attention")
  readonly property int cursor: {
    for (var i = 0; i < shown.length; i++) if (shown[i].path === selectedPath) return i
    return shown.length > 0 ? 0 : -1
  }
  readonly property var selected: cursor >= 0 ? shown[cursor] : null
  readonly property bool canCommit: !!selected && !acting && (Model.changes(selected) > 0 || selected.merging)
  readonly property bool canPush: !!selected && !acting && selected.hasRemote && Model.needsPush(selected)
  readonly property bool canPull: !!selected && !acting && !!selected.upstream
  readonly property bool canMerge: !!selected && !acting && (selected.branches || []).length > 0

  // Git actions on the selected repo.
  property bool acting: false
  property string actingLabel: ""
  property string resultPath: ""
  property string resultText: ""
  property bool resultOk: true
  property bool mergeOpen: false
  property string pendingMerge: ""
  onSelectedChanged: { mergeOpen = false; pendingMerge = "" }

  function act(action, r, arg) {
    if (!r || acting) return
    acting = true
    actingLabel = tr("acting." + action)
    resultPath = r.path
    resultText = ""
    mergeOpen = false
    pendingMerge = ""
    actProc.command = ["/usr/bin/python3", "-I", actionPath, action, r.path].concat(arg !== undefined ? arg : [])
    actProc.running = true
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function scan(fetch) {
    if (scanProc.running) { if (fetch) pendingFetch = true; return }
    var args = ["/usr/bin/python3", "-I", scriptPath, "--depth", String(depth)]
    if (fetch) args.push("--fetch")
    for (var i = 0; i < excludes.length; i++) args.push("--exclude", excludes[i])
    scanProc.command = args.concat(roots)
    scanning = true
    fetching = fetch
    scanProc.running = true
  }

  function moveCursor(dy) {
    if (shown.length === 0) return
    var i = Math.max(0, Math.min(shown.length - 1, cursor + dy))
    selectedPath = shown[i].path
    list.positionViewAtIndex(i, ListView.Contain)
  }

  function cycleFilter(dx) {
    var i = Model.FILTERS.indexOf(filter)
    filter = Model.FILTERS[(i + dx + Model.FILTERS.length) % Model.FILTERS.length]
  }

  function openWeb(r) {
    var url = r ? Model.safeUrl(r.url) : ""
    if (url) { Util.execArgv(["omarchy-launch-browser", url]); root.close() }
    else if (r) openTerminal(r)
  }
  function openTerminal(r, cmd) {
    if (!r) return
    Util.execArgv(["setsid", "uwsm-app", "--", "xdg-terminal-exec", "--dir=" + r.path].concat(cmd || []))
    root.close()
  }
  function openFiles(r) {
    if (!r) return
    Util.execArgv(["xdg-open", r.path])
    root.close()
  }

  onOpenedChanged: if (opened) { now = Date.now(); if (Date.now() - scannedAt > 30000) scan(false) }

  Process {
    id: scanProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var data = JSON.parse(String(text || "{}"))
          if (!Array.isArray(data.repos)) throw new Error("bad output")
          root.repos = data.repos.slice(0, 400)
          root.scannedAt = Date.now()
          if (data.fetched) root.fetchedAt = Date.now()
          root.error = ""
        } catch (e) {
          root.error = root.tr("scanFailed")
        }
      }
    }
    onExited: function(code) {
      if (code !== 0) root.error = root.tr("scanFailed")
      root.scanning = false
      root.fetching = false
      root.now = Date.now()
      if (root.pendingFetch) { root.pendingFetch = false; Qt.callLater(function() { root.scan(true) }) }
    }
  }

  Process {
    id: actProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var res = JSON.parse(String(text || "{}"))
          root.resultOk = res.ok === true
          // The tail carries git's verdict and our hint.
          var lines = String(res.output || "").split("\n").filter(function(l) { return l.trim() !== "" })
          root.resultText = lines.slice(-5).join("\n").slice(-600) || root.tr(root.resultOk ? "done" : "failed")
        } catch (e) {
          root.resultOk = false
          root.resultText = root.tr("failed")
        }
      }
    }
    onExited: {
      root.acting = false
      root.scan(false)
    }
  }

  Timer {
    interval: root.refreshIntervalSec * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.scan(false)
  }
  Timer {
    interval: root.fetchIntervalSec * 1000
    running: root.autoFetch
    repeat: true
    onTriggered: root.scan(true)
  }
  Timer {
    interval: 30000
    running: root.opened
    repeat: true
    onTriggered: root.now = Date.now()
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { root.scan(false); return "ok" }
    function fetch(): string { root.scan(true); return "ok" }
    function status(): string { return root.attentionCount + "/" + root.repos.length }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰊢"
    labelText: root.attentionCount > 0 ? String(root.attentionCount) : ""
    active: root.attentionCount > 0
    tooltipText: root.attentionCount > 0
      ? root.tr("tooltip", { attention: root.attentionCount, repos: root.repos.length })
      : root.tr("tooltipClean", { repos: root.repos.length })
    onPressed: function(b) {
      if (b === Qt.RightButton) root.scan(false)
      else if (b === Qt.MiddleButton) root.scan(true)
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(520))
    contentHeight: panel.fittedContentHeight(Style.space(760), Style.space(760))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      // While searching, the field owns every key; its own handlers below cover Esc/Enter/arrows.
      blocked: search.activeFocus || commitField.activeFocus
      onMoveRequested: function(dx, dy) {
        if (dy !== 0) root.moveCursor(dy)
        else if (dx !== 0) root.cycleFilter(dx)
      }
      onActivateRequested: root.openWeb(root.selected)
      onCloseRequested: {
        if (search.text !== "") search.text = ""
        else root.close()
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r") root.scan(false)
        else if (t === "f") root.scan(true)
        else if (t === "t") root.openTerminal(root.selected)
        else if (t === "g") root.openTerminal(root.selected, ["lazygit"])
        else if (t === "o") root.openFiles(root.selected)
        else if (t === "/") search.forceActiveFocus()
        else if (t === "c" && root.canCommit) commitField.forceActiveFocus()
        else if (t === "p" && root.canPush) root.act("push", root.selected)
        else if (t === "u" && root.canPull) root.act("pull", root.selected)
        else if (t === "m" && root.selected) root.mergeOpen = !root.mergeOpen
      }

      ColumnLayout {
        anchors.fill: parent
        spacing: Style.space(10)

        // Header: title, summary, refresh + fetch.
        RowLayout {
          Layout.fillWidth: true
          spacing: Style.space(8)
          Text {
            textFormat: Text.PlainText
            text: "󰊢"
            color: root.attentionCount > 0 ? root.urgent : root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.display
          }
          ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space(1)
            Text {
              textFormat: Text.PlainText
              text: root.tr("title")
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.heading
              font.bold: true
            }
            Text {
              textFormat: Text.PlainText
              Layout.fillWidth: true
              elide: Text.ElideRight
              color: root.error ? root.urgent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              text: root.error ? root.error
                : root.fetching ? root.tr("fetching")
                : root.scanning && root.repos.length === 0 ? root.tr("scanning")
                : (root.attentionCount > 0 ? root.tr("summary", { repos: root.repos.length, attention: root.attentionCount })
                                           : root.tr("allClean", { repos: root.repos.length }))
                  + " · " + (root.fetchedAt ? root.tr("fetchedAgo", { age: Model.age(root.fetchedAt / 1000, root.now) }) : root.tr("neverFetched"))
            }
          }
          PanelActionButton {
            iconText: "󰑐"
            tooltipText: root.tr("action.refresh")
            foreground: root.foreground
            fontFamily: root.fontFamily
            opacity: root.scanning && !root.fetching ? 0.5 : 1
            onClicked: root.scan(false)
          }
          PanelActionButton {
            iconText: "󰇚"
            tooltipText: root.tr("action.fetch")
            foreground: root.foreground
            fontFamily: root.fontFamily
            opacity: root.fetching ? 0.5 : 1
            onClicked: root.scan(true)
          }
        }

        // Search line.
        CursorSurface {
          Layout.fillWidth: true
          implicitHeight: Style.spacing.controlHeight
          bordered: true
          foreground: root.foreground
          Text {
            textFormat: Text.PlainText
            anchors.fill: search
            verticalAlignment: Text.AlignVCenter
            visible: search.text === ""
            text: root.tr("search")
            color: root.dim
            font: search.font
          }
          FilterInput {
            id: search
            anchors.fill: parent
            anchors.leftMargin: Style.spacing.controlPaddingX
            anchors.rightMargin: Style.spacing.controlPaddingX
            verticalAlignment: TextInput.AlignVCenter
            keyHandler: keyCatcher
            focus: false
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            onTextChanged: root.query = text
            Keys.onEscapePressed: { if (text !== "") text = ""; else keyCatcher.forceActiveFocus() }
            Keys.onReturnPressed: root.openWeb(root.selected)
            Keys.onUpPressed: root.moveCursor(-1)
            Keys.onDownPressed: root.moveCursor(1)
          }
        }

        // Filter chips with live counts.
        Flow {
          Layout.fillWidth: true
          spacing: Style.space(6)
          Repeater {
            model: Model.FILTERS
            CursorSurface {
              id: chip
              required property string modelData
              readonly property int n: Model.count(root.repos, modelData)
              current: root.filter === modelData
              bordered: true
              foreground: root.foreground
              implicitWidth: chipText.implicitWidth + Style.space(16)
              implicitHeight: chipText.implicitHeight + Style.space(8)
              Text {
                id: chipText
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: root.tr("filter." + chip.modelData) + "  " + chip.n
                color: chip.modelData !== "all" && chip.modelData !== "noRemote" && chip.n > 0 ? root.urgent : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.filter = chip.modelData
              }
            }
          }
        }

        PanelSeparator { Layout.fillWidth: true; foreground: root.foreground }

        Text {
          textFormat: Text.PlainText
          visible: root.shown.length === 0 && !root.scanning
          Layout.fillWidth: true
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.WordWrap
          text: root.repos.length === 0 ? root.tr("emptyAll") : root.tr("empty")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        ListView {
          id: list
          Layout.fillWidth: true
          Layout.fillHeight: true
          clip: true
          spacing: Style.space(4)
          boundsBehavior: Flickable.StopAtBounds
          model: root.shown
          ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
          delegate: RepoRow {
            required property var modelData
            required property int index
            width: list.width - Style.space(6)
            repo: modelData
            rowIndex: index
          }
        }

        // Actions for the selected repo.
        BorderSurface {
          id: actionCard
          Layout.fillWidth: true
          visible: !!root.selected
          implicitHeight: actionColumn.implicitHeight + Style.space(20)
          radius: Style.cornerRadius
          color: Commons.Util.alpha(root.foreground, 0.05)
          borderSpec: Border.controlSpec("normal", root.foreground, Commons.Color.accent)

          ColumnLayout {
            id: actionColumn
            anchors.fill: parent
            anchors.margins: Style.space(10)
            spacing: Style.space(8)

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.space(6)
              Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: root.selected ? root.selected.name + "   " + (root.selected.branch || "") : ""
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.subtitle
                font.bold: true
              }
              Text {
                textFormat: Text.PlainText
                visible: !!root.selected && root.selected.merging
                text: root.tr("merging")
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.space(6)
              TextField {
                id: commitField
                Layout.fillWidth: true
                enabled: root.canCommit
                opacity: enabled ? 1 : 0.5
                placeholderText: root.canCommit ? root.tr("commitPlaceholder") : root.tr("nothingToCommit")
                foreground: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                onAccepted: if (text.trim() !== "") { root.act("commit", root.selected, text.trim()); text = "" }
                Keys.onEscapePressed: function(event) { keyCatcher.forceActiveFocus(); event.accepted = true }
              }
              Button {
                text: root.tr("commit")
                iconText: "󰜘"
                bordered: true
                enabled: root.canCommit && commitField.text.trim() !== ""
                opacity: enabled ? 1 : 0.45
                foreground: root.foreground
                fontFamily: root.fontFamily
                tooltipText: root.tr("commitTip")
                onClicked: { root.act("commit", root.selected, commitField.text.trim()); commitField.text = "" }
              }
            }

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.space(6)
              Button {
                Layout.fillWidth: true
                text: root.selected && root.selected.behind ? root.tr("pullN", { n: root.selected.behind }) : root.tr("pull")
                iconText: "󰁅"
                bordered: true
                enabled: root.canPull
                opacity: enabled ? 1 : 0.45
                foreground: root.foreground
                fontFamily: root.fontFamily
                tooltipText: root.tr("pullTip")
                onClicked: root.act("pull", root.selected)
              }
              Button {
                Layout.fillWidth: true
                text: root.selected && root.selected.ahead ? root.tr("pushN", { n: root.selected.ahead }) : root.tr("push")
                iconText: "󰁝"
                bordered: true
                enabled: root.canPush
                opacity: enabled ? 1 : 0.45
                foreground: root.foreground
                fontFamily: root.fontFamily
                tooltipText: root.selected && !root.selected.upstream ? root.tr("pushNewTip") : root.tr("pushTip")
                onClicked: root.act("push", root.selected)
              }
              Button {
                Layout.fillWidth: true
                visible: !(root.selected && root.selected.merging)
                text: root.tr("merge")
                iconText: "󰘭"
                bordered: true
                selected: root.mergeOpen
                enabled: root.canMerge
                opacity: enabled ? 1 : 0.45
                foreground: root.foreground
                fontFamily: root.fontFamily
                tooltipText: root.tr("mergeTip")
                onClicked: { root.mergeOpen = !root.mergeOpen; root.pendingMerge = "" }
              }
              Button {
                Layout.fillWidth: true
                visible: !!root.selected && root.selected.merging
                text: root.tr("abortMerge")
                iconText: "󰜺"
                bordered: true
                enabled: !root.acting
                foreground: root.urgent
                fontFamily: root.fontFamily
                tooltipText: root.tr("abortTip")
                onClicked: root.act("abort", root.selected)
              }
            }

            // Merge picker: choose a branch, then confirm.
            Text {
              textFormat: Text.PlainText
              visible: root.mergeOpen && root.pendingMerge === ""
              Layout.fillWidth: true
              wrapMode: Text.WordWrap
              text: root.selected ? root.tr("pickBranch", { branch: root.selected.branch }) : ""
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            Flow {
              Layout.fillWidth: true
              visible: root.mergeOpen && root.pendingMerge === ""
              spacing: Style.space(6)
              Repeater {
                model: root.selected ? root.selected.branches || [] : []
                Button {
                  required property string modelData
                  text: modelData
                  iconText: "\ue725"
                  bordered: true
                  fontSize: Style.font.bodySmall
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  onClicked: root.pendingMerge = modelData
                }
              }
            }
            RowLayout {
              Layout.fillWidth: true
              visible: root.pendingMerge !== ""
              spacing: Style.space(6)
              Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: root.selected ? root.tr("confirmMerge", { from: root.pendingMerge, into: root.selected.branch }) : ""
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              Button {
                text: root.tr("confirm")
                bordered: true
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.act("merge", root.selected, [root.pendingMerge, root.selected.branch])
              }
              Button {
                text: root.tr("cancel")
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: { root.pendingMerge = ""; root.mergeOpen = false }
              }
            }

            // Progress and the last result for this repo.
            Text {
              textFormat: Text.PlainText
              Layout.fillWidth: true
              visible: root.acting || (root.resultText !== "" && root.selected && root.resultPath === root.selected.path)
              wrapMode: Text.WrapAnywhere
              maximumLineCount: 5
              elide: Text.ElideRight
              text: root.acting ? root.actingLabel : (root.resultOk ? "✓ " : "✗ ") + root.resultText
              color: root.acting ? root.dim : (root.resultOk ? root.foreground : root.urgent)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }

        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          horizontalAlignment: Text.AlignHCenter
          text: root.tr("hint")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
      }
    }
  }

  component RepoRow: CursorSurface {
    id: row
    property var repo: ({})
    property int rowIndex: 0
    readonly property bool attention: Model.needsAttention(repo)

    hasCursor: root.cursor === rowIndex
    foreground: root.foreground
    implicitHeight: body.implicitHeight + Style.space(14)

    MouseArea {
      id: rowMouse
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: root.selectedPath = row.repo.path
      onDoubleClicked: root.openWeb(row.repo)
    }

    RowLayout {
      anchors.fill: parent
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(6)
      spacing: Style.space(8)

      Rectangle {
        Layout.alignment: Qt.AlignVCenter
        implicitWidth: Style.space(6)
        implicitHeight: Style.space(6)
        radius: width / 2
        color: row.attention ? root.urgent : Qt.darker(root.foreground, 2.2)
      }

      ColumnLayout {
        id: body
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        spacing: Style.space(2)

        RowLayout {
          Layout.fillWidth: true
          spacing: Style.space(6)
          Text {
            textFormat: Text.PlainText
            Layout.maximumWidth: row.width * 0.5
            elide: Text.ElideRight
            text: row.repo.name || ""
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            font.bold: true
          }
          Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            elide: Text.ElideRight
            text: " " + (row.repo.branch || "") + (row.repo.upstream ? "  →  " + row.repo.upstream : "")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Flow {
          Layout.fillWidth: true
          spacing: Style.space(8)
          Repeater {
            model: Model.badges(row.repo)
            Text {
              required property var modelData
              textFormat: Text.PlainText
              text: root.tr("badge." + modelData.key, { n: modelData.n })
              color: modelData.urgent ? root.urgent : (modelData.key === "clean" ? root.dim : root.foreground)
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }
        }

        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          elide: Text.ElideRight
          text: (row.repo.displayPath || "") + (row.repo.lastCommit
            ? "  ·  " + Model.age(row.repo.lastCommit, root.now) + " · " + (row.repo.subject || "") : "")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      PanelActionButton {
        id: webBtn
        visible: Model.safeUrl(row.repo.url) !== ""
        iconText: Model.hostIcon(row.repo.url)
        tooltipText: root.tr("action.open")
        foreground: root.foreground
        fontFamily: root.fontFamily
        onClicked: root.openWeb(row.repo)
      }
      PanelActionButton {
        id: gitBtn
        iconText: "󰊢"
        tooltipText: root.tr("action.lazygit")
        foreground: root.foreground
        fontFamily: root.fontFamily
        onClicked: root.openTerminal(row.repo, ["lazygit"])
      }
      PanelActionButton {
        id: termBtn
        iconText: "\ue795"
        tooltipText: root.tr("action.terminal")
        foreground: root.foreground
        fontFamily: root.fontFamily
        onClicked: root.openTerminal(row.repo)
      }
    }
  }
}
