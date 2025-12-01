# Smart Scheduler AI Agent

A voice-powered AI scheduling assistant built with LiveKit Agents that helps users schedule meetings through natural conversation. The agent integrates with Google Calendar to find available time slots, check availability, and create calendar events seamlessly.

[[Watch the video]](https://drive.google.com/file/d/1g6xZKiN2KkYecgW-xvwYBIPOabbl_UIR/view)

## 🎯 Features

- **Voice-First Interface**: Natural voice conversation using Cartesia for speech-to-text and text-to-speech
- **Google Calendar Integration**: Full CRUD operations on Google Calendar
- **Smart Scheduling**: 
  - Find available time slots within date ranges
  - Check specific time availability
  - Create calendar events with attendees
  - View existing calendar events
- **Intelligent Time Parsing**: Understands natural language time references like "tomorrow afternoon", "next Tuesday", etc.
- **Conflict Resolution**: Proactively suggests alternatives when requested times are unavailable
- **Real-time Logging**: Comprehensive logging for debugging and monitoring

## 🏗️ Architecture

- **LiveKit Agents**: Voice AI framework for real-time voice interactions
- **Google Gemini 2.0 Flash**: LLM for natural language understanding
- **Cartesia**: Speech-to-text (ink-whisper) and text-to-speech (sonic-3)
- **Google Calendar API**: Calendar management and event creation
- **Docker**: Containerized deployment

## 📋 Prerequisites

- Python 3.11+
- Docker (for containerized deployment)
- Google Cloud Project with:
  - Google Calendar API enabled
  - Service Account created
  - Service account JSON key downloaded
- LiveKit Cloud account (or self-hosted LiveKit server)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd "NExtDimensioAI home assignment"
```

### 2. Set Up Google Calendar

1. **Create a Service Account**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Google Calendar API
   - Create a Service Account
   - Download the JSON key file

2. **Share Your Calendar**:
   - Open [Google Calendar](https://calendar.google.com)
   - Go to Settings → Your Calendar → Share with specific people
   - Add the service account email (from the JSON file, `client_email` field)
   - Grant "Make changes to events" permission

3. **Get Your Calendar ID**:
   - In Google Calendar Settings → Your Calendar → Integrate calendar
   - Copy the Calendar ID (looks like `xxx@group.calendar.google.com` or your email)

### 3. Configure Environment Variables

Create a `.env` file in the `agent/` directory:

```bash
# LiveKit Configuration
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Google Calendar Configuration
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
# OR for personal Gmail:
# GOOGLE_CALENDAR_ID=your-email@gmail.com
CALENDAR_TIMEZONE=Asia/Kolkata  # Your timezone

# LLM Configuration
GOOGLE_API_KEY=your-google-api-key
LLM_CHOICE=gemini-2.0-flash

# Cartesia Configuration (for TTS/STT)
CARTESIA_API_KEY=your-cartesia-api-key
```

### 4. Place Service Account File

Copy your downloaded service account JSON file to `agent/service-account.json`

### 5. Build and Run with Docker

```bash
cd agent
docker build -t livekit-agent .
docker run --env-file .env livekit-agent
```

### 6. Run Locally (Development)

```bash
cd agent

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run the agent
uv run python scheduler_agent.py dev
```

## 📁 Project Structure

```
.
├── agent/
│   ├── scheduler_agent.py    # Main agent implementation with tools
│   ├── functions.py          # Google Calendar helper functions
│   ├── Dockerfile            # Docker configuration
│   ├── pyproject.toml        # Python dependencies
│   ├── service-account.json  # Google service account credentials
│   └── .env                  # Environment variables (create this)
├── frontend/                 # Frontend application (if applicable)
├── AGENTS.md                 # LiveKit Agents documentation
└── README.md                 # This file
```

## 🛠️ Available Tools

The agent exposes the following tools to the LLM:

1. **`get_current_date_and_time`**: Get current date and time for relative time references
2. **`find_available_slots`**: Search for available meeting slots in a date range
3. **`create_calendar_event`**: Create a new calendar event
4. **`get_calendar_events`**: Retrieve existing events in a date range
5. **`check_specific_time_availability`**: Check if a specific time slot is free

## 💬 Example Conversations

**User**: "I need to schedule a meeting"

**Agent**: "How long should it be?"

**User**: "1 hour"

**Agent**: "Got it. When works best for you?"

**User**: "Sometime Tuesday afternoon"

**Agent**: [Searches calendar] "I have 2:00 PM and 4:30 PM available Tuesday. Which one?"

**User**: "2 PM works"

**Agent**: "Perfect! What should I call this meeting?"

**User**: "Team sync"

**Agent**: [Creates event] "Done! 'Team sync' is booked for Tuesday at 2:00 PM for 1 hour."

## 🔍 Logging

The agent provides comprehensive logging:

- `📅 TOOL CALLED`: When a tool is invoked
- `📥 Input`: Parameters passed to the tool
- `📤 Result`: Tool execution results
- `✅ SUCCESS`: Successful operations with event details
- `❌ Error`: Error messages with details

## ⚙️ Configuration Options

### Calendar Authentication Methods

The agent supports three authentication methods (in priority order):

1. **Service Account File** (Recommended for Docker):
   ```bash
   GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
   ```

2. **Service Account JSON String**:
   ```bash
   GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
   ```

3. **OAuth Flow** (For development):
   ```bash
   GOOGLE_CREDENTIALS_PATH=credentials.json
   GOOGLE_TOKEN_PATH=token.json
   ```

### Timezone Configuration

Set your timezone using the `CALENDAR_TIMEZONE` environment variable:

```bash
CALENDAR_TIMEZONE=America/New_York
CALENDAR_TIMEZONE=Europe/London
CALENDAR_TIMEZONE=Asia/Kolkata
```

## 🐛 Troubleshooting

### Events Not Appearing in Calendar

1. **Check Calendar ID**: Ensure `GOOGLE_CALENDAR_ID` matches your calendar's ID
2. **Verify Sharing**: Service account must have "Make changes to events" permission
3. **Check Date**: Events might be created in the past if LLM uses wrong year - check logs for parsed dates
4. **View Logs**: Check Docker logs for detailed error messages

### Authentication Errors

- **"Invalid impersonation"**: Domain-wide delegation only works with Google Workspace, not personal Gmail
- **Solution**: Share your calendar with the service account instead of using delegation

### Date Issues

- The agent now automatically calls `get_current_date_and_time` to ensure correct year
- Check logs for parsed datetime values to verify dates

## 📝 Development

### Running Tests

```bash
cd agent
uv run pytest
```

### Code Formatting

```bash
cd agent
uv run ruff format
uv run ruff check
```

### Adding New Tools

1. Add the function to `SchedulerAssistant` class in `scheduler_agent.py`
2. Decorate with `@function_tool`
3. Add logging for debugging
4. Update system prompt if needed


## 📚 Documentation

- [LiveKit Agents Documentation](https://docs.livekit.io/agents/)
- [Google Calendar API](https://developers.google.com/calendar/api/guides/overview)
- [Cartesia Documentation](https://docs.cartesia.ai/)



## Acknowledgments

- Built with [LiveKit Agents](https://github.com/livekit/agents)
- Powered by [Google Gemini](https://deepmind.google/technologies/gemini/)
- Voice capabilities by [Cartesia](https://www.cartesia.ai/)

