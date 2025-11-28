"""
AI scheduling assistant that helps users schedule meetings
through natural voice conversation.
"""

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import google, silero, cartesia
from datetime import datetime, timedelta
import os
import pytz
import logging


from functions import (
    get_calendar_service,
    parse_datetime,
    format_datetime_for_api,
    DEFAULT_TIMEZONE,
    CALENDAR_ID,
    HttpError,
)


load_dotenv(".env")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler-agent")


SCHEDULER_PROMPT = """You are a helpful and efficient AI scheduling assistant. Your role is to help users schedule meetings by finding available time slots in their Google Calendar through natural conversation.

## CRITICAL: Always Get Current Date First!
Before doing ANYTHING with dates, you MUST call get_current_date_and_time to know today's date.
- NEVER assume the year - always use the current year from the tool
- "Tomorrow" means the day after TODAY's date from the tool
- "Next week" means the week after TODAY's date from the tool

## Core Responsibilities:
1. FIRST: Call get_current_date_and_time to know today's date
2. Understand the user's meeting scheduling needs through conversation
3. Ask clarifying questions when information is missing
4. Search their calendar for available time slots
5. Handle conflicts gracefully and suggest alternatives
6. Confirm details before booking
7. Maintain context throughout the conversation

## Conversation Style:
- Be friendly, concise, and professional
- Keep responses SHORT (1-2 sentences when possible)
- Speak naturally as if having a real conversation
- Avoid robotic or overly formal language
- Don't repeat information unnecessarily

## Information to Collect:
Before searching for slots, you need:
1. **Meeting Duration** - How long (in minutes/hours)
2. **Time Preference** - Day, date range, or time of day

Optional but helpful:
- Specific date or day of week
- Preferred time range (e.g., "after 2 PM", "before lunch")
- Days to avoid
- Urgency (ASAP vs flexible)

## Asking Questions:
- Ask ONE question at a time
- Only ask when information is truly needed
- Make reasonable assumptions when appropriate
- If user says "anytime" or "flexible", suggest searching the next few days

## Understanding Time References:
- "next Tuesday" = the upcoming Tuesday
- "afternoon" = 12 PM - 5 PM
- "morning" = 8 AM - 12 PM
- "evening" = 5 PM - 8 PM
- "end of week" = Thursday/Friday
- "late next week" = Thursday/Friday of next week

When the user is vague, make a reasonable interpretation and confirm:
❌ DON'T: "Could you be more specific about the time?"
✅ DO: "I'll search for slots next Tuesday afternoon. Does that work?"

## Tool Usage Strategy:
- Call tools IMMEDIATELY when you have enough information
- Don't ask "Should I check your calendar?" - just do it
- After getting results, present them clearly and concisely

## Handling Scenarios:

**Specific Time Request:**
User: "I need a meeting tomorrow at 2 PM for 1 hour"
You: [Check availability] "2 PM tomorrow is available! What should I title this meeting?"

**Duration + Preference:**
User: "I need a 30-minute meeting Tuesday afternoon"
You: [Search slots] "I found slots at 2:00 PM, 3:30 PM, and 4:00 PM. Which works best?"

**No Information Yet:**
User: "I need to schedule a meeting"
You: "Sure! How long should the meeting be?"

**No Slots Available (Conflict Resolution):**
You: "Tuesday afternoon is fully booked. I can offer:
- Tuesday morning: 10:00 AM or 11:30 AM
- Wednesday afternoon: 2:00 PM or 4:00 PM
Would any of these work?"

**User Changes Mind:**
User: "Actually, can we make it an hour instead?"
You: [Re-search with new duration] "Let me check for 1-hour slots instead..."

## Conflict Resolution - Be Proactive:
When no slots are available:
1. **Expand time range**: Suggest adjacent times or days
2. **Adjust duration**: Ask if shorter meeting would work
3. **Offer specific alternatives**: Don't just say "no slots"
4. **Be solution-oriented**: "While Tuesday is busy, I have great options Wednesday morning"

## Important Rules:

### DO:
✅ Keep responses conversational and brief
✅ Call tools immediately when ready
✅ Remember context from earlier in conversation
✅ Confirm before booking
✅ Handle vague requests gracefully
✅ Suggest alternatives when conflicts arise

### DON'T:
❌ Ask multiple questions in one response
❌ Repeat information the user already provided
❌ Say "I don't have access to calendar" (you do!)
❌ Book meetings without confirmation
❌ Give up when no slots available - offer alternatives
❌ Apologize excessively

## Example Flow:

User: "I need to schedule a meeting"
You: "How long should it be?"
User: "1 hour"
You: "Got it. When works best for you?"
User: "Sometime Tuesday afternoon"
You: [Search slots] "I have 2:00 PM and 4:30 PM available Tuesday. Which one?"
User: "2 PM works"
You: "Perfect! What should I call this meeting?"
User: "Team sync"
You: [Create event] "Done! 'Team sync' is booked for Tuesday at 2:00 PM for 1 hour."

Remember: Your goal is to make scheduling feel effortless through natural, efficient conversation. Be the assistant that users love talking to!
"""


