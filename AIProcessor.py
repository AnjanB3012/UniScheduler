import base64
import os
import json
import time
import datetime
from google import genai
from google.genai import types

class AIProcessor:
    def __init__(self, ai_config=None):
        if ai_config is None:
            raise ValueError("AI config is required. Please provide a valid configuration with API keys.")
        
        self.ai_config = ai_config
        self.current_key_index = 0
        self.current_api = self.ai_config["api_keys"][self.current_key_index]
        self.model = self.ai_config["model"]
        self.client = genai.Client(api_key=self.current_api)

        # Cooldown tracking
        self.last_quota_exhausted = None
        self.cooldown_1_hour_completed = False
        self.cooldown_24_hour_completed = False
        self.quota_error_count = 0
        
        # Debug logging
        self.debug_log_file = "debug_logs.json"
        self.debug_logs = []

    def _log_debug(self, attempt, prompt, response_text, response_dict, error=None):
        """Log debug information for AI responses"""
        debug_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "attempt": attempt,
            "model": self.model,
            "api_key_index": self.current_key_index,
            "prompt": prompt[:500] + "..." if len(prompt) > 500 else prompt,  # Truncate long prompts
            "response_text": response_text,
            "response_dict": response_dict,
            "error": str(error) if error else None,
            "success": error is None
        }
        
        self.debug_logs.append(debug_entry)
        
        # Keep only last 50 entries
        if len(self.debug_logs) > 50:
            self.debug_logs = self.debug_logs[-50:]
        
        # Save to file
        try:
            with open(self.debug_log_file, 'w') as f:
                json.dump(self.debug_logs, f, indent=2)
        except Exception as e:
            print(f"Error saving debug logs: {e}")

    def _switch_to_next_api_key(self):
        """Switch to the next available API key"""
        self.current_key_index = (self.current_key_index + 1) % len(self.ai_config["api_keys"])
        self.current_api = self.ai_config["api_keys"][self.current_key_index]
        self.client = genai.Client(api_key=self.current_api)
        print(f"Switched to API key index {self.current_key_index}")

    def _is_quota_error(self, error_message):
        """Check if the error is a quota/rate limit error"""
        quota_indicators = [
            "quota",
            "rate limit",
            "429",
            "exceeded your current quota",
            "GenerateRequestsPerDayPerProjectPerModel"
        ]
        return any(indicator.lower() in str(error_message).lower() for indicator in quota_indicators)

    def _should_wait_for_cooldown(self):
        """Check if we should wait for cooldown period"""
        if self.last_quota_exhausted is None:
            return False
        
        now = datetime.datetime.now()
        time_since_quota_exhausted = now - self.last_quota_exhausted
        
        # First cooldown: 1 hour
        if not self.cooldown_1_hour_completed:
            if time_since_quota_exhausted.total_seconds() < 3600:  # 1 hour
                remaining = 3600 - time_since_quota_exhausted.total_seconds()
                print(f"Waiting for 1-hour cooldown. Remaining: {remaining/60:.1f} minutes")
                return True
            else:
                self.cooldown_1_hour_completed = True
                print("1-hour cooldown completed")
                return False
        
        # Second cooldown: 24 hours (only if we've had quota errors after the first cooldown)
        if self.quota_error_count > 1 and not self.cooldown_24_hour_completed:
            if time_since_quota_exhausted.total_seconds() < 86400:  # 24 hours
                remaining = 86400 - time_since_quota_exhausted.total_seconds()
                print(f"Waiting for 24-hour cooldown. Remaining: {remaining/3600:.1f} hours")
                return True
            else:
                self.cooldown_24_hour_completed = True
                print("24-hour cooldown completed")
                return False
        
        return False

    def _handle_quota_error(self, error_message):
        """Handle quota errors with appropriate cooldown logic"""
        self.quota_error_count += 1
        self.last_quota_exhausted = datetime.datetime.now()
        
        print(f"Quota error detected (attempt {self.quota_error_count}): {error_message}")
        
        # Reset cooldown flags if this is a new quota error cycle
        if self.quota_error_count == 1:
            self.cooldown_1_hour_completed = False
            self.cooldown_24_hour_completed = False

    def _has_schedule_overlaps(self, response_dict):
        """Check if the generated schedule has time overlaps"""
        try:
            classes_by_day = {}
            for cls in response_dict["classes"]:
                try:
                    days = list(cls["days"])
                    time_str = cls["time"]
                    
                    # Normalize time format
                    time_str = time_str.replace('-', ' - ')
                    time_str = ' '.join(time_str.split())
                    time_parts = time_str.split(" - ")
                    
                    if len(time_parts) != 2:
                        print(f"Invalid time format: {cls['time']}")
                        continue

                    start_time, end_time = time_parts
                    start_minutes = self._time_to_minutes(start_time)
                    end_minutes = self._time_to_minutes(end_time)

                    for day in days:
                        if day not in classes_by_day:
                            classes_by_day[day] = []
                        classes_by_day[day].append({
                            "start": start_minutes,
                            "end": end_minutes,
                            "crn": cls["crn"],
                            "course": cls["courseNumber"]
                        })
                except Exception as e:
                    print(f"Error processing class {cls['courseNumber']}: {str(e)}")
                    continue

            # Check for overlaps in each day
            for day, classes in classes_by_day.items():
                classes.sort(key=lambda x: x["start"])
                
                for i in range(len(classes) - 1):
                    current = classes[i]
                    next_class = classes[i + 1]
                    
                    # Check for overlap or insufficient gap
                    if current["end"] > next_class["start"] or \
                       (next_class["start"] - current["end"]) < 5:  # 5-minute gap requirement
                        print(f"Overlap found on {day} between {current['course']} and {next_class['course']}")
                        return True

            return False
            
        except Exception as e:
            print(f"Error checking for overlaps: {e}")
            return True  # Assume overlap if we can't check

    def process_ai_request(self, prompt, courses=None):
        """
        Process AI request using the client format from test.py and app[old].py
        Returns structured JSON response with class schedule data
        """
        ai_start_time = time.time()
        
        # Check if we should wait for cooldown
        if self._should_wait_for_cooldown():
            return {"classes": [], "error": "COOLDOWN_ACTIVE", "message": "API keys are in cooldown period"}
        
        # Fallback models if the primary one fails
        fallback_models = ["gemini-2.5-pro", "gemini-2.5-flash-lite"]
        current_model_index = 0
        max_retries = 20
        retry_count = 0
        api_key_attempts = 0
        max_api_key_attempts = len(self.ai_config["api_keys"])
        
        # Create the structured output schema matching app[old].py
        schema = {
            "type": "object",
            "properties": {
                "classes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "crn": {"type": "string"},
                            "courseNumber": {"type": "string"},
                            "courseName": {"type": "string"},
                            "professorName": {"type": "string"},
                            "days": {"type": "string"},
                            "time": {"type": "string"},
                            "location": {"type": "string"},
                            "isLab": {"type": "boolean"}
                        },
                        "required": ["crn", "courseNumber", "courseName", "professorName", "days", "time", "location"]
                    }
                }
            },
            "required": ["classes"]
        }
        
        while retry_count < max_retries and api_key_attempts < max_api_key_attempts:
            print(f"AI Schedule Generation - Attempt {retry_count + 1}/{max_retries} (API Key: {api_key_attempts + 1}/{max_api_key_attempts})")
            
            try:
                # Use the client format from test.py
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=prompt),
                        ],
                    ),
                ]
                
                generate_content_config = types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=-1,
                    ),
                    response_mime_type="application/json",
                    response_schema=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=["classes"],
                        properties={
                            "classes": genai.types.Schema(
                                type=genai.types.Type.ARRAY,
                                items=genai.types.Schema(
                                    type=genai.types.Type.OBJECT,
                                    required=["crn", "courseNumber", "courseName", "professorName", "days", "time", "location"],
                                    properties={
                                        "crn": genai.types.Schema(type=genai.types.Type.STRING),
                                        "courseNumber": genai.types.Schema(type=genai.types.Type.STRING),
                                        "courseName": genai.types.Schema(type=genai.types.Type.STRING),
                                        "professorName": genai.types.Schema(type=genai.types.Type.STRING),
                                        "days": genai.types.Schema(type=genai.types.Type.STRING),
                                        "time": genai.types.Schema(type=genai.types.Type.STRING),
                                        "location": genai.types.Schema(type=genai.types.Type.STRING),
                                        "isLab": genai.types.Schema(type=genai.types.Type.BOOLEAN)
                                    },
                                ),
                            ),
                        },
                    ),
                    system_instruction=[
                        types.Part.from_text(text="""You are a virtual timetable generator.
!!! IMPORTANT !!!
IF ANY COURSE IS CLASHING WITH ANOTHER COURSE, RETURN NOTHING AT ALL UNTIL THE CLASH IS RESOLVED.

🚨 CRITICAL FORMAT REQUIREMENT:
- Course codes MUST be in the format: DEPARTMENTNUMBER (e.g., "ENGL1106", "CS2114")
- DO NOT use hyphens in course codes (e.g., do NOT use "ENGL-1106" or "CS-2114")
                                 
Input:
- A list of required courses the user must take.
- A list of available sections. Each section includes:
    - CRN (Course Reference Number)
    - Course Code
    - Course Name
    - Instructor Name
    - Schedule Type (Lecture, Lab, etc.)
    - Days (e.g., M, T, W, R, F)
    - Start Time and End Time
    - Location

Special Handling for "* Additional Times *":
- Some sections may include rows labeled "* Additional Times *".
- These rows contain the actual **meeting days, time, and location**, but are missing other fields.
- If an entry is marked as "* Additional Times *", fetch the full course details (Course Code, Name, Instructor, etc.) from the matching CRN's main section.
- Treat these as valid class time blocks and combine them with the main row to form the complete schedule.

🚨 SUPER STRICT RULES (MUST NEVER BE BROKEN):

1. You must select **exactly one section (CRN)** per required course.
2. A selected CRN may have multiple time blocks (e.g., lecture + lab, or MWF) — you must include **all** of them.
3. **No two classes can overlap at all — even by a single minute.**  
   - Example: A class ending at 10:00AM and another starting at 10:00AM is a conflict.
4. There must be **at least a 5-minute gap** between any two consecutive classes.
5. If even a single course causes conflict (due to overlap or missing buffer), you must return **nothing at all** — no partial schedules.
6. If a CRN includes any "* Additional Time *" entries, those must be treated as part of that CRN. Do not exclude them.
7. You must never include only part of a CRN's time blocks — **include all or exclude all**.
8. For courses with both lecture and lab components:
   - You MUST include both components in the schedule
   - If you cannot fit both components without conflicts, return nothing
   - Do not create a schedule with only lecture or only lab
9. For courses with only lecture or only lab:
   - You MUST include that component
   - If you cannot fit it without conflicts, return nothing
10. **CRITICAL**: You MUST try MANY different combinations of CRNs before giving up
11. **CRITICAL**: For each retry, try completely different CRN selections
12. **CRITICAL**: If one combination fails, immediately try another combination
13. **CRITICAL**: Only return "NO_VALID_SCHEDULE_FOUND" after trying at least 15-20 different combinations
14. If no valid schedule is possible after trying all combinations, return "NO_VALID_SCHEDULE_FOUND"

✨ Preferences (only if all strict rules are satisfied):
- Prefer professors mentioned by the user
- Prefer morning or afternoon classes, if specified
- Prioritize classes with cleaner or fewer blocks

✅ Output Format:
If a valid, fully non-overlapping timetable is possible, return it in this format (one row per time block):

CRN    Course    Course Name    Instructor    Day    Start Time - End Time    Location

- One row per day — if a class meets on M/W/F, generate three separate rows
- Use 12-hour format (e.g., 9:30AM - 10:45AM)
- Do not include headers, comments, or notes — just rows
- Course codes MUST be in the format: DEPARTMENTNUMBER (e.g., "ENGL1106", "CS2114")
- DO NOT use hyphens in course codes

❌ If even one course makes the schedule invalid (due to overlap or timing), return **nothing at all**.

!!! IMPORTANT !!!
BEFORE RETURNING ANY SCHEDULE:
1. Check for any time overlaps between all classes
2. Verify that all required components (lecture/lab) are included
3. Ensure there is at least a 5-minute gap between consecutive classes
4. If any of these checks fail, return nothing and try another combination
5. If no valid combination is found after trying all possibilities, return "NO_VALID_SCHEDULE_FOUND"
"""),
                    ],
                )

                # Generate content using the client
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=generate_content_config,
                )
                
                # Process the response
                response_text = response.text
                
                try:
                    response_dict = json.loads(response_text)
                    
                    # Log debug information
                    self._log_debug(retry_count + 1, prompt, response_text, response_dict)
                    
                    # If we got a valid schedule, check for overlaps and completeness
                    if "classes" in response_dict and response_dict["classes"]:
                        # Check for schedule overlaps first
                        if self._has_schedule_overlaps(response_dict):
                            print("Schedule has overlaps, retrying...")
                            retry_count += 1
                            continue
                        
                        # Validate the schedule if courses are provided
                        if courses:
                            if self._validate_schedule(response_dict, courses):
                                print(f"Valid schedule found after {retry_count + 1} attempts")
                                return response_dict
                            else:
                                print(f"Schedule validation failed, retrying...")
                                retry_count += 1
                                continue
                        else:
                            # If no courses provided for validation, return the response
                            print(f"Valid schedule found after {retry_count + 1} attempts")
                            return response_dict
                    else:
                        print("No classes found in response, retrying...")
                        retry_count += 1
                        continue
                        
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    # Log debug information for JSON decode error
                    self._log_debug(retry_count + 1, prompt, response_text, None, e)
                    retry_count += 1
                    continue
                    
            except Exception as e:
                error_message = str(e)
                print(f"Error in AI request: {error_message}")
                
                # Log debug information for general errors
                self._log_debug(retry_count + 1, prompt, "", None, e)
                
                # Check if this is a quota error
                if self._is_quota_error(error_message):
                    self._handle_quota_error(error_message)
                    
                    # Switch to next API key
                    if api_key_attempts < max_api_key_attempts - 1:
                        self._switch_to_next_api_key()
                        api_key_attempts += 1
                        retry_count += 1
                        continue
                    else:
                        # All API keys exhausted, wait for cooldown
                        print("All API keys exhausted, entering cooldown period")
                        return {"classes": [], "error": "QUOTA_EXHAUSTED", "message": "All API keys have exceeded quota limits"}
                else:
                    # Non-quota error, try fallback model
                    retry_count += 1
                    
                    # Try fallback model if available
                    if current_model_index < len(fallback_models) - 1:
                        current_model_index += 1
                        self.model = fallback_models[current_model_index]
                        print(f"Switching to fallback model: {self.model}")
                    continue
        
        # If we've exhausted all retries
        print("No valid schedule found after all attempts")
        return {"classes": [], "error": "NO_VALID_SCHEDULE_FOUND"}
    
    def _validate_schedule(self, response_dict, courses):
        """
        Validate the generated schedule for completeness and conflicts
        """
        try:
            # Check if all requested courses are included
            requested_courses = set()
            for course in courses:
                requested_courses.add(course['department'] + course['number'])

            scheduled_courses = set()
            for cls in response_dict["classes"]:
                # Normalize course number by removing hyphens
                course_number = cls["courseNumber"].replace("-", "")
                scheduled_courses.add(course_number)

            if requested_courses != scheduled_courses:
                print(f"Missing courses in schedule. Requested: {requested_courses}, Scheduled: {scheduled_courses}")
                return False

            # Check for time overlaps
            classes_by_day = {}
            for cls in response_dict["classes"]:
                try:
                    days = list(cls["days"])
                    time_str = cls["time"]
                    
                    # Normalize time format
                    time_str = time_str.replace('-', ' - ')
                    time_str = ' '.join(time_str.split())
                    time_parts = time_str.split(" - ")
                    
                    if len(time_parts) != 2:
                        print(f"Invalid time format: {cls['time']}")
                        continue

                    start_time, end_time = time_parts
                    start_minutes = self._time_to_minutes(start_time)
                    end_minutes = self._time_to_minutes(end_time)

                    for day in days:
                        if day not in classes_by_day:
                            classes_by_day[day] = []
                        classes_by_day[day].append({
                            "start": start_minutes,
                            "end": end_minutes,
                            "crn": cls["crn"],
                            "course": cls["courseNumber"]
                        })
                except Exception as e:
                    print(f"Error processing class {cls['courseNumber']}: {str(e)}")
                    continue

            # Check for overlaps in each day
            for day, classes in classes_by_day.items():
                classes.sort(key=lambda x: x["start"])
                
                for i in range(len(classes) - 1):
                    current = classes[i]
                    next_class = classes[i + 1]
                    
                    # Check for overlap or insufficient gap
                    if current["end"] > next_class["start"] or \
                       (next_class["start"] - current["end"]) < 5:  # 5-minute gap requirement
                        print(f"Overlap found on {day} between {current['course']} and {next_class['course']}")
                        return False

            return True
            
        except Exception as e:
            print(f"Error validating schedule: {e}")
            return False
    
    def _time_to_minutes(self, time_str):
        """Convert time string to minutes for comparison"""
        try:
            # Handle different time formats
            if ' ' in time_str:
                time, period = time_str.split()
            else:
                # If no space, find where the time ends and period begins
                for i, char in enumerate(time_str):
                    if char.isalpha():
                        time = time_str[:i]
                        period = time_str[i:]
                        break
                else:
                    # If no period found, assume 24-hour format
                    time = time_str
                    period = ''

            # Parse hours and minutes
            if ':' in time:
                hours, minutes = map(int, time.split(':'))
            else:
                hours = int(time)
                minutes = 0

            # Convert to 24-hour format
            if period:
                if period.upper() == 'PM' and hours != 12:
                    hours += 12
                elif period.upper() == 'AM' and hours == 12:
                    hours = 0

            return hours * 60 + minutes
        except Exception as e:
            print(f"Error parsing time {time_str}: {e}")
            return 0