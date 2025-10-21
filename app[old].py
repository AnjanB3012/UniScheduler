import time
from collections import defaultdict, deque
import heapq
import itertools
from datetime import datetime, timezone
import ast
from uuid import uuid4
import random
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import pandas as pd
import google.generativeai as genai
import json
from dotenv import load_dotenv
import os
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
import io
import matplotlib
matplotlib.use('Agg')


app = Flask(__name__)
CORS(app)
load_dotenv()

# json_doc_loc = "invite_codes.json"

log_file = "server_logs.json"
if not os.path.exists(log_file):
    with open(log_file, 'w') as f:
        json.dump([], f)

# Token total file for running total
TOKEN_TOTAL_FILE = "token_total.json"
if not os.path.exists(TOKEN_TOTAL_FILE):
    with open(TOKEN_TOTAL_FILE, 'w') as f:
        json.dump({"total_tokens": 0}, f)

# Cost tracking CSV file
COST_TRACKING_FILE = "cost_tracking.csv"
COMPANY_COST_FILE = "company_total_cost.txt"

# Initialize cost tracking CSV if it doesn't exist
if not os.path.exists(COST_TRACKING_FILE):
    cost_columns = [
        'timestamp', 'request_id', 'user_email', 'optimization_method',
        'total_time_seconds', 'courses_processed', 'total_sections_analyzed',
        'total_attempts', 'models_used', 'total_tokens', 'total_cost',
        'success_status', 'schedule_classes_count'
    ]
    df = pd.DataFrame(columns=cost_columns)
    df.to_csv(COST_TRACKING_FILE, index=False)

# Initialize company cost summary text file if it doesn't exist
if not os.path.exists(COMPANY_COST_FILE):
    with open(COMPANY_COST_FILE, 'w') as f:
        f.write("COMPANY TOTAL COST SUMMARY\n")
        f.write("=" * 50 + "\n")
        f.write("Last Updated: Never\n")
        f.write("Total Cost: $0.0000\n")
        f.write("Total Requests: 0\n")
        f.write("Total Tokens: 0\n")
        f.write("Success Rate: 0.0%\n")
        f.write("=" * 50 + "\n")


def save_log_entry(timestamp=datetime.now(timezone.utc), message=""):
    log_entry = {
        timestamp.isoformat(): message
    }
    with open(log_file, 'r+') as f:
        logs = json.load(f)
        logs.append(log_entry)
        f.seek(0)
        json.dump(logs, f, indent=4)


def load_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


def save_json_file(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)


def log_cost_data(request_data, performance_metrics, cost_info, success_status):
    """Log cost data to CSV file"""
    try:
        # Generate unique request ID
        request_id = f"req_{int(time.time())}_{random.randint(1000, 9999)}"

        # Extract data
        timestamp = datetime.now().isoformat()
        user_email = request_data.get('email', 'anonymous')
        optimization_method = performance_metrics.get(
            'optimization_method', 'unknown')
        total_time = performance_metrics.get('time_taken_seconds', 0)
        courses_processed = performance_metrics.get('courses_processed', 0)
        total_sections = performance_metrics.get('total_sections_analyzed', 0)
        total_attempts = performance_metrics.get('total_attempts', 0)
        models_used = ','.join(performance_metrics.get('models_used', []))
        total_tokens = performance_metrics.get('total_tokens', 0)
        total_cost = cost_info.get(
            'total_cost_all_models', cost_info.get('total_cost', 0))
        schedule_classes_count = len(
            request_data.get('schedule', {}).get('classes', []))

        # Create row data
        row_data = {
            'timestamp': timestamp,
            'request_id': request_id,
            'user_email': user_email,
            'optimization_method': optimization_method,
            'total_time_seconds': total_time,
            'courses_processed': courses_processed,
            'total_sections_analyzed': total_sections,
            'total_attempts': total_attempts,
            'models_used': models_used,
            'total_tokens': total_tokens,
            'total_cost': total_cost,
            'success_status': success_status,
            'schedule_classes_count': schedule_classes_count
        }

        # Append to CSV
        df = pd.read_csv(COST_TRACKING_FILE)
        df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)
        df.to_csv(COST_TRACKING_FILE, index=False)

        # Update company cost summary
        update_company_cost_summary()

        return request_id

    except Exception as e:
        print(f"Error logging cost data: {e}")
        return None


