pragma Singleton

import QtQuick

/// Дизайн-система RedZ Voice Studio.
///
/// Тёмная «западная» палитра по референсу: угольные поверхности,
/// тёплое золото, приглушённый песочный текст.
/// Один источник правды для цвета, типографики, отступов и таймингов.
QtObject {
    id: theme

    // ------------------------------------------------------------------
    // Поверхности
    // ------------------------------------------------------------------
    readonly property color bg:            "#0A0C10"
    readonly property color bgGlow:        "#121722"
    readonly property color sidebar:       "#0C0F15"
    readonly property color surface0:      "#10141C"
    readonly property color surface1:      "#161B25"
    readonly property color surface2:      "#1E2532"
    readonly property color surface3:      "#28303F"
    readonly property color surfaceHover:  "#2E3647"
    readonly property color surfaceActive: "#3A4356"

    // ------------------------------------------------------------------
    // Границы
    // ------------------------------------------------------------------
    readonly property color border:        "#2A303D"
    readonly property color borderStrong:  "#3D4556"
    readonly property color borderFocus:   "#E3AE5A"

    // ------------------------------------------------------------------
    // Фирменная палитра: золото Дикого Запада
    // ------------------------------------------------------------------
    readonly property color accent:        "#E3AE5A"
    readonly property color accentBright:  "#F7D79B"
    readonly property color accentDeep:    "#9C6B21"
    readonly property color accentInk:     "#161005"

    readonly property color incoming:      "#7FB2E5"
    readonly property color incomingDeep:  "#3C6E9E"
    readonly property color outgoing:      "#E3AE5A"
    readonly property color outgoingDeep:  "#9C6B21"

    readonly property color success:       "#4CD07D"
    readonly property color successDeep:   "#1E7B47"
    readonly property color warning:       "#E8B04B"
    readonly property color warningDeep:   "#8A5C16"
    readonly property color danger:        "#E0574F"
    readonly property color dangerDeep:    "#8E2F2A"

    // ------------------------------------------------------------------
    // Текст
    // ------------------------------------------------------------------
    readonly property color textPrimary:   "#F4EFE6"
    readonly property color textSecondary: "#BEB4A6"
    readonly property color textMuted:     "#8B8175"
    readonly property color textOnAccent:  "#161005"

    // ------------------------------------------------------------------
    // Типографика
    // ------------------------------------------------------------------
    readonly property string fontFamily: "Segoe UI Variable Display"
    readonly property string fontFamilyText: "Segoe UI Variable Text"
    readonly property string fontFamilyMono: "Cascadia Mono"
    // «Вывеска» приложения — засечный шрифт, как на референсе
    readonly property string fontFamilyBrand: "Georgia"

    readonly property int fontDisplay: 34
    readonly property int fontTitle:   24
    readonly property int fontH1:      19
    readonly property int fontH2:      16
    readonly property int fontBody:    14
    readonly property int fontSmall:   12
    readonly property int fontTiny:    11

    readonly property int weightRegular:  400
    readonly property int weightMedium:   500
    readonly property int weightSemiBold: 600
    readonly property int weightBold:     700

    readonly property int fontDisplayPx: fontDisplay * 1.34
    readonly property int fontTitlePx:   fontTitle * 1.34
    readonly property int fontH1Px:      fontH1 * 1.34
    readonly property int fontH2Px:      fontH2 * 1.34
    readonly property int fontBodyPx:    fontBody * 1.34
    readonly property int fontSmallPx:   fontSmall * 1.34
    readonly property int fontTinyPx:    fontTiny * 1.34

    // ------------------------------------------------------------------
    // Отступы
    // ------------------------------------------------------------------
    readonly property int spaceXXS: 4
    readonly property int spaceXS:  8
    readonly property int spaceSM:  12
    readonly property int spaceMD:  16
    readonly property int spaceLG:  24
    readonly property int spaceXL:  32
    readonly property int spaceXXL: 48

    // ------------------------------------------------------------------
    // Радиусы
    // ------------------------------------------------------------------
    readonly property int radiusWindow: 20
    readonly property int radiusCard:   16
    readonly property int radiusInner:  12
    readonly property int radiusControl: 10
    readonly property int radiusPill:   999

    // ------------------------------------------------------------------
    // Движение
    // ------------------------------------------------------------------
    readonly property int motionFast:   110
    readonly property int motionBase:   180
    readonly property int motionSlow:   280
    readonly property int motionReveal: 420

    readonly property int eOutCubic:  Easing.OutCubic
    readonly property int eInOutCubic: Easing.InOutCubic
    readonly property int eOutBack:  Easing.OutBack

    // ------------------------------------------------------------------
    // Готовые градиенты
    // ------------------------------------------------------------------
    readonly property var gradAccent: Gradient {
        GradientStop { position: 0.0; color: theme.accentBright }
        GradientStop { position: 1.0; color: theme.accentDeep }
    }

    readonly property var gradIncoming: Gradient {
        GradientStop { position: 0.0; color: theme.incoming }
        GradientStop { position: 1.0; color: theme.incomingDeep }
    }

    readonly property var gradSuccess: Gradient {
        GradientStop { position: 0.0; color: theme.success }
        GradientStop { position: 1.0; color: theme.successDeep }
    }

    readonly property var gradDanger: Gradient {
        GradientStop { position: 0.0; color: theme.danger }
        GradientStop { position: 1.0; color: theme.dangerDeep }
    }

    readonly property var gradAppBg: Gradient {
        GradientStop { position: 0.0; color: theme.bgGlow }
        GradientStop { position: 0.55; color: theme.bg }
        GradientStop { position: 1.0; color: "#080A0E" }
    }

    // активный пункт навигации: тёплое золотое свечение слева
    readonly property var gradNavActive: Gradient {
        GradientStop { position: 0.0; color: "#3A2A12" }
        GradientStop { position: 1.0; color: "#1D1710" }
    }

    // карточка: чуть светлее сверху, как в референсе
    readonly property var gradCard: Gradient {
        GradientStop { position: 0.0; color: "#1A202B" }
        GradientStop { position: 1.0; color: "#12161E" }
    }
}
