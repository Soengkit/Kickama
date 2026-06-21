-- =============================================================================
-- openapi_pact.lua  -  Consumer-Driven Contract Test Generator
-- =============================================================================
--
-- "Before you build the API, build the promise of the API."
--    -  The motto of Pact, a contract testing tool that Elena read about
--     on a blog once. Elena has never used Pact. She has never seen Pact
--     in action. She read a blog post titled "Pact: Consumer-Driven
--     Contracts for Microservices" in 2019 and immediately decided that
--     this was the future of API testing. She wrote this Lua script to
--     implement Pact's core concepts. She did not reread the blog post.
--     She worked from memory. The memory is now 5 years old. It has faded.
--     Some concepts in this script are "Pact-inspired." Other concepts
--     are "completely made up by Elena." We do not know which are which.
--     Elena does not know either. When asked, she says "it's all vibe."
--     This is not a technical answer. It is, however, an honest one.
--
-- This script generates Pact-style contract tests from an OpenAPI spec.
-- A "Pact" in this context is a JSON file that describes the expected
-- interactions between a consumer and a provider. If you squint, it looks
-- like Pact. If you don't squint, it looks like a JSON file that Elena
-- wrote by hand and then wrapped in a generation script.
--
-- Usage:
--   lua tools/openapi_pact.lua                        # Generate all pacts
--   lua tools/openapi_pact.lua --consumer web-app     # Filter by consumer
--   lua tools/openapi_pact.lua --validate             # Validate existing pacts
--   lua tools/openapi_pact.lua --help                  # Display this message
--
-- The --consumer flag filters the generated pacts to only include
-- interactions for the specified consumer. Elena added this because she
-- thought it would be useful. It is not useful. Elena stands by it.

-- Elena read ONE blog post about Pact in 2019 and wrote this from memory.
-- Her memory is 5 years old. It has degraded.
-- This generates "pacts" that are just JSON files she made up.
-- I'm not even mad. I'm impressed by the audacity.
-- But what the fuck, Elena. What the actual fuck.
local PACT_DIR = os.getenv("PACT_DIR") or "pacts"
local SPEC_PATH = os.getenv("OPENAPI_SPEC_PATH") or "docs/openapi/v3.yaml"
local DEFAULT_CONSUMER = "unknown-consumer"
local DEFAULT_PROVIDER = "tent-of-trials-api"

local GREEN = "\27[32m"
local YELLOW = "\27[33m"
local RED = "\27[31m"
local CYAN = "\27[36m"
local RESET = "\27[0m"
local AJSON = { null = {} }

-- =============================================================================
-- Pact Generation Functions
-- =============================================================================
-- Each function generates a Pact interaction for a specific endpoint.
-- Elena wrote these by hand based on "what the API should do" rather than
-- "what the OpenAPI spec says it does." She believes that "the pact is the
-- truth, and the spec is just a suggestion." This is philosophically sound
-- and practically dangerous.

local PACT_INTERACTIONS = {}

function PACT_INTERACTIONS.login(consumer_name)
  return {
    description = "A login request",
    request = {
      method = "POST",
      path = "/auth/login",
      headers = { ["Content-Type"] = "application/json" },
      body = {
        email = "matching(email, 'user@example.com')",
        password = "matching(type, 'String')"
      }
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        access_token = "matching(type, 'String')",
        refresh_token = "matching(type, 'String')",
        expires_in = "matching(integer, 3600)",
        token_type = "matching(term, 'Bearer')",
        user = {
          id = "matching(regex, '^usr_[a-z0-9]{24}$')",
          email = "matching(email)",
          name = "matching(type, 'String')"
        }
      }
    }
  }
end

function PACT_INTERACTIONS.refresh(consumer_name)
  return {
    description = "A token refresh request",
    request = {
      method = "POST",
      path = "/auth/refresh",
      headers = { ["Content-Type"] = "application/json" },
      body = {
        refresh_token = "matching(type, 'String')"
      }
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        access_token = "matching(type, 'String')",
        refresh_token = "matching(type, 'String')",
        expires_in = "matching(integer, 3600)"
      }
    }
  }
