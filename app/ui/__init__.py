"""UI модули прототипа Liquid Glass для Auraloom Voice Studio.

Соответствует утверждённому дизайну (ui_visual_tokens.json — второй концепт).
"""

from .theme import (
    WINDOW_BG, MICA_FALLBACK, SIDEBAR_BG,
    SURFACE_1, SURFACE_2, SURFACE_3, SURFACE_HOVER, SURFACE_PRESSED,
    BORDER_SUBTLE, BORDER_FOCUS,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, ACCENT_STRONG, ACCENT_GLOW,
    INCOMING_ACCENT, OUTGOING_ACCENT,
    SUCCESS, WARNING, ERROR, BAD,
    TRACK, SLIDER_FILL,
    FONT_FAMILY, FONT_FALLBACK,
    FONT_APP_TITLE, FONT_PAGE_TITLE, FONT_CARD_TITLE,
    FONT_BODY, FONT_SECONDARY, FONT_METRIC, FONT_MONO,
    SPACE_XXS, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL, SPACE_XXL,
    RADIUS_WINDOW, RADIUS_CARD, RADIUS_INNER, RADIUS_CONTROL, RADIUS_PILL,
    BORDER_WIDTH,
    HOVER_MS, FOCUS_MS, SIDEBAR_MS,
    MICA_ENABLED, apply_window_theme, try_mica,
)

from .glass_card import GlassCard
from .navigation import Navigation
from .sidebar import Sidebar
from .home import HomePage
from .voices import VoicesPage
from .settings import SettingsPage
from .main_window import MainWindow

__all__ = [
    # theme
    "WINDOW_BG", "MICA_FALLBACK", "SIDEBAR_BG",
    "SURFACE_1", "SURFACE_2", "SURFACE_3", "SURFACE_HOVER", "SURFACE_PRESSED",
    "BORDER_SUBTLE", "BORDER_FOCUS",
    "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED",
    "ACCENT", "ACCENT_STRONG", "ACCENT_GLOW",
    "INCOMING_ACCENT", "OUTGOING_ACCENT",
    "SUCCESS", "WARNING", "ERROR", "BAD",
    "TRACK", "SLIDER_FILL",
    "FONT_FAMILY", "FONT_FALLBACK",
    "FONT_APP_TITLE", "FONT_PAGE_TITLE", "FONT_CARD_TITLE",
    "FONT_BODY", "FONT_SECONDARY", "FONT_METRIC", "FONT_MONO",
    "SPACE_XXS", "SPACE_XS", "SPACE_SM", "SPACE_MD", "SPACE_LG", "SPACE_XL", "SPACE_XXL",
    "RADIUS_WINDOW", "RADIUS_CARD", "RADIUS_INNER", "RADIUS_CONTROL", "RADIUS_PILL",
    "BORDER_WIDTH",
    "HOVER_MS", "FOCUS_MS", "SIDEBAR_MS",
    "MICA_ENABLED", "apply_window_theme", "try_mica",
    # modules
    "GlassCard", "Navigation", "Sidebar", "HomePage", "VoicesPage",
    "SettingsPage", "MainWindow",
]
