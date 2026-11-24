-- Клиентская часть звуковой панели Auraloom.
--
-- Два режима (config.lua -> Config.ServerBroadcast):
--   true  -> нажатие клавиши уходит на сервер, сервер играет фразу ВСЕМ.
--           Твоя речь идёт через микрофон как обычно, ничего не смешивается.
--   false -> фраза играет локально, только у тебя.
--
-- Воспроизведение через NUI: ресурс отдаёт .ogg в страницу, страница играет
-- файл через HTML5 <audio>. Работает и в RedM (rdr3), и в GTA V (gta5).

local soundList = {
    [1]  = 'mx_01', [2]  = 'mx_02', [3]  = 'mx_03', [4]  = 'mx_04', [5]  = 'mx_05',
    [6]  = 'mx_06', [7]  = 'mx_07', [8]  = 'mx_08', [9]  = 'mx_09', [10] = 'mx_10',
    [11] = 'mx_11', [12] = 'mx_12', [13] = 'mx_13', [14] = 'mx_14', [15] = 'mx_15',
    [16] = 'mx_16', [17] = 'mx_17', [18] = 'mx_18', [19] = 'mx_19', [20] = 'mx_20',
    [21] = 'mx_21', [22] = 'mx_22', [23] = 'mx_23', [24] = 'mx_24', [25] = 'mx_25',
    [26] = 'mx_26', [27] = 'mx_27', [28] = 'mx_28', [29] = 'mx_29', [30] = 'mx_30',
    [31] = 'mx_31',
}

local sbEnabled = true
local sbVolume = Config and Config.Volume or 0.9
local lastPlayed = nil
local lastAt = 0

--- Проиграть клип по номеру (1..31).
---@param idx number
local function playSound(idx)
    if not sbEnabled then return end
    local name = soundList[idx]
    if not name then return end

    -- анти-спам: не даём одной и той же реплике сыпаться чаще 120 мс
    local now = GetGameTimer()
    if name == lastPlayed and (now - lastAt) < 120 then return end
    lastPlayed, lastAt = name, now

    SendNUIMessage({
        action      = 'play',
        sound       = name,
        volume      = sbVolume,
        resourceName = GetCurrentResourceName(),
    })
end

--- Нажата клавиша реплики: уходит на сервер либо играет локально.
---@param idx number
local function trigger(idx)
    if not sbEnabled then return end
    if Config and Config.ServerBroadcast then
        -- сервер раздаст фразу всем (в т.ч. тебе)
        TriggerServerEvent('sb:requestSound', idx)
    else
        playSound(idx)
    end
end

--- Фраза пришла от сервера (для всех).
RegisterNetEvent('sb:play', function(id)
    playSound(tonumber(id) or 0)
end)

--- Остановить всё.
local function stopAll()
    SendNUIMessage({ action = 'stop' })
end

--- Включить/выключить панель.
local function toggleEnabled()
    sbEnabled = not sbEnabled
    if not sbEnabled then stopAll() end
    TriggerEvent('chat:addMessage', {
        args = { '[Звуковая панель] ' .. (sbEnabled and 'включена' or 'выключена') },
    })
end

-- Команды: /sb <n>, /sb off, /sb on, /sb stop, /sb vol 0.5
RegisterCommand('sb', function(source, args)
    if args[1] == nil then
        TriggerEvent('chat:addMessage', { args = { '[SB] /sb <1-31> | /sb on | /sb off | /sb stop | /sb vol 0.5' } })
        return
    end
    local a = tostring(args[1]):lower()

    if a == 'on' then
        sbEnabled = true
        TriggerEvent('chat:addMessage', { args = { '[SB] панель включена' } })
    elseif a == 'off' then
        sbEnabled = false
        stopAll()
        TriggerEvent('chat:addMessage', { args = { '[SB] панель выключена' } })
    elseif a == 'stop' then
        stopAll()
    elseif a == 'vol' then
        local v = tonumber(args[2])
        if v then
            sbVolume = math.min(1.0, math.max(0.0, v))
            TriggerEvent('chat:addMessage', { args = { '[SB] громкость: ' .. tostring(sbVolume) } })
        end
    else
        local n = tonumber(args[1])
        if n and n >= 1 and n <= 31 then
            trigger(math.floor(n))
        else
            TriggerEvent('chat:addMessage', { args = { '[SB] нет такой реплики: ' .. tostring(args[1]) } })
        end
    end
end, false)

-- Команда на каждую реплику — чтобы работали бинды и переназначение клавиш.
for idx = 1, 31 do
    RegisterCommand('sbplay' .. idx, function()
        trigger(idx)
    end, false)
end

-- Экспорт для внешних скриптов/UI.
exports('playSound', function(idx) playSound(idx) end)
exports('stopAll', stopAll)
exports('isEnabled', function() return sbEnabled end)

-- Сообщаем странице, что ресурс готов (иначе NUI может не получить первое сообщение).
CreateThread(function()
    while not HasDoneProfiling() do Wait(0) end
    SendNUIMessage({ action = 'init' })
end)