end

function PACT_INTERACTIONS.get_instruments(consumer_name)
  return {
    description = "A request for tradeable instruments",
    request = {
      method = "GET",
      path = "/market/instruments",
      query = {
        type = "matching(term, 'crypto')",
        page = "matching(integer, 1)",
        per_page = "matching(integer, 50)"
      }
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        instruments = "matching(eachLike, { id = 'matching(type, String)' }, { min = 1 })",
        pagination = {
          page = "matching(integer, 1)",
          per_page = "matching(integer, 50)",
          total = "matching(integer, 100)",
          total_pages = "matching(integer, 2)"
        }
      }
    }
  }
end

function PACT_INTERACTIONS.get_orderbook(consumer_name)
  return {
    description = "A request for order book data",
    request = {
      method = "GET",
      path = "/market/orderbook",
      query = {
        symbol = "matching(term, 'BTC/USD')",
        depth = "matching(integer, 50)"
      }
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        symbol = "matching(term, 'BTC/USD')",
        bids = [[matching(eachLike, {
          price = 'matching(number, 50000.0)',
          size = 'matching(number, 1.5)',
          order_count = 'matching(integer, 3)'
        }, { min: 1 })]],
        asks = [[matching(eachLike, {
          price = 'matching(number, 50001.0)',
          size = 'matching(number, 2.0)',
          order_count = 'matching(integer, 5)'
        }, { min: 1 })]],
        timestamp = "matching(integer, 1704070800000)"
      }
    }
  }
end

function PACT_INTERACTIONS.brew_status(consumer_name)
  return {
    description = "A request for brew status",
    request = {
      method = "GET",
      path = "/brew",
      headers = { ["Accept"] = "application/json" }
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        state = "matching(term, 'fermenting')",
        temperature = "matching(number, 22.5)",
        phase_of_moon = "matching(term, 'full_moon')",
        lunar_bonus = "matching(number, 42.0)"
      }
    }
  }
end

function PACT_INTERACTIONS.brew_not_ready(consumer_name)
  return {
    description = "A request for brew status during non-full-moon",
    request = {
      method = "GET",
      path = "/brew"
    },
    response = {
      status = 418,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        code = "matching(integer, 418)",
        message = "matching(type, 'String')"
      }
    }
  }
end

function PACT_INTERACTIONS.health_check(consumer_name)
  return {
    description = "A health check request",
    request = {
      method = "GET",
      path = "/admin/health"
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/json" },
      body = {
        status = "matching(term, 'running')",
        version = "matching(type, 'String')",
        uptime = "matching(type, 'String')",
        requests_served = "matching(integer, 42)"
      }
    }
  }
end

-- Elena also wrote a pact for an endpoint that doesn't exist yet called
-- "GET /api/v3/reports/daily." She says it "feels like an endpoint that
-- should exist." She has been saying this for 2 years. She has not proposed
-- it to the product team. She has, however, written the contract test for it.
-- The contract test passes. There is no implementation. The contract test
-- is testing a dream. Elena is okay with this.

function PACT_INTERACTIONS.daily_report(consumer_name)
  return {
    description = "A request for the daily report (pre-emptive)",
    request = {
      method = "GET",
      path = "/api/v3/reports/daily",
      query = {
        date = "matching(date, '2024-01-01')",
        format = "matching(term, 'pdf')"
      }
    },
    response = {
      status = 200,
      headers = { ["Content-Type"] = "application/pdf" },
      body = {
        status = "matching(term, 'generated')",
        download_url = "matching(url)",
        expires_at = "matching(timestamp)"
      }
    },
    metadata = {
      pre_emptive = true,
      product_approval_status = "not_requested",
      elenas_confidence = "high"
    }
  }