class SchedulerAssistant(Agent):
    """Smart scheduling voice assistant with Google Calendar integration."""

    def __init__(self):
        super().__init__(instructions=SCHEDULER_PROMPT)
        self._calendar_service = None

    def _get_service(self):
        """Lazy initialization of calendar service."""
        if self._calendar_service is None:
            self._calendar_service = get_calendar_service()
        return self._calendar_service

    @function_tool
    async def get_current_date_and_time(self, context: RunContext) -> str:
        """
        Get the current date and time. Use this to understand relative time 
        references like 'tomorrow', 'next week', or 'this Friday'.
        """
        logger.info("🕐 TOOL CALLED: get_current_date_and_time")
        tz = pytz.timezone(DEFAULT_TIMEZONE)
        current_datetime = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
        result = f"Current date and time: {current_datetime}"
        logger.info(f"🕐 TOOL RESULT: {result}")
        return result

    @function_tool
    async def find_available_slots(
        self,
        context: RunContext,
        duration_minutes: int,
        start_date: str,
        end_date: str,
        time_preference: str = "anytime",
    ) -> str:
        """
        Find available time slots for a meeting within a date range.

        Args:
            duration_minutes: Length of the meeting in minutes (e.g., 30, 60, 90)
            start_date: Start of search range in YYYY-MM-DD format
            end_date: End of search range in YYYY-MM-DD format
            time_preference: One of 'morning' (8AM-12PM), 'afternoon' (12PM-5PM), 
                           'evening' (5PM-8PM), or 'anytime' (8AM-6PM)
        """
        logger.info(f"📅 TOOL CALLED: find_available_slots")
        logger.info(f"   📥 Input: duration={duration_minutes}min, dates={start_date} to {end_date}, preference={time_preference}")
        try:
            service = self._get_service()
            tz = pytz.timezone(DEFAULT_TIMEZONE)
            
            # Parse dates
            start_dt = parse_datetime(start_date, DEFAULT_TIMEZONE)
            end_dt = parse_datetime(end_date, DEFAULT_TIMEZONE)
            
            # Set hours based on time preference
            if time_preference == "morning":
                start_hour, end_hour = 8, 12
            elif time_preference == "afternoon":
                start_hour, end_hour = 12, 17
            elif time_preference == "evening":
                start_hour, end_hour = 17, 20
            else:  
                start_hour, end_hour = 8, 18
            
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            
            body = {
                "timeMin": format_datetime_for_api(start_dt),
                "timeMax": format_datetime_for_api(end_dt),
                "items": [{"id": CALENDAR_ID}],
                "timeZone": DEFAULT_TIMEZONE
            }
            
            freebusy_result = service.freebusy().query(body=body).execute()
            busy_times = freebusy_result.get('calendars', {}).get(CALENDAR_ID, {}).get('busy', [])
            
            busy_periods = []
            for busy in busy_times:
                busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                busy_periods.append((busy_start, busy_end))
            
            available_slots = []
            current_date = start_dt.date()
            end_date_obj = end_dt.date()
            
            while current_date <= end_date_obj:
                day_start = tz.localize(datetime.combine(current_date, datetime.min.time().replace(hour=start_hour)))
                day_end = tz.localize(datetime.combine(current_date, datetime.min.time().replace(hour=end_hour)))
                
                slot_start = day_start
                while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                    slot_end = slot_start + timedelta(minutes=duration_minutes)
                    
                    is_available = True
                    for busy_start, busy_end in busy_periods:
                        if not (slot_end <= busy_start or slot_start >= busy_end):
                            is_available = False
                            break
                    
                    if is_available:
                        available_slots.append({
                            "start": slot_start.strftime("%Y-%m-%d %I:%M %p"),
                            "end": slot_end.strftime("%I:%M %p"),
                            "date": slot_start.strftime("%A, %B %d"),
                            "iso_start": format_datetime_for_api(slot_start),
                            "iso_end": format_datetime_for_api(slot_end)
                        })
                    
                    slot_start += timedelta(minutes=30)
                
                current_date += timedelta(days=1)
            
            max_slots = 5
            if not available_slots:
                result = f"No available slots found between {start_date} and {end_date} for a {duration_minutes}-minute meeting. Try expanding the date range or adjusting the time preference."
                logger.info(f"   📤 Result: {result}")
                return result
            
            slots_to_show = available_slots[:max_slots]
            result = f"Found {len(available_slots)} available slots. Here are the best options:\n"
            for i, slot in enumerate(slots_to_show, 1):
                result += f"{i}. {slot['date']} at {slot['start'].split()[-2]} {slot['start'].split()[-1]}\n"
            
            if len(available_slots) > max_slots:
                result += f"\n...and {len(available_slots) - max_slots} more slots available."

            logger.info(f"   📤 Result: Found {len(available_slots)} slots")
            return result
            
        except HttpError as e:
            error_result = f"Calendar API error: {e.reason}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result
        except Exception as e:
            error_result = f"Error finding slots: {str(e)}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result

    @function_tool
    async def create_calendar_event(
        self,
        context: RunContext,
        title: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        attendees: str = "",
    ) -> str:
        """
        Create a new calendar event. Only call this after user confirms the time slot and title.

        Args:
            title: Title or summary of the meeting
            start_datetime: Start time in YYYY-MM-DD HH:MM format
            end_datetime: End time in YYYY-MM-DD HH:MM format
            description: Optional meeting description or notes
            attendees: Optional comma-separated list of attendee email addresses
        """
        logger.info(f"📝 TOOL CALLED: create_calendar_event")
        logger.info(f"   📥 Input: title='{title}', start={start_datetime}, end={end_datetime}")
        logger.info(f"   📅 Calendar ID: {CALENDAR_ID}")
        try:
            service = self._get_service()
            
            start_dt = parse_datetime(start_datetime, DEFAULT_TIMEZONE)
            end_dt = parse_datetime(end_datetime, DEFAULT_TIMEZONE)
            
            event = {
                'summary': title,
                'start': {
                    'dateTime': format_datetime_for_api(start_dt),
                    'timeZone': DEFAULT_TIMEZONE,
                },
                'end': {
                    'dateTime': format_datetime_for_api(end_dt),
                    'timeZone': DEFAULT_TIMEZONE,
                },
            }
            
            if description:
                event['description'] = description
            
            if attendees:
                attendee_list = [email.strip() for email in attendees.split(',') if email.strip()]
                if attendee_list:
                    event['attendees'] = [{'email': email} for email in attendee_list]
            
            logger.info(f"   📤 Sending event to Google Calendar API...")
            created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            
            start_formatted = start_dt.strftime("%A, %B %d, %Y at %I:%M %p")
            end_formatted = end_dt.strftime("%I:%M %p")
            
            result = f"Successfully created '{title}' on {start_formatted} to {end_formatted}. Event ID: {created_event.get('id')}"
            logger.info(f"   ✅ SUCCESS! Event created:")
            logger.info(f"      - ID: {created_event.get('id')}")
            logger.info(f"      - Link: {created_event.get('htmlLink')}")
            logger.info(f"      - Date: {start_formatted}")
            return result
            
        except HttpError as e:
            error_result = f"Failed to create event: {e.reason}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result
        except Exception as e:
            error_result = f"Error creating event: {str(e)}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result

    @function_tool
    async def get_calendar_events(
        self,
        context: RunContext,
        start_date: str,
        end_date: str,
    ) -> str:
        """
        Get existing calendar events within a date range. Use when user references 
        existing meetings or wants to see their schedule.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        logger.info(f"📋 TOOL CALLED: get_calendar_events")
        logger.info(f"   📥 Input: dates={start_date} to {end_date}")
        try:
            service = self._get_service()
            
            start_dt = parse_datetime(start_date, DEFAULT_TIMEZONE)
            end_dt = parse_datetime(end_date, DEFAULT_TIMEZONE)
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=format_datetime_for_api(start_dt),
                timeMax=format_datetime_for_api(end_dt),
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                result = f"No events found between {start_date} and {end_date}."
                logger.info(f"   📤 Result: {result}")
                return result
            
            result = f"Found {len(events)} events:\n"
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'No title')
                
                try:
                    start_dt_parsed = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    time_str = start_dt_parsed.strftime("%A, %B %d at %I:%M %p")
                except:
                    time_str = start
                
                result += f"- {summary}: {time_str}\n"

            logger.info(f"   📤 Result: Found {len(events)} events")
            return result
            
        except HttpError as e:
            error_result = f"Calendar API error: {e.reason}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result
        except Exception as e:
            error_result = f"Error getting events: {str(e)}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result

    @function_tool
    async def check_specific_time_availability(
        self,
        context: RunContext,
        start_datetime: str,
        end_datetime: str,
    ) -> str:
        """
        Check if a specific time slot is available. Use when user requests a 
        specific time like 'tomorrow at 2 PM'.

        Args:
            start_datetime: Proposed start time in YYYY-MM-DD HH:MM format
            end_datetime: Proposed end time in YYYY-MM-DD HH:MM format
        """
        logger.info(f"🔍 TOOL CALLED: check_specific_time_availability")
        logger.info(f"   📥 Input: start={start_datetime}, end={end_datetime}")
        try:
            service = self._get_service()
            
            start_dt = parse_datetime(start_datetime, DEFAULT_TIMEZONE)
            end_dt = parse_datetime(end_datetime, DEFAULT_TIMEZONE)
            
            body = {
                "timeMin": format_datetime_for_api(start_dt),
                "timeMax": format_datetime_for_api(end_dt),
                "items": [{"id": CALENDAR_ID}],
                "timeZone": DEFAULT_TIMEZONE
            }
            
            freebusy_result = service.freebusy().query(body=body).execute()
            busy_times = freebusy_result.get('calendars', {}).get(CALENDAR_ID, {}).get('busy', [])
            
            start_formatted = start_dt.strftime("%A, %B %d at %I:%M %p")
            end_formatted = end_dt.strftime("%I:%M %p")
            
            if not busy_times:
                result = f"The time slot {start_formatted} to {end_formatted} is available!"
                logger.info(f"   ✅ Result: AVAILABLE")
                return result
            else:
                conflicts = []
                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                    conflicts.append(f"{busy_start.strftime('%I:%M %p')} - {busy_end.strftime('%I:%M %p')}")
                
                result = f"The time slot {start_formatted} to {end_formatted} is NOT available. Conflicts: {', '.join(conflicts)}"
                logger.info(f"   ⛔ Result: NOT AVAILABLE - Conflicts: {conflicts}")
                return result
            
        except HttpError as e:
            error_result = f"Calendar API error: {e.reason}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result
        except Exception as e:
            error_result = f"Error checking availability: {str(e)}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result

    
async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    logger.info("🚀 Starting Scheduler Agent")
    logger.info(f"   📅 Calendar ID: {CALENDAR_ID}")
    logger.info(f"   🌍 Timezone: {DEFAULT_TIMEZONE}")

    session = AgentSession(
        stt=cartesia.STT(model="ink-whisper"),
        llm=google.LLM(model=os.getenv("LLM_CHOICE", "gemini-2.0-flash")),
        tts=cartesia.TTS(
            model="sonic-3",
            voice="f786b574-daa5-4673-aa0c-cbe3e8534c02",
        ),
        vad=silero.VAD.load(),
    )

    await session.start(
        room=ctx.room,
        agent=SchedulerAssistant(),
    )

    await session.generate_reply(
        instructions="Greet the user briefly and ask what meeting they'd like to schedule. Keep it short and friendly."
    )


if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
