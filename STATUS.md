# Discord AI Assistant Bot - Project Status Document

## Project Overview

**Current State**: Production-ready Discord bot with AI text/image generation capabilities  
**Last Updated**: January 2025  
**Deployment Status**: Stable with recent feature enhancements  

### What Works
✅ **AI Text Responses** - OpenAI GPT models responding to user messages  
✅ **AI Image Generation** - Automatic image creation when contextually appropriate  
✅ **Multi-Channel Support** - Per-channel configuration and conversation history  
✅ **Command System** - Full admin command suite for bot management  
✅ **Background Processing** - Non-blocking AI calls prevent Discord connection issues  
✅ **Conversation Context** - Bot maintains conversation history for coherent responses  
✅ **Direct AI Addressing** - NEW: Address specific providers without changing defaults  
✅ **DeepSeek Thinking Control** - Show/hide reasoning process with `!thinking` commands  

## Architecture Overview

### Core Components
```
discord-bot/
├── main.py                 # Entry point and initialization
├── bot.py                  # Discord event handling and message processing
├── config.py              # Environment-based configuration
├── ai_providers/          # AI provider abstraction layer
│   ├── openai_provider.py # OpenAI Responses API integration
│   ├── anthropic_provider.py # Anthropic Claude integration
│   └── baseten_provider.py # BaseTen DeepSeek R1 integration
├── commands/              # Discord command modules
│   ├── history_commands.py # History and prompt management
│   ├── prompt_commands.py  # System prompt management
│   ├── ai_provider_commands.py # Provider switching
│   ├── thinking_commands.py # DeepSeek reasoning control
│   └── auto_respond_commands.py # Auto-response controls
└── utils/                 # Utility modules
    ├── ai_utils.py        # AI provider abstraction
    ├── logging_utils.py   # Structured logging system
    └── history/           # Conversation management package
```

### Key Design Decisions

#### 1. Single API Approach (Stable)
**Implementation**: Uses only OpenAI Responses API for both text and images
- **File**: `ai_providers/openai_provider.py`
- **Key Insight**: `response.output_text` contains text, `response.output` contains images
- **Benefit**: One API call handles both text and image generation
- **AI Decides**: Model determines when images are helpful vs text-only responses

#### 2. Background Task Processing (Stable)
**Implementation**: AI processing runs in `asyncio.create_task()` to prevent Discord heartbeat blocking
- **File**: `bot.py` - `handle_ai_response()` and `handle_ai_response_task()`
- **Problem Solved**: Eliminated "Shard ID None heartbeat blocked" warnings
- **Pattern**: Show typing immediately, process in background, respond when complete

#### 3. Direct AI Addressing (NEW - Version 2.3.0)
**Implementation**: Parse provider prefix at message start without changing channel defaults
- **File**: `bot.py` - `parse_provider_override()` function
- **Usage**: `"openai, draw a cat"`, `"anthropic, write a poem"`, `"deepseek, solve this"`
- **Benefits**: 
  - No configuration changes needed
  - Natural conversation flow
  - Clean history storage (removes provider prefix)
  - Works with both auto-respond and direct addressing

#### 4. Structured Response Format (Stable)
**Implementation**: AI providers return consistent format regardless of content type
```python
{
    "text": "response text",
    "images": [{"data": bytes, "format": "png", "base64": "..."}],
    "metadata": {"model_used": "gpt-4o", "tools_called": ["image_generation"]}
}
```

#### 5. Per-Channel State Management (Stable)
**Current**: In-memory dictionaries for channel-specific settings
```python
channel_history = defaultdict(list)           # Conversation context
channel_system_prompts = {}                   # Custom AI personalities  
channel_ai_providers = {}                     # Provider overrides
auto_respond_channels = set()                  # Auto-response enabled channels
channel_thinking_enabled = {}                 # DeepSeek thinking display
```

## Current Implementation Details

### AI Provider System
**OpenAI Provider** (`ai_providers/openai_provider.py`):
- **API**: Uses `client.responses.create()` exclusively
- **Tools**: `[{"type": "image_generation"}]` enables image generation
- **Text Extraction**: `response.output_text`
- **Image Extraction**: Iterates `response.output` for `type="image_generation_call"`
- **No Fallbacks**: Removed dual API complexity

**Anthropic Provider** (`ai_providers/anthropic_provider.py`):
- **API**: Uses `client.messages.create()` (text only)
- **Format**: Converts messages to Anthropic format (system prompt separate)
- **Context**: Large 200k context window