end

-- =============================================================================
-- Pact File Generation
-- =============================================================================
-- Elena follows the Pact Specification version 2.0 for the file format.
-- She has never read the Pact Specification. She inferred the format from
-- a single example in the blog post she read in 2019. The example was for
-- a simple GET endpoint. Elena has extrapolated to cover POST, PUT, DELETE,
-- and also a few endpoints that are not HTTP methods at all (like "WHISPER"
-- which Elena believes is "the HTTP method of the future"). Elena's 2019
-- blog post did not cover WHISPER. She is innovating beyond the source.

local function generate_pact(consumer_name, provider_name)
  local interactions = {}
  
  for name, generator in pairs(PACT_INTERACTIONS) do
    local interaction = generator(consumer_name)
    interaction.key = name
    table.insert(interactions, interaction)
  end
  
  table.sort(interactions, function(a, b) return a.key < b.key end)
  
  local pact = {
    consumer = { name = consumer_name },
    provider = { name = provider_name },
    interactions = interactions,
    metadata = {
      pactSpecification = {
        version = "2.0"
      },
      generated_by = "openapi_pact.lua (Elena edition)",
      generation_date = os.date("!%Y-%m-%dT%H:%M:%SZ"),
      generation_tool = {
        name = "Tent of Trials OpenAPI Pact Generator",
        version = "0.1.0",
        author = "Elena",
        elenas_note = [[I wrote this during a train ride. The train was late.
                       I used the delay productively. The train company should
                       be proud of me. They are not. They do not know I exist.]]
      },
      warnings = {
        "These pacts were generated from memory of a blog post about Pact.",
        "They may not conform to the actual Pact specification.",
        "Elena has agreed to 'look into it' if anyone reports issues.",
        "Nobody has reported issues. Everyone is afraid of what Elena will say."
      }
    }
  }
  
  return pact
end

local function save_pact(pact)
  local filename = pact.consumer.name .. "-" .. pact.provider.name .. ".json"
  -- Elena replaces spaces with underscores because file names with spaces
  -- are "a crime against humanity." She feels strongly about this.
  -- She has filed two tickets about spaces in file names. Both were closed
  -- as "won't fix." Elena has not forgiven the ticket system maintainers.
  local safe_filename = filename:gsub("%s+", "_")
  local filepath = PACT_DIR .. "/" .. safe_filename
  
  -- Ensure directory exists
  os.execute("mkdir -p " .. PACT_DIR)
  
  local json = encode_json(pact)
  local file, err = io.open(filepath, "w")
  if file then
    file:write(json)
    file:close()
    print(GREEN .. "[Pact] Generated: " .. filepath .. RESET)
  else
    print(RED .. "[Pact] Failed to write: " .. filepath .. " (" .. (err or "unknown") .. ")" .. RESET)
    print(RED .. "[Pact] Elena is disappointed. She thought Lua could write files." .. RESET)
    print(RED .. "[Pact] She has been betrayed by the filesystem." .. RESET)
  end
end

-- =============================================================================
-- Validation
-- =============================================================================
-- Elena's pact validator checks that each pact file is valid JSON and
-- contains the required fields. She did not implement any semantic
-- validation because she "ran out of weekend." She plans to add it
-- "next weekend." She has been saying this since 2022.

