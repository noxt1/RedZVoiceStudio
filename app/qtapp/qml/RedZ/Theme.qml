pragma Singleton

import QtQuick

/// Дизайн-система Auraloom — неоновая тема по новым референсам.
///
/// Глубокий сине-фиолетовый фон, стеклянные поверхности, фирменный
/// градиент «фиолетовый → циан». Один источник правды для цвета,
/// типографики, отступов и таймингов: страницы не задают цвета сами.
QtObject {
    id: theme

    // ------------------------------------------------------------------
    // Поверхности
    // ------------------------------------------------------------------
    readonly property color bg:            "#050819"
    readonly property color bgGlow:        "#0B1030"
    readonly property color sidebar:       "#070B22"
    readonly property color surface0:      "#0B0F2A"
    readonly property color surface1:      "#111739"
    readonly property color surface2:      "#161D48"
    readonly property color surface3:      "#1D2557"
    readonly property color surfaceHover:  "#242D66"
    readonly property color surfaceActive: "#2C3675"

    // ------------------------------------------------------------------
    // Границы
    // ------------------------------------------------------------------
    readonly property color border:        "#252C55"
    readonly property color borderStrong:  "#333C6E"
    readonly property color borderFocus:   "#8B5CF6"

    // ------------------------------------------------------------------
    // Фирменная палитра: неон «фиолетовый → циан»
    // ------------------------------------------------------------------
    readonly property color accent:        "#8B5CF6"
    readonly property color accentBright:  "#B79CFF"
    readonly property color accentDeep:    "#4C1D95"
    readonly property color accentInk:     "#0B0620"
    readonly property color accentCyan:    "#22D3EE"
    readonly property color accentBlue:    "#3B82F6"

    // плитки-иконки на карточках (вместо тёплого золота)
    readonly property color accentTile:    "#171A44"

    readonly property color incoming:      "#38BDF8"
    readonly property color incomingDeep:  "#1D4ED8"
    readonly property color outgoing:      "#8B5CF6"
    readonly property color outgoingDeep:  "#4C1D95"

    readonly property color success:       "#34D399"
    readonly property color successDeep:   "#0F766E"
    readonly property color warning:       "#FBBF24"
    readonly property color warningDeep:   "#92400E"
    readonly property color danger:        "#F87171"
    readonly property color dangerDeep:    "#7F1D1D"

    readonly property color successTile:   "#0E2A2E"
    readonly property color dangerTile:    "#2A1428"

    // ------------------------------------------------------------------
    // Текст
    // ------------------------------------------------------------------
    readonly property color textPrimary:   "#F2F5FF"
    readonly property color textSecondary: "#AEB6DE"
    readonly property color textMuted:     "#7C86B4"
    readonly property color textOnAccent:  "#06091C"

    // ------------------------------------------------------------------
    // Типографика
    // ------------------------------------------------------------------
    readonly property string fontFamily: "Segoe UI Variable Display"
    readonly property string fontFamilyText: "Segoe UI Variable Text"
    readonly property string fontFamilyMono: "Cascadia Mono"
    // «Вывеска» приложения — геометрический гротеск, как на референсах
    readonly property string fontFamilyBrand: "Segoe UI Variable Display"

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
    // основной акцент: фиолетовый -> циан (кнопки, логотип, полосы)
    readonly property var gradAccent: Gradient {
        GradientStop { position: 0.0; color: "#7C4DFF" }
        GradientStop { position: 0.55; color: theme.accentBlue }
        GradientStop { position: 1.0; color: theme.accentCyan }
    }

    // логотип: чуть теплее слева
    readonly property var gradBrand: Gradient {
        GradientStop { position: 0.0; color: "#C084FC" }
        GradientStop { position: 0.5; color: "#7C4DFF" }
        GradientStop { position: 1.0; color: theme.accentCyan }
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
        GradientStop { position: 0.5; color: "#070B24" }
        GradientStop { position: 1.0; color: "#03050F" }
    }

    // активный пункт навигации: неоновая пилюля
    readonly property var gradNavActive: Gradient {
        GradientStop { position: 0.0; color: "#5B2BE0" }
        GradientStop { position: 1.0; color: "#2A1D6E" }
    }

    // карточка: стекло — светлее сверху
    readonly property var gradCard: Gradient {
        GradientStop { position: 0.0; color: "#111739" }
        GradientStop { position: 1.0; color: "#0C1130" }
    }

    readonly property color cardTop:    "#111739"
    readonly property color cardBottom: "#0C1130"
}
