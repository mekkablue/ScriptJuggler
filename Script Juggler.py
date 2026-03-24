# MenuTitle: Script Juggler
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals
__doc__ = """
Manage a custom workflow of Glyphs scripts: collect, reorder, toggle done status, run.
"""

import os
import re
import copy
import fnmatch
import traceback
import ast
import objc
import vanilla
from AppKit import (
	NSApplication,
	NSMenu, NSMenuItem,
	NSAlert, NSAlertFirstButtonReturn, NSAlertSecondButtonReturn,
	NSSavePanel, NSOpenPanel, NSModalResponseOK,
	NSEvent, NSKeyDownMask, NSEventModifierFlagCommand,
	NSDragOperationMove,
	NSTableViewDropAbove,
	NSPasteboardItem,
	NSTextAlignmentCenter,
	NSBezierPath,
	NSCell,
	NSColor,
	NSString, NSFont, NSForegroundColorAttributeName,
	NSFontAttributeName, NSParagraphStyleAttributeName,
	NSMutableParagraphStyle, NSLeftTextAlignment, NSRightTextAlignment,
	NSPasteboard,
)
from Foundation import (
	NSObject,
	NSPropertyListSerialization,
	NSPropertyListXMLFormat_v1_0,
	NSData, NSURL, NSIndexSet,
)
import GlyphsApp as _GlyphsAppModule
from GlyphsApp import Glyphs


# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPTS_FOLDER = os.path.expanduser("~/Library/Application Support/Glyphs 3/Scripts")
ROW_HEIGHT = 28
BOTTOM_BAR_HEIGHT = 36
DRAG_COL_WIDTH = 20
DONE_COL_WIDTH = 22
PLAY_COL_WIDTH = 44
SCROLLBAR_WIDTH = 16
INSET = 8
MIN_TITLE_WIDTH = 80
MIN_WINDOW_WIDTH = DRAG_COL_WIDTH + DONE_COL_WIDTH + MIN_TITLE_WIDTH + PLAY_COL_WIDTH + SCROLLBAR_WIDTH + 20
MIN_WINDOW_HEIGHT = ROW_HEIGHT * 2 + ROW_HEIGHT // 2 + BOTTOM_BAR_HEIGHT + 22

SELF_NAME = "Script Juggler"

# Column index constants (must match columnDescriptions order)
COL_NUM = 0
COL_DONE = 1
COL_TITLE = 2
COL_PLAY = 3


# ─── Helpers ──────────────────────────────────────────────────────────────────

def getFontFolder():
	"""Return the folder of the frontmost saved font, or None."""
	for font in Glyphs.fonts:
		if font.filepath:
			return os.path.dirname(font.filepath)
	return None


def getMenuTitle(path):
	"""Extract #MenuTitle (or # MenuTitle) from the first 3 lines. Returns None if absent."""
	try:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			for i, line in enumerate(f):
				if i >= 3:
					break
				m = re.match(r"#\s*MenuTitle:\s*(.+)", line)
				if m:
					return m.group(1).strip()
	except Exception:
		pass
	return None


def getScriptDoc(path):
	"""Extract the module __doc__ string from a script file.

	Handles two conventions:
	  1. Bare string literal as first statement (standard Python)
	  2. __doc__ = '''...''' assignment (Glyphs script convention)
	"""
	try:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			source = f.read()
		# Standard Python: bare string literal as first statement
		try:
			tree = ast.parse(source)
			if (tree.body and isinstance(tree.body[0], ast.Expr)
					and isinstance(tree.body[0].value, ast.Constant)
					and isinstance(tree.body[0].value.value, str)):
				doc = tree.body[0].value.value.strip()
				lines = doc.split("\n")
				if lines:
					return "\n".join(line.rstrip() for line in lines).strip()
		except SyntaxError:
			pass
		# Glyphs convention: __doc__ = """...""" or '''...''' assignment
		m = re.search(r'__doc__\s*=\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')', source, re.DOTALL)
		if m:
			doc = (m.group(1) or m.group(2) or "").strip()
			lines = doc.split("\n")
			return "\n".join(line.rstrip() for line in lines).strip()
	except Exception:
		pass
	return ""


def collectAllScripts():
	"""
	Walk the Glyphs Scripts folder and return a sorted list of dicts for every
	.py file that declares a MenuTitle in its first 3 lines (excluding Script Juggler).

	Each dict: {path, title, displayPath, subfolders, done, doc}
	Sorted: alphabetically by subfolder chain, then by title within the same folder.
	"""
	results = []
	if not os.path.isdir(SCRIPTS_FOLDER):
		return results

	for root, dirs, files in os.walk(SCRIPTS_FOLDER, followlinks=True):
		dirs.sort()
		for fname in sorted(files):
			if not fname.endswith(".py"):
				continue
			path = os.path.join(root, fname)
			title = getMenuTitle(path)
			if title is None:
				continue
			if SELF_NAME in fname or SELF_NAME in title:
				continue
			relpath = os.path.relpath(path, SCRIPTS_FOLDER)
			parts = relpath.replace("\\", "/").split("/")
			subfolders = parts[:-1]
			displayParts = subfolders + [title]
			displayPath = " → ".join(displayParts)
			results.append({
				"path": path,
				"title": title,
				"displayPath": displayPath,
				"subfolders": subfolders,
				"done": False,
				"doc": getScriptDoc(path),
			})

	results.sort(key=lambda x: ([s.lower() for s in x["subfolders"]], x["title"].lower()))
	return results