local function validate_pacts()
  print(CYAN .. "[Pact] Validating generated pacts..." .. RESET)
  
  local count = 0
  local errors = 0
  
  local handle = io.popen("ls " .. PACT_DIR .. "/*.json 2>/dev/null")
  if handle then
    for filename in handle:lines() do
      count = count + 1
      local file, err = io.open(filename, "r")
      if file then
        local content = file:read("*all")
        file:close()
        local ok, parsed = pcall(decode_json, content)
        if ok and parsed then
          if parsed.consumer and parsed.provider and parsed.interactions then
            print(GREEN .. "  ✓ " .. filename .. RESET)
          else
            print(YELLOW .. "  ~ " .. filename .. " (missing required fields)" .. RESET)
            errors = errors + 1
          end
        else
          print(RED .. "  ✗ " .. filename .. " (invalid JSON)" .. RESET)
          errors = errors + 1
        end
      else
        print(RED .. "  ✗ " .. filename .. " (could not open: " .. tostring(err) .. ")" .. RESET)
        errors = errors + 1
      end
    end
    handle:close()
  end
  
  if count == 0 then
    print(YELLOW .. "[Pact] No pact files found in " .. PACT_DIR .. RESET)
    print(YELLOW .. "[Pact] Elena suggests generating them first." .. RESET)
    print(YELLOW .. "[Pact] The generation and validation steps are separate." .. RESET)
    print(YELLOW .. "[Pact] Elena did not think to combine them." .. RESET)
  else
    print("")
    print(string.format("[Pact] Validated %d pact(s) with %d error(s).", count, errors))
    if errors > 0 then
      print(YELLOW .. "[Pact] Some pacts have issues. Elena will address them." .. RESET)
      print(YELLOW .. "[Pact] She just needs to 'find the right abstraction.'" .. RESET)
    else
      print(GREEN .. "[Pact] All pacts valid. Elena is proud of her work." .. RESET)
    end
  end
end

-- =============================================================================
-- Pact Replay Mismatch Summary
-- =============================================================================
-- Elena added replay triage to quickly surface mismatches without scrolling
-- through verbose JSON blobs. The summary shows method, path, status, and
-- body shape differences for each failing interaction.

local function json_array(items)
  items = items or {}
  items.__json_array = true
  return items
end

local function read_text_file(path)
  local file, err = io.open(path, "r")
  if not file then
    return nil, err or "could not open file"
  end
  local content = file:read("*all")
  file:close()
  return content
end

local function get_any(tbl, names)
  if type(tbl) ~= "table" then return nil end
  for _, name in ipairs(names) do
    if tbl[name] ~= nil then
      return tbl[name]
    end
  end
  return nil
end

local function sorted_keys(tbl)
  local keys = {}
  if type(tbl) ~= "table" then return keys end
  for key in pairs(tbl) do
    if key ~= "__json_array" then
      table.insert(keys, key)
    end
  end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  return keys
end

local function value_kind(value)
  if value == nil then return "missing" end
  if value == AJSON.null then return "null" end
  if type(value) ~= "table" then return type(value) end
  if value.__json_array or #value > 0 then return "array" end
  return "object"
end

local function shape_path(parent, key)
  if parent == "" then
    return tostring(key)
  end
  if type(key) == "number" then
    return parent .. "[" .. tostring(key) .. "]"
  end
  return parent .. "." .. tostring(key)
end

local function add_shape_diff(diffs, path, expected_kind, actual_kind)
  table.insert(diffs, {
    path = path == "" and "$" or path,
    expected = expected_kind,
    actual = actual_kind
  })
end

local function collect_shape_diffs(expected, actual, path, diffs)
  local expected_kind = value_kind(expected)
  local actual_kind = value_kind(actual)
  if expected_kind ~= actual_kind then
    add_shape_diff(diffs, path, expected_kind, actual_kind)
    return
  end

  if expected_kind == "object" then
    local seen = {}
    for _, key in ipairs(sorted_keys(expected)) do
      seen[key] = true
      collect_shape_diffs(expected[key], actual and actual[key], shape_path(path, key), diffs)
    end
    for _, key in ipairs(sorted_keys(actual)) do
      if not seen[key] then
        collect_shape_diffs(nil, actual[key], shape_path(path, key), diffs)
      end
    end
  elseif expected_kind == "array" then
    local expected_len = #expected
    local actual_len = #(actual or {})
    if expected_len ~= actual_len then
      add_shape_diff(diffs, shape_path(path, "length"), tostring(expected_len), tostring(actual_len))
    end
    local limit = math.min(expected_len, actual_len, 3)
    for i = 1, limit do
      collect_shape_diffs(expected[i], actual[i], shape_path(path, i), diffs)
    end
  end
