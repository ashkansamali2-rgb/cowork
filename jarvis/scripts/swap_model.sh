#!/bin/bash
# Usage: swap_model.sh <slot> <filename>
#   slot: fast | brain
#   filename: model filename in ~/Downloads/
#
# Example: swap_model.sh brain gemma-4-27B-it-Q4_K_M.gguf

set -e
SLOT="${1:?Usage: swap_model.sh <fast|brain> <model_filename.gguf>}"
FILE="${2:?Usage: swap_model.sh <fast|brain> <model_filename.gguf>}"
CONFIG="$HOME/cowork/jarvis/config/models.json"

if [[ "$SLOT" != "fast" && "$SLOT" != "brain" ]]; then
    echo "Error: slot must be 'fast' or 'brain'"
    exit 1
fi

if [[ ! -f "$HOME/Downloads/$FILE" ]]; then
    echo "Error: ~/Downloads/$FILE not found"
    exit 1
fi

# Update models.json
python3 - <<PYEOF
import json
c = json.load(open("$CONFIG"))
c["$SLOT"]["file"] = "$FILE"
json.dump(c, open("$CONFIG", "w"), indent=2)
print(f"Updated $SLOT -> $FILE")
PYEOF

# Get port and ctx_size for sed replacement
PORT=$(python3 -c "import json; c=json.load(open('$CONFIG')); print(c['$SLOT']['port'])")
CTX=$(python3 -c "import json; c=json.load(open('$CONFIG')); print(c['$SLOT']['ctx_size'])")

# Update zshrc: replace the model filename on the line that has this port
sed -i '' "s|gemma-4-[^ ]*\.gguf \(.*--port $PORT\)|$FILE \1|" ~/.zshrc

echo "Updated ~/.zshrc: port $PORT now uses $FILE (ctx-size $CTX)"
echo "Run:  stop && start"
