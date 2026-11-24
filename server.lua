-- Серверная часть звуковой панели Auraloom.
--
-- Как работает: игрок нажимает клавишу -> клиент просит сервер -> сервер играет
-- фразу ВСЕМ участникам. Обычная речь при этом не трогается вообще:
-- ничего не подмешивается в микрофон, виртуальный кабель не нужен.
--
-- Защита от спама: кулдаун на игрока, лимит фраз в минуту и белый список
-- допустимых звуков (файлы из sounds/).

local COOLDOWN_MS = 1200       -- минимальный интервал между фразами
local MAX_PER_MINUTE = 25      -- лимит фраз в минуту с одного игрока

local lastUsed = {}
local rateLimit = {}

--- Есть ли такой звук в ресурсе (белый список).
local function soundAllowed(id)
    local want = ('sounds/mx_%02d.ogg'):format(id)
    for _, value in pairs(GetResourceMetadata(GetCurrentResourceName(), 'files') or {}) do
        if value == want then
            return true
        end
    end
    return false
end

--- Проверки анти-спама. Возвращает true, если можно играть.
local function allow(source)
    local now = GetGameTimer()

    local last = lastUsed[source] or 0
    if now - last < COOLDOWN_MS then
        return false
    end
    lastUsed[source] = now

    local bucket = math.floor(now / 60000)
    local counter = rateLimit[source]
    if not counter or counter.bucket ~= bucket then
        counter = { bucket = bucket, count = 0 }
        rateLimit[source] = counter
    end
    counter.count = counter.count + 1
    if counter.count > MAX_PER_MINUTE then
        return false
    end
    return true
end

--- Сыграть фразу всем.
local function playForAll(id)
    TriggerClientEvent('sb:play', -1, id)
end

-- Клиент просит фразу: sb:requestSound <id>
RegisterNetEvent('sb:requestSound', function(id)
    local source = source
    id = tonumber(id)
    if not id then return end
    if not allow(source) then return end
    if not soundAllowed(id) then return end
    playForAll(id)
end)

-- Прямая команда с серверной консоли: sb <id>
RegisterCommand('sb', function(source, args)
    if source == 0 then
        local id = tonumber(args[1])
        if id and soundAllowed(id) then
            playForAll(id)
        end
    end
end, false)

-- Уборка при выходе игрока
AddEventHandler('playerDropped', function()
    local src = source
    lastUsed[src] = nil
    rateLimit[src] = nil
end)