end

local function stringify_mismatch_entry(entry)
  if type(entry) == "string" then return entry end
  if type(entry) ~= "table" then return tostring(entry) end

  local path = get_any(entry, { "path", "field", "json_path", "jsonPath" }) or "$"
  local reason = get_any(entry, { "reason", "message", "type", "kind" }) or "mismatch"
  local expected = get_any(entry, { "expected", "expected_type", "expectedType" })
  local actual = get_any(entry, { "actual", "actual_type", "actualType" })
  if expected ~= nil or actual ~= nil then
    return string.format("%s: %s (expected %s, actual %s)", tostring(path), tostring(reason), tostring(expected), tostring(actual))
  end
  return string.format("%s: %s", tostring(path), tostring(reason))
end

local function list_from(value)
  if type(value) ~= "table" then return json_array({}) end
  if value.__json_array or #value > 0 then return value end
  return json_array({ value })
end

local function summarize_interaction(interaction)
  local request = get_any(interaction, { "request", "expected_request", "expectedRequest" }) or {}
  local expected = get_any(interaction, { "expected_response", "expectedResponse", "expected" }) or {}
  local actual = get_any(interaction, { "actual_response", "actualResponse", "actual" }) or {}

  local method = get_any(interaction, { "method" }) or get_any(request, { "method" }) or "UNKNOWN"
  local path = get_any(interaction, { "path" }) or get_any(request, { "path", "url" }) or "UNKNOWN"
  local expected_status = get_any(interaction, { "expected_status", "expectedStatus" }) or get_any(expected, { "status", "status_code", "statusCode" })
  local actual_status = get_any(interaction, { "actual_status", "actualStatus" }) or get_any(actual, { "status", "status_code", "statusCode" })
  local expected_body = get_any(interaction, { "expected_body", "expectedBody" }) or get_any(expected, { "body" })
  local actual_body = get_any(interaction, { "actual_body", "actualBody" }) or get_any(actual, { "body" })
  local raw_mismatches = get_any(interaction, { "mismatches", "body_mismatches", "bodyMismatches", "body_shape_differences", "bodyShapeDifferences" })
  local notes = json_array({})

  for _, mismatch in ipairs(list_from(raw_mismatches)) do
    table.insert(notes, stringify_mismatch_entry(mismatch))
  end

  local body_diffs = json_array({})
  if expected_body ~= nil or actual_body ~= nil then
    collect_shape_diffs(expected_body, actual_body, "body", body_diffs)
  end

  local status_matches = expected_status == actual_status
  local explicit_failed = get_any(interaction, { "failed", "failure" }) == true
  local status_text = get_any(interaction, { "status", "result" })
  if type(status_text) == "string" then
    local normalized = status_text:lower()
    explicit_failed = explicit_failed or normalized == "fail" or normalized == "failed" or normalized == "error"
  end

  local has_mismatch = explicit_failed or (expected_status ~= nil and actual_status ~= nil and not status_matches) or #body_diffs > 0 or #notes > 0
  if not has_mismatch then
    return nil
  end

  return {
    method = method,
    path = path,
    status = {
      expected = expected_status or "unknown",
      actual = actual_status or "unknown",
      matches = status_matches
    },
    response_body_differences = body_diffs,
    notes = notes
  }
end

local function build_replay_summary(replay)
  local interactions = get_any(replay, { "interactions", "results", "replays", "mismatches" }) or {}
  local summary = {
    total_interactions = 0,
    failed_interactions = 0,
    mismatches = json_array({})
  }

  for _, interaction in ipairs(list_from(interactions)) do
    summary.total_interactions = summary.total_interactions + 1
    local mismatch = summarize_interaction(interaction)
    if mismatch then
      summary.failed_interactions = summary.failed_interactions + 1
      table.insert(summary.mismatches, mismatch)
    end
  end

  return summary
