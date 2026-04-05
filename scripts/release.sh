#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [version]"
    echo "  version: tag name for the release (e.g. 0.1.0)"
    echo "  If omitted, inferred from pyproject.toml"
    exit 1
}

if [[ $# -gt 1 ]]; then
    usage
fi

# Read version from pyproject.toml
PYPROJECT_VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
if [[ -z "$PYPROJECT_VERSION" ]]; then
    echo "Error: could not read version from pyproject.toml" >&2
    exit 1
fi

if [[ $# -eq 1 ]]; then
    VERSION="$1"
    if [[ "$PYPROJECT_VERSION" != "$VERSION" ]]; then
        echo "Error: pyproject.toml version ($PYPROJECT_VERSION) does not match release version ($VERSION)" >&2
        exit 1
    fi
else
    VERSION="$PYPROJECT_VERSION"
    echo "Inferred version $VERSION from pyproject.toml"
fi

TAG="$VERSION"

# Validate version format (digits and dots only)
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: version must be in semver format (e.g. 0.1.0)" >&2
    exit 1
fi

# Ensure working copy has no uncommitted changes
if jj diff --stat | grep -q .; then
    echo "Error: working copy has uncommitted changes. Commit or squash first." >&2
    exit 1
fi

# Determine the release revision: if @ is empty, use @- (the parent)
if jj log -r @ --no-graph -T 'empty'; then
    RELEASE_REV="@-"
else
    RELEASE_REV="@"
fi

# Ensure release revision is on main bookmark
if ! jj log -r "$RELEASE_REV" --no-graph -T 'bookmarks' | grep -q '\bmain\b'; then
    BOOKMARKS=$(jj log -r "$RELEASE_REV" --no-graph -T 'bookmarks')
    echo "Warning: release revision is not on 'main' (bookmarks: ${BOOKMARKS:-none})."
    read -rp "Continue? [y/N] " confirm
    if [[ "$confirm" != [yY] ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# Check if tag already exists
if jj tag list "$TAG" 2>/dev/null | grep -q .; then
    echo "Error: tag '$TAG' already exists." >&2
    exit 1
fi

echo "Creating release $TAG..."

# Create tag and push to remote
jj tag create "$TAG" -r "$RELEASE_REV"
jj git push --remote origin --tag "$TAG"

# Create GitHub release
gh release create "$TAG" \
    --title "v$VERSION" \
    --generate-notes

echo "Release $TAG created successfully."
echo "View at: $(gh release view "$TAG" --json url --jq '.url')"
