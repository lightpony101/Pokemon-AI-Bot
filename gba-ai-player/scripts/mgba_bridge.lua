-- mGBA Lua Bridge Script
-- Runs inside mGBA and communicates with the Python AI client over TCP.
--
-- Usage: mgba-qt game.gba --lua scripts/mgba_bridge.lua
--
-- Protocol: newline-delimited JSON over TCP (Lua is server, Python connects).
-- Lua sends state every N frames; Lua receives action commands.
--
-- This script includes a minimal JSON serializer so no external library is needed.

local json = {}

-- Minimal JSON encoder
function json.encode(obj)
    if obj == nil then return "null" end
    local t = type(obj)
    if t == "boolean" then
        return obj and "true" or "false"
    elseif t == "number" then
        if obj ~= obj then return "null" end
        return tostring(obj)
    elseif t == "string" then
        return '"' .. string.gsub(obj, '["\\]', function(c) return '\\' .. c end) .. '"'
    elseif t == "table" then
        -- Check if array-like
        local max_index = 0
        local is_array = true
        for k, _ in pairs(obj) do
            if type(k) ~= "number" or k < 1 or math.floor(k) ~= k then
                is_array = false
                break
            end
            if k > max_index then max_index = k end
        end
        if is_array and max_index > 0 then
            local parts = {}
            for i = 1, max_index do
                table.insert(parts, json.encode(obj[i]))
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(obj) do
                if type(k) == "string" then
                    table.insert(parts, json.encode(k) .. ":" .. json.encode(v))
                end
            end
            table.sort(parts)
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

-- Minimal JSON decoder (only handles flat-ish objects for commands)
function json.decode(str)
    local idx = 1
    local len = #str

    local skip_ws
    skip_ws = function()
        while idx <= len and string.find(" \t\n\r", string.sub(str, idx, idx), 1, true) do
            idx = idx + 1
        end
    end

    local parse_value
    parse_value = function()
        skip_ws()
        if idx > len then error("unexpected end of input") end
        local ch = string.sub(str, idx, idx)
        if ch == '"' then
            idx = idx + 1
            local s = {}
            while idx <= len do
                local c = string.sub(str, idx, idx)
                if c == '\\' then
                    idx = idx + 1
                    if idx > len then break end
                    local esc = string.sub(str, idx, idx)
                    if esc == 'n' then table.insert(s, '\n')
                    elseif esc == 't' then table.insert(s, '\t')
                    elseif esc == 'r' then table.insert(s, '\r')
                    elseif esc == '"' then table.insert(s, '"')
                    elseif esc == '\\' then table.insert(s, '\\')
                    else table.insert(s, esc) end
                    idx = idx + 1
                elseif c == '"' then
                    idx = idx + 1
                    break
                else
                    table.insert(s, c)
                    idx = idx + 1
                end
            end
            return table.concat(s)
        elseif ch == '[' then
            idx = idx + 1
            local arr = {}
            skip_ws()
            while idx <= len and string.sub(str, idx, idx) ~= ']' do
                local val = parse_value()
                table.insert(arr, val)
                skip_ws()
                if idx <= len and string.sub(str, idx, idx) == ',' then
                    idx = idx + 1
                end
            end
            if idx <= len and string.sub(str, idx, idx) == ']' then idx = idx + 1 end
            return arr
        elseif ch == '{' then
            idx = idx + 1
            local obj = {}
            skip_ws()
            while idx <= len and string.sub(str, idx, idx) ~= '}' do
                skip_ws()
                local key = parse_value()
                skip_ws()
                if idx <= len and string.sub(str, idx, idx) == ':' then idx = idx + 1 end
                local val = parse_value()
                obj[key] = val
                skip_ws()
                if idx <= len and string.sub(str, idx, idx) == ',' then
                    idx = idx + 1
                end
            end
            if idx <= len and string.sub(str, idx, idx) == '}' then idx = idx + 1 end
            return obj
        elseif ch == 't' and string.sub(str, idx, idx + 3) == "true" then
            idx = idx + 4
            return true
        elseif ch == 'f' and string.sub(str, idx, idx + 4) == "false" then
            idx = idx + 5
            return false
        elseif ch == 'n' and string.sub(str, idx, idx + 3) == "null" then
            idx = idx + 4
            return nil
        else
            -- number
            local start = idx
            if ch == '-' then idx = idx + 1 end
            while idx <= len and string.find("0123456789", string.sub(str, idx, idx), 1, true) do
                idx = idx + 1
            end
            if idx <= len and string.sub(str, idx, idx) == '.' then
                idx = idx + 1
                while idx <= len and string.find("0123456789", string.sub(str, idx, idx), 1, true) do
                    idx = idx + 1
                end
            end
            return tonumber(string.sub(str, start, idx - 1))
        end
    end

    local result = parse_value()
    skip_ws()
    return result
end

-- ===== Configuration =====
local HOST = "127.0.0.1"
local PORT = 9999
local STATE_INTERVAL = 2 -- frames between state broadcasts
local READ_TIMEOUT = 0.01 -- non-blocking with short timeout