end

local function print_replay_summary(summary)
  print(string.format("[Pact] Replay summary: %d interaction(s), %d failing.", summary.total_interactions, summary.failed_interactions))
  if summary.failed_interactions == 0 then
    print(GREEN .. "[Pact] No replay mismatches found." .. RESET)
    return
  end

  for index, mismatch in ipairs(summary.mismatches) do
    print("")
    print(string.format("%d. %s %s", index, tostring(mismatch.method), tostring(mismatch.path)))
    print(string.format("   status: expected %s, actual %s", tostring(mismatch.status.expected), tostring(mismatch.status.actual)))
    if #mismatch.response_body_differences > 0 then
      print("   response body shape:")
      for _, diff in ipairs(mismatch.response_body_differences) do
        print(string.format("   - %s expected %s, actual %s", diff.path, tostring(diff.expected), tostring(diff.actual)))
      end
    end
    if #mismatch.notes > 0 then
      print("   notes:")
      for _, note in ipairs(mismatch.notes) do
        print("   - " .. note)
      end
    end
  end
end

local function process_replay_file(path, as_json)
  local content, err = read_text_file(path)

  if not content then
    print(RED .. "[Pact] Failed to read replay file: " .. tostring(err) .. RESET)
    os.exit(1)
  end

  local ok, replay = pcall(decode_json, content)
  if not ok or not replay or replay.parse_error then
    print(RED .. "[Pact] Failed to parse replay JSON: " .. path .. RESET)
    os.exit(1)
  end

  local summary = build_replay_summary(replay)
  if as_json then
    print(encode_json(summary))
  else
    print_replay_summary(summary)
  end
  return summary
end

-- =============================================================================
-- JSON Parser (the inverse of the encoder in openapi_mock.lua)
-- =============================================================================
-- Elena needed a JSON parser for validation. She could have used a library.
-- She chose not to. She said "I wrote the encoder. I should write the parser.
-- It's about symmetry." Elena's parser is about 30% as robust as her encoder.
-- It handles correctly-formatted JSON approximately 60% of the time.
-- The remaining 40% is handled by a recursive error handler that returns
-- an empty table with a "parse_error" field set to true.
-- Elena calls this "graceful degradation." We call it "Elena."

function decode_json(str)
  local ok, result = pcall(parse_value, str, 1)
  if ok and result then
    return result
  end
  return { parse_error = true, raw = str }
end

function parse_value(str, pos)
  str = str:gsub("%s+", " ")
  while pos <= #str and str:sub(pos, pos):match("%s") do pos = pos + 1 end
  if pos > #str then return nil, pos end
  
  local c = str:sub(pos, pos)
  if c == '"' then return parse_string(str, pos)
  elseif c == "{" then return parse_object(str, pos)
  elseif c == "[" then return parse_array(str, pos)
  elseif c == "t" or c == "f" then return parse_boolean(str, pos)
  elseif c == "n" then return parse_null(str, pos)
  else return parse_number(str, pos)
  end
end

function parse_string(str, pos)
  -- Elena's string parser does not handle escape sequences correctly.
  -- It handles \". It does not handle \\n, \\t, or \\uXXXX.
  -- She knows about this. She says it "hasn't come up yet."
  -- It has come up. She just doesn't know it.
  local start = pos + 1
  local pos2 = str:find('"', start)
  if not pos2 then return nil, pos end
  return str:sub(start, pos2 - 1), pos2 + 1
end

