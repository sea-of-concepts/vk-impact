"""Folder Chip component for dialog folders navigation."""
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty


class FolderChip(ButtonBehavior, BoxLayout):
    """Clickable folder filter chip."""
    folder_id = StringProperty("")
    title = StringProperty("")
    is_active = BooleanProperty(False)
    is_system = BooleanProperty(True)