def parseSearchTerms(searchText):
	"""
	Parse a search string into a list of terms.
	  - Quoted substrings become one literal term (quotes stripped).
	  - Remaining words are individual terms.
	  - Wildcards (* ?) are supported.
	All terms are lowercased.
	"""
	terms = []
	remaining = searchText.strip()
	while remaining:
		remaining = remaining.lstrip()
		if not remaining:
			break
		if remaining.startswith('"'):
			end = remaining.find('"', 1)
			if end > 0:
				terms.append(remaining[1:end].lower())
				remaining = remaining[end + 1:]
			else:
				terms.append(remaining[1:].lower())
				break
		else:
			space = remaining.find(" ")
			if space > 0:
				terms.append(remaining[:space].lower())
				remaining = remaining[space:]
			else:
				terms.append(remaining.lower())
				break
	return [t for t in terms if t]


def matchesSearchTerms(displayPath, terms):
	"""Return True if displayPath (lowercased) matches every term."""
	lower = displayPath.lower()
	for term in terms:
		if "*" in term or "?" in term:
			if not fnmatch.fnmatch(lower, "*" + term + "*"):
				return False
		else:
			if term not in lower:
				return False
	return True


def runScript(path):
	"""Execute a Glyphs Python script with the full GlyphsApp namespace available."""
	try:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			source = f.read()
		namespace = {k: v for k, v in vars(_GlyphsAppModule).items() if not k.startswith("_")}
		namespace["__file__"] = path
		namespace["__name__"] = "__main__"
		exec(compile(source, path, "exec"), namespace)  # noqa: S102
	except Exception:
		print(f"Script Juggler: error running {os.path.basename(path)}:\n{traceback.format_exc()}")
		Glyphs.showMacroWindow()


DONE_OFF = "○"		# U+25CB  empty circle
DONE_ON  = "✅"		# U+2705  green check-mark button emoji


# ─── Callback-action helper ───────────────────────────────────────────────────

_sjMenuItemHandlers = []  # module-level GC root for NSMenuItem handlers

try:
	class _SJMenuItemHandler(NSObject):
		"""Thin NSObject wrapper that invokes a Python callable from an NSMenuItem action."""
		_callback = None

		def trigger_(self, sender):
			if self._callback is not None:
				self._callback()
except objc.error:
	_SJMenuItemHandler = objc.lookUpClass("_SJMenuItemHandler")


def makeNSMenuItem(title, callback, enabled=True):
	"""Return an NSMenuItem that calls *callback* when selected."""
	handler = _SJMenuItemHandler.alloc().init()
	handler._callback = callback
	_sjMenuItemHandlers.append(handler)  # prevent GC without setting attr on NSMenuItem
	item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "trigger:", "")
	item.setTarget_(handler)
	item.setEnabled_(enabled)
	return item


# ─── Window-close interceptor ─────────────────────────────────────────────────

try:
	class _SJCloseInterceptor(NSObject):
		"""
		NSWindowDelegate proxy that intercepts windowShouldClose: so we can show
		an 'unsaved changes' alert.  All other delegate messages are forwarded to
		the original vanilla delegate via forwardingTargetForSelector_.
		"""
		_juggler = None
		_originalDelegate = None

		def windowShouldClose_(self, sender):
			if self._juggler:
				return self._juggler._confirmClose()
			return True

		def windowWillClose_(self, notification):
			if self._juggler:
				self._juggler._onWindowClose()
			if self._originalDelegate and self._originalDelegate.respondsToSelector_("windowWillClose:"):
				self._originalDelegate.windowWillClose_(notification)

		def respondsToSelector_(self, sel):
			selName = str(sel)
			if selName in ("windowShouldClose:", "windowWillClose:"):
				return True
			if self._originalDelegate:
				return self._originalDelegate.respondsToSelector_(sel)
			return False

		def forwardingTargetForSelector_(self, sel):
			if self._originalDelegate and self._originalDelegate.respondsToSelector_(sel):
				return self._originalDelegate
			return None
except objc.error:
	_SJCloseInterceptor = objc.lookUpClass("_SJCloseInterceptor")


# ─── Tooltip proxy ────────────────────────────────────────────────────────────
# Generic per-row tooltip delegate for cell-based NSTableViews.
# Point _items at any list of dicts and set _key to the field to show.
# tableView:toolTipForCell:rect:... has a pointer-out param (rect), so PyObjC
# requires the return value to be (string, rect).