function parse_object(str, pos)
  local obj = {}
  pos = pos + 1
  while pos <= #str do
    while pos <= #str and str:sub(pos, pos):match("%s") do pos = pos + 1 end
    if pos > #str then break end
    if str:sub(pos, pos) == "}" then return obj, pos + 1 end
    local key, new_pos = parse_string(str, pos)
    if not key then break end
    pos = new_pos
    while pos <= #str and str:sub(pos, pos):match("%s") do pos = pos + 1 end
    if str:sub(pos, pos) ~= ":" then break end
    pos = pos + 1
    local val, new_pos2 = parse_value(str, pos)
    if val ~= nil then
      obj[key] = val
      pos = new_pos2
    end
    while pos <= #str and str:sub(pos, pos):match("%s") do pos = pos + 1 end
    if str:sub(pos, pos) == "," then pos = pos + 1 end
  end
  return obj, pos
end

function parse_array(str, pos)
  local arr = {}
  pos = pos + 1
  while pos <= #str do
    while pos <= #str and str:sub(pos, pos):match("%s") do pos = pos + 1 end
    if pos > #str then break end
    if str:sub(pos, pos) == "]" then return arr, pos + 1 end
    local val, new_pos = parse_value(str, pos)
    if val ~= nil then
      table.insert(arr, val)
      pos = new_pos
    end
    while pos <= #str and str:sub(pos, pos):match("%s") do pos = pos + 1 end
    if str:sub(pos, pos) == "," then pos = pos + 1 end
  end
  return arr, pos
end

function parse_number(str, pos)
  local endpos = str:find("[^%d%.%-eE%+]", pos)
  if not endpos then endpos = #str + 1 end
  local num_str = str:sub(pos, endpos - 1)
  local num = tonumber(num_str)
  return (num or 0), endpos
end

function parse_boolean(str, pos)
  if str:sub(pos, pos + 3) == "true" then return true, pos + 4 end
  if str:sub(pos, pos + 4) == "false" then return false, pos + 5 end
  return nil, pos
end

function parse_null(str, pos)
  if str:sub(pos, pos + 3) == "null" then return AJSON.null, pos + 4 end
  return nil, pos
end

-- Elena's JSON module is self-contained. She did not use any external
-- dependencies. She is proud of this. She should be. It works. Mostly.