**BaseTen DeepSeek Provider** (`ai_providers/baseten_provider.py`):
- **API**: OpenAI-compatible interface via BaseTen
- **Model**: `deepseek-ai/DeepSeek-R1`
- **Special Feature**: Thinking process filtering based on channel settings
- **Context**: 64k context window, 8k max response tokens

### Message Processing Flow
1. **Message Received** → Parse for provider override OR check for bot prefix/auto-respond
2. **Provider Override Handling** → Extract provider (e.g., "openai,") and clean content
3. **History Loading** → Auto-load channel history if not already loaded  
4. **Message Storage** → Add to `channel_history[channel_id]` (using clean content)
5. **AI Processing** → Background task with typing indicator
6. **Response Handling** → Send text and/or images to Discord
7. **History Update** → Store bot response in conversation history

### Direct AI Addressing Implementation
**Provider Override Parsing** (`bot.py`):
```python
def parse_provider_override(content):
    """Extract provider override from message start"""
    providers = ['openai', 'anthropic', 'deepseek']
    for provider in providers:
        prefix = f"{provider},"
        if content.lower().startswith(prefix):
            clean_content = content[len(prefix):].strip()
            return provider, clean_content
    return None, content
```

**Usage Flow**:
1. User types: `"openai, draw me a sunset"`
2. Bot parses: `provider_override="openai"`, `clean_content="draw me a sunset"`
3. Bot stores clean content in history: `"Username: draw me a sunset"`
4. Bot uses OpenAI provider for this response only
5. Channel default provider remains unchanged

### Command System
**History Management**:
- `!setprompt <text>` - Custom AI personality per channel
- `!setai <provider>` - Switch between OpenAI/Anthropic/DeepSeek  
- `!loadhistory` - Reload channel message history
- `!cleanhistory` - Remove commands from conversation context

**Auto-Response**:
- `!autorespond` - Toggle automatic responses for channel
- `!autosetup` - Apply default auto-response setting

**DeepSeek Thinking Control**:
- `!thinking on/off` - Show/hide DeepSeek reasoning process
- `!thinkingstatus` - Check current thinking display setting

## Known Issues & Technical Debt

### Fixed Issues ✅
1. **Message Formatting Bug** - RESOLVED
   - **Problem**: Username duplication in API calls (e.g., "user: user: message")
   - **Solution**: Fixed message conversion in OpenAI provider
   - **Status**: ✅ COMPLETED in Version 2.3.0

### High Priority Issues

#### 1. Configuration Persistence 
**Problem**: Channel settings lost on bot restart
- **Affected**: AI provider choices, system prompts, auto-response settings
- **Current**: Stored in memory dictionaries only
- **Proposed Solution**: Parse settings from conversation history instead of external storage
- **Implementation Location**: `utils/history/loading.py` - add settings reconstruction

#### 2. Channel Data Cleanup
**Problem**: Orphaned data for deleted/inaccessible channels
- **Growth**: Memory dictionaries accumulate stale channel data
- **Solution Needed**: Periodic cleanup task to validate channel access

#### 3. Discord Connection Stability  
**Problem**: Occasional "waiting too long" errors from Discord
- **Likely Cause**: Edge cases where operations still block event loop
- **Solution**: Add timeout handling and retry logic

## Special Implementation Notes

### 1. Direct AI Addressing Considerations
**Memory Efficiency**: Provider overrides don't create persistent state
**History Cleanliness**: Provider prefixes are removed from stored conversation history
**Fallback Behavior**: Invalid provider names are ignored, using channel default instead

### 2. OpenAI Responses API Structure
**Critical Knowledge**: The response object structure is non-standard
```python
# Text content location
text = response.output_text  # NOT response.content or response.text

# Image data location  
for output in response.output:
    if output.type == "image_generation_call":
        image_data = base64.b64decode(output.result)
```

### 3. Discord File Handling for Images
**Implementation**: Convert base64 to Discord File objects
```python
image_buffer = io.BytesIO(image_data)
discord_file = discord.File(image_buffer, filename="generated_image.png")
await message.channel.send(file=discord_file)
```

### 4. History Loading Strategy
**Automatic Loading**: Channels load history on first message
- **Trigger**: `channel_id not in loaded_history_channels`
- **Mechanism**: `load_channel_history(channel, is_automatic=True)`
- **Locking**: Per-channel locks prevent race conditions

### 5. Message Filtering Logic
**Smart Filtering**: Excludes commands and bot outputs from conversation context
- **Commands**: Skip messages starting with `!` (except `!setprompt`)
- **History Output**: Filter bot responses that look like command output
- **Attachments**: Skip messages with files/images