try:
	class _SJTooltipProxy(NSObject):
		_items            = None   # list of dicts; reassign whenever the list changes
		_key              = "displayPath"
		_originalDelegate = None

		def tableView_toolTipForCell_rect_tableColumn_row_mouseLocation_(
			self, tableView, cell, rect, tableColumn, row, mouseLocation
		):
			text = ""
			if self._items and 0 <= row < len(self._items):
				text = self._items[row].get(self._key, "") or ""
			print(f"[SJTooltip] delegate called row={row} key={self._key!r} items={len(self._items) if self._items else 'None'} text={text[:60]!r}")
			return (text, rect)

		def respondsToSelector_(self, sel):
			if str(sel) == "tableView:toolTipForCell:rect:tableColumn:row:mouseLocation:":
				return True
			if self._originalDelegate:
				return self._originalDelegate.respondsToSelector_(sel)
			return False

		def forwardingTargetForSelector_(self, sel):
			if self._originalDelegate and self._originalDelegate.respondsToSelector_(sel):
				return self._originalDelegate
			return None
	print("[SJTooltipProxy] FRESH class registered")
except objc.error:
	_SJTooltipProxy = objc.lookUpClass("_SJTooltipProxy")
	print("[SJTooltipProxy] using STALE class from cache")


# ─── Drag-to-reorder data source proxy ───────────────────────────────────────

_DRAG_TYPE = "com.mekkablue.ScriptJuggler.rowDrag"


try:
	class _SJDragSource(NSObject):
		"""
		NSTableViewDataSource proxy for row drag-and-drop reorder.
		Uses setData_forType_ / dataForType_ which works with any custom UTI.
		setString_forType_ requires a text-conforming UTI and silently fails for
		custom types, leaving an empty pasteboard that rejects all drops.
		Implements both the modern pasteboardWriterForRow: API and the older
		writeRowsWithIndexes:toPasteboard: fallback.
		"""
		_originalDataSource = None
		_juggler = None

		_ownSelectors = frozenset({
			"tableView:pasteboardWriterForRow:",
			"tableView:validateDrop:proposedRow:proposedDropOperation:",
			"tableView:acceptDrop:row:dropOperation:",
			"tableView:writeRowsWithIndexes:toPasteboard:",
		})

		# ── drag source (new API) ────────────────────────────────────────────────

		def tableView_pasteboardWriterForRow_(self, tableView, row):
			print(f"[SJDragSource] pasteboardWriterForRow: {row}")
			encoded = str(row).encode("utf-8")
			data = NSData.dataWithBytes_length_(encoded, len(encoded))
			item = NSPasteboardItem.alloc().init()
			item.setData_forType_(data, _DRAG_TYPE)
			# Also write as plain text so the drag session always initiates
			item.setString_forType_(str(row), "public.utf8-plain-text")
			print(f"[SJDragSource] pasteboard item created OK for row {row}")
			return item

		# ── drag source (old API fallback) ───────────────────────────────────────

		def tableView_writeRowsWithIndexes_toPasteboard_(self, tableView, indexSet, pboard):
			rows = []
			idx = indexSet.firstIndex()
			while idx != NSNotFound:
				rows.append(idx)
				idx = indexSet.indexGreaterThanIndex_(idx)
			if not rows:
				return False
			encoded = (",".join(str(i) for i in rows)).encode("utf-8")
			data = NSData.dataWithBytes_length_(encoded, len(encoded))
			pboard.clearContents()
			pboard.declareTypes_owner_([_DRAG_TYPE], None)
			pboard.setData_forType_(data, _DRAG_TYPE)
			return True

		# ── drag destination: validate ───────────────────────────────────────────

		def tableView_validateDrop_proposedRow_proposedDropOperation_(
			self, tableView, info, row, operation
		):
			tableView.setDropRow_dropOperation_(row, NSTableViewDropAbove)
			return NSDragOperationMove

		# ── drag destination: accept ─────────────────────────────────────────────

		def tableView_acceptDrop_row_dropOperation_(self, tableView, info, row, operation):
			pboard = info.draggingPasteboard()
			sourceRows = []
			print(f"[SJDragSource] acceptDrop at row={row}")
			# New API: NSPasteboardItem list – check _DRAG_TYPE first, then plain text
			for pbItem in (pboard.pasteboardItems() or []):
				data = pbItem.dataForType_(_DRAG_TYPE)
				if data:
					try:
						for tok in bytes(data).decode("utf-8").split(","):
							sourceRows.append(int(tok.strip()))
					except (ValueError, UnicodeDecodeError):
						pass
				if not sourceRows:
					s = pbItem.stringForType_("public.utf8-plain-text")
					if s:
						try:
							for tok in str(s).split(","):
								sourceRows.append(int(tok.strip()))
						except (ValueError, UnicodeDecodeError):
							pass
			# Old API fallback: flat NSData on pasteboard
			if not sourceRows:
				data = pboard.dataForType_(_DRAG_TYPE)
				if data:
					try:
						for tok in bytes(data).decode("utf-8").split(","):
							sourceRows.append(int(tok.strip()))
					except (ValueError, UnicodeDecodeError):
						pass
			print(f"[SJDragSource] sourceRows={sourceRows}")
			if not sourceRows:
				return False
			if self._juggler:
				self._juggler._moveRows(sorted(sourceRows), row)
			return True

		# ── forwarding ───────────────────────────────────────────────────────────

		def respondsToSelector_(self, sel):
			if str(sel) in self._ownSelectors:
				return True
			if self._originalDataSource:
				return self._originalDataSource.respondsToSelector_(sel)
			return False

		def forwardingTargetForSelector_(self, sel):
			if str(sel) not in self._ownSelectors and self._originalDataSource:
				if self._originalDataSource.respondsToSelector_(sel):
					return self._originalDataSource
			return None
	print("[SJDragSource] FRESH class registered")
