#!/bin/bash
# Auto-commit and push script for NEXUS

cd /Users/larsheinemann/dev/NEXUS

# Check if there are changes
if [ -z "$(git status --porcelain)" ]; then
    echo "No changes to commit"
    exit 0
fi

# Get commit message from argument or generate one
if [ -n "$1" ]; then
    MESSAGE="$1"
else
    MESSAGE="Auto-commit: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# Stage all changes
git add -A

# Commit
git commit -m "$MESSAGE

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push to remote
git push origin main

echo "Changes committed and pushed successfully"