def update_company_cost_summary():
    """Update company total cost summary"""
    try:
        # Read cost tracking data
        df = pd.read_csv(COST_TRACKING_FILE)

        if len(df) > 0:
            # Calculate overall company metrics
            total_requests = len(df)
            total_cost = df['total_cost'].sum()
            total_tokens = df['total_tokens'].sum()
            successful_requests = len(df[df['success_status'] == 'success'])
            failed_requests = len(df[df['success_status'] == 'failed'])
            success_rate = (successful_requests / total_requests) * \
                100 if total_requests > 0 else 0
            avg_cost_per_request = total_cost / total_requests if total_requests > 0 else 0
            avg_tokens_per_request = total_tokens / \
                total_requests if total_requests > 0 else 0

            # Get today's data for today's summary
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            today = datetime.now().date()
            today_data = df[df['date'] == today]

            today_requests = len(today_data)
            today_cost = today_data['total_cost'].sum() if len(
                today_data) > 0 else 0
            today_tokens = today_data['total_tokens'].sum() if len(
                today_data) > 0 else 0

            # Update company cost summary text file
            with open(COMPANY_COST_FILE, 'w') as f:
                f.write("COMPANY TOTAL COST SUMMARY\n")
                f.write("=" * 60 + "\n")
                f.write(
                    f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Cost: ${total_cost:.4f}\n")
                f.write(f"Total Requests: {total_requests:,}\n")
                f.write(f"Total Tokens: {total_tokens:,}\n")
                f.write(f"Success Rate: {success_rate:.1f}%\n")
                f.write(f"Avg Cost/Request: ${avg_cost_per_request:.4f}\n")
                f.write(f"Avg Tokens/Request: {avg_tokens_per_request:,.0f}\n")
                f.write("\n")
                f.write("TODAY'S SUMMARY:\n")
                f.write("-" * 30 + "\n")
                f.write(f"Today's Requests: {today_requests}\n")
                f.write(f"Today's Cost: ${today_cost:.4f}\n")
                f.write(f"Today's Tokens: {today_tokens:,}\n")
                f.write("=" * 60 + "\n")

            # Print company cost summary
            print("\n" + "="*80)
            print("🏢 COMPANY COST SUMMARY")
            print("="*80)
            print(
                f"📅 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"💰 Total Cost: ${total_cost:.4f}")
            print(f"📊 Total Requests: {total_requests:,}")
            print(f"📝 Total Tokens: {total_tokens:,}")
            print(f"📈 Success Rate: {success_rate:.1f}%")
            print(f"💵 Avg Cost/Request: ${avg_cost_per_request:.4f}")
            print(f"📊 Avg Tokens/Request: {avg_tokens_per_request:,.0f}")
            print(f"\n📅 TODAY'S SUMMARY:")
            print(f"   • Requests: {today_requests}")
            print(f"   • Cost: ${today_cost:.4f}")
            print(f"   • Tokens: {today_tokens:,}")
            print("="*80)

    except Exception as e:
        print(f"Error updating company cost summary: {e}")


def get_company_cost_summary():
    """Get comprehensive company cost summary"""
    try:
        # Read cost tracking data
        cost_df = pd.read_csv(COST_TRACKING_FILE)

        if len(cost_df) == 0:
            return {
                'total_cost': 0,
                'total_requests': 0,
                'total_tokens': 0,
                'avg_cost_per_request': 0,
                'success_rate': 0
            }

        # Calculate overall metrics
        total_cost = cost_df['total_cost'].sum()
        total_requests = len(cost_df)
        total_tokens = cost_df['total_tokens'].sum()
        successful_requests = len(
            cost_df[cost_df['success_status'] == 'success'])
        avg_cost_per_request = total_cost / total_requests if total_requests > 0 else 0
        success_rate = (successful_requests / total_requests) * \
            100 if total_requests > 0 else 0

        # Get today's data
        cost_df['date'] = pd.to_datetime(cost_df['timestamp']).dt.date
        today = datetime.now().date()
        today_data = cost_df[cost_df['date'] == today]

        today_requests = len(today_data)
        today_cost = today_data['total_cost'].sum() if len(
            today_data) > 0 else 0
        today_tokens = today_data['total_tokens'].sum() if len(
            today_data) > 0 else 0

        return {
            'total_cost': round(total_cost, 4),
            'total_requests': total_requests,
            'total_tokens': total_tokens,
            'avg_cost_per_request': round(avg_cost_per_request, 4),
            'success_rate': round(success_rate, 1),
            'today_requests': today_requests,
            'today_cost': round(today_cost, 4),
            'today_tokens': today_tokens,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        print(f"Error getting company cost summary: {e}")
        return None


# def verify_invite_code(code: str) -> bool:
#     data = load_json_file(json_doc_loc)
#     if code in data:
#         return True
#     else:
#         return False


# def add_invite_code(username: str, password: str, name: str, email: str) -> str:
#     credentials_str = os.getenv("AUTHORIZED_USERS")
#     auth_users_credentials = ast.literal_eval(credentials_str)

#     if username not in auth_users_credentials or password != auth_users_credentials[username]:
#         return "0"

#     data = load_json_file(json_doc_loc)

#     # Check if email already exists
#     for code, info in data.items():
#         if info.get("email") == email:
#             return code  # Return existing code if email matches

#     # Otherwise, create a new code
#     code = str(uuid4())
#     while code in data:
#         code = str(uuid4())

#     data[code] = {"name": name, "email": email}
#     save_json_file(json_doc_loc, data)
#     save_log_entry(message=f"New invite code generated for {name} ({email}) with code {code}")
#     return code


# def remove_invite_code(code: str, username: str, password: str) -> bool:
#     data = load_json_file(json_doc_loc)
#     credentials_str = os.getenv("AUTHORIZED_USERS")
#     auth_users_credentials = ast.literal_eval(credentials_str)
#     if username not in auth_users_credentials or password != auth_users_credentials[username]:
#         return False
#     if code in data:
#         del data[code]
#         save_json_file(json_doc_loc, data)
#         return True
#     else:
#         return False


def generate_schedule_pdf(schedule_data, inputColors):
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []
        elements.append(Paragraph("Course Schedule", styles["Title"]))
        elements.append(Spacer(1, 12))

        table_data = [["Course", "Number", "CRN",
                       "Day", "Time", "Location", "Professor"]]
        for cls in schedule_data:
            table_data.append([
                cls["courseName"], cls["courseNumber"], cls["crn"],
                cls["days"], cls["time"], cls["location"], cls["professorName"]
            ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

        create_calendar_plot(schedule_data, inputColors, "calendar_plot.png")
        from reportlab.platypus import Image
        elements.append(Image("calendar_plot.png", width=500, height=300))

        doc.build(elements)
        buffer.seek(0)
        os.remove("calendar_plot.png")
        save_log_entry(message="PDF generated successfully")
        return buffer
    except Exception as e:
        save_log_entry(message=f"Error generating PDF: {str(e)}")


def create_calendar_plot(classes, inputColors, filename):
    days_map = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 5)
    ax.set_ylim(7, 21)  # 7 AM to 9 PM
    ax.set_xticks(range(5))
    for i, day in enumerate(['Mon', 'Tue', 'Wed', 'Thu', 'Fri']):
        ax.text(i + 0.5, 6.9, day, ha='center',
                va='bottom', fontsize=10, fontweight='bold')
    ax.set_yticks(range(7, 22))
    ax.set_yticklabels([f"{h}:00" for h in range(7, 22)])
    ax.grid(True)
    ax.invert_yaxis()

    # Assign a unique color per courseNumber
    color_choices = list(mcolors.TABLEAU_COLORS.values())
    random.shuffle(color_choices)
    course_colors = {}
    color_index = 0

    for cls in classes:
        try:
            course_number = cls["courseNumber"]
            if course_number not in course_colors:
                course_colors[course_number] = mcolors.to_rgb(
                    inputColors[cls['crn']])
                color_index += 1

            color = course_colors[course_number]

            start_time, end_time = cls["time"].split(" - ")
            start_hour = convert_to_24hr(start_time)
            end_hour = convert_to_24hr(end_time)

            # Only show classes between 7AM and 9PM
            if start_hour < 7 or end_hour > 21:
                continue

            for day in cls["days"]:
                day_index = days_map.get(day)
                if day_index is not None:
                    ax.add_patch(plt.Rectangle(
                        (day_index, start_hour),
                        1, end_hour - start_hour,
                        color=color, alpha=1.0, zorder=2
                    ))
                    ax.text(
                        day_index + 0.5,
                        start_hour + (end_hour - start_hour) / 2,
                        f"{cls['courseNumber']}\n{cls['location']}",
                        ha='center',
                        va='center',
                        fontsize=8,
                        wrap=True
                    )
        except Exception as e:
            save_log_entry(message=f"Error plotting class {cls}: {e}")

    plt.title("Weekly Calendar View", pad=20)
    plt.tight_layout()
    plt.subplots_adjust(top=0.90)
    plt.savefig(filename)
    plt.close()


def convert_to_24hr(time_str):
    return datetime.strptime(time_str, "%I:%M%p").hour + datetime.strptime(time_str, "%I:%M%p").minute / 60


def get_total_tokens():
    with open(TOKEN_TOTAL_FILE, 'r') as f:
        data = json.load(f)
    return data.get("total_tokens", 0)


def update_total_tokens(tokens):
    total = get_total_tokens() + tokens
    with open(TOKEN_TOTAL_FILE, 'w') as f:
        json.dump({"total_tokens": total}, f)
    return total


def ai_maker(prompt, courses):
    ai_start_time = time.time()

    # Configure the API key
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    # Use the model from environment variable
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

    # Fallback models if the primary one fails
    fallback_models = ["gemini-2.5-pro", "gemini-2.5-flash-lite"]
    current_model_index = 0

    max_retries = 20  # Increased retries for complex course combinations
    retry_count = 0
    total_tokens = 0
    total_input_tokens = 0
    total_output_tokens = 0

    # Track cumulative cost across all models and attempts
    cumulative_cost = 0.0
    model_usage = []  # Track usage per model

    while retry_count < max_retries:
        print(
            f"AI Schedule Generation - Attempt {retry_count + 1}/{max_retries}")
        # Create the structured output schema
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

        try:
            # Create the model
            model = genai.GenerativeModel(model_name)

            # Generate content with structured output
            response = model.generate_content(
                f"""You are a virtual timetable generator.
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

{prompt}""",
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=schema
                )
            )

            responseText = response.text

            # Track input and output tokens separately for pricing
            if response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count if hasattr(
                    response.usage_metadata, 'prompt_token_count') else 0
                output_tokens = response.usage_metadata.candidates_token_count if hasattr(
                    response.usage_metadata, 'candidates_token_count') else 0
                total_tokens = response.usage_metadata.total_token_count

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens

                # Calculate cost for this attempt
                attempt_cost_info = calculate_gemini_cost(
                    input_tokens, output_tokens, model_name)
                cumulative_cost += attempt_cost_info['total_cost']

                # Track model usage
                model_usage.append({
                    'model': model_name,
                    'attempt': retry_count + 1,
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'cost': attempt_cost_info['total_cost'],
                    'success': False  # Will be updated if successful
                })

                print(
                    f"Token usage: {input_tokens} input + {output_tokens} output = {total_tokens} total tokens")
                print(
                    f"Attempt cost: ${attempt_cost_info['total_cost']} | Cumulative cost: ${cumulative_cost:.4f}")
            else:
                total_tokens = 0
                input_tokens = 0
                output_tokens = 0
                print(
                    f"Token usage: {input_tokens} input + {output_tokens} output = {total_tokens} total tokens")

            try:
                response_dict = json.loads(responseText)

                # If we got a valid schedule, check for overlaps and completeness
                if "classes" in response_dict and response_dict["classes"]:
                    # First, check if all requested courses are included
                    requested_courses = set()
                    for course in courses:
                        requested_courses.add(
                            course['department'] + course['number'])

                    scheduled_courses = set()
                    for cls in response_dict["classes"]:
                        # Normalize course number by removing hyphens
                        course_number = cls["courseNumber"].replace("-", "")
                        scheduled_courses.add(course_number)

                    if requested_courses != scheduled_courses:
                        print(
                            f"Missing courses in schedule. Requested: {requested_courses}, Scheduled: {scheduled_courses}")
                        retry_count += 1
                        continue

                    # Normalize time format to ensure consistent spacing
                    def normalize_time_format(time_str):
                        """Ensure consistent spacing around dashes in time strings"""
                        # Replace dash without spaces with dash with spaces
                        time_str = time_str.replace('-', ' - ')
                        # Clean up any double spaces
                        time_str = ' '.join(time_str.split())
                        return time_str

                    # Convert time strings to minutes for easier comparison
                    def time_to_minutes(time_str):
                        # Normalize the time format first
                        time_str = normalize_time_format(time_str)

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

                    # Group classes by day
                    classes_by_day = {}
                    for cls in response_dict["classes"]:
                        try:
                            days = list(cls["days"])
                            # Log the time string for debugging
                            print(f"Processing time string: {cls['time']}")

                            # Normalize and split time string
                            normalized_time = normalize_time_format(
                                cls["time"])
                            time_parts = normalized_time.split(" - ")
                            if len(time_parts) != 2:
                                print(
                                    f"Invalid time format: {cls['time']} (normalized: {normalized_time})")
                                continue

                            start_time, end_time = time_parts

                            for day in days:
                                if day not in classes_by_day:
                                    classes_by_day[day] = []
                                classes_by_day[day].append({
                                    "start": time_to_minutes(start_time),
                                    "end": time_to_minutes(end_time),
                                    "crn": cls["crn"],
                                    "course": cls["courseNumber"]
                                })
                        except Exception as e:
                            save_log_entry(
                                message=f"Error processing class {cls['courseNumber']}: {str(e)}")
                            continue

                    # Check for overlaps in each day
                    has_overlap = False
                    for day, classes in classes_by_day.items():
                        # Sort classes by start time
                        classes.sort(key=lambda x: x["start"])

                        # Check each consecutive pair
                        for i in range(len(classes) - 1):
                            current = classes[i]
                            next_class = classes[i + 1]

                            # Check for overlap or insufficient gap
                            if current["end"] > next_class["start"] or \
                               (next_class["start"] - current["end"]) < 5:  # 5-minute gap requirement
                                has_overlap = True
                                print(
                                    f"Overlap found on {day} between {current['course']} and {next_class['course']}")
                                break

                        if has_overlap:
                            break

                    if not has_overlap:
                        # Normalize time formats in the response before returning
                        for cls in response_dict["classes"]:
                            if "time" in cls:
                                cls["time"] = normalize_time_format(
                                    cls["time"])
                        ai_end_time = time.time()
                        ai_total_time = ai_end_time - ai_start_time

                        # Mark the successful attempt
                        if model_usage:
                            model_usage[-1]['success'] = True

                        # Create comprehensive cost info with detailed breakdowns
                        comprehensive_cost_info = {
                            'input_cost': sum(usage['cost'] for usage in model_usage if usage['model'] == model_name),
                            'output_cost': 0,  # Will be calculated from total
                            'total_cost': cumulative_cost,
                            'input_tokens': total_input_tokens,
                            'output_tokens': total_output_tokens,
                            'model_used': model_name,
                            'cumulative_cost': cumulative_cost,
                            'total_attempts': len(model_usage),
                            'models_used': list(set(usage['model'] for usage in model_usage)),
                            'model_usage_breakdown': model_usage,
                            'model_cost_breakdown': _calculate_model_breakdown(model_usage),
                            'total_cost_all_models': cumulative_cost
                        }

                        print(
                            f"AI generation successful after {ai_total_time:.2f} seconds and {total_tokens} tokens")
                        print(
                            f"Total cost: ${cumulative_cost:.4f} across {len(model_usage)} attempts using models: {comprehensive_cost_info['models_used']}")

                        # Print detailed model breakdown
                        model_breakdown = comprehensive_cost_info['model_cost_breakdown']
                        print("\n" + "="*60)
                        print("DETAILED MODEL BREAKDOWN:")
                        print("="*60)

                        for model, stats in model_breakdown.items():
                            print(f"\n📊 {model.upper()}:")
                            print(
                                f"   • Total Attempts: {stats['total_attempts']}")
                            print(
                                f"   • Successful Attempts: {stats['successful_attempts']}")
                            print(
                                f"   • Success Rate: {stats['success_rate']}%")
                            print(
                                f"   • Total Tokens: {stats['total_tokens']:,}")
                            print(
                                f"   • Total Cost: ${stats['total_cost']:.4f}")
                            print(
                                f"   • Avg Tokens/Attempt: {stats['avg_tokens_per_attempt']:,}")
                            print(
                                f"   • Avg Cost/Attempt: ${stats['avg_cost_per_attempt']:.4f}")

                        print(
                            f"\n💰 TOTAL COST ACROSS ALL MODELS: ${cumulative_cost:.4f}")
                        print("="*60)

                        return response_dict, total_tokens, comprehensive_cost_info
                    else:
                        print("Overlap detected, retrying...")
                        retry_count += 1
                        continue
                else:
                    return response_dict, total_tokens

            except json.JSONDecodeError:
                save_log_entry(message="Invalid JSON response, retrying...")
                retry_count += 1
                continue
            except Exception as e:
                save_log_entry(message=f"Error processing response: {str(e)}")
                retry_count += 1
                continue

        except Exception as e:
            save_log_entry(message=f"Error calling Gemini API: {str(e)}")
            retry_count += 1

            # Try switching to a different model if we've had multiple failures
            if retry_count > 10 and current_model_index < len(fallback_models):
                current_model_index += 1
                model_name = fallback_models[current_model_index - 1]
                print(f"Switching to fallback model: {model_name}")
                retry_count = 0  # Reset retry count for new model

            continue

    # If we've exhausted all retries
    ai_end_time = time.time()
    ai_total_time = ai_end_time - ai_start_time

    # Create comprehensive cost info for failed attempts
    comprehensive_cost_info = {
        'input_cost': sum(usage['cost'] for usage in model_usage if usage['model'] == model_name),
        'output_cost': 0,  # Will be calculated from total
        'total_cost': cumulative_cost,
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'model_used': model_name,
        'cumulative_cost': cumulative_cost,
        'total_attempts': len(model_usage),
        'models_used': list(set(usage['model'] for usage in model_usage)),
        'model_usage_breakdown': model_usage,
        'model_cost_breakdown': _calculate_model_breakdown(model_usage),
        'total_cost_all_models': cumulative_cost,
        'status': 'failed'
    }

    print(
        f"AI generation failed after {ai_total_time:.2f} seconds and {total_tokens} tokens")
    print(
        f"Total cost: ${cumulative_cost:.4f} across {len(model_usage)} attempts using models: {comprehensive_cost_info['models_used']}")

    # Print detailed model breakdown for failed attempts
    model_breakdown = comprehensive_cost_info['model_cost_breakdown']
    print("\n" + "="*60)
    print("DETAILED MODEL BREAKDOWN (FAILED):")
    print("="*60)

    for model, stats in model_breakdown.items():
        print(f"\n📊 {model.upper()}:")
        print(f"   • Total Attempts: {stats['total_attempts']}")
        print(f"   • Successful Attempts: {stats['successful_attempts']}")
        print(f"   • Success Rate: {stats['success_rate']}%")
        print(f"   • Total Tokens: {stats['total_tokens']:,}")
        print(f"   • Total Cost: ${stats['total_cost']:.4f}")
        print(f"   • Avg Tokens/Attempt: {stats['avg_tokens_per_attempt']:,}")
        print(f"   • Avg Cost/Attempt: ${stats['avg_cost_per_attempt']:.4f}")

    print(f"\n💰 TOTAL COST ACROSS ALL MODELS: ${cumulative_cost:.4f}")
    print("="*60)

    return {"classes": []}, total_tokens, comprehensive_cost_info


class SmartScheduleOptimizer:
    def __init__(self):
        self.time_slots = self._generate_time_slots()
        self.day_mapping = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}

    def _generate_time_slots(self):
        """Generate time slots from 7 AM to 10 PM in 15-minute intervals"""
        slots = []
        for hour in range(7, 22):
            for minute in [0, 15, 30, 45]:
                slots.append(f"{hour:02d}:{minute:02d}")
        return slots

    def _time_to_minutes(self, time_str):
        """Convert time string to minutes since midnight"""
        try:
            # Handle different time formats
            if ' ' in time_str:
                time, period = time_str.split()
            else:
                # Find where time ends and period begins
                for i, char in enumerate(time_str):
                    if char.isalpha():
                        time = time_str[:i]
                        period = time_str[i:]
                        break
                else:
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

    def _parse_section_times(self, section_data):
        """Parse section times and return structured data with proper handling of labs, online, and hybrid classes"""
        sections = []

        # Group sections by CRN to handle labs and additional times
        crn_groups = {}

        for _, row in section_data.iterrows():
            try:
                crn = row['CRN']
                course = row['Course']
                title = row['Title']
                instructor = row['Instructor']
                days = row['Days'].strip()
                begin_time = row['Begin Time'].strip()
                end_time = row['End Time'].strip()
                location = row['Location'].strip()
                schedule_type = row['Schedule Type'].strip()
                modality = row.get('Modality', '').strip()

                # Initialize CRN group if not exists
                if crn not in crn_groups:
                    crn_groups[crn] = {
                        'crn': crn,
                        'course': course,
                        'title': title,
                        'instructor': instructor,
                        'schedule_type': schedule_type,
                        'modality': modality,
                        'time_blocks': [],
                        'is_online': False,
                        'is_hybrid': False
                    }

                # Handle different types of sections
                if not days and not begin_time and not end_time:
                    # Online class
                    crn_groups[crn]['is_online'] = True
                    crn_groups[crn]['time_blocks'].append({
                        'days': [],
                        'start_minutes': 0,
                        'end_minutes': 0,
                        'location': location,
                        'schedule_type': schedule_type
                    })
                elif days and begin_time and end_time:
                    # In-person class with time
                    start_minutes = self._time_to_minutes(begin_time)
                    end_minutes = self._time_to_minutes(end_time)

                    if start_minutes > 0 and end_minutes > 0:
                        # Parse days
                        day_indices = []
                        for day in days:
                            if day in self.day_mapping:
                                day_indices.append(self.day_mapping[day])

                        crn_groups[crn]['time_blocks'].append({
                            'days': day_indices,
                            'start_minutes': start_minutes,
                            'end_minutes': end_minutes,
                            'location': location,
                            'schedule_type': schedule_type
                        })
                elif days and (not begin_time or not end_time):
                    # Additional times (labs, etc.) - use main section data
                    if crn_groups[crn]['time_blocks']:
                        # Add to existing time blocks
                        start_minutes = self._time_to_minutes(
                            begin_time) if begin_time else 0
                        end_minutes = self._time_to_minutes(
                            end_time) if end_time else 0

                        day_indices = []
                        for day in days:
                            if day in self.day_mapping:
                                day_indices.append(self.day_mapping[day])

                        if day_indices:
                            crn_groups[crn]['time_blocks'].append({
                                'days': day_indices,
                                'start_minutes': start_minutes,
                                'end_minutes': end_minutes,
                                'location': location,
                                'schedule_type': schedule_type
                            })

                # Check for hybrid classes
                if modality and 'hybrid' in modality.lower():
                    crn_groups[crn]['is_hybrid'] = True

            except Exception as e:
                print(
                    f"Error parsing section {row.get('CRN', 'unknown')}: {e}")
                continue

        # Convert grouped sections to individual sections
        for crn, group in crn_groups.items():
            if not group['time_blocks']:
                # Online class with no time blocks
                sections.append({
                    'crn': crn,
                    'course': group['course'],
                    'title': group['title'],
                    'instructor': group['instructor'],
                    'days': [],
                    'start_minutes': 0,
                    'end_minutes': 0,
                    'location': 'Online',
                    'schedule_type': group['schedule_type'],
                    'modality': group['modality'],
                    'is_online': True,
                    'is_hybrid': group['is_hybrid'],
                    'duration': 0
                })
            else:
                # Create sections for each time block
                for block in group['time_blocks']:
                    sections.append({
                        'crn': crn,
                        'course': group['course'],
                        'title': group['title'],
                        'instructor': group['instructor'],
                        'days': block['days'],
                        'start_minutes': block['start_minutes'],
                        'end_minutes': block['end_minutes'],
                        'location': block['location'],
                        'schedule_type': block['schedule_type'],
                        'modality': group['modality'],
                        'is_online': group['is_online'],
                        'is_hybrid': group['is_hybrid'],
                        'duration': block['end_minutes'] - block['start_minutes'] if block['end_minutes'] > block['start_minutes'] else 0
                    })

        return sections

    def _check_conflicts(self, section1, section2):
        """Check if two sections conflict"""
        # Online classes don't conflict with in-person classes
        if section1.get('is_online', False) or section2.get('is_online', False):
            return False

        # Check for day overlap
        day_overlap = set(section1['days']) & set(section2['days'])
        if not day_overlap:
            return False

        # Check for time overlap on overlapping days
        for day in day_overlap:
            # Check if times overlap (with 5-minute buffer)
            if (section1['start_minutes'] < section2['end_minutes'] + 5 and
                    section2['start_minutes'] < section1['end_minutes'] + 5):
                return True

        return False

    def _build_conflict_graph(self, sections):
        """Build a graph where nodes are sections and edges represent conflicts"""
        conflict_graph = defaultdict(set)

        for i, section1 in enumerate(sections):
            for j, section2 in enumerate(sections[i+1:], i+1):
                if self._check_conflicts(section1, section2):
                    conflict_graph[i].add(j)
                    conflict_graph[j].add(i)

        return conflict_graph

    def _find_independent_sets(self, sections, conflict_graph):
        """Find sets of non-conflicting sections using graph coloring"""
        # Simple greedy coloring algorithm
        colors = {}
        available_colors = set()

        for node in range(len(sections)):
            # Find used colors in neighbors
            used_colors = set()
            for neighbor in conflict_graph[node]:
                if neighbor in colors:
                    used_colors.add(colors[neighbor])

            # Find first available color
            color = 0
            while color in used_colors:
                color += 1

            colors[node] = color
            available_colors.add(color)

        # Group sections by color (each color represents a non-conflicting set)
        color_groups = defaultdict(list)
        for node, color in colors.items():
            color_groups[color].append(sections[node])

        return list(color_groups.values())

    def _calculate_schedule_score(self, schedule, preferences=""):
        """Calculate a score for a schedule based on preferences"""
        score = 0

        # Base score for valid schedule
        score += 1000

        # Time distribution preferences
        morning_classes = 0
        afternoon_classes = 0
        evening_classes = 0
        gaps = []

        # Group classes by day
        daily_schedules = defaultdict(list)
        for section in schedule:
            for day in section['days']:
                daily_schedules[day].append(section)

        # Analyze each day
        for day, day_classes in daily_schedules.items():
            # Sort by start time
            day_classes.sort(key=lambda x: x['start_minutes'])

            # Count time periods
            for section in day_classes:
                start_hour = section['start_minutes'] // 60
                if 7 <= start_hour < 12:
                    morning_classes += 1
                elif 12 <= start_hour < 17:
                    afternoon_classes += 1
                else:
                    evening_classes += 1

            # Calculate gaps between classes
            for i in range(len(day_classes) - 1):
                gap = day_classes[i+1]['start_minutes'] - \
                    day_classes[i]['end_minutes']
                gaps.append(gap)

        # Preference scoring
        if "morning" in preferences.lower():
            score += morning_classes * 10
        if "afternoon" in preferences.lower():
            score += afternoon_classes * 10
        if "evening" in preferences.lower():
            score += evening_classes * 10
        if "no classes before 10" in preferences.lower():
            score -= morning_classes * 20

        # Gap preferences
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        if "lunch break" in preferences.lower():
            # Prefer gaps around lunch time (11-2)
            lunch_gaps = [g for g in gaps if 30 <= g <= 120]
            score += len(lunch_gaps) * 5

        # Compact schedule preference
        if "close together" in preferences.lower():
            score += (len(gaps) - len([g for g in gaps if g > 30])) * 3
        else:
            # Prefer reasonable gaps
            score += len([g for g in gaps if 15 <= g <= 60]) * 2

        return score

    def _generate_optimal_schedules(self, course_sections, preferences=""):
        """Generate optimal schedules using constraint satisfaction"""
        all_sections = []
        course_to_sections = defaultdict(list)

        # Parse all sections
        for course_code, sections in course_sections.items():
            parsed_sections = self._parse_section_times(sections)
            course_to_sections[course_code] = parsed_sections
            all_sections.extend(parsed_sections)

        # Build conflict graph
        conflict_graph = self._build_conflict_graph(all_sections)

        # Find independent sets (non-conflicting section groups)
        independent_sets = self._find_independent_sets(
            all_sections, conflict_graph)

        # Generate valid combinations
        valid_schedules = []

        # For each course, we need exactly one section
        required_courses = list(course_sections.keys())

        def backtrack(selected_sections, course_index):
            if course_index >= len(required_courses):
                # We have a complete schedule
                if len(selected_sections) == len(required_courses):
                    # Validate that all required components are included
                    if self._validate_schedule_completeness(selected_sections, course_to_sections):
                        score = self._calculate_schedule_score(
                            selected_sections, preferences)
                        valid_schedules.append((score, selected_sections))
                return

            course_code = required_courses[course_index]
            available_sections = course_to_sections[course_code]

            for section in available_sections:
                # Check if this section conflicts with already selected sections
                conflicts = False
                for selected in selected_sections:
                    if self._check_conflicts(section, selected):
                        conflicts = True
                        break

                if not conflicts:
                    selected_sections.append(section)
                    backtrack(selected_sections, course_index + 1)
                    selected_sections.pop()

        # Start backtracking
        backtrack([], 0)

        # Sort by score and return top schedules
        valid_schedules.sort(key=lambda x: x[0], reverse=True)

        return valid_schedules[:10]  # Return top 10 schedules

    def _validate_schedule_completeness(self, selected_sections, course_to_sections):
        """Validate that all required components (lecture + lab) are included"""
        # Group selected sections by course
        course_sections_map = {}
        for section in selected_sections:
            course_code = section.get('course_code', section['course'])
            if course_code not in course_sections_map:
                course_sections_map[course_code] = []
            course_sections_map[course_code].append(section)

        # Check each course for completeness
        for course_code, sections in course_sections_map.items():
            # Check if this course has both lecture and lab components
            has_lecture = any('lecture' in s.get(
                'schedule_type', '').lower() for s in sections)
            has_lab = any('lab' in s.get('schedule_type', '').lower()
                          for s in sections)

            # If course has both components, ensure both are included
            if has_lecture and has_lab:
                if not (has_lecture and has_lab):
                    return False

        return True

    def optimize_schedule(self, courses_data, preferences=""):
        """Main optimization method"""
        start_time = time.time()

        # Group sections by course
        course_sections = defaultdict(list)
        for course_code, sections_df in courses_data.items():
            course_sections[course_code] = sections_df

        # Generate optimal schedules
        optimal_schedules = self._generate_optimal_schedules(
            course_sections, preferences)

        if not optimal_schedules:
            return {"classes": []}, 0

        # Convert best schedule to AI format
        best_schedule = optimal_schedules[0][1]
        ai_schedule = self._convert_to_ai_format(best_schedule)

        processing_time = time.time() - start_time
        print(f"Smart optimization completed in {processing_time:.2f} seconds")

        return {"classes": ai_schedule}, 0

    def _convert_to_ai_format(self, schedule):
        """Convert internal schedule format to AI response format"""
        ai_classes = []

        for section in schedule:
            # Handle online classes
            if section.get('is_online', False):
                ai_classes.append({
                    "crn": section['crn'],
                    "courseNumber": section['course'],
                    "courseName": section['title'],
                    "professorName": section['instructor'],
                    "days": "Online",
                    "time": "Online",
                    "location": "Online",
                    "isLab": "lab" in section['schedule_type'].lower(),
                    "isOnline": True,
                    "isHybrid": section.get('is_hybrid', False)
                })
            else:
                # Convert days back to string format
                day_str = ""
                for day_idx in sorted(section['days']):
                    day_str += list(self.day_mapping.keys()
                                    )[list(self.day_mapping.values()).index(day_idx)]

                # Convert times back to string format
                start_hour = section['start_minutes'] // 60
                start_minute = section['start_minutes'] % 60
                end_hour = section['end_minutes'] // 60
                end_minute = section['end_minutes'] % 60

                start_time = f"{start_hour if start_hour <= 12 else start_hour - 12}:{start_minute:02d}{'AM' if start_hour < 12 else 'PM'}"
                end_time = f"{end_hour if end_hour <= 12 else end_hour - 12}:{end_minute:02d}{'AM' if end_hour < 12 else 'PM'}"

                ai_classes.append({
                    "crn": section['crn'],
                    "courseNumber": section['course'],
                    "courseName": section['title'],
                    "professorName": section['instructor'],
                    "days": day_str,
                    "time": f"{start_time} - {end_time}",
                    "location": section['location'],
                    "isLab": "lab" in section['schedule_type'].lower(),
                    "isOnline": False,
                    "isHybrid": section.get('is_hybrid', False)
                })

        return ai_classes


# Initialize the smart optimizer
smart_optimizer = SmartScheduleOptimizer()

# Course data cache
course_cache = {}
CACHE_DURATION = 3600  # 1 hour cache


class GeneticScheduleOptimizer:
    """Advanced genetic algorithm for schedule optimization"""

    def __init__(self, population_size=50, generations=100, mutation_rate=0.1):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.day_mapping = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}

    def _time_to_minutes(self, time_str):
        """Convert time string to minutes since midnight"""
        try:
            if ' ' in time_str:
                time, period = time_str.split()
            else:
                for i, char in enumerate(time_str):
                    if char.isalpha():
                        time = time_str[:i]
                        period = time_str[i:]
                        break
                else:
                    time = time_str
                    period = ''

            if ':' in time:
                hours, minutes = map(int, time.split(':'))
            else:
                hours = int(time)
                minutes = 0

            if period:
                if period.upper() == 'PM' and hours != 12:
                    hours += 12
                elif period.upper() == 'AM' and hours == 12:
                    hours = 0

            return hours * 60 + minutes
        except Exception as e:
            return 0

    def _parse_sections(self, course_sections):
        """Parse all sections into structured format with proper handling of labs, online, and hybrid classes"""
        all_sections = []
        course_to_sections = defaultdict(list)

        for course_code, sections_df in course_sections.items():
            course_sections_list = []

            # Group sections by CRN to handle labs and additional times
            crn_groups = {}

            for _, row in sections_df.iterrows():
                try:
                    crn = row['CRN']
                    course = row['Course']
                    title = row['Title']
                    instructor = row['Instructor']
                    days = row['Days'].strip()
                    begin_time = row['Begin Time'].strip()
                    end_time = row['End Time'].strip()
                    location = row['Location'].strip()
                    schedule_type = row['Schedule Type'].strip()
                    modality = row.get('Modality', '').strip()

                    # Initialize CRN group if not exists
                    if crn not in crn_groups:
                        crn_groups[crn] = {
                            'crn': crn,
                            'course': course,
                            'title': title,
                            'instructor': instructor,
                            'schedule_type': schedule_type,
                            'modality': modality,
                            'time_blocks': [],
                            'is_online': False,
                            'is_hybrid': False,
                            'course_code': course_code
                        }

                    # Handle different types of sections
                    if not days and not begin_time and not end_time:
                        # Online class
                        crn_groups[crn]['is_online'] = True
                        crn_groups[crn]['time_blocks'].append({
                            'days': [],
                            'start_minutes': 0,
                            'end_minutes': 0,
                            'location': location,
                            'schedule_type': schedule_type
                        })
                    elif days and begin_time and end_time:
                        # In-person class with time
                        start_minutes = self._time_to_minutes(begin_time)
                        end_minutes = self._time_to_minutes(end_time)

                        if start_minutes > 0 and end_minutes > 0:
                            # Parse days
                            day_indices = []
                            for day in days:
                                if day in self.day_mapping:
                                    day_indices.append(self.day_mapping[day])

                            crn_groups[crn]['time_blocks'].append({
                                'days': day_indices,
                                'start_minutes': start_minutes,
                                'end_minutes': end_minutes,
                                'location': location,
                                'schedule_type': schedule_type
                            })
                    elif days and (not begin_time or not end_time):
                        # Additional times (labs, etc.) - use main section data
                        if crn_groups[crn]['time_blocks']:
                            # Add to existing time blocks
                            start_minutes = self._time_to_minutes(
                                begin_time) if begin_time else 0
                            end_minutes = self._time_to_minutes(
                                end_time) if end_time else 0

                            day_indices = []
                            for day in days:
                                if day in self.day_mapping:
                                    day_indices.append(self.day_mapping[day])

                            if day_indices:
                                crn_groups[crn]['time_blocks'].append({
                                    'days': day_indices,
                                    'start_minutes': start_minutes,
                                    'end_minutes': end_minutes,
                                    'location': location,
                                    'schedule_type': schedule_type
                                })

                    # Check for hybrid classes
                    if modality and 'hybrid' in modality.lower():
                        crn_groups[crn]['is_hybrid'] = True

                except Exception as e:
                    continue

            # Convert grouped sections to individual sections
            for crn, group in crn_groups.items():
                if not group['time_blocks']:
                    # Online class with no time blocks
                    section_data = {
                        'crn': crn,
                        'course': group['course'],
                        'title': group['title'],
                        'instructor': group['instructor'],
                        'days': [],
                        'start_minutes': 0,
                        'end_minutes': 0,
                        'location': 'Online',
                        'schedule_type': group['schedule_type'],
                        'modality': group['modality'],
                        'is_online': True,
                        'is_hybrid': group['is_hybrid'],
                        'course_code': course_code
                    }
                    course_sections_list.append(section_data)
                    all_sections.append(section_data)
                else:
                    # Create sections for each time block
                    for block in group['time_blocks']:
                        section_data = {
                            'crn': crn,
                            'course': group['course'],
                            'title': group['title'],
                            'instructor': group['instructor'],
                            'days': block['days'],
                            'start_minutes': block['start_minutes'],
                            'end_minutes': block['end_minutes'],
                            'location': block['location'],
                            'schedule_type': block['schedule_type'],
                            'modality': group['modality'],
                            'is_online': group['is_online'],
                            'is_hybrid': group['is_hybrid'],
                            'course_code': course_code
                        }
                        course_sections_list.append(section_data)
                        all_sections.append(section_data)

            course_to_sections[course_code] = course_sections_list

        return course_to_sections, all_sections

    def _check_conflicts(self, section1, section2):
        """Check if two sections conflict"""
        # Online classes don't conflict with in-person classes
        if section1.get('is_online', False) or section2.get('is_online', False):
            return False

        day_overlap = set(section1['days']) & set(section2['days'])
        if not day_overlap:
            return False

        for day in day_overlap:
            if (section1['start_minutes'] < section2['end_minutes'] + 5 and
                    section2['start_minutes'] < section1['end_minutes'] + 5):
                return True

        return False

    def _is_valid_schedule(self, schedule):
        """Check if a schedule is valid (no conflicts)"""
        for i, section1 in enumerate(schedule):
            for section2 in schedule[i+1:]:
                if self._check_conflicts(section1, section2):
                    return False
        return True

    def _calculate_fitness(self, schedule, preferences=""):
        """Calculate fitness score for a schedule"""
        if not self._is_valid_schedule(schedule):
            return 0

        score = 1000  # Base score for valid schedule

        # Time distribution analysis
        daily_schedules = defaultdict(list)
        for section in schedule:
            for day in section['days']:
                daily_schedules[day].append(section)

        total_gaps = 0
        morning_classes = 0
        afternoon_classes = 0
        evening_classes = 0

        for day, day_classes in daily_schedules.items():
            day_classes.sort(key=lambda x: x['start_minutes'])

            # Count time periods
            for section in day_classes:
                start_hour = section['start_minutes'] // 60
                if 7 <= start_hour < 12:
                    morning_classes += 1
                elif 12 <= start_hour < 17:
                    afternoon_classes += 1
                else:
                    evening_classes += 1

            # Calculate gaps
            for i in range(len(day_classes) - 1):
                gap = day_classes[i+1]['start_minutes'] - \
                    day_classes[i]['end_minutes']
                total_gaps += gap

        # Preference scoring
        if "morning" in preferences.lower():
            score += morning_classes * 15
        if "afternoon" in preferences.lower():
            score += afternoon_classes * 15
        if "evening" in preferences.lower():
            score += evening_classes * 15
        if "no classes before 10" in preferences.lower():
            score -= morning_classes * 25

        # Gap preferences
        if "lunch break" in preferences.lower():
            lunch_gaps = sum(1 for gap in [total_gaps] if 30 <= gap <= 120)
            score += lunch_gaps * 10

        if "close together" in preferences.lower():
            score += (len(daily_schedules) -
                      len([g for g in [total_gaps] if g > 30])) * 5
        else:
            score += len([g for g in [total_gaps] if 15 <= g <= 60]) * 3

        # Professor preference bonus
        for section in schedule:
            if section['instructor'].lower() in preferences.lower():
                score += 20

        return score

    def _create_individual(self, course_to_sections):
        """Create a random individual (schedule)"""
        schedule = []
        for course_code, sections in course_to_sections.items():
            if sections:
                schedule.append(random.choice(sections))
        return schedule

    def _create_population(self, course_to_sections):
        """Create initial population"""
        population = []
        for _ in range(self.population_size):
            individual = self._create_individual(course_to_sections)
            population.append(individual)
        return population

    def _crossover(self, parent1, parent2):
        """Perform crossover between two parents"""
        if len(parent1) != len(parent2):
            return parent1, parent2

        crossover_point = random.randint(1, len(parent1) - 1)
        child1 = parent1[:crossover_point] + parent2[crossover_point:]
        child2 = parent2[:crossover_point] + parent1[crossover_point:]

        return child1, child2

    def _mutate(self, individual, course_to_sections):
        """Mutate an individual"""
        if random.random() < self.mutation_rate:
            # Randomly replace one section
            course_codes = list(course_to_sections.keys())
            if course_codes:
                course_code = random.choice(course_codes)
                sections = course_to_sections[course_code]
                if sections:
                    # Find the section for this course in the individual
                    for i, section in enumerate(individual):
                        if section['course_code'] == course_code:
                            individual[i] = random.choice(sections)
                            break

        return individual

    def _select_parents(self, population, fitness_scores):
        """Select parents using tournament selection"""
        tournament_size = 3
        parent1_idx = max(random.sample(range(len(population)), tournament_size),
                          key=lambda i: fitness_scores[i])
        parent2_idx = max(random.sample(range(len(population)), tournament_size),
                          key=lambda i: fitness_scores[i])

        return population[parent1_idx], population[parent2_idx]

    def optimize(self, course_sections, preferences=""):
        """Main genetic algorithm optimization"""
        course_to_sections, _ = self._parse_sections(course_sections)

        # Create initial population
        population = self._create_population(course_to_sections)

        best_fitness = 0
        best_schedule = None

        for generation in range(self.generations):
            # Calculate fitness for all individuals
            fitness_scores = []
            for individual in population:
                fitness = self._calculate_fitness(individual, preferences)
                fitness_scores.append(fitness)

                if fitness > best_fitness:
                    best_fitness = fitness
                    best_schedule = individual.copy()

            # Create new population
            new_population = []

            # Elitism: keep best individual
            best_idx = max(range(len(fitness_scores)),
                           key=lambda i: fitness_scores[i])
            new_population.append(population[best_idx])

            # Generate rest of population
            while len(new_population) < self.population_size:
                parent1, parent2 = self._select_parents(
                    population, fitness_scores)
                child1, child2 = self._crossover(parent1, parent2)

                child1 = self._mutate(child1, course_to_sections)
                child2 = self._mutate(child2, course_to_sections)

                new_population.extend([child1, child2])

            # Trim to population size
            population = new_population[:self.population_size]

            if generation % 20 == 0:
                print(
                    f"Generation {generation}: Best fitness = {best_fitness}")

        return best_schedule if best_schedule else []

    def _convert_to_ai_format(self, schedule):
        """Convert genetic algorithm schedule to AI format"""
        ai_classes = []

        for section in schedule:
            # Handle online classes
            if section.get('is_online', False):
                ai_classes.append({
                    "crn": section['crn'],
                    "courseNumber": section['course'],
                    "courseName": section['title'],
                    "professorName": section['instructor'],
                    "days": "Online",
                    "time": "Online",
                    "location": "Online",
                    "isLab": "lab" in section['schedule_type'].lower(),
                    "isOnline": True,
                    "isHybrid": section.get('is_hybrid', False)
                })
            else:
                # Convert days back to string format
                day_str = ""
                for day_idx in sorted(section['days']):
                    day_str += list(self.day_mapping.keys()
                                    )[list(self.day_mapping.values()).index(day_idx)]

                # Convert times back to string format
                start_hour = section['start_minutes'] // 60
                start_minute = section['start_minutes'] % 60
                end_hour = section['end_minutes'] // 60
                end_minute = section['end_minutes'] % 60

                start_time = f"{start_hour if start_hour <= 12 else start_hour - 12}:{start_minute:02d}{'AM' if start_hour < 12 else 'PM'}"
                end_time = f"{end_hour if end_hour <= 12 else end_hour - 12}:{end_minute:02d}{'AM' if end_hour < 12 else 'PM'}"

                ai_classes.append({
                    "crn": section['crn'],
                    "courseNumber": section['course'],
                    "courseName": section['title'],
                    "professorName": section['instructor'],
                    "days": day_str,
                    "time": f"{start_time} - {end_time}",
                    "location": section['location'],
                    "isLab": "lab" in section['schedule_type'].lower(),
                    "isOnline": False,
                    "isHybrid": section.get('is_hybrid', False)
                })

        return ai_classes


# Initialize genetic optimizer
genetic_optimizer = GeneticScheduleOptimizer()


def get_cached_course_data(department, coursenumber, term_year):
    """Get course data from cache or fetch if not available"""
    cache_key = f"{department}_{coursenumber}_{term_year}"

    # Check if data is in cache and not expired
    if cache_key in course_cache:
        cached_data, timestamp = course_cache[cache_key]
        if time.time() - timestamp < CACHE_DURATION:
            return cached_data

    # Fetch fresh data
    fresh_data = courseDetailsExractor(department, coursenumber, term_year)
    if fresh_data is not None:
        course_cache[cache_key] = (fresh_data, time.time())

    return fresh_data


def _calculate_model_breakdown(model_usage):
    """Calculate detailed breakdown for each model used"""
    model_stats = {}

    for usage in model_usage:
        model = usage['model']
        if model not in model_stats:
            model_stats[model] = {
                'total_attempts': 0,
                'successful_attempts': 0,
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_cost': 0.0,
                'attempts': []
            }

        model_stats[model]['total_attempts'] += 1
        model_stats[model]['total_input_tokens'] += usage['input_tokens']
        model_stats[model]['total_output_tokens'] += usage['output_tokens']
        model_stats[model]['total_cost'] += usage['cost']
        model_stats[model]['attempts'].append(usage)

        if usage['success']:
            model_stats[model]['successful_attempts'] += 1

    # Calculate averages and summaries
    for model, stats in model_stats.items():
        stats['avg_tokens_per_attempt'] = round(
            (stats['total_input_tokens'] + stats['total_output_tokens']) / stats['total_attempts'], 2)
        stats['avg_cost_per_attempt'] = round(
            stats['total_cost'] / stats['total_attempts'], 4)
        stats['success_rate'] = round(
            (stats['successful_attempts'] / stats['total_attempts']) * 100, 1)
        stats['total_tokens'] = stats['total_input_tokens'] + \
            stats['total_output_tokens']

    return model_stats


def calculate_gemini_cost(input_tokens, output_tokens, model_name="gemini-2.5-pro"):
    """Calculate cost based on Gemini model pricing"""

    # Convert tokens to millions for pricing calculation
    input_millions = input_tokens / 1_000_000
    output_millions = output_tokens / 1_000_000

    # Model-specific pricing (per 1M tokens)
    if model_name == "gemini-2.5-pro":
        # Gemini 2.5 Pro pricing
        if input_tokens <= 200_000:
            input_cost_per_million = 1.25
        else:
            input_cost_per_million = 2.50

        if input_tokens <= 200_000:
            output_cost_per_million = 10.00
        else:
            output_cost_per_million = 15.00

    elif model_name == "gemini-2.0-flash-exp":
        # Gemini 2.0 Flash Exp pricing
        input_cost_per_million = 0.10  # $0.10 per 1M tokens for text
        output_cost_per_million = 0.40  # $0.40 per 1M tokens

    elif model_name == "gemini-2.5-flash-lite":
        # Gemini 2.5 Flash-Lite pricing
        input_cost_per_million = 0.10  # $0.10 per 1M tokens for text
        output_cost_per_million = 0.40  # $0.40 per 1M tokens

    else:
        # Default pricing for unknown models
        input_cost_per_million = 0.10
        output_cost_per_million = 0.40

    # Calculate costs
    input_cost = input_millions * input_cost_per_million
    output_cost = output_millions * output_cost_per_million
    total_cost = input_cost + output_cost

    return {
        'input_cost': round(input_cost, 4),
        'output_cost': round(output_cost, 4),
        'total_cost': round(total_cost, 4),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'model_used': model_name
    }


def clear_expired_cache():
    """Clear expired cache entries"""
    current_time = time.time()
    expired_keys = [
        key for key, (_, timestamp) in course_cache.items()
        if current_time - timestamp > CACHE_DURATION
    ]
    for key in expired_keys:
        del course_cache[key]


def courseDetailsExractor(department: str, coursenumber, term_year: str):
    try:
        url = "https://selfservice.banner.vt.edu/ssb/HZSKVTSC.P_ProcRequest"
        form_data = {
            "CAMPUS": "0",
            "TERMYEAR": term_year,
            "CORE_CODE": "AR%",
            "subj_code": department.upper(),
            "SCHDTYPE": "%",
            "CRSE_NUMBER": coursenumber,
            "crn": "",
            "open_only": "",
            "disp_comments_in": "Y",
            "sess_code": "%",
            "BTN_PRESSED": "FIND class sections",
            "inst_name": ""
        }
        response = requests.post(url=url, data=form_data)
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        courses_data = []
        rows = soup.find_all('tr')
        for row in rows:
            crn_cell = row.find('a', href=lambda x: x and 'CRN=' in x)
            if not crn_cell:
                continue
            cells = row.find_all('td')
            if len(cells) < 12:
                continue
            crn = crn_cell.find('b').text.strip() if crn_cell.find('b') else ""
            course_cell = cells[1]
            course = course_cell.text.strip()
            title = cells[2].text.strip()
            schedule_type = cells[3].text.strip()
            modality = cells[4].text.strip()
            cr_hrs = cells[5].text.strip()
            capacity = cells[6].text.strip()
            instructor = cells[7].text.strip()
            days = cells[8].text.strip()
            begin_time = cells[9].text.strip()
            end_time = cells[10].text.strip()
            location = cells[11].text.strip()
            exam_cell = cells[12] if len(cells) > 12 else None
            exam_code = exam_cell.find('a').text.strip(
            ) if exam_cell and exam_cell.find('a') else ""
            courses_data.append({
                'CRN': crn,
                'Course': course,
                'Title': title,
                'Schedule Type': schedule_type,
                'Modality': modality,
                'Credit Hours': cr_hrs,
                'Capacity': capacity,
                'Instructor': instructor,
                'Days': days,
                'Begin Time': begin_time,
                'End Time': end_time,
                'Location': location,
                'Exam Code': exam_code
            })
        return pd.DataFrame(courses_data)
    except Exception as e:
        save_log_entry(message=f"Error extracting course details: {str(e)}")


@app.route("/api/generate_schedule", methods=['POST'])
def generate_schedule():
    start_time = time.time()
    total_tokens_used = 0
    optimization_method = "unknown"

    print("Starting smart schedule generation")
    data = request.json
    courses = data.get("courses", [])
    preferences = data.get("preferences", "")
    email = data.get("email", None)

    # Use smart optimization first
    try:
        # Clear expired cache entries
        clear_expired_cache()

        # Extract course data with caching
        courses_data = {}
        for course in courses:
            course_code = course['department'] + course['number']
            df = get_cached_course_data(
                course['department'], course['number'], data['term_year'])
            if df is not None and not df.empty:
                courses_data[course_code] = df

        if not courses_data:
            return jsonify({"classes": []}), 400

            # Check if courses have complex structures (labs, online, hybrid, multiple time blocks)
        has_complex_structure = False
        for course_code, df in courses_data.items():
            # Check for multiple time blocks per CRN (indicating labs or multiple meetings)
            crn_counts = df['CRN'].value_counts()
            if any(count > 1 for count in crn_counts.values):
                has_complex_structure = True
                print(f"Found multiple time blocks for course {course_code}")
                break

            # Check for labs, online classes, or hybrid classes
            for _, row in df.iterrows():
                schedule_type = row.get('Schedule Type', '').lower()
                modality = row.get('Modality', '').lower()
                days = row.get('Days', '').strip()
                begin_time = row.get('Begin Time', '').strip()

                # Check for labs
                if 'lab' in schedule_type:
                    has_complex_structure = True
                    print(f"Found lab in course {course_code}")
                    break

                # Check for online/hybrid classes
                if 'online' in modality or 'hybrid' in modality:
                    has_complex_structure = True
                    print(f"Found online/hybrid in course {course_code}")
                    break

                # Check for classes without times (asynchronous)
                if days and not begin_time:
                    has_complex_structure = True
                    print(f"Found asynchronous class in course {course_code}")
                    break

                # Check for ARR (Arranged) schedules
                if 'arr' in days.lower() or 'arr' in begin_time.lower():
                    has_complex_structure = True
                    print(f"Found ARR schedule in course {course_code}")
                    break

        # Determine optimization strategy
        num_courses = len(courses_data)
        total_sections = sum(len(df) for df in courses_data.values())

        print(
            f"Schedule complexity: {num_courses} courses, {total_sections} total sections, complex structure: {has_complex_structure}")

        # Use AI approach for complex structures, smart optimization for simple ones
        if has_complex_structure:
            optimization_method = "ai"
            print(
                "Using AI approach for complex course structures (labs, online, hybrid)")
            # Build AI prompt with raw data
            ai_prompt = ""
            ai_prompt += f"<preferences_by_user>\n{preferences}\n</preferences_by_user>\n"
            for course in courses:
                ai_prompt += f"<course_number>{course['department']+course['number']}</course_number>\n"
                ai_prompt += f"<professor_preference>{course['professor']}</professor_preference>\n"
                ai_prompt += f"<timetable_of_classes_for_the_course>\n"
                df = get_cached_course_data(
                    course['department'], course['number'], data['term_year'])
                ai_prompt += df.to_csv(index=False)
                ai_prompt += "\n</timetable_of_classes_for_the_course>"

            schedule, tokens_used, cost_info = ai_maker(ai_prompt, courses)
            total_tokens_used = tokens_used
            total_tokens = update_total_tokens(tokens_used)
        else:
            # Use smart optimization for simple schedules
            print("Using smart optimization for simple schedule")
            if num_courses > 3 or total_sections > 20:
                optimization_method = "genetic"
                print("Using genetic algorithm for complex schedule")
                genetic_schedule = genetic_optimizer.optimize(
                    courses_data, preferences)
                if genetic_schedule:
                    ai_schedule = genetic_optimizer._convert_to_ai_format(
                        genetic_schedule)
                    schedule = {"classes": ai_schedule}
                    tokens_used = 0
                else:
                    print("Genetic algorithm failed, trying smart optimizer")
                    optimization_method = "constraint_satisfaction"
                    schedule, tokens_used = smart_optimizer.optimize_schedule(
                        courses_data, preferences)
            else:
                optimization_method = "constraint_satisfaction"
                print("Using smart optimizer for simple schedule")
                schedule, tokens_used = smart_optimizer.optimize_schedule(
                    courses_data, preferences)

            if schedule['classes']:
                total_tokens = get_total_tokens()  # No tokens used for smart optimization
            else:
                total_tokens = get_total_tokens()

        # If both optimizers fail, fall back to AI
        if not schedule['classes']:
            optimization_method = "ai_fallback"
            print("All optimizers failed, falling back to AI")
            ai_prompt = ""
            ai_prompt += f"<preferences_by_user>\n{preferences}\n</preferences_by_user>\n"
            for course in courses:
                ai_prompt += f"<course_number>{course['department']+course['number']}</course_number>\n"
                ai_prompt += f"<professor_preference>{course['professor']}</professor_preference>\n"
                ai_prompt += f"<timetable_of_classes_for_the_course>\n"
                df = courseDetailsExractor(
                    course['department'], course['number'], data['term_year'])
                ai_prompt += df.to_csv(index=False)
                ai_prompt += "\n</timetable_of_classes_for_the_course>"
            schedule, tokens_used, cost_info = ai_maker(ai_prompt, courses)
            total_tokens_used = tokens_used
            total_tokens = update_total_tokens(tokens_used)
        else:
            total_tokens = get_total_tokens()  # No tokens used for smart optimization

        end_time = time.time()
        total_time_taken = end_time - start_time

        log_msg = f"Smart schedule generation completed with {len(schedule['classes'])} classes | tokens used: {total_tokens_used} | total tokens: {total_tokens} | time: {total_time_taken:.2f}s | method: {optimization_method}"
        if email:
            log_msg += f" | email: {email}"
        save_log_entry(message=log_msg)

        # Add performance metrics to response
        schedule['performance_metrics'] = {
            'total_tokens': total_tokens_used,
            'optimization_method': optimization_method,
            'time_taken_seconds': round(total_time_taken, 2),
            'courses_processed': len(courses),
            'total_sections_analyzed': sum(len(df) for df in courses_data.values())
        }

        # Add cost information if AI was used
        if optimization_method in ['ai', 'ai_fallback', 'ai_exception_fallback']:
            schedule['performance_metrics']['cost_info'] = cost_info
            # Add detailed cost breakdown
            schedule['performance_metrics']['cost_breakdown'] = {
                'cumulative_cost': cost_info.get('cumulative_cost', cost_info['total_cost']),
                'total_attempts': cost_info.get('total_attempts', 1),
                'models_used': cost_info.get('models_used', [cost_info['model_used']]),
                'model_usage_breakdown': cost_info.get('model_usage_breakdown', []),
                'model_cost_breakdown': cost_info.get('model_cost_breakdown', {}),
                'total_cost_all_models': cost_info.get('total_cost_all_models', cost_info['total_cost'])
            }
        else:
            schedule['performance_metrics']['cost_info'] = {
                'input_cost': 0.0,
                'output_cost': 0.0,
                'total_cost': 0.0,
                'input_tokens': 0,
                'output_tokens': 0,
                'model_used': 'local_optimization',
                'cumulative_cost': 0.0,
                'total_attempts': 0,
                'models_used': ['local_optimization'],
                'model_usage_breakdown': [],
                'model_cost_breakdown': {},
                'total_cost_all_models': 0.0
            }

        # Log cost data to CSV
        request_data = {
            'email': email,
            'schedule': schedule
        }
        log_cost_data(request_data, schedule['performance_metrics'],
                      schedule['performance_metrics']['cost_info'], 'success')

        return jsonify(schedule)

    except Exception as e:
        end_time = time.time()
        total_time_taken = end_time - start_time
        optimization_method = "ai_exception_fallback"

        print(f"Smart optimization error: {e}")
        save_log_entry(message=f"Smart optimization failed: {str(e)}")

        # Fall back to AI method
        ai_prompt = ""
        ai_prompt += f"<preferences_by_user>\n{preferences}\n</preferences_by_user>\n"
        for course in courses:
            ai_prompt += f"<course_number>{course['department']+course['number']}</course_number>\n"
            ai_prompt += f"<professor_preference>{course['professor']}</professor_preference>\n"
            ai_prompt += f"<timetable_of_classes_for_the_course>\n"
            df = courseDetailsExractor(
                course['department'], course['number'], data['term_year'])
            ai_prompt += df.to_csv(index=False)
            ai_prompt += "\n</timetable_of_classes_for_the_course>"
        schedule, tokens_used, cost_info = ai_maker(ai_prompt, courses)
        total_tokens_used = tokens_used
        total_tokens = update_total_tokens(tokens_used)
        log_msg = f"AI fallback schedule generation completed with {len(schedule['classes'])} classes | tokens used: {tokens_used} | total tokens: {total_tokens}"
        if email:
            log_msg += f" | email: {email}"
        save_log_entry(message=log_msg)

        # Log cost data to CSV for exception fallback
        request_data = {
            'email': email,
            'schedule': schedule
        }
        performance_metrics = {
            'total_tokens': tokens_used,
            'optimization_method': optimization_method,
            'time_taken_seconds': round(total_time_taken, 2),
            'courses_processed': len(courses),
            'total_sections_analyzed': 0
        }
        cost_info = {
            'total_cost_all_models': tokens_used * 0.000001,  # Approximate cost
            'total_cost': tokens_used * 0.000001
        }
        log_cost_data(request_data, performance_metrics, cost_info, 'success')
        return jsonify(schedule)


@app.route("/api/generate_multiple_schedules", methods=['POST'])
def generate_multiple_schedules():
    """Generate multiple schedule options for comparison"""
    start_time = time.time()
    total_tokens_used = 0
    optimization_method = "unknown"

    print("Starting multiple schedule generation")
    data = request.json
    courses = data.get("courses", [])
    preferences = data.get("preferences", "")
    email = data.get("email", None)
    num_options = data.get("num_options", 3)

    try:
        # Extract course data with caching
        clear_expired_cache()
        courses_data = {}
        for course in courses:
            course_code = course['department'] + course['number']
            df = get_cached_course_data(
                course['department'], course['number'], data['term_year'])
            if df is not None and not df.empty:
                courses_data[course_code] = df

        if not courses_data:
            return jsonify({"schedules": []}), 400

            # Check if courses have complex structures (labs, online, hybrid, multiple time blocks)
        has_complex_structure = False
        for course_code, df in courses_data.items():
            # Check for multiple time blocks per CRN (indicating labs or multiple meetings)
            crn_counts = df['CRN'].value_counts()
            if any(count > 1 for count in crn_counts.values):
                has_complex_structure = True
                print(f"Found multiple time blocks for course {course_code}")
                break

            for _, row in df.iterrows():
                schedule_type = row.get('Schedule Type', '').lower()
                modality = row.get('Modality', '').lower()
                days = row.get('Days', '').strip()
                begin_time = row.get('Begin Time', '').strip()

                if ('lab' in schedule_type or 'online' in modality or 'hybrid' in modality or
                        (days and not begin_time) or 'arr' in days.lower() or 'arr' in begin_time.lower()):
                    has_complex_structure = True
                    print(f"Found complex structure in course {course_code}")
                    break
            if has_complex_structure:
                break

        if has_complex_structure:
            optimization_method = "ai"
            print("Using AI approach for multiple schedules with complex structures")
            # For complex structures, generate one AI schedule
            ai_prompt = ""
            ai_prompt += f"<preferences_by_user>\n{preferences}\n</preferences_by_user>\n"
            for course in courses:
                ai_prompt += f"<course_number>{course['department']+course['number']}</course_number>\n"
                ai_prompt += f"<professor_preference>{course['professor']}</professor_preference>\n"
                ai_prompt += f"<timetable_of_classes_for_the_course>\n"
                df = get_cached_course_data(
                    course['department'], course['number'], data['term_year'])
                ai_prompt += df.to_csv(index=False)
                ai_prompt += "\n</timetable_of_classes_for_the_course>"

            schedule, tokens_used, cost_info = ai_maker(ai_prompt, courses)
            total_tokens_used = tokens_used
            if schedule['classes']:
                schedules = [{
                    "id": 1,
                    "classes": schedule['classes'],
                    "score": 1200  # High score for AI-generated schedule
                }]
        else:
            optimization_method = "genetic_multiple"
            # Generate multiple schedules using genetic algorithm
            print(f"Generating {num_options} schedule options")

            # Configure genetic optimizer for multiple solutions
            multi_optimizer = GeneticScheduleOptimizer(
                population_size=100,
                generations=150,
                mutation_rate=0.15
            )

            schedules = []
            seen_schedules = set()

            for i in range(num_options):
                print(f"Generating schedule option {i+1}")
                genetic_schedule = multi_optimizer.optimize(
                    courses_data, preferences)

                if genetic_schedule:
                    # Convert to AI format
                    ai_schedule = multi_optimizer._convert_to_ai_format(
                        genetic_schedule)

                    # Create unique identifier for this schedule
                    schedule_id = hash(
                        tuple(sorted([(cls['crn'], cls['time'], cls['days']) for cls in ai_schedule])))

                    if schedule_id not in seen_schedules:
                        seen_schedules.add(schedule_id)
                        schedules.append({
                            "id": i + 1,
                            "classes": ai_schedule,
                            "score": multi_optimizer._calculate_fitness(genetic_schedule, preferences)
                        })

        # Sort by score
        schedules.sort(key=lambda x: x['score'], reverse=True)

        end_time = time.time()
        total_time_taken = end_time - start_time

        log_msg = f"Multiple schedule generation completed with {len(schedules)} options | tokens used: {total_tokens_used} | time: {total_time_taken:.2f}s | method: {optimization_method}"
        if email:
            log_msg += f" | email: {email}"
        save_log_entry(message=log_msg)

        # Add performance metrics to response
        response_data = {
            "schedules": schedules,
            "performance_metrics": {
                'total_tokens': total_tokens_used,
                'optimization_method': optimization_method,
                'time_taken_seconds': round(total_time_taken, 2),
                'courses_processed': len(courses),
                'total_sections_analyzed': sum(len(df) for df in courses_data.values()),
                'schedules_generated': len(schedules)
            }
        }

        # Add cost information if AI was used
        if optimization_method == 'ai':
            response_data['performance_metrics']['cost_info'] = cost_info
            # Add detailed cost breakdown
            response_data['performance_metrics']['cost_breakdown'] = {
                'cumulative_cost': cost_info.get('cumulative_cost', cost_info['total_cost']),
                'total_attempts': cost_info.get('total_attempts', 1),
                'models_used': cost_info.get('models_used', [cost_info['model_used']]),
                'model_usage_breakdown': cost_info.get('model_usage_breakdown', [])
            }
        else:
            response_data['performance_metrics']['cost_info'] = {
                'input_cost': 0.0,
                'output_cost': 0.0,
                'total_cost': 0.0,
                'input_tokens': 0,
                'output_tokens': 0,
                'model_used': 'local_optimization',
                'cumulative_cost': 0.0,
                'total_attempts': 0,
                'models_used': ['local_optimization'],
                'model_usage_breakdown': []
            }

        # Log cost data to CSV for multiple schedules
        request_data = {
            'email': email,
            # Multiple schedules don't have a single schedule
            'schedule': {'classes': []}
        }
        log_cost_data(request_data, response_data['performance_metrics'],
                      response_data['performance_metrics']['cost_info'], 'success')

        return jsonify(response_data)

    except Exception as e:
        end_time = time.time()
        total_time_taken = end_time - start_time

        print(f"Multiple schedule generation error: {e}")
        save_log_entry(
            message=f"Multiple schedule generation failed: {str(e)} | time: {total_time_taken:.2f}s")
        return jsonify({
            "schedules": [],
            "performance_metrics": {
                'total_tokens': total_tokens_used,
                'optimization_method': optimization_method,
                'time_taken_seconds': round(total_time_taken, 2),
                'error': str(e)
            }
        }), 500


@app.route("/api/downloadSchedule", methods=['POST'])
def downloadSchedule():
    try:
        schedule = request.json.get("schedule", [])
        schedule = schedule['classes']
        colorsV = request.json.get("crnColors")
        pdf_buffer = generate_schedule_pdf(schedule, colorsV)
        save_log_entry(message="PDF generated successfully")
        return send_file(pdf_buffer, as_attachment=True, download_name="schedule.pdf", mimetype='application/pdf')
    except Exception as e:
        save_log_entry(message=e)
        return {"error": str(e)}, 500


@app.route("/api/get_logs", methods=['POST'])
def get_logs():
    try:
        data = request.json
        username = data.get("username", None)
        password = data.get("password", None)
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        # Load users from security_config.json
        with open("security_config.json", 'r') as sec_file:
            sec_data = json.load(sec_file)
            users = sec_data.get("users", [])
        # Check if user exists and password matches
        authorized = any(
            u["username"] == username and u["password"] == password for u in users)
        if not authorized:
            return jsonify({"error": "Unauthorized"}), 401
        with open(log_file, 'r') as f:
            logs = json.load(f)
        logs = logs[-10:] if len(logs) > 10 else logs
        return jsonify(logs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/company_cost_summary", methods=['GET'])
def company_cost_summary():
    """Get company-wide cost summary"""
    try:
        summary = get_company_cost_summary()
        if summary:
            return jsonify(summary), 200
        else:
            return jsonify({"error": "Unable to retrieve cost summary"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download_cost_data", methods=['GET'])
def download_cost_data():
    """Download cost tracking CSV file"""
    try:
        if os.path.exists(COST_TRACKING_FILE):
            return send_file(COST_TRACKING_FILE, as_attachment=True, download_name="cost_tracking.csv")
        else:
            return jsonify({"error": "Cost tracking file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/view_company_cost", methods=['GET'])
def view_company_cost():
    """View company cost summary text file"""
    try:
        if os.path.exists(COMPANY_COST_FILE):
            with open(COMPANY_COST_FILE, 'r') as f:
                content = f.read()
            return jsonify({"content": content}), 200
        else:
            return jsonify({"error": "Company cost file not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host="0.0.0.0", port=port)