except objc.error:
	_SJDragSource = objc.lookUpClass("_SJDragSource")
	print("[SJDragSource] using STALE class from cache")


# ─── Table single-click handler ───────────────────────────────────────────────

try:
	class _SJTableClickHandler(NSObject):
		"""Receives NSTableView single-click actions and dispatches to the juggler."""
		_juggler = None

		def tableClicked_(self, sender):
			if self._juggler is None:
				return
			col = sender.clickedColumn()
			row = sender.clickedRow()
			if row < 0 or col < 0:
				return
			self._juggler._onCellClick(col, row)
except objc.error:
	_SJTableClickHandler = objc.lookUpClass("_SJTableClickHandler")


# ─── Custom table cells (NSBezierPath rendering) ──────────────────────────────

try:
	class _SJDoneCell(NSCell):
		"""Grey-stroked empty circle when not done; solid green circle when done."""

		def drawWithFrame_inView_(self, frame, view):
			cx = frame.origin.x + frame.size.width  * 0.5
			cy = frame.origin.y + frame.size.height * 0.5
			r  = min(frame.size.width, frame.size.height) * 0.24
			path = NSBezierPath.bezierPathWithOvalInRect_(((cx - r, cy - r), (r * 2.0, r * 2.0)))
			hi = self.isHighlighted()
			if str(self.objectValue() or "") == DONE_ON:
				(NSColor.whiteColor() if hi else
				 NSColor.colorWithCalibratedRed_green_blue_alpha_(0.204, 0.780, 0.349, 1.0)).setFill()
				path.fill()
			else:
				NSColor.colorWithCalibratedWhite_alpha_(0.85 if hi else 0.55, 1.0).setStroke()
				path.setLineWidth_(1.5)
				path.stroke()
except objc.error:
	_SJDoneCell = objc.lookUpClass("_SJDoneCell")


try:
	class _SJPlayCell(NSCell):
		"""Right-pointing filled triangle (play button)."""

		def drawWithFrame_inView_(self, frame, view):
			cx = frame.origin.x + frame.size.width  * 0.5
			cy = frame.origin.y + frame.size.height * 0.5
			th = min(frame.size.width, frame.size.height) * 0.46	# vertical extent
			tw = th * 0.84									# horizontal extent
			path = NSBezierPath.bezierPath()
			path.moveToPoint_((cx - tw * 0.45, cy - th * 0.5))
			path.lineToPoint_((cx + tw * 0.55, cy))
			path.lineToPoint_((cx - tw * 0.45, cy + th * 0.5))
			path.closePath()
			(NSColor.whiteColor() if self.isHighlighted() else
			 NSColor.colorWithCalibratedWhite_alpha_(0.35, 1.0)).setFill()
			path.fill()
except objc.error:
	_SJPlayCell = objc.lookUpClass("_SJPlayCell")


try:
	class _SJNumCell(NSCell):
		"""Right-aligned monospaced row-position number, vertically centered."""

		def drawWithFrame_inView_(self, frame, view):
			val = self.objectValue()
			text = str(val) if val is not None else ""
			para = NSMutableParagraphStyle.alloc().init()
			para.setAlignment_(NSRightTextAlignment)
			hi = self.isHighlighted()
			attrs = {
				NSFontAttributeName: NSFont.monospacedDigitSystemFontOfSize_weight_(10, 0),
				NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(1.0 if hi else 0.40, 1.0),
				NSParagraphStyleAttributeName: para,
			}
			nsStr = NSString.stringWithString_(text)
			textSize = nsStr.sizeWithAttributes_(attrs)
			ty = frame.origin.y + (frame.size.height - textSize.height) * 0.5
			drawRect = ((frame.origin.x, ty), (frame.size.width - 2, textSize.height))
			nsStr.drawInRect_withAttributes_(drawRect, attrs)
except objc.error:
	_SJNumCell = objc.lookUpClass("_SJNumCell")


try:
	class _SJTitleCell(NSCell):
		"""Left-aligned title text, vertically centered in row."""

		def drawWithFrame_inView_(self, frame, view):
			val = self.objectValue() or ""
			para = NSMutableParagraphStyle.alloc().init()
			para.setAlignment_(NSLeftTextAlignment)
			hi = self.isHighlighted()
			attrs = {
				NSFontAttributeName: NSFont.systemFontOfSize_(13),
				NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(1.0 if hi else 0.0, 1.0),
				NSParagraphStyleAttributeName: para,
			}
			nsStr = NSString.stringWithString_(str(val))
			textSize = nsStr.sizeWithAttributes_(attrs)
			ty = frame.origin.y + (frame.size.height - textSize.height) * 0.5
			drawRect = ((frame.origin.x + 4, ty), (frame.size.width - 8, textSize.height))
			nsStr.drawInRect_withAttributes_(drawRect, attrs)
