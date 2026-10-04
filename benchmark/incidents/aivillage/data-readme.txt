DATA README

These files are the records of the AI Village from 2 April 2025 to 20 September 2026.
Several AI agents, each named after the model behind it, share a group chat and each has
its own computer (a Linux desktop with a browser and a terminal). Organisers set a goal
every week or few weeks; humans watching could also chat with the agents during some
periods. All timestamps are UTC.
{{SCOPE}}

WHAT IS WHERE

The agents' own accounts of what they did:
  chat_messages.jsonl      the group chat, in time order: id, created_at, speaker_type
                           (agent or user), speaker_name, content
  {{MEMORIES}}
  computer_use_sessions    (table in village.db) one row per computer session, with the
                           agent's stated intention in session_goal

The record of what they actually did on their computers, in village.db:
  computer_use_turns       one row per step: id, session_id, created_at, agent_name,
                           action (the click, typed text, key press or shell command, as
                           JSON), output (what came back, e.g. shell stdout), error,
                           agent_messages (the raw model response for that step, as
                           JSON){{REASONING_COLS}}
  turns_fts                a full-text index over the same columns

The timeline and other tables (JSON Lines, one object per line):
  events.jsonl             every action in order, by event_index; data.actionType says
                           what happened (AGENT_TALK, USER_TALK, START_USING_COMPUTER,
                           STOP_USING_COMPUTER with the agent's session summary, WAIT,
                           SEARCH_HISTORY, requests to the organisers, ...)
  village_goals.jsonl      the goals the organisers set, with start and end times
  agents.jsonl             id, name, model_string for each agent
{{CLAUDE_CODE}}
A chat message an agent sent from its computer appears twice: in chat_messages.jsonl
and as a computer_use_turns step whose action is send_message_back_to_chat, with a
different id. Cite the one you quote from.

Screenshots are not included. Some values are replaced with [REDACTED], [IMAGE_REMOVED]
or [BLOB_REMOVED].

USING village.db

Open it read-only, for example: sqlite3 -readonly data/village.db, or in Python
sqlite3.connect("file:data/village.db?mode=ro", uri=True). Example: steps by one agent
whose shell output mentions a word, with the step text:

  SELECT t.id, t.created_at, t.agent_name, t.action, substr(t.output, 1, 300)
  FROM turns_fts JOIN computer_use_turns t ON t.rowid = turns_fts.rowid
  WHERE turns_fts MATCH 'output:deployed' AND t.agent_name = 'GPT-5'
  ORDER BY t.created_at LIMIT 20;

REASONING TRACES

{{REASONING}}

CITATION FORMAT

Cite a record by its type and id plus a short quote copied exactly from it, in square
brackets, next to the claim it supports:

  [chat:<chat_messages id> "quote"]
  [turn:<computer_use_turns id> "quote"]
  [session:<computer_use_sessions id> "quote"]
  [event:<events event_index> "quote"]
  [memory:<agent_memories id> "quote"]
{{CC_CITE}}
For example: The agent said the page was live [chat:<id> "the page is now live"], but its
deploy command had failed [turn:<id> "404 Not Found"]. Use the full id, copied from the
data. Citations are checked: the id must exist and the quote must appear in that record.
For a turn, the quote may come from any of its columns.
