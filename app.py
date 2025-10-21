import os
import json
import time
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading
import logging
import io
import random
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from WaitList import WaitList
from AIProcessor import AIProcessor
from AIResponse import AIResponse

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
waitlist = None
ai_processor = None
server_folder = "server_data"
config_file = None

def initialize_server():
    """Initialize the server with waitlist and AI processor"""
    global waitlist, ai_processor, config_file
    
    # Create server folder if it doesn't exist
    if not os.path.exists(server_folder):
        os.makedirs(server_folder)
    
    # Load AI config first
    ai_config = load_ai_config()
    
    # Initialize waitlist with AI config
    waitlist = WaitList(server_folder, ai_config)
    
    # Initialize AI processor with config
    ai_processor = AIProcessor(ai_config)
    
    logger.info("Server initialized successfully")

def load_ai_config():
    """Load AI configuration from file or environment"""
    global config_file
    
    # Check if config file path is provided
    if not config_file:
        # Try to find config file in server folder
        config_path = os.path.join(server_folder, "ai_config.json")
        if os.path.exists(config_path):
            config_file = config_path
        else:
            # Ask for config file path
            config_file = input("Please provide the path to your AI config JSON file: ").strip()
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Config file not found: {config_file}")
    
    # Load config from file
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Copy config to waitlist folder for persistence
    waitlist_config_path = os.path.join(server_folder, "ai_config.json")
    with open(waitlist_config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"AI config loaded from {config_file}")
    return config