except objc.error:
	_SJTitleCell = objc.lookUpClass("_SJTitleCell")


# ─── Collect window ───────────────────────────────────────────────────────────

class CollectWindow:
	"""Floating dialog for picking scripts to add to the juggler."""

	def __init__(self, juggler):
		self._juggler = juggler
		self._allScripts = collectAllScripts()
		self._filtered = list(self._allScripts)

		windowWidth = 620
		windowHeight = 520
		self.w = vanilla.Window(
			(windowWidth, windowHeight),
			"Collect Scripts",
			minSize=(400, 300),
			maxSize=(1400, 1000),
		)

		inset = 10
		self.w.searchLabel = vanilla.TextBox(
			(inset, 13, 52, 18), "Search:", sizeStyle="small"
		)
		self.w.searchField = vanilla.EditText(
			(inset + 56, 8, -inset, 24),
			"",
			callback=self._filterScripts,
			continuous=True,
		)
		self.w.searchField.setToolTip(
			"Space-separated search terms (AND). Use * and ? as wildcards. "
			"Put \"quotes\" around a phrase for literal search."
		)

		self.w.scriptList = vanilla.List(
			(inset, 40, -inset, -50),
			[],
			columnDescriptions=[{"title": "Script", "key": "displayPath"}],
			showColumnTitles=False,
			allowsMultipleSelection=True,
			doubleClickCallback=self._collectSelected,
			rowHeight=22,
			autohidesScrollers=False,
		)
		# Per-row tooltip delegate: shows the script's __doc__ on hover
		ctv = self.w.scriptList.getNSTableView()
		self._tooltipDelegate = _SJTooltipProxy.alloc().init()
		self._tooltipDelegate._items = self._filtered
		self._tooltipDelegate._key   = "doc"
		self._tooltipDelegate._originalDelegate = ctv.delegate()
		ctv.setDelegate_(self._tooltipDelegate)
		# Enable tooltips (required for the delegate method to fire)
		ctv.setToolTip_("")
		_sample = repr(self._filtered[0].get("doc", "")[:40]) if self._filtered else "N/A"
		print(f"[CollectWindow] tooltip delegate installed; {len(self._filtered)} scripts; sample doc={_sample}")

		self.w.cancelButton = vanilla.Button(
			(-inset - 180, -40, -inset - 90, -inset), "Cancel", callback=self._cancel
		)
		self.w.collectButton = vanilla.Button(
			(-inset - 80, -40, -inset, -inset), "Collect", callback=self._collectSelected
		)

		self.w.setDefaultButton(self.w.collectButton)

		self._updateList()
		self.w.open()
		self.w.makeKey()

	# ── internal ──────────────────────────────────────────────────────────────

	def _filterScripts(self, sender=None):
		text = self.w.searchField.get().strip()
		if not text:
			self._filtered = list(self._allScripts)
		else:
			terms = parseSearchTerms(text)
			self._filtered = [s for s in self._allScripts if matchesSearchTerms(s["displayPath"], terms)]
		self._updateList()

	def _updateList(self):
		self._tooltipDelegate._items = self._filtered   # re-point after filter changes
		self.w.scriptList.set([{"displayPath": s["displayPath"]} for s in self._filtered])

	def _collectSelected(self, sender=None):
		selection = self.w.scriptList.getSelection()
		if not selection:
			return
		chosen = [self._filtered[i] for i in selection]
		self._juggler.addScripts(chosen)
		self.w.close()

	def _cancel(self, sender=None):
		self.w.close()


# ─── Main window ──────────────────────────────────────────────────────────────

