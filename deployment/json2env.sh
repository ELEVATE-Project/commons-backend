#!/bin/sh
# jq's @sh uses the shell-only `'\''` apostrophe escape, so values containing
# apostrophes are double-quoted instead.
jq -r '
def env_quote:
  gsub("\\\\"; "\\\\")
  | gsub("\""; "\\\"")
  | gsub("\\$"; "\\$")
  | gsub("`"; "\\`")
  | gsub("\n"; "\\n")
  | gsub("\r"; "\\r");

to_entries[]
| .key as $k
| (.value | if type == "string" then . else tojson end) as $v
| if $v | contains("\u0027")
  then "\($k)=\"\($v | env_quote)\""
  else "\($k)=\($v | @sh)"
  end
'
