"""High-performance Avatar component with initials fallback and memory caching."""
from kivy.uix.relativelayout import RelativeLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty
from src.data.cache.media_cache import media_cache
from src.utils.formatters import get_avatar_color, get_user_initials


class CircularAvatar(RelativeLayout):
    """Circular avatar with instant initials rendering and non-blocking image loading."""
    
    source = StringProperty("")
    local_source = StringProperty("")
    initials = StringProperty("")
    bg_color = ListProperty([0.24, 0.48, 0.95, 1])
    size_dp = NumericProperty(48)
    is_online = BooleanProperty(False)
    peer_id = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (self.size_dp, self.size_dp)
        self.bind(size_dp=self._update_size, source=self._on_source_change, peer_id=self._on_peer_change)
        if self.source:
            self._load_avatar(self.source)

    def _update_size(self, *args):
        self.size = (self.size_dp, self.size_dp)

    def _on_peer_change(self, instance, value):
        if value:
            self.bg_color = list(get_avatar_color(value))

    def _on_source_change(self, instance, value):
        self._load_avatar(value)

    def _load_avatar(self, url: str):
        if not url:
            self.local_source = ""
            return
            
        local = media_cache.get_local_path(url)
        if local:
            self.local_source = local
        else:
            self.local_source = ""
            media_cache.fetch_image_async(url, on_ready=self._on_image_ready)

    def _on_image_ready(self, local_path: str):
        if local_path and self.source:
            self.local_source = local_path
