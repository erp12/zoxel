# mainwindow.py
# The Zoxel main window.
# Copyright (c) 2013, Graham R King
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from PySide import QtCore
from PySide import QtGui
from dialog_about import AboutDialog
from ui_mainwindow import Ui_MainWindow
from voxel_widget import GLWidget
import json
from palette_widget import PaletteWidget
from io_sproxel import SproxelFile
from io_zoxel import ZoxelFile
from tool_draw import DrawingTool
from tool_paint import PaintingTool
from tool_erase import EraseTool

class MainWindow(QtGui.QMainWindow):

    def __init__(self, parent=None):
        # Initialise the UI
        self.display = None
        super(MainWindow, self).__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # Current file
        self._filename = None
        self._last_file_handler = None
        # Importers / Exporters
        self._file_handlers = []
        # Update our window caption
        self._caption = "Zoxel"
        # Our global state
        self.settings = QtCore.QSettings("Zoxel", "Zoxel")
        self.state = {}
        # Load our state if possible
        self.load_state()
        # Create our GL Widget
        try:
            widget = GLWidget(self.ui.glparent)
            self.ui.glparent.layout().addWidget(widget)
            self.display = widget
        except Exception as E:
            QtGui.QMessageBox.warning(self, "Initialisation Failed",
                str(E))
            exit(1)
        # Create our palette widget
        widget = PaletteWidget(self.ui.palette)
        self.ui.palette.layout().addWidget(widget)
        self.colour_palette = widget
        # More UI state
        value = self.get_setting("display_floor_grid")
        if value is not None:
            self.ui.action_floor_grid.setChecked(value)
            self.display.floor_grid = value
        # Connect some signals
        if self.display:
            self.display.voxels.notify = self.on_data_changed
            self.display.tool_activated.connect(self.on_tool_activated)
        if self.colour_palette:
            self.colour_palette.changed.connect(self.on_colour_changed)
        # Load file handlers
        self._io = []
        self._io.append( SproxelFile(self) )
        self._io.append( ZoxelFile(self) )
        # Initialise our tools
        self._tool_group = QtGui.QActionGroup(self.ui.toolbar_drawing)
        self._tools = []
        self.load_tool(DrawingTool(self))
        self.load_tool(PaintingTool(self))
        self.load_tool(EraseTool(self))
        # Setup window
        self.update_caption()

    @QtCore.Slot()
    def on_action_about_triggered(self):
        dialog = AboutDialog(self)
        if dialog.exec_():
            pass

    @QtCore.Slot()
    def on_action_floor_grid_triggered(self):
        self.display.floor_grid = self.ui.action_floor_grid.isChecked()
        self.set_setting("display_floor_grid", self.display.floor_grid)

    @QtCore.Slot()
    def on_action_new_triggered(self):
        if self.display.voxels.changed:
            if not self.confirm_save():
                return
        # Clear our data
        self._filename = ""
        self.display.clear()
        self.display.voxels.saved()
        self.update_caption()
                
    @QtCore.Slot()
    def on_action_wireframe_triggered(self):
        self.display.wireframe = self.ui.action_wireframe.isChecked()
        self.set_setting("display_wireframe", self.display.wireframe)

    @QtCore.Slot()
    def on_action_save_triggered(self):
        # Save
        self.save()

    @QtCore.Slot()
    def on_action_saveas_triggered(self):
        # Save
        self.save(True)
    
    @QtCore.Slot()
    def on_action_open_triggered(self):
        # Load
        self.load()
        
    def on_tool_activated(self):
        self.activate_tool(self.display.target)

    # Confirm if user wants to save before doing something drastic.
    # returns True if we should continue
    def confirm_save(self):
        responce = QtGui.QMessageBox.question(self,"Save changes?", 
            "Save changes before discarding?", 
            buttons = (QtGui.QMessageBox.Save | QtGui.QMessageBox.Cancel
            | QtGui.QMessageBox.No))
        if responce == QtGui.QMessageBox.StandardButton.Save:
            if not self.save():
                return False
        elif responce == QtGui.QMessageBox.StandardButton.Cancel:
            return False
        return True

    # Voxel data changed signal handler
    def on_data_changed(self):
        self.update_caption()
        
    # Colour selection changed handler
    def on_colour_changed(self):
        self.display.voxel_colour = self.colour_palette.colour

    # Return a section of our internal config
    def get_setting(self, name):
        if name in self.state:
            return self.state[name]
        return None

    # Set some config.  Value should be a serialisable type
    def set_setting(self, name, value):
        self.state[name] = value

    def closeEvent(self, event):
        # Save state
        self.save_state()
        event.accept()

    # Save our state
    def save_state(self):
        try:
            state = json.dumps(self.state)
            self.settings.setValue("system/state", state)
        except Exception as E:
            # XXX Fail. Never displays because we're on our way out
            error = QtGui.QErrorMessage(self)
            error.showMessage(str(E))
            print str(E)

    # Load our state
    def load_state(self):
        try:
            state = self.settings.value("system/state")
            if state:
                self.state = json.loads(state)
        except Exception as E:
            error = QtGui.QErrorMessage(self)
            error.showMessage(str(E))

    # Update the window caption to reflect the current state
    def update_caption(self):
        caption = "Zoxel"
        if self._filename:
            caption += " - [%s]" % self._filename
        else:
            caption += " - [Unsaved model]"
        if self.display and self.display.voxels.changed:
            caption += " *"
        if caption != self._caption:
            self.setWindowTitle(caption)
        self._caption = caption

    # Save the current data
    def save(self, newfile = False):

        # Find the handlers that support saving
        handlers = [x for x in self._file_handlers if hasattr(x, 'save')]

        saved = False
        filename = self._filename
        handler = self._last_file_handler
        if handler:
            filetype = handler.filetype

        # Build list of available types
        choices = []
        for exporter in handlers:
            choices.append( "%s (%s)" % (exporter.description, exporter.filetype))
        choices = ";;".join(choices)

        # Get a filename if we need one
        if newfile or not filename:
            filename, filetype = QtGui.QFileDialog.getSaveFileName(self,
                "Save As",
                "model",
                choices)
            if not filename:
                return
            handler = None

        # Find the handler if we need to
        if not handler:
            for exporter in handlers:
                ourtype = "%s (%s)" % (exporter.description, exporter.filetype)
                if filetype == ourtype:
                    handler =  exporter

        # Call the save handler
        try:
            handler.save(filename)
            saved = True
        except Exception as Ex:
            QtGui.QMessageBox.warning(self, "Save Failed",
            str(Ex))
                    
        # If we saved, clear edited state
        if saved:
            self._filename = filename
            self._last_file_handler = handler
            self.display.voxels.saved()
            self.update_caption()
        return saved

    # Registers an file handler (importer/exporter) with the system
    def register_file_handler(self, handler):
        self._file_handlers.append(handler)

    # Return the voxel data
    def get_voxel_data(self):
        return self.display.voxels

    # load a file
    def load(self):
        # If we have changes, perhaps we should save?
        if self.display.voxels.changed:
            if not self.confirm_save():
                return

        # Find the handlers that support loading
        handler = None
        handlers = [x for x in self._file_handlers if hasattr(x, 'load')]

        # Build list of types we can load
        choices = []
        for importer in handlers:
            choices.append( "%s (%s)" % (importer.description, importer.filetype))
        choices = ";;".join(choices)

        # Get a filename
        filename, filetype = QtGui.QFileDialog.getOpenFileName(self,
                caption="Open file",
                filter=choices)
        if not filename:
            return

        # Find the handler
        for importer in handlers:
            ourtype = "%s (%s)" % (importer.description, importer.filetype)
            if filetype == ourtype:
                handler =  importer
                self._last_file_handler = handler
        
        # Load the file
        self.display.clear()
        self._filename = None
        try:
            handler.load(filename)
            self._filename = filename
        except Exception as Ex:
            QtGui.QMessageBox.warning(self, "Could not load file",
            str(Ex))
            
        self.display.voxels.resize()
        self.display.voxels.saved()
        self.update_caption()
        self.display.refresh()

    def load_tool(self, tool):
        self._tools.append(tool)
        self._tool_group.addAction(tool.get_action())
        self.ui.toolbar_drawing.addAction(tool.get_action())
    
    def activate_tool(self, target):
        action = self._tool_group.checkedAction()
        if not action:
            return
        # Find who owns this action and activate
        for tool in self._tools:
            if tool.get_action() is action:
                tool.on_activate(target)
                return