#!/bin/sh
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
input_tokens=$(echo "$input" | jq -r '.context_window.current_usage.input_tokens // empty')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // empty')

# Build token info string
token_info=""
if [ -n "$input_tokens" ] && [ -n "$ctx_size" ]; then
  token_info=$(printf "%s / %s tokens" "$input_tokens" "$ctx_size")
fi

# Build context usage percentage string
ctx_pct_info=""
if [ -n "$used_pct" ]; then
  ctx_pct_info=$(printf "%.0f%% used" "$used_pct")
fi

# Print cwd in green
printf '\033[0;32m%s\033[0m' "$cwd"

# Print token info if available
if [ -n "$token_info" ]; then
  printf '\033[0;38m | \033[0;33m%s\033[0m' "$token_info"
fi

# Print context window percentage if available
if [ -n "$ctx_pct_info" ]; then
  printf '\033[0;38m [\033[0;36m%s\033[0;38m]\033[0m' "$ctx_pct_info"
fi