### 6. DeepSeek Thinking Process Control
**Implementation**: Filter `<think>...</think>` tags based on channel setting
- **Default**: Thinking hidden for cleaner output
- **Command Control**: `!thinking on/off` toggles display per channel
- **Pattern**: Uses regex to remove thinking sections when disabled

## Development Environment

### Required Environment Variables
```bash
# Core API Keys
DISCORD_TOKEN=<bot_token>
OPENAI_API_KEY=<api_key>
ANTHROPIC_API_KEY=<api_key>
BASETEN_DEEPSEEK_KEY=<api_key>

# Configuration
AI_PROVIDER=openai                    # Default provider
AI_MODEL=gpt-4o-mini                  # OpenAI model
ANTHROPIC_MODEL=claude-3-haiku-20240307
AUTO_RESPOND=false                    # Default auto-respond
MAX_HISTORY=10                        # Messages to remember
BOT_PREFIX="Bot, "                    # Activation prefix

# Logging
LOG_LEVEL=INFO                        # DEBUG for development
LOG_FILE=stdout                       # or file path
```

### Key Dependencies
- `discord.py>=2.0.0` - Discord bot framework
- `openai>=1.0.0` - OpenAI API client
- `anthropic>=0.3.0` - Anthropic API client
- `python-dotenv>=0.19.0` - Environment management

## Testing Strategy

### Current Testing
- **Manual Testing**: Interactive Discord testing in development server
- **Log Monitoring**: Structured logging for debugging
- **Direct Addressing Testing**: Verified all three provider overrides work correctly

### Recommended Testing Additions
- Unit tests for message processing logic
- Integration tests for AI provider responses
- Mock Discord events for isolated testing
- Performance testing for high-traffic scenarios

## Deployment Considerations

### Production Readiness
**Ready For**:
- Single-server deployment
- Low to medium traffic Discord servers
- Basic AI interaction use cases
- Direct provider addressing without configuration

**Needs Work**:
- High-availability deployment
- Database persistence
- Monitoring and alerting
- Cost tracking and limits

### Scaling Considerations
- **Memory Usage**: Grows with number of active channels
- **API Costs**: No built-in usage tracking or limits
- **Rate Limiting**: Basic handling, could be improved
- **Concurrent Requests**: Background tasks help but no request queuing

## Next Developer Onboarding

### Immediate Priority
1. **Implement history-based persistence** - Elegant solution, no external storage needed
2. **Add timeout handling** - Prevent API calls from hanging indefinitely
3. **Channel cleanup task** - Remove orphaned data for deleted channels

### Recent Achievements
1. ✅ **Fixed message formatting bug** - Username duplication resolved
2. ✅ **Added direct AI addressing** - Major UX improvement
3. ✅ **Enhanced provider parsing** - Clean message handling

### Development Setup
1. Clone repository and install dependencies
2. Set up Discord bot in Discord Developer Portal
3. Configure environment variables
4. Test in development Discord server
5. Monitor logs for any remaining issues

### Code Quality Notes
- **Logging**: Comprehensive module-specific logging already implemented
- **Error Handling**: Basic error handling in place, could be enhanced
- **Documentation**: Code is well-commented, README is comprehensive
- **Architecture**: Clean separation of concerns, modular design

## Success Metrics
- ✅ **Functionality**: Both text and image generation working
- ✅ **Stability**: No heartbeat blocking issues
- ✅ **User Experience**: Intuitive commands and responses
- ✅ **Direct Addressing**: Seamless provider override functionality
- ✅ **Message Quality**: Fixed username duplication issues
- 🔄 **Persistence**: Settings survive restarts (in progress)
- 🔄 **Resource Management**: Clean memory usage (needs work)

## Version History

### Version 2.3.0 (Current) - Direct AI Addressing
- **NEW**: Direct provider addressing without changing defaults
- **FIXED**: Username duplication in message formatting
- **ENHANCED**: Provider override parsing and clean content handling
- **IMPROVED**: Natural conversation flow with multiple providers

### Version 2.2.0 - Enhanced AI Response Control
- **ADDED**: DeepSeek thinking control with `!thinking on/off` commands
- **REMOVED**: Artificial response truncation for natural AI completion
- **ENHANCED**: Message handling and Discord limit management

### Version 2.1.0 - Multi-Provider Enhancement
- **ADDED**: BaseTen DeepSeek R1 integration
- **REFACTORED**: Command structure into focused modules
- **FIXED**: Discord message length handling with smart splitting

This project represents a mature, production-ready Discord AI bot with excellent user experience features and room for enhancement in persistence and monitoring capabilities.
