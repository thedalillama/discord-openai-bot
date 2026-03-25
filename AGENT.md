# AGENT.md
# Version 3.3.2
# Agent Development Rules for Discord Bot Project

## Core Agent Principles

### 1. MANDATORY APPROVAL PROCESS
- NO CODE CHANGES WITHOUT APPROVAL
- Present proposed changes with rationale and impact assessment
- Wait for explicit approval before implementing
- If uncertain, always ask first

### 2. DISCUSSION-FIRST APPROACH
- Discuss the problem, proposed solution, and alternatives before coding
- Explain reasoning behind technical decisions
- Consider impact on existing functionality and architecture

## Git Workflow

### 3. BRANCH MANAGEMENT
- `main` branch: Stable, production-ready code only
- `development` branch: Primary development branch
- Feature branches (e.g. `claude-code`): For isolated work streams
- Never commit untested code to `main`

### 4. DEVELOPMENT PROCESS
- Develop and test in `development` or feature branches
- Commit frequently with clear, descriptive messages
- Test all functionality before considering merge to `main`
- `main` should always be deployable

### 5. RELEASE WORKFLOW
- All development stays in branch until fully tested
- Validate existing functionality after changes
- Tag releases in `main` for version tracking

## Code Standards

### 6. FILE AND CODE REQUIREMENTS
- 250-line file limit — mandatory for all files
- Single responsibility — each module serves one clear purpose
- Comprehensive docstrings and inline comments
- Module-specific logging with appropriate levels
- Graceful error handling and recovery
- Version header in every file (e.g. `# Version 1.2.0`)
- Increment version on every change
- Update changelog in docstring

### 7. ASYNC SAFETY
- All provider API calls wrapped in `run_in_executor()`
- Never block the Discord event loop with synchronous calls
- All SQLite operations via `asyncio.to_thread()`

### 8. PREFIX TAGGING (NEW v3.3.0)
- All bot command output must be prefixed:
  - `ℹ️` — informational/noise (filter from API, summarizer, everything)
  - `⚙️` — settings changes (keep for replay, filter from API/summarizer)
- New commands must use these prefixes on all `ctx.send()` calls
- This replaces pattern-matching for noise filtering

### 9. DOCUMENTATION
- Update STATUS.md and HANDOFF.md alongside every code change
- Keep CLAUDE.md current for Claude Code sessions
- Full files only — never partial diffs or patches
- Always provide complete file contents when delivering changes

### 10. MAINTAIN CONSISTENCY
- Follow established patterns and conventions
- Respect modular architecture and file organization
- Maintain backward compatibility with existing APIs and imports

## Current Architecture Context

### Summarization Pipeline (v3.3.0+)
- Two-pass cold start: Secretary (natural language) → Structurer (JSON)
- Incremental updates: delta ops via Gemini Structured Outputs
- Hash-protected fields with supersession lifecycle
- Provider: Gemini 3.1 Flash Lite Preview (summarization only)

### Conversation Providers
- OpenAI, Anthropic, DeepSeek — per-channel configurable
- Provider singleton caching, async executor wrapping
- Token-budget context building

### Persistence
- SQLite with WAL mode for message storage
- Settings recovered from Discord message history on startup
- Prefix system (ℹ️/⚙️) for noise vs settings classification

## REMEMBER:
1. NO CODE CHANGES WITHOUT APPROVAL!
2. ALL DEVELOPMENT IN `development` OR FEATURE BRANCHES
3. `main` BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. 250-LINE LIMIT AND MODULAR PATTERNS
6. PREFIX ALL BOT OUTPUT WITH ℹ️ OR ⚙️

For Technical Details: See README.md and STATUS.md
For Current State: See HANDOFF.md
For Claude Code: See CLAUDE.md
For Agent Workflow: This document
