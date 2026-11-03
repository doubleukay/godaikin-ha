.PHONY: bump release

# Bump the patch version, push the commit + tag, then publish the GitHub release.
bump:
	bump-my-version bump patch
	git push --follow-tags
	$(MAKE) release

# Publish a GitHub release for the current version's tag (re-runnable if gh failed).
# Notes default to commit subjects since the previous tag (bump commits excluded);
# override with: make release NOTES_FILE=notes.md
release:
	@set -e; \
	tag=v$$(bump-my-version show current_version); \
	prev=$$(git describe --tags --abbrev=0 "$$tag^"); \
	if [ -n "$(NOTES_FILE)" ]; then \
		notes=$$(cat "$(NOTES_FILE)"); \
	else \
		notes=$$(git log --no-merges --format='- %s' "$$prev..$$tag" | grep -v '^- Bump version' || true); \
	fi; \
	echo "Creating release $$tag (changes since $$prev)"; \
	gh release create "$$tag" --verify-tag --notes "$$notes"