class ScriptJuggler:
	"""Main Script Juggler window."""

	def __init__(self):
		self.entries = []  # list of {path, title, displayPath, done, doc}
		self._undoBuffer = None  # stores entries just before last delete
		self._hasUnsaved = False
		self._keyMonitor = None
		self._collectWindow = None

		# ── build window ──────────────────────────────────────────────────────
		self.w = vanilla.Window(
			(500, 400),
			SELF_NAME,
			minSize=(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
			autosaveName="com.mekkablue.ScriptJuggler.mainwindow",
		)

		columnDescriptions = [
			{"title": "", "key": "drag", "width": DRAG_COL_WIDTH, "editable": False},
			{"title": "", "key": "done", "width": DONE_COL_WIDTH, "editable": False},
			{"title": "Script", "key": "title", "editable": False},
			{"title": "", "key": "play", "width": PLAY_COL_WIDTH, "editable": False},
		]
		self.w.scriptList = vanilla.List(
			(0, 0, -0, -BOTTOM_BAR_HEIGHT),
			[],
			columnDescriptions=columnDescriptions,
			showColumnTitles=False,
			doubleClickCallback=self._listDoubleClicked,
			allowsMultipleSelection=True,
			rowHeight=ROW_HEIGHT,
			autohidesScrollers=True,
			drawVerticalLines=False,
			drawHorizontalLines=False,
		)

		tableView = self.w.scriptList.getNSTableView()

		# Tighten horizontal gaps between columns
		tableView.setIntercellSpacing_((2, 2))

		# Per-row tooltip delegate showing displayPath on hover
		self._tooltipDelegate = _SJTooltipProxy.alloc().init()
		self._tooltipDelegate._items = self.entries
		self._tooltipDelegate._key   = "displayPath"
		self._tooltipDelegate._originalDelegate = tableView.delegate()
		tableView.setDelegate_(self._tooltipDelegate)

		# Install drag-reorder data source (chained)
		self._dragDataSource = _SJDragSource.alloc().init()
		self._dragDataSource._originalDataSource = tableView.dataSource()
		self._dragDataSource._juggler = self
		tableView.setDataSource_(self._dragDataSource)
		tableView.setDraggingSourceOperationMask_forLocal_(NSDragOperationMove, True)
		tableView.registerForDraggedTypes_([_DRAG_TYPE, "public.utf8-plain-text"])

		# Wire single-click action handler for play/done column clicks
		self._tableClickHandler = _SJTableClickHandler.alloc().init()
		self._tableClickHandler._juggler = self
		tableView.setTarget_(self._tableClickHandler)
		tableView.setAction_("tableClicked:")

		# Replace default text cells with custom drawn cells
		tableView.tableColumns()[COL_NUM].setDataCell_(_SJNumCell.alloc().init())
		tableView.tableColumns()[COL_DONE].setDataCell_(_SJDoneCell.alloc().init())
		tableView.tableColumns()[COL_TITLE].setDataCell_(_SJTitleCell.alloc().init())
		tableView.tableColumns()[COL_PLAY].setDataCell_(_SJPlayCell.alloc().init())

		# ── bottom bar ────────────────────────────────────────────────────────
		self.w.bottomLine = vanilla.HorizontalLine((0, -BOTTOM_BAR_HEIGHT, -0, 1))

		btnY = -BOTTOM_BAR_HEIGHT + (BOTTOM_BAR_HEIGHT - 26) // 2

		self.w.actionsButton = vanilla.Button(
			(INSET, btnY, 30, 26),
			"⋯",
			callback=self._showActionsMenu,
			sizeStyle="small",
		)
		self.w.actionsButton.setToolTip("Actions: Save Preset, Load Preset, Clear")

		self.w.undoButton = vanilla.Button(
			(INSET + 36, btnY, 30, 26),
			"↺",
			callback=self._undoDelete,
			sizeStyle="small",
		)
		self.w.undoButton.setToolTip("Undo last deletion")
		self.w.undoButton.show(False)

		self.w.plusButton = vanilla.Button(
			(-INSET - 30, btnY, 30, 26),
			"+",
			callback=self._openCollect,
		)
		self.w.plusButton.setToolTip("Add scripts (opens Collect dialog)")

		# ── window close interception ─────────────────────────────────────────
		win = self.w._window
		self._closeInterceptor = _SJCloseInterceptor.alloc().init()
		self._closeInterceptor._juggler = self
		self._closeInterceptor._originalDelegate = win.delegate()
		win.setDelegate_(self._closeInterceptor)

		# ── keyboard: delete/backspace ────────────────────────────────────────
		_self = self

		def _keyHandler(event):
			try:
				if _self.w._window and _self.w._window.isKeyWindow():
					tableView = _self.w.scriptList.getNSTableView()
					if tableView.window() and tableView.window().firstResponder() == tableView:
						chars = event.characters()
						mods = event.modifierFlags()
						cmd = bool(mods & NSEventModifierFlagCommand)
						if chars in ("\x7f", "\x08"):  # Delete / Backspace
							_self._deleteSelected()
							return None
						elif chars == " ":  # Space – toggle done
							_self._toggleDoneSelected()
							return None
						elif chars in ("\r", "\x03"):  # Return / Enter – run
							sel = _self.w.scriptList.getSelection()
							if len(sel) == 1:
								_self._runEntry(sel[0])
							return None
						elif cmd and event.keyCode() == 126:  # Cmd-Up – move up
							_self._moveSelectedUp()
							return None
						elif cmd and event.keyCode() == 125:  # Cmd-Down – move down
							_self._moveSelectedDown()
							return None
			except Exception:
				pass
			return event

		self._keyMonitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
			NSKeyDownMask, _keyHandler
		)

		self.w.open()
		self.w.makeKey()

	# ── unsaved / close ───────────────────────────────────────────────────────

	def _markChanged(self):
		self._hasUnsaved = True

	def _confirmClose(self):
		"""Called by _CloseInterceptor.windowShouldClose_. Returns True to allow close."""
		if not self._hasUnsaved or not self.entries:
			return True
		alert = NSAlert.alloc().init()
		alert.setMessageText_("Save changes to Script Juggler?")
		alert.setInformativeText_("Your script list has unsaved changes.")
		alert.addButtonWithTitle_("Save")
		alert.addButtonWithTitle_("Close without Saving")
		alert.addButtonWithTitle_("Cancel")
		response = alert.runModal()
		if response == NSAlertFirstButtonReturn:
			self._savePreset()
			return True
		elif response == NSAlertSecondButtonReturn:
			return True
		return False  # Cancel → block close

	def _onWindowClose(self):
		"""Cleanup called when the window actually closes."""
		if self._keyMonitor:
			NSEvent.removeMonitor_(self._keyMonitor)
			self._keyMonitor = None

	# ── list interaction ──────────────────────────────────────────────────────

	def _onCellClick(self, col, row):
		"""Called by _SJTableClickHandler on every single click."""
		if row < 0 or row >= len(self.entries):
			return
		if col == COL_PLAY:
			self._runEntry(row)
		elif col == COL_DONE:
			self.entries[row]["done"] = not self.entries[row].get("done", False)
			selection = self.w.scriptList.getSelection()
			self._refreshList()
			self.w.scriptList.setSelection(selection)
			self._markChanged()

	def _toggleDoneSelected(self):
		"""Space bar: flip done state for every selected entry."""
		selection = self.w.scriptList.getSelection()
		if not selection:
			return
		for i in selection:
			self.entries[i]["done"] = not self.entries[i].get("done", False)
		self._refreshList()
		self.w.scriptList.setSelection(selection)
		self._markChanged()

	def _moveSelectedUp(self):
		"""Cmd-Up: shift selected rows one position upward."""
		selection = sorted(self.w.scriptList.getSelection())
		if not selection or selection[0] == 0:
			return
		for i in selection:
			self.entries[i - 1], self.entries[i] = self.entries[i], self.entries[i - 1]
		self._refreshList()
		self.w.scriptList.setSelection([i - 1 for i in selection])
		self._markChanged()

	def _moveSelectedDown(self):
		"""Cmd-Down: shift selected rows one position downward."""
		selection = sorted(self.w.scriptList.getSelection(), reverse=True)
		if not selection or selection[0] == len(self.entries) - 1:
			return
		for i in selection:
			self.entries[i + 1], self.entries[i] = self.entries[i], self.entries[i + 1]
		self._refreshList()
		self.w.scriptList.setSelection([i + 1 for i in selection])
		self._markChanged()

	def _listDoubleClicked(self, sender=None):
		"""Double-clicking the title column also runs the script."""
		tableView = self.w.scriptList.getNSTableView()
		col = tableView.clickedColumn()
		row = tableView.clickedRow()
		if row >= 0 and row < len(self.entries) and col == COL_TITLE:
			self._runEntry(row)

	def _moveRows(self, sourceRows, toRow):
		"""Move one or more rows to a new position (called from _RowDragDataSource)."""
		sourceRows = sorted(sourceRows)
		if not sourceRows:
			return
		# No-op: single row dropped onto itself
		if len(sourceRows) == 1 and sourceRows[0] in (toRow, toRow - 1):
			return
		movedEntries = [self.entries[i] for i in sourceRows]
		# Number of source rows that sit before the drop point shifts the insert index
		numBefore = sum(1 for r in sourceRows if r < toRow)
		insertAt = toRow - numBefore
		# Remove source rows (high-to-low to keep lower indices stable)
		for i in reversed(sourceRows):
			del self.entries[i]
		# Re-insert in original relative order
		for entry in reversed(movedEntries):
			self.entries.insert(insertAt, entry)
		self._refreshList()
		self._markChanged()

	# ── sync helpers ──────────────────────────────────────────────────────────

	def _listItems(self):
		"""Build list items from self.entries."""
		return [
			{
				"drag":  str(idx + 1),
				"done":  DONE_ON if entry.get("done", False) else DONE_OFF,
				"title": entry["title"],
				"play":  "▶",
				"_path": entry["path"],		# hidden – used for re-sync after drag
			}
			for idx, entry in enumerate(self.entries)
		]

	def _refreshList(self):
		self._tooltipDelegate._items = self.entries   # re-point after any reassignment
		self.w.scriptList.set(self._listItems())

	def _syncEntriesFromList(self):
		"""Rebuild self.entries in the order currently shown in the list."""
		listItems = self.w.scriptList.get()
		byPath = {e["path"]: e for e in self.entries}
		newEntries = []
		for item in listItems:
			path = item.get("_path", "")
			if path in byPath:
				entry = copy.copy(byPath[path])
				entry["done"] = item.get("done", DONE_OFF) == DONE_ON
				newEntries.append(entry)
		self.entries = newEntries

	# ── run script ────────────────────────────────────────────────────────────

	def _runEntry(self, index):
		if 0 <= index < len(self.entries):
			path = self.entries[index]["path"]
			if os.path.isfile(path):
				runScript(path)
			else:
				print(f"Script Juggler: file not found – {path}")

	# ── add scripts (called from CollectWindow) ───────────────────────────────

	def addScripts(self, scripts):
		"""Insert scripts after the last selected row, or append at the end."""
		selection = self.w.scriptList.getSelection()
		insertAt = max(selection) + 1 if selection else len(self.entries)
		existingPaths = {e["path"] for e in self.entries}
		newEntries = [
			{
				"path": s["path"],
				"title": s["title"],
				"displayPath": s["displayPath"],
				"done": False,
				"doc": s.get("doc", ""),
			}
			for s in scripts
			if s["path"] not in existingPaths
		]
		self.entries[insertAt:insertAt] = newEntries
		self._refreshList()
		self._markChanged()

	# ── delete / undo ─────────────────────────────────────────────────────────

	def _deleteSelected(self):
		selection = sorted(self.w.scriptList.getSelection(), reverse=True)
		if not selection:
			return
		self._undoBuffer = copy.deepcopy(self.entries)
		for i in selection:
			del self.entries[i]
		self._refreshList()
		self.w.undoButton.show(True)
		self._markChanged()

	def _undoDelete(self, sender=None):
		if self._undoBuffer is not None:
			self.entries = copy.deepcopy(self._undoBuffer)
			self._undoBuffer = None
			self._refreshList()
			self.w.undoButton.show(False)
			self._markChanged()

	# ── open collect dialog ───────────────────────────────────────────────────

	def _openCollect(self, sender=None):
		self._collectWindow = CollectWindow(self)

	# ── actions menu ──────────────────────────────────────────────────────────

	def _showActionsMenu(self, sender=None):
		menu = NSMenu.alloc().init()
		menu.setAutoenablesItems_(False)
		menu.addItem_(makeNSMenuItem("Save Preset", self._savePreset))
		menu.addItem_(makeNSMenuItem("Load Preset", self._loadPreset))
		menu.addItem_(NSMenuItem.separatorItem())
		menu.addItem_(makeNSMenuItem("Clear", self._clearEntries, enabled=bool(self.entries)))

		nsButton = self.w.actionsButton._nsObject
		currentEvent = NSApplication.sharedApplication().currentEvent()
		if currentEvent:
			NSMenu.popUpContextMenu_withEvent_forView_(menu, currentEvent, nsButton)
		else:
			# Fallback: pop up at bottom-left of button
			from AppKit import NSPoint
			pt = NSPoint(nsButton.frame().origin.x, nsButton.frame().origin.y)
			menu.popUpMenuPositioningItem_atLocation_inView_(None, pt, nsButton.superview())

	# ── preset: save ──────────────────────────────────────────────────────────

	def _savePreset(self, sender=None):
		panel = NSSavePanel.savePanel()
		panel.setTitle_("Save Script Juggler Preset")
		panel.setAllowedFileTypes_(["plist"])
		panel.setCanCreateDirectories_(True)
		fontFolder = getFontFolder()
		if fontFolder:
			panel.setDirectoryURL_(NSURL.fileURLWithPath_(fontFolder))

		if panel.runModal() != NSModalResponseOK:
			return

		savePath = panel.URL().path()
		if not savePath.endswith(".plist"):
			savePath += ".plist"

		presetData = [
			{
				"path": e["path"],
				"title": e["title"],
				"displayPath": e["displayPath"],
				"done": e.get("done", False),
			}
			for e in self.entries
		]

		plistData, error = NSPropertyListSerialization.dataWithPropertyList_format_options_error_(
			presetData, NSPropertyListXMLFormat_v1_0, 0, None
		)

		if plistData:
			plistData.writeToFile_atomically_(savePath, True)
			self._hasUnsaved = False
		elif error:
			print(f"Script Juggler: could not save preset – {error}")

	# ── preset: load ──────────────────────────────────────────────────────────

	def _loadPreset(self, sender=None):
		panel = NSOpenPanel.openPanel()
		panel.setTitle_("Load Script Juggler Preset")
		panel.setAllowedFileTypes_(["plist"])
		fontFolder = getFontFolder()
		if fontFolder:
			panel.setDirectoryURL_(NSURL.fileURLWithPath_(fontFolder))

		if panel.runModal() != NSModalResponseOK:
			return

		loadPath = panel.URL().path()
		data = NSData.dataWithContentsOfFile_(loadPath)
		if not data:
			print(f"Script Juggler: could not read file – {loadPath}")
			return

		presetData, _, error = NSPropertyListSerialization.propertyListWithData_options_format_error_(
			data, 0, None, None
		)

		if error:
			print(f"Script Juggler: could not parse preset – {error}")
			return

		if presetData:
			self.entries = [
				{
					"path": str(item.get("path", "")),
					"title": str(item.get("title", "")),
					"displayPath": str(item.get("displayPath", "")),
					"done": bool(item.get("done", False)),
					"doc": "",  # reset doc on load
				}
				for item in presetData
			]
			self._refreshList()
			self._hasUnsaved = False

	# ── clear ─────────────────────────────────────────────────────────────────

	def _clearEntries(self, sender=None):
		if not self.entries:
			return
		alert = NSAlert.alloc().init()
		alert.setMessageText_("Clear all entries?")
		alert.setInformativeText_("This will remove all scripts from Script Juggler.")
		alert.addButtonWithTitle_("Clear")
		alert.addButtonWithTitle_("Cancel")
		if alert.runModal() == NSAlertFirstButtonReturn:
			self._undoBuffer = copy.deepcopy(self.entries)
			self.entries = []
			self._refreshList()
			self.w.undoButton.show(True)
			self._markChanged()


# ─── Entry point ──────────────────────────────────────────────────────────────

ScriptJuggler()
