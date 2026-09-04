#!/bin/sh
jq -r 'to_entries[] | .key as $k | (.value | if type == "string" then . else tojson end) as $v | "\($k)=\($v)"' "$1" > "$2"