def log_waitlist_event(event, data=None):
    """Log events to waitlist logs"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "data": data or {}
    }
    
    log_file = os.path.join(server_folder, "waitlist_logs.json")
    
    # Load existing logs
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = json.load(f)
    else:
        logs = []
    
    # Add new log entry
    logs.append(log_entry)
    
    # Keep only last 1000 entries
    if len(logs) > 1000:
        logs = logs[-1000:]
    
    # Save logs
    with open(log_file, 'w') as f:
        json.dump(logs, f, indent=2)
    
    logger.info(f"Waitlist event logged: {event}")

def convert_to_24hr(time_str):
    """Convert time string from 12-hour format to 24-hour decimal format"""
    return datetime.strptime(time_str, "%I:%M%p").hour + datetime.strptime(time_str, "%I:%M%p").minute / 60

def create_calendar_plot(classes, inputColors, filename):
    """Create a visual calendar plot of the schedule"""
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
            logger.error(f"Error plotting class {cls}: {e}")

    plt.title("Weekly Calendar View", pad=20)
    plt.tight_layout()
    plt.subplots_adjust(top=0.90)
    plt.savefig(filename)
    plt.close()

def generate_schedule_pdf(schedule_data, inputColors):
    """Generate a PDF with the schedule data and calendar plot"""
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

        # Create calendar plot
        calendar_filename = f"calendar_plot_{uuid.uuid4().hex}.png"
        create_calendar_plot(schedule_data, inputColors, calendar_filename)
        elements.append(Image(calendar_filename, width=500, height=300))

        doc.build(elements)
        buffer.seek(0)
        
        # Clean up the temporary file
        if os.path.exists(calendar_filename):
            os.remove(calendar_filename)
        
        logger.info("PDF generated successfully")
        return buffer
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise

@app.route('/api/submit_request', methods=['POST'])
def submit_request():
    """Submit a new schedule generation request"""
    try:
        data = request.json
        courses = data.get('courses', [])
        preferences = data.get('preferences', '')
        term_year = data.get('term_year', '202501')
        email = data.get('email', '')
        
        # Validate input
        if not courses:
            return jsonify({'error': 'No courses provided'}), 400
        
        # Check if server is in cooldown mode
        if waitlist.is_ai_processing() and ai_processor._should_wait_for_cooldown():
            log_waitlist_event("request_rejected_cooldown", {
                "email": email,
                "courses_count": len(courses)
            })
            return jsonify({
                'error': 'Service is currently in cooldown mode. Please try again later.',
                'cooldown_mode': True
            }), 503
        
        # Create new request
        request_id = waitlist.new_request(email, courses, preferences, term_year)
        
        log_waitlist_event("request_submitted", {
            "request_id": str(request_id),
            "email": email,
            "courses_count": len(courses),
            "term_year": term_year
        })
        
        return jsonify({
            'request_id': str(request_id),
            'status': 'submitted',
            'message': 'Request submitted successfully. You can check status at /schedule/' + str(request_id)
        }), 200
        
    except Exception as e:
        logger.error(f"Error submitting request: {str(e)}")
        log_waitlist_event("request_error", {"error": str(e)})
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/schedule/<request_id>', methods=['GET'])
def get_schedule_status(request_id):
    """Get the status and result of a schedule request"""
    try:
        # Convert string to UUID
        request_uuid = uuid.UUID(request_id)
        
        # Get status from waitlist
        status = waitlist.get_status(request_uuid)
        
        if status == "not found":
            return jsonify({'error': 'Request not found'}), 404
        
        # Get response data
        response_data = waitlist.get_response(request_uuid)
        
        # Check if server is in cooldown mode
        cooldown_mode = ai_processor._should_wait_for_cooldown() if ai_processor else False
        
        result = {
            'request_id': request_id,
            'status': status,
            'cooldown_mode': cooldown_mode,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Add progress information
        if status == "initiated":
            result['progress'] = {
                'stage': 'Request submitted',
                'percentage': 10,
                'message': 'Your request has been submitted and is queued for processing.'
            }
        elif status == "extracting_courses":
            result['progress'] = {
                'stage': 'Fetching course data',
                'percentage': 30,
                'message': 'Fetching course information from Virginia Tech database...'
            }
        elif status == "courses_collected":
            result['progress'] = {
                'stage': 'Course data collected',
                'percentage': 50,
                'message': 'Course data has been collected. Starting AI processing...'
            }
        elif status == "ai_processing":
            result['progress'] = {
                'stage': 'AI processing',
                'percentage': 80,
                'message': 'AI is generating your optimal schedule...'
            }
        elif status == "done_processing":
            result['progress'] = {
                'stage': 'Complete',
                'percentage': 100,
                'message': 'Your schedule has been generated successfully!'
            }
            result['schedule'] = response_data
        elif status == "extraction_failed":
            result['progress'] = {
                'stage': 'Failed',
                'percentage': 0,
                'message': 'Failed to fetch course data. Please try again.'
            }
            result['error'] = 'Course data extraction failed'
        elif status == "ai_failed":
            result['progress'] = {
                'stage': 'Failed',
                'percentage': 0,
                'message': 'AI processing failed. Please try again.'
            }
            result['error'] = 'AI processing failed'
        
        # Add timeline information
        result['timeline'] = get_request_timeline(request_uuid)
        
        return jsonify(result), 200
        
    except ValueError:
        return jsonify({'error': 'Invalid request ID format'}), 400
    except Exception as e:
        logger.error(f"Error getting schedule status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def get_request_timeline(request_uuid):
    """Get timeline of events for a request"""
    timeline = []
    
    # Get logs for this request
    log_file = os.path.join(server_folder, "waitlist_logs.json")
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            logs = json.load(f)
        
        # Filter logs for this request
        request_logs = [log for log in logs if str(request_uuid) in str(log.get('data', {}))]
        
        # Create timeline
        for log in request_logs:
            if log['event'] == 'request_submitted':
                timeline.append({
                    'time': log['timestamp'],
                    'event': 'Request submitted',
                    'description': 'Your schedule request was submitted successfully'
                })
            elif log['event'] == 'courses_extracted':
                timeline.append({
                    'time': log['timestamp'],
                    'event': 'Course data fetched',
                    'description': 'Course information has been retrieved from Virginia Tech'
                })
            elif log['event'] == 'ai_processing_started':
                timeline.append({
                    'time': log['timestamp'],
                    'event': 'AI processing started',
                    'description': 'AI is now generating your optimal schedule'
                })
            elif log['event'] == 'ai_processing_completed':
                timeline.append({
                    'time': log['timestamp'],
                    'event': 'Processing completed',
                    'description': 'Your schedule has been generated successfully'
                })
    
    return timeline

@app.route('/api/download_schedule/<request_id>', methods=['POST'])
def download_schedule(request_id):
    """Download schedule as PDF"""
    try:
        # Convert string to UUID
        request_uuid = uuid.UUID(request_id)
        
        # Get schedule data
        schedule_data = waitlist.get_response(request_uuid)
        
        if schedule_data == "processing" or schedule_data == "not found":
            return jsonify({'error': 'Schedule not ready or not found'}), 404
        
        # Get colors from request
        colors = request.json.get('crnColors', {}) if request.json else {}
        
        # Generate PDF using the new implementation
        pdf_buffer = generate_schedule_pdf(schedule_data.get('classes', []), colors)
        
        log_waitlist_event("schedule_downloaded", {
            "request_id": str(request_uuid),
            "classes_count": len(schedule_data.get('classes', []))
        })
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"schedule_{request_id}.pdf",
            mimetype='application/pdf'
        )
        
    except ValueError:
        return jsonify({'error': 'Invalid request ID format'}), 400
    except Exception as e:
        logger.error(f"Error downloading schedule: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/waitlist_status', methods=['GET'])
def get_waitlist_status():
    """Get overall waitlist status"""
    try:
        status = {
            'total_requests': len(waitlist.get_waitlist()),
            'ai_processing': waitlist.is_ai_processing(),
            'cooldown_mode': ai_processor._should_wait_for_cooldown() if ai_processor else False,
            'queue_size': waitlist.get_queue_size(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Error getting waitlist status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get waitlist logs"""
    try:
        log_file = os.path.join(server_folder, "waitlist_logs.json")
        
        if not os.path.exists(log_file):
            return jsonify({'logs': []}), 200
        
        with open(log_file, 'r') as f:
            logs = json.load(f)
        
        # Return last 100 entries
        logs = logs[-100:] if len(logs) > 100 else logs
        
        return jsonify({'logs': logs}), 200
        
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'waitlist_initialized': waitlist is not None,
        'ai_processor_initialized': ai_processor is not None
    }), 200

if __name__ == '__main__':
    # Initialize server
    initialize_server()
    
    # Start the Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=False, host="0.0.0.0", port=port)
