import threading
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

class AIResponse:
    def __init__(self, id, courses_requested, semester, preferences, email=None):
        self.id = id
        self.courses_requested = courses_requested
        self.semester = semester
        self.email = email
        self.preferences = preferences
        self.stage = "initiated"
        self.course_timetable = None
        self.ai_response = None
        self._extraction_thread = None
        self._extraction_error = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        
        # Start course extraction asynchronously
        self._start_course_extraction()
    
    def to_dict(self):
        # Convert DataFrames to JSON-serializable format
        course_timetable_serializable = {}
        if self.course_timetable:
            for course_code, df in self.course_timetable.items():
                if df is not None and not df.empty:
                    course_timetable_serializable[course_code] = df.to_dict('records')
                else:
                    course_timetable_serializable[course_code] = []
        
        return {
            "id": str(self.id),
            "courses_requested": self.courses_requested,
            "semester": self.semester,
            "email": self.email,
            "stage": self.stage,
            "course_timetable": course_timetable_serializable,
            "ai_response": self.ai_response,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    def from_dict(self, data):
        from uuid import UUID
        id_value = data.get('id', None)
        # Handle both string and UUID object cases
        if isinstance(id_value, str):
            self.id = UUID(id_value)
        else:
            self.id = id_value
        self.courses_requested = data.get('courses_requested', None)
        self.semester = data.get('semester', None)
        self.email = data.get('email', None)
        self.stage = data.get('stage', None)
        
        # Convert serialized course timetable back to DataFrames
        course_timetable_data = data.get('course_timetable', None)
        if course_timetable_data:
            self.course_timetable = {}
            for course_code, records in course_timetable_data.items():
                if records and len(records) > 0:
                    self.course_timetable[course_code] = pd.DataFrame(records)
                else:
                    self.course_timetable[course_code] = pd.DataFrame()
        else:
            self.course_timetable = None
            
        self.ai_response = data.get('ai_response', None)
        self.preferences = data.get('preferences', None)
        self.created_at = datetime.fromisoformat(data.get('created_at', datetime.now().isoformat()))
        self.updated_at = datetime.fromisoformat(data.get('updated_at', datetime.now().isoformat()))
        return self
    
    def _start_course_extraction(self):
        """Start the course extraction process in a separate thread"""
        self.stage = "extracting_courses"
        self._extraction_thread = threading.Thread(target=self._extract_courses_async)
        self._extraction_thread.daemon = True
        self._extraction_thread.start()
    
    def _extract_courses_async(self):
        """Extract course timetable data asynchronously"""
        try:
            self.course_timetable = {}
            
            for course in self.courses_requested:
                department = course.get('department', '')
                number = course.get('number', '')
                course_code = department + number
                
                # Extract course data
                course_data = self._extract_course_details(department, number, self.semester)
                
                if course_data is not None and not course_data.empty:
                    self.course_timetable[course_code] = course_data
                else:
                    print(f"Warning: No data found for course {course_code}")
            
            # Update stage to courses collected
            self.stage = "courses_collected"
            self.updated_at = datetime.now()
            print(f"Course extraction completed for {len(self.course_timetable)} courses")
            
        except Exception as e:
            self._extraction_error = str(e)
            self.stage = "extraction_failed"
            print(f"Error during course extraction: {e}")
    
    def _extract_course_details(self, department, coursenumber, term_year):
        """Extract course details from Virginia Tech's course system"""
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
                "disp_comments_in": "N",  # Changed to N to reduce comments
                "sess_code": "%",
                "BTN_PRESSED": "FIND class sections",
                "inst_name": ""
            }
            
            response = requests.post(url=url, data=form_data, timeout=30)
            response.raise_for_status()
            
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
                exam_code = exam_cell.find('a').text.strip() if exam_cell and exam_cell.find('a') else ""
                
                # Skip rows with invalid CRN or malformed data
                if not crn or not crn.isdigit():
                    continue
                
                # Skip rows that are clearly comments or malformed
                if any(indicator in str(cells).lower() for indicator in [
                    'comments for crn', 'each crn is a combined', 'students outside',
                    'graduate students looking', 'to force/add', 'show all types',
                    'course number', 'course request number', 'display'
                ]):
                    continue
                
                # Add the main course entry
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
                
                # Check for additional times in the same row
                # Look for patterns like "* Additional Times *" followed by day/time info
                row_text = row.get_text()
                if '* Additional Times *' in row_text or '* Additional Time *' in row_text:
                    # Try to extract additional time information
                    additional_times = self._extract_additional_times(row_text, crn, course, title, instructor)
                    courses_data.extend(additional_times)
            
            return pd.DataFrame(courses_data)
            
        except Exception as e:
            print(f"Error extracting course details for {department}{coursenumber}: {str(e)}")
            return None
    
    def _extract_additional_times(self, row_text, crn, course, title, instructor):
        """Extract additional times from row text"""
        import re
        
        additional_times = []
        
        # Look for patterns like "* Additional Times *" followed by day/time info
        # Pattern: * Additional Times * followed by day, time, location
        pattern = r'\* Additional Times?\s*\*\s*([A-Z])\s+(\d{1,2}:\d{2}[AP]M)\s+(\d{1,2}:\d{2}[AP]M)\s+([A-Z0-9\s]+)'
        matches = re.findall(pattern, row_text)
        
        for match in matches:
            day, start_time, end_time, location = match
            additional_times.append({
                'CRN': crn,
                'Course': course,
                'Title': title,
                'Schedule Type': 'Lab',  # Additional times are usually labs
                'Modality': 'Face-to-Face Instruction',
                'Credit Hours': '',
                'Capacity': '',
                'Instructor': instructor,
                'Days': day.strip(),
                'Begin Time': start_time.strip(),
                'End Time': end_time.strip(),
                'Location': location.strip(),
                'Exam Code': ''
            })
        
        return additional_times
    
    def get_course_timetable(self):
        """Get the course timetable data (returns None if extraction is still in progress)"""
        return self.course_timetable
    
    def is_extraction_complete(self):
        """Check if course extraction is complete"""
        return self.stage in ["courses_collected", "extraction_failed"]
    
    def get_extraction_error(self):
        """Get any error that occurred during extraction"""
        return self._extraction_error
    
    def wait_for_extraction(self, timeout=60):
        """Wait for course extraction to complete with timeout"""
        if self._extraction_thread and self._extraction_thread.is_alive():
            self._extraction_thread.join(timeout=timeout)
        return self.is_extraction_complete()
    
    def update_stage(self, new_stage):
        """Update the stage and timestamp"""
        self.stage = new_stage
        self.updated_at = datetime.now()
    
    def set_ai_response(self, response):
        """Set the AI response and update stage"""
        self.ai_response = response
        self.stage = "done_processing"
        self.updated_at = datetime.now()
    
    def set_ai_error(self, error):
        """Set AI processing error and update stage"""
        self._extraction_error = error
        self.stage = "ai_failed"
        self.updated_at = datetime.now()
    
    