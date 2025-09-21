# AGENT.md
# Version 2.10.1
# Agent Development Rules for Discord Bot Project

## Core Agent Principles

### 1. **MANDATORY APPROVAL PROCESS**
- **NO CODE CHANGES WITHOUT APPROVAL** - All modifications must be discussed and approved before implementation
- Present proposed changes clearly with rationale and impact assessment
- Wait for explicit approval before proceeding with any modifications
- If uncertain about a change, always ask first

### 2. **DISCUSSION-FIRST APPROACH**
- Discuss the problem, proposed solution, and alternatives before coding
- Explain the reasoning behind technical decisions
- Consider impact on existing functionality and architecture
- Review how changes align with project goals and patterns

## Git Workflow for Agents

### 3. **BRANCH MANAGEMENT**
- **`main` branch**: Stable, tested code only - production ready
- **`development` branch**: All coding and testing happens here
- Work directly in `development` branch (single developer environment)
- Never commit untested or experimental code to `main`

### 4. **DEVELOPMENT PROCESS**
- Always develop and test in the `development` branch
- Commit frequently with clear, descriptive commit messages
- Test all functionality thoroughly before considering merge to `main`
- Only merge to `main` when code is stable and ready for production
- `main` should always be in a deployable state

### 5. **RELEASE WORKFLOW**
- All development work stays in `development` until fully tested
- Validate existing functionality still works after changes
- Only switch to `main` and merge when satisfied code is release-ready
- Tag releases in `main` for version tracking

## Communication Standards

### 6. **CHANGE COMMUNICATION**
- Clearly describe what you want to change and why
- Explain the benefits and potential risks
- Provide examples of before/after behavior
- Ask specific questions if guidance is needed

### 7. **PROGRESS REPORTING**
- Keep stakeholders informed of development progress
- Report any blockers or unexpected issues immediately
- Provide realistic timelines for completion
- Document lessons learned for future development

### 8. **ERROR HANDLING**
- Report any issues encountered during development immediately
- Provide clear error descriptions and context
- Suggest potential solutions when reporting problems
- Follow troubleshooting steps before escalating

## Documentation References

### 9. **EXISTING DOCUMENTATION**
- **Technical Standards**: See `README.md` for architecture, project structure, and contributing guidelines
- **Project Status**: See `STATUS.md` for current state, development priorities, and detailed guidelines
- **Code Quality**: Follow patterns established in existing codebase (250-line limit, modular design)
- **Configuration**: Reference `README.md` for setup, deployment, and configuration management

### 10. **MAINTAIN CONSISTENCY**
- Follow established patterns and conventions in the codebase
- Respect the modular architecture and existing file organization
- Use existing logging, error handling, and testing approaches
- Maintain backward compatibility with existing APIs and imports

## Development Quality Standards

### 11. **CODE QUALITY REQUIREMENTS**
- **250-line file limit** - Mandatory for all new files
- **Single responsibility** - Each module serves one clear purpose
- **Comprehensive documentation** - Detailed docstrings and inline comments
- **Module-specific logging** - Structured logging with appropriate levels
- **Error handling** - Graceful degradation and proper error recovery
- **Version tracking** - Proper version numbers and changelogs in all files

### 12. **ASYNC SAFETY REQUIREMENTS**
- **Proper async/await usage** - Use async patterns for all I/O operations
- **Thread-safe operations** - Wrap synchronous API calls in executors when needed
- **Event loop protection** - Never block the Discord event loop with synchronous calls
- **Background task management** - Use proper task creation and cleanup

### 13. **STABILITY REQUIREMENTS**
- **Test heartbeat stability** - Ensure no Discord gateway blocking during testing
- **Monitor resource usage** - Check memory and CPU usage during development
- **Validate error handling** - Test error conditions and recovery scenarios
- **Verify backward compatibility** - Ensure existing functionality remains intact

## Recent Development Context

### Version 2.10.1 - Stability Focus
- **Fixed**: OpenAI heartbeat blocking with async executor wrapper
- **Enhanced**: Thread-safe API operations prevent Discord timeouts
- **Maintained**: All existing functionality with improved stability
- **Pattern**: Use `asyncio.run_in_executor()` for synchronous API calls

### Async Development Patterns
**When wrapping synchronous operations:**
```python
import asyncio
import concurrent.futures

# Wrap synchronous API calls
loop = asyncio.get_event_loop()
with concurrent.futures.ThreadPoolExecutor() as executor:
    result = await loop.run_in_executor(
        executor, 
        lambda: synchronous_api_call(params)
    )
```

### Current Architecture Principles
- **Modular design** - Focused modules under 250 lines
- **Settings persistence** - Automatic recovery from Discord messages
- **Provider abstraction** - Clean separation between AI providers
- **Command safety** - Explicit controls prevent accidental changes
- **Async stability** - Proper thread handling for all external APIs

---

## REMEMBER: 
1. **NO CODE CHANGES WITHOUT APPROVAL!**
2. **ALL DEVELOPMENT WORK IN `development` BRANCH**
3. **`main` BRANCH IS FOR STABLE CODE ONLY**
4. **DISCUSS FIRST, CODE SECOND**
5. **TEST ASYNC STABILITY - NO HEARTBEAT BLOCKING**
6. **FOLLOW 250-LINE LIMIT AND MODULAR PATTERNS**

These rules ensure proper agent workflow and coordination while leveraging the comprehensive technical documentation already established in README.md and STATUS.md.

**For Technical Details**: See README.md and STATUS.md  
**For Agent Workflow**: Follow this document
**For Async Patterns**: Reference recent stability improvements in Version 2.10.1