local server = nil
local client = nil
local frame_counter = 0
local last_state_sent = 0

-- Memory addresses (FireRed/Emerald defaults; override with env vars)
local ADDR = {
    player_x     = tonumber(os.getenv("GBA_ADDR_PLAYER_X", "0x02024A6C")),
    player_y     = tonumber(os.getenv("GBA_ADDR_PLAYER_Y", "0x02024A70")),
    current_map  = tonumber(os.getenv("GBA_ADDR_MAP", "0x020244AC")),
    battle_state = tonumber(os.getenv("GBA_ADDR_BATTLE", "0x02000022")),
    menu_state   = tonumber(os.getenv("GBA_ADDR_MENU", "0x0200002B")),
    money        = tonumber(os.getenv("GBA_ADDR_MONEY", "0x0200002E")),
    party_count  = tonumber(os.getenv("GBA_ADDR_PARTY_COUNT", "0x020240C8")),
    party_hp     = tonumber(os.getenv("GBA_ADDR_PARTY_HP", "0x020240CC")),
    facing       = tonumber(os.getenv("GBA_ADDR_FACING", "0x02024A74")),
    warp_flag    = tonumber(os.getenv("GBA_ADDR_WARP", "0x02000024")),
}

local FACING_MAP = {[0] = "down", [1] = "up", [2] = "left", [3] = "right"}
local BATTLE_MAP = {[0] = "none", [1] = "active", [2] = "transition"}
local MENU_MAP = {[0] = "overworld", [1] = "menu", [2] = "bag", [3] = "pokemon", [4] = "save", [5] = "option", [6] = "battle_menu"}

function init()
    server = assert(socket.bind(HOST, PORT))
    server:settimeout(0)
    server:setoption("reuseaddr", true)
    emu.message(string.format("GBA AI Bridge: %s:%d", HOST, PORT))
    print(string.format("[GBA Bridge] Listening on %s:%d", HOST, PORT))
end

function read_u8(addr)
    return memory.readbyte(addr)
end

function read_u16(addr)
    return memory.readword(addr)
end

function read_u32(addr)
    return memory.readlong(addr)
end

function read_state()
    local state = {
        frame = emu.framecount(),
        map = read_u32(ADDR.current_map),
        x = read_u32(ADDR.player_x),
        y = read_u32(ADDR.player_y),
        battle = read_u8(ADDR.battle_state),
        menu = read_u8(ADDR.menu_state),
        money = read_u32(ADDR.money),
        party_count = read_u8(ADDR.party_count),
        facing = read_u8(ADDR.facing),
        warp = read_u8(ADDR.warp_flag),
    }

    state.party_hp = {}
    local count = state.party_count
    if count > 6 then count = 6 end
    for i = 0, count - 1 do
        local hp_addr = ADDR.party_hp + (i * 8)
        local ok, cur, max = pcall(function()
            return read_u16(hp_addr), read_u16(hp_addr + 2)
        end)
        if ok then
            state.party_hp[i + 1] = {current = cur, max = max}
        end
    end

    return state
end

function apply_buttons(button_str)
    if not button_str or button_str == "" then return end
    local parts = {}
    for part in string.gmatch(button_str, "[^,]+") do
        table.insert(parts, string.upper(string.match(part, "^%s*(.-)%s*$")))
    end
    for _, btn in ipairs(parts) do
        joypad.set(btn, true)
    end
    emu.frameadvance()
    for _, btn in ipairs(parts) do
        joypad.set(btn, false)
    end
end

function handle_command(line)
    local ok, cmd = pcall(function() return json.decode(line) end)
    if not ok or type(cmd) ~= "table" then
        emu.message("Bad JSON from client")
        return
    end

    if cmd.type == "action" and cmd.buttons then
        apply_buttons(cmd.buttons)
    end
end

function on_frame()
    frame_counter = frame_counter + 1

    -- Accept new connections
    local new_client, err = server:accept()
    if new_client then
        if client then
            client:close()
        end
        client = new_client
        client:settimeout(READ_TIMEOUT)
        emu.message("Python client connected")
    end

    -- Read commands from client (non-blocking)
    if client then
        local line, err = client:receive()
        if line == nil and err == "timeout" then
            -- normal, no data available
        elseif line == nil then
            client:close()
            client = nil
        else
            handle_command(line)
        end
    end

    -- Broadcast state periodically
    if (frame_counter - last_state_sent) >= STATE_INTERVAL then
        last_state_sent = frame_counter
        local state = read_state()
        local ok, encoded = pcall(function() return json.encode(state) end)
        if ok and client then
            local ok2, err2 = pcall(function()
                client:send(encoded .. "\n")
            end)
            if not ok2 then
                client = nil
            end
        end
    end
end

function cleanup()
    if client then
        client:close()
        client = nil
    end
    if server then
        server:close()
        server = nil
    end
    print("[GBA Bridge] Shutdown complete")
end

event.onframe(on_frame)
event.onexit(cleanup)
init()
emu.message("GBA AI Bridge initialized")
