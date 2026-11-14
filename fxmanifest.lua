-- Звуковая панель RedZ (RedM / FiveM).
-- Клиентский ресурс: озвучка по горячим клавишам, воспроизведение через NUI.
--
-- Установка (если есть права на сервере):
--   1) скопировать папку redz_mx_soundboard в resources/ сервера
--   2) в server.cfg добавить:  ensure redz_mx_soundboard
--
-- Установка локально (без прав на сервер):
--   1) папку ресурса положить в
--      %LOCALAPPDATA%\RedM\RedM.app\data\cache\  (или FiveM\FiveM.app\data\cache\)
--   2) в консоли клиента выполнить:  ensure redz_mx_soundboard

fx_version 'cerulean'
games { 'rdr3', 'gta5' }

name 'redz-mx-soundboard'
description 'Mexican accent soundboard for RedZ RolePlay (no family insults, per rule 3.2)'
author 'RedZ player'
version '1.0.0'

ui_page 'html/index.html'

client_scripts {
    'client.lua',
    'keybinds.lua',
}

-- Серверная часть: по запросу клиента играет фразу всем игрокам.
-- Если ресурс запущен только локально, переключи в config.lua
-- Config.ServerBroadcast = false.
server_script 'server.lua'
shared_script 'config.lua'

-- NUI-страница и звуки (OGG Vorbis — формат, который принимают FiveM/RedM-ресурсы)
files {
    'html/index.html',

    'sounds/mx_01.ogg',
    'sounds/mx_02.ogg',
    'sounds/mx_03.ogg',
    'sounds/mx_04.ogg',
    'sounds/mx_05.ogg',
    'sounds/mx_06.ogg',
    'sounds/mx_07.ogg',
    'sounds/mx_08.ogg',
    'sounds/mx_09.ogg',
    'sounds/mx_10.ogg',
    'sounds/mx_11.ogg',
    'sounds/mx_12.ogg',
    'sounds/mx_13.ogg',
    'sounds/mx_14.ogg',
    'sounds/mx_15.ogg',
    'sounds/mx_16.ogg',
    'sounds/mx_17.ogg',
    'sounds/mx_18.ogg',
    'sounds/mx_19.ogg',
    'sounds/mx_20.ogg',
    'sounds/mx_21.ogg',
    'sounds/mx_22.ogg',
    'sounds/mx_23.ogg',
    'sounds/mx_24.ogg',
    'sounds/mx_25.ogg',
    'sounds/mx_26.ogg',
    'sounds/mx_27.ogg',
    'sounds/mx_28.ogg',
    'sounds/mx_29.ogg',
    'sounds/mx_30.ogg',
    'sounds/mx_31.ogg',
    'sounds/mx_33.ogg',
    'sounds/mx_32.ogg',
}
