"""Entry point for VK_IMPACT application."""
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kivy.core.window import Window
from src.ui.app import VKImpactApp


def main():
    """Initializes window properties and runs the application."""
    # Set default window dimensions for mobile-style preview on desktop
    Window.size = (420, 780)
    Window.minimum_width = 360
    Window.minimum_height = 600

    app = VKImpactApp()
    app.run()


if __name__ == "__main__":
    main()
