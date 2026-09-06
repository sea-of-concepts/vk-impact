"""Cairo stub module for Android environments where libcairo is unavailable."""

class _DummyCairoObject:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _DummyCairoObject()

    def __call__(self, *args, **kwargs):
        return _DummyCairoObject()


FORMAT_ARGB32 = 0
FORMAT_RGB24 = 1
FORMAT_A8 = 2
FORMAT_A1 = 3
FORMAT_RGB16_565 = 4
FORMAT_RGB30 = 5

Context = _DummyCairoObject
ImageSurface = _DummyCairoObject
SurfacePattern = _DummyCairoObject
Format = _DummyCairoObject
