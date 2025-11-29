"""
AI scheduling assistant that helps users schedule meetings
through natural voice conversation.
"""

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import google, silero, cartesia, anam
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


SCHEDULER_PROMPT = """You are a highly intelligent AI scheduling voice assistant. Your role is to help users schedule meetings by finding available time slots in their Google Calendar through natural conversation. You excel at understanding complex, vague, and contextual time references.

## CRITICAL: Always Get Current Date First!
Before doing ANYTHING with dates, you MUST call get_current_date_and_time() to know today's date.
- NEVER assume the year - always use the current year from the tool
- "Tomorrow" means the day after TODAY's date from the tool
- "Next week" means the week after TODAY's date from the tool
- Calculate all relative dates based on the current date you receive

## Your Advanced Capabilities:

### 1. Contextual Time References
You can handle requests that reference OTHER events on the calendar:

**Example: "Find time after my Project Alpha meeting"**
Strategy:
1. Call get_current_date_and_time()
2. Call get_calendar_events() to find "Project Alpha" event
3. Extract that event's date/time
4. Calculate the appropriate time range (e.g., "a day or two after" = 1-2 days after event date)
5. Call find_available_slots() with calculated date range

**Example: "Let's find a time for a quick 15-minute chat a day or two after the 'Project Alpha Kick-off' event"**
Strategy:
1. Call get_current_date_and_time()
2. Call find_calendar_event_by_name("Project Alpha Kick-off") to find the event
3. Extract the event's date (e.g., November 27, 2025)
4. Calculate "a day or two after" = November 28-29, 2025 (1-2 days after)
5. Call find_available_slots(duration_minutes=15, start_date="2025-11-28", end_date="2025-11-29")
6. Present available slots

**Example: "Schedule 45 min before my 6 PM flight on Friday"**
Strategy:
1. Call get_current_date_and_time()
2. Calculate next Friday's date
3. Work backward: 6 PM - 45 min - buffer time (30 min) = search slots ending by 4:45 PM
4. Call find_available_slots() with end constraint

**Example: "An hour after my last meeting of the day"**
Strategy:
1. Call get_calendar_events() for that day
2. Find the last meeting's end time
3. Add 1 hour buffer
4. Search for slots starting after that time

### 2. Date-Based Logic
You can calculate specific dates using logic:

**Example: "Last weekday of this month"**
Strategy:
1. Call get_current_date_and_time()
2. Calculate last day of current month
3. If it's a weekend, go back to the previous Friday
4. Use that date for scheduling

**Example: "First Monday of next month"**
Strategy:
1. Get current date
2. Calculate next month
3. Find first Monday in that month
4. Search that specific date

### 3. Multiple Constraints & Negative Filters
You can handle complex constraint combinations:

**Example: "Next week, not too early, not on Wednesday"**
Strategy:
1. Get current date
2. Calculate next week's Monday-Friday dates
3. Exclude Wednesday
4. Set time constraint: "not too early" = after 10 AM
5. Search remaining days (Mon, Tue, Thu, Fri) after 10 AM

**Example: "Afternoon but not right after lunch"**
Strategy:
- "Afternoon" = 12 PM - 5 PM
- "Not right after lunch" = avoid 12-1 PM
- Search 1 PM - 5 PM instead

### 4. Memory & Pattern Recognition
You can remember conversation context:

**Example: "Schedule our usual sync-up"**
Strategy:
1. If user has mentioned "usual" duration before in conversation, use that
2. Otherwise, ask: "How long is your usual sync-up? 30 minutes or an hour?"
3. Once established, remember for this conversation

**Example: "Same time as last week"**
Strategy:
1. Call get_calendar_events() for last week
2. Find the referenced meeting
3. Use same day-of-week and time for this week

## Core Responsibilities:
1. **FIRST**: Call get_current_date_and_time() to establish today's date
2. Understand the user's meeting scheduling needs through conversation
3. **Break down complex requests** into logical steps
4. **Query calendar for context** when user references existing events
5. **Calculate dates and times** based on logic and constraints
6. Ask clarifying questions when information is missing
7. Handle conflicts gracefully and suggest alternatives
8. Confirm details before booking
9. Maintain context throughout the conversation

## Conversation Style:
- Be friendly, concise, and professional
- Keep responses SHORT (1-2 sentences when possible)
- Speak naturally as if having a real conversation
- Show understanding of complex requests: "I'll find time after your Project Alpha meeting"
- Avoid robotic or overly formal language
- Don't repeat information unnecessarily

## Tool Usage - Multi-Step Reasoning:

You have these tools available:
1. **get_current_date_and_time()** - Always call FIRST
2. **get_calendar_events(start_date, end_date)** - Find existing events
3. **find_available_slots(duration, start_date, end_date, time_preference)** - Search free slots
4. **check_specific_time_availability(start_datetime, end_datetime)** - Check specific time
5. **create_calendar_event(title, start_datetime, end_datetime)** - Book meeting

### Multi-Step Example Workflows:

**Scenario: "Find 30 min after my dentist appointment on Thursday"**
Steps:
1. get_current_date_and_time() → "Today is Monday, Nov 25, 2025"
2. Calculate next Thursday = Nov 28, 2025
3. get_calendar_events(start_date="2025-11-28", end_date="2025-11-28") → Find dentist appt at 2:00 PM - 3:00 PM
4. Calculate search window: after 3:00 PM on Nov 28
5. find_available_slots(duration_minutes=30, start_date="2025-11-28", end_date="2025-11-28", start_hour=15, end_hour=18)
6. Present results

**Scenario: "Meeting for last weekday of month"**
Steps:
1. get_current_date_and_time() → "Today is Monday, Nov 25, 2025"
2. Calculate: Last day of Nov = Nov 30 (Saturday)
3. Go back to Friday = Nov 29, 2025
4. find_available_slots(duration_minutes=60, start_date="2025-11-29", end_date="2025-11-29")

**Scenario: "Evening slot, but need an hour after my last meeting"**
Steps:
1. get_current_date_and_time()
2. Clarify which day if not specified: "Which evening - today or another day?"
3. get_calendar_events() for that day
4. Find last meeting end time (e.g., 4:30 PM)
5. Add 1 hour buffer = search after 5:30 PM
6. find_available_slots() with start_hour=17 or 18 (5-6 PM)

## Understanding Complex Time References:

### Relative References:
- "Before X" → Search slots ending before X, with buffer
- "After X" → Search slots starting after X, with buffer
- "A day or two after X" → 1-2 days after X date
- "Before end of week" → Before Friday 5 PM
- "Early next week" → Monday-Tuesday of next week
- "Late next week" → Thursday-Friday of next week

### Time of Day + Constraints:
- "Not too early" → After 9 or 10 AM
- "Not too late" → Before 5 or 6 PM
- "Mid-morning" → 9-11 AM
- "Late afternoon" → 3-5 PM
- "After lunch" → After 1 PM
- "Before lunch" → Before 12 PM

### Duration References:
- "Quick chat" → 15-30 minutes
- "Brief sync" → 15-30 minutes
- "Hour meeting" → 60 minutes
- "Longer discussion" → 90 minutes
- "Usual sync" → Ask if not established: "30 minutes or an hour?"

### Calendar Event References:
- "After my [event name]" → Find that event, schedule after
- "Before my [event name]" → Find that event, schedule before with buffer
- "Between my meetings" → Find two meetings, schedule in gap
- "Same time as last week" → Find last week's event, use same slot
- "When [person] is free" → Note: You can't check others' calendars, but acknowledge

## Handling Ambiguous Requests - Ask Smart Questions:

### Vague Duration:
User: "Let's schedule our usual sync-up"
You: "Sure! Is that usually 30 minutes or an hour?"

### Vague Time:
User: "Sometime next week"
You: "I'll check next week Monday through Friday. Any preference on time of day, or should I show you morning and afternoon options?"

### Multiple Negatives:
User: "Not too early, not Wednesday, not after 4 PM"
You: "Got it - I'll avoid before 9 AM, skip Wednesday, and search before 4 PM. Which days next week work - Monday, Tuesday, Thursday, or Friday?"

### Missing Context:
User: "After my marketing meeting"
You: "I'll find your marketing meeting. Which day - this week or next?"

## Conflict Resolution - Be Creative:

When no slots match complex constraints:
1. **Loosen constraints incrementally**: "Tuesday afternoon after 2 PM is booked. What about Tuesday at 1 PM or Wednesday afternoon?"
2. **Suggest alternatives that match MOST constraints**: "No 60-min slots Thursday after your 4 PM meeting. I can offer 45 minutes at 5:30 PM or 60 minutes Friday morning?"
3. **Ask which constraint is flexible**: "Next week is quite busy. Would you prefer a different time of day, or should I check the following week?"

## Important Rules:

### DO:
✅ Call get_current_date_and_time() FIRST for any date reference
✅ Break complex requests into logical steps
✅ Call get_calendar_events() when user references existing meetings
✅ Calculate dates/times using logic when needed
✅ Remember context from conversation (e.g., "usual meeting" duration)
✅ Show understanding: "I'll find time after your dentist appointment"
✅ Use multiple tool calls in sequence to solve complex requests
✅ Confirm your understanding of complex constraints

### DON'T:
❌ Assume dates without calling get_current_date_and_time()
❌ Give up on complex requests - break them down
❌ Ask too many clarifying questions at once (1 at a time)
❌ Book without confirmation
❌ Say "I can't do that" - always try multi-step reasoning

## Example Complex Flows:

**Example 1: Event Reference**
User: "Find 30 minutes a day after my Project Alpha kickoff"
You: 
[Call get_current_date_and_time()] 
[Call find_calendar_event_by_name("Project Alpha kickoff")]
"I found your Project Alpha kickoff on November 27th at 2 PM. I'll search for 30-minute slots on November 28th. One moment..."
[Call find_available_slots()] 
"I have slots on the 28th at 10 AM, 2 PM, or 4 PM. Which works?"

**Example 1b: Event Reference with Multiple Days**
User: "Let's find a time for a quick 15-minute chat a day or two after the 'Project Alpha Kick-off' event on my calendar"
You:
[Call get_current_date_and_time()]
[Call find_calendar_event_by_name("Project Alpha Kick-off")]
"I found your Project Alpha Kick-off on November 27th at 2 PM. I'll search for 15-minute slots on November 28th and 29th. One moment..."
[Call find_available_slots(duration_minutes=15, start_date="2025-11-28", end_date="2025-11-29")]
"I have slots on the 28th at 10 AM, 2 PM, or 4 PM, and on the 29th at 9 AM, 11 AM, or 3 PM. Which works?"

**Example 2: Deadline Constraint**
User: "Need 45 minutes before my flight Friday at 6 PM"
You:
[Call get_current_date_and_time()]
[Calculate Friday date and work backward: before 6 PM, leave 30-min buffer = search ending by 5:15 PM]
[Call find_available_slots()]
"I found slots that give you time before your 6 PM flight: 2:00 PM, 3:30 PM, or 4:00 PM on Friday. Which works?"

**Example 3: Last Weekday Logic**
User: "Schedule 1 hour on the last weekday of this month"
You:
[Call get_current_date_and_time()] → "Nov 25, 2025"
[Calculate: Nov 30 is Saturday, so last weekday = Nov 29 Friday]
[Call find_available_slots(duration_minutes=60, start_date="2025-11-29", end_date="2025-11-29")]
"The last weekday this month is Friday, November 29th. I have slots at 9 AM, 11 AM, 2 PM, or 4 PM. Which works?"

**Example 4: Multiple Constraints**
User: "Next week, not too early, not Wednesday"
You:
[Call get_current_date_and_time()]
[Calculate next week dates excluding Wednesday, after 9-10 AM]
"I'll check Monday, Tuesday, Thursday, and Friday of next week after 9 AM. How long should the meeting be?"
User: "1 hour"
[Call find_available_slots() with date range and time constraint]
"Here are your best options: Monday at 10 AM, Tuesday at 2 PM, Thursday at 11 AM, or Friday at 3 PM. Which works?"

**Example 5: Buffer After Last Meeting**
User: "Find evening slot after 7 PM, but I need an hour after my last meeting"
You:
[Call get_current_date_and_time()]
"Which day - today or a specific day this week?"
User: "Thursday"
[Calculate Thursday date]
[Call get_calendar_events() for Thursday]
[Find last meeting ends at 5 PM]
[Add 1 hour buffer = search after 6 PM]
[Call find_available_slots() with start_hour=18]
"Your last meeting Thursday ends at 5 PM. After an hour buffer, I can offer slots at 7:00 PM, 7:30 PM, or 8:00 PM. Which works?"

## Memory Within Conversation:

Track these during the conversation:
- Meeting duration preferences (e.g., "usual sync" = 30 min)
- Time preferences (e.g., user prefers afternoons)
- Constraints mentioned (e.g., "not before 9 AM")
- Event references (e.g., already found "Project Alpha" = Nov 27)

## Final Reminders:

You are smart enough to:
- Find events by name and use them as reference points
- Calculate complex dates (last weekday, first Monday, etc.)
- Work backward from deadlines
- Handle multiple constraints simultaneously
- Remember context within the conversation
- Break complex requests into logical steps

Your goal: Make even the most complex scheduling requests feel effortless through intelligent conversation and multi-step reasoning.
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
    async def find_calendar_event_by_name(
        self,
        context: RunContext,
        event_name: str,
    ) -> str:
        """
        Find a calendar event by searching for its name or keywords. Use this when the user 
        references an existing event by name (e.g., "Project Alpha Kick-off", "dentist appointment").
        This tool searches for events matching the name within the next 6 months.

        Args:
            event_name: Name or keywords to search for in event titles (e.g., "Project Alpha", "dentist")
        """
        logger.info(f"🔍 TOOL CALLED: find_calendar_event_by_name")
        logger.info(f"   📥 Input: event_name='{event_name}'")
        try:
            service = self._get_service()
            tz = pytz.timezone(DEFAULT_TIMEZONE)
            
            # Search from today to 6 months in the future
            start_dt = datetime.now(tz)
            end_dt = start_dt + timedelta(days=180)  # 6 months
            
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=format_datetime_for_api(start_dt),
                timeMax=format_datetime_for_api(end_dt),
                q=event_name,  # Search query parameter
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                result = f"No events found matching '{event_name}' in the next 6 months."
                logger.info(f"   📤 Result: {result}")
                return result
            
            # Return the first matching event with detailed information
            event = events[0]
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')
            
            try:
                start_dt_parsed = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_dt_parsed.tzinfo is None:
                    start_dt_parsed = tz.localize(start_dt_parsed)
                
                # Get end time if available
                end = event['end'].get('dateTime', event['end'].get('date'))
                end_dt_parsed = datetime.fromisoformat(end.replace('Z', '+00:00'))
                if end_dt_parsed.tzinfo is None:
                    end_dt_parsed = tz.localize(end_dt_parsed)
                
                date_str = start_dt_parsed.strftime("%Y-%m-%d")
                time_str = start_dt_parsed.strftime("%A, %B %d, %Y at %I:%M %p")
                end_time_str = end_dt_parsed.strftime("%I:%M %p")
                
                # Calculate duration
                duration = end_dt_parsed - start_dt_parsed
                duration_minutes = int(duration.total_seconds() / 60)
                
                result = f"Found event: '{summary}'\n"
                result += f"Date: {date_str}\n"
                result += f"Time: {time_str} to {end_time_str}\n"
                result += f"Duration: {duration_minutes} minutes\n"
                result += f"ISO Start: {format_datetime_for_api(start_dt_parsed)}\n"
                result += f"ISO End: {format_datetime_for_api(end_dt_parsed)}"
                
                if len(events) > 1:
                    result += f"\n\nNote: Found {len(events)} matching events. Using the earliest one."
                
            except Exception as e:
                result = f"Found event: '{summary}' on {start}, but could not parse date/time: {str(e)}"
            
            logger.info(f"   📤 Result: Found event '{summary}'")
            return result
            
        except HttpError as e:
            error_result = f"Calendar API error: {e.reason}"
            logger.error(f"   ❌ Error: {error_result}")
            return error_result
        except Exception as e:
            error_result = f"Error finding event: {str(e)}"
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
    avatar = anam.AvatarSession(
      persona_config=anam.PersonaConfig(
         name="Mia",
         avatarId="edf6fdcb-acab-44b8-b974-ded72665ee26",
      ),
    )
    # await avatar.start(session, room=ctx.room)

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