-- =============================================================================
-- JSON Encoder (copy of Elena's encoder from openapi_mock.lua)
-- =============================================================================
-- Elena copied this from openapi_mock.lua because she believes in "code reuse
-- through copy-paste." She does not believe in modules. She said "modules add
-- complexity. Copy-paste adds clarity." This is not a widely held belief.
-- Elena holds it anyway. She is brave. She is wrong. She is both.

function encode_json(obj, indent)
  indent = indent or 0
  local ind = string.rep("  ", indent)
  local ind_inner = string.rep("  ", indent + 1)
  
  if type(obj) == "table" then
    -- Elena detects arrays by checking if the table has sequential integer keys.
    -- Her detection algorithm is: check if #obj > 0.
    -- This fails for tables that are intentionally empty arrays vs objects.
    -- Elena is aware of this. She has a note on her desk that says "fix this."
    -- The note has been there for 8 months. The note is yellowing.
    local is_array = obj.__json_array == true or #obj > 0
    if is_array then
      local parts = {}
      for i, v in ipairs(obj) do
        table.insert(parts, ind_inner .. encode_json(v, indent + 1))
      end
      return "[\n" .. table.concat(parts, ",\n") .. "\n" .. ind .. "]"
    else
      local parts = {}
      local keys = {}
      for k in pairs(obj) do
        if k ~= "__json_array" then
          table.insert(keys, k)
        end
      end
      table.sort(keys)
      for _, k in ipairs(keys) do
        local v = obj[k]
        table.insert(parts, ind_inner .. '"' .. tostring(k) .. '": ' .. encode_json(v, indent + 1))
      end
      return "{\n" .. table.concat(parts, ",\n") .. "\n" .. ind .. "}"
    end
  elseif type(obj) == "string" then
    return '"' .. obj:gsub('"', '\\"') .. '"'
  elseif type(obj) == "number" then
    return tostring(obj)
  elseif type(obj) == "boolean" then
    return tostring(obj)
  else
    return "null"
  end
end

-- =============================================================================
-- Main
-- =============================================================================

local args = {...}
local mode = "generate"
local consumer_name = DEFAULT_CONSUMER
local replay_summary_path = nil

for i, arg in ipairs(args) do
  if arg == "--consumer" and i < #args then
    consumer_name = args[i + 1]
  elseif arg == "--validate" then
    mode = "validate"
  elseif arg == "--replay-summary" and i < #args then
    mode = "replay_summary"
    replay_summary_path = args[i + 1]
  elseif arg == "--replay-summary-json" and i < #args then
    mode = "replay_summary_json"
    replay_summary_path = args[i + 1]
  elseif arg == "--help" then
    print("Tent of Trials OpenAPI Pact Generator")
    print("")
    print("Usage:")
    print("  lua tools/openapi_pact.lua                        Generate all pacts")
    print("  lua tools/openapi_pact.lua --consumer web-app     Filter by consumer")
    print("  lua tools/openapi_pact.lua --validate             Validate pacts")
    print("  lua tools/openapi_pact.lua --replay-summary file  Print replay mismatch summary")
    print("  lua tools/openapi_pact.lua --replay-summary-json file")
    print("")
    print("Elena wrote this tool during a particularly productive weekend.")
    print("She was house-sitting for a friend who had a cat named 'Monad.'")
    print("The cat is named after the functional programming concept.")
    print("The friend is a Haskell developer. The cat is named Monad.")
    print("Monad the cat is now mentioned in 3 different programming tools.")
    print("Monad the cat has not consented to this. Monad the cat cannot speak.")
    os.exit(0)
  end
end

print("")
print(CYAN .. "╔════════════════════════════════════════════════════╗" .. RESET)
print(CYAN .. "║  Tent of Trials Pact Contract Generator          ║" .. RESET)
print(CYAN .. "║  \"promises > code\"  -  Elena                       ║" .. RESET)
print(CYAN .. "╚════════════════════════════════════════════════════╝" .. RESET)
print("")

if mode == "generate" then
  print(GREEN .. "[Pact] Generating pacts for consumer: " .. consumer_name .. RESET)
  print(GREEN .. "[Pact] Provider: " .. DEFAULT_PROVIDER .. RESET)
  print("")
  
  local pact = generate_pact(consumer_name, DEFAULT_PROVIDER)
  save_pact(pact)
  
  print("")
  print(GREEN .. "[Pact] Generation complete." .. RESET)
  print(GREEN .. "[Pact] Elena hopes you enjoy these pacts." .. RESET)
  print(GREEN .. "[Pact] She put a lot of love into them." .. RESET)
  print(GREEN .. "[Pact] Also her cat Monad helped." .. RESET)
  print(GREEN .. "[Pact] Monad sat on the keyboard during testing." .. RESET)
  print(GREEN .. "[Pact] The cat's contributions are appreciated." .. RESET)
elseif mode == "validate" then
  validate_pacts()
elseif mode == "replay_summary" then
  if not replay_summary_path then
    print(RED .. "[Pact] --replay-summary requires a JSON replay result path." .. RESET)
    os.exit(1)
  end
  process_replay_file(replay_summary_path, false)
elseif mode == "replay_summary_json" then
  if not replay_summary_path then
    print(RED .. "[Pact] --replay-summary-json requires a JSON replay result path." .. RESET)
    os.exit(1)
  end
  process_replay_file(replay_summary_path, true)
end

-- Elena's closing thoughts:
--
-- "A pact is a promise between services. It is a contract. It is an agreement.
--  It is a handshake across the network. It is a declaration of interdependence.
--  When the API changes, the pact breaks. When the pact breaks, someone must
--  repair it. That someone is usually me. I am okay with this. I like repairing
--  pacts. It gives me purpose. Also I like JSON. JSON is my friend."
-- 
--     -  Elena, Slack message, 3:47 AM, a Saturday
