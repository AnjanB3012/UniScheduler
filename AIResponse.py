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
        # Convert DataFrames to JSON-serializable format using cleaned data
        course_timetable_serializable = {}
        if self.course_timetable:
            # Use cleaned data to avoid bloated/duplicate records
            cleaned_data = self.get_clean_course_data()
            for course_code, df in cleaned_data.items():
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

    @classmethod
    def from_dict(cls, data):
        from uuid import UUID
        instance = cls.__new__(cls)
        
        id_value = data.get('id', None)
        # Handle both string and UUID object cases
        if isinstance(id_value, str):
            instance.id = UUID(id_value)
        else:
            instance.id = id_value
        instance.courses_requested = data.get('courses_requested', None)
        instance.semester = data.get('semester', None)
        instance.email = data.get('email', None)
        instance.stage = data.get('stage', None)
        
        # Convert serialized course timetable back to DataFrames
        course_timetable_data = data.get('course_timetable', None)
        if course_timetable_data:
            instance.course_timetable = {}
            for course_code, records in course_timetable_data.items():
                if records and len(records) > 0:
                    instance.course_timetable[course_code] = pd.DataFrame(records)
                else:
                    instance.course_timetable[course_code] = pd.DataFrame()
        else:
            instance.course_timetable = None
            
        instance.ai_response = data.get('ai_response', None)
        instance.preferences = data.get('preferences', None)
        instance.created_at = datetime.fromisoformat(data.get('created_at', datetime.now().isoformat()))
        instance.updated_at = datetime.fromisoformat(data.get('updated_at', datetime.now().isoformat()))
        
        # Set other instance variables that would normally be set in __init__
        instance._extraction_thread = None
        instance._extraction_error = None
        
        return instance
    
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
        """Extract course details from Virginia Tech's course system - captures all time slots including labs/recitations"""
        try:
            url = "https://selfservice.banner.vt.edu/ssb/HZSKVTSC.P_ProcRequest"
            form_data = {
                "CAMPUS": "0",
                "TERMYEAR": term_year,
                "CORE_CODE": "AR%",
                "SUBJ_CODE": department.upper(),
                "CRSE_NUMBER": coursenumber,
                "CRSE_TITLE": "",
                "BEGIN_HH": "0",
                "BEGIN_MI": "0",
                "BEGIN_AP": "A",
                "END_HH": "0",
                "END_MI": "0",
                "END_AP": "A",
                "DAY_CODE": "M",
                "DAY_CODE": "T",
                "DAY_CODE": "W",
                "DAY_CODE": "R",
                "DAY_CODE": "F",
                "DAY_CODE": "S",
                "DAY_CODE": "U",
                "DETAIL_PTR": "",
                "BTN_PRESSED": "FIND class sections",
                "inst_name": ""
            }
            
            response = requests.post(url=url, data=form_data, timeout=30)
            response.raise_for_status()
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find the main data table
            data_table = soup.find('table', class_='dataentrytable')
            if not data_table:
                return pd.DataFrame()
            
            # Extract all time slots including additional times
            sections = []
            rows = data_table.find_all('tr')
            
            current_crn = None
            current_course_info = {}
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 8:
                    continue
                
                # Check if this is a main CRN row (has CRN link in first cell)
                crn_link = cells[0].find('a', href=lambda x: x and 'CRN=' in x)
                if crn_link:
                    crn = crn_link.find('b')
                    if crn and crn.text.strip().isdigit():
                        current_crn = crn.text.strip()
                        
                        # Extract basic course info for this CRN
                        current_course_info = {
                            'CRN': current_crn,
                            'Course': cells[1].text.strip(),
                            'Title': cells[2].text.strip(),
                            'Schedule_Type': cells[3].text.strip(),
                            'Modality': cells[4].text.strip(),
                            'Credit_Hours': cells[5].text.strip(),
                            'Instructor': cells[7].text.strip()
                        }
                        
                        # Extract main time slot (cells 8-11)
                        if len(cells) >= 12:
                            time_info = {
                                'Days': cells[8].text.strip(),
                                'Begin_Time': cells[9].text.strip(),
                                'End_Time': cells[10].text.strip(),
                                'Location': self._clean_location_field(cells[11].text.strip())
                            }
                            
                            if time_info['Days'] and time_info['Begin_Time'] and time_info['End_Time']:
                                section = {**current_course_info, **time_info}
                                sections.append(section)
                
                # Check if this is an additional time row (has "* Additional Times *" in cell 4)
                elif (current_crn and len(cells) >= 8 and 
                      cells[4].text.strip() == "* Additional Times *"):
                    
                    # Extract additional time information (cells 5-8)
                    days = cells[5].text.strip() if len(cells) > 5 else ""
                    begin_time = cells[6].text.strip() if len(cells) > 6 else ""
                    end_time = cells[7].text.strip() if len(cells) > 7 else ""
                    location = self._clean_location_field(cells[8].text.strip()) if len(cells) > 8 else ""
                    
                    # Only add if we have valid time data
                    if days and begin_time and end_time:
                        additional_time_info = {
                            'Days': days,
                            'Begin_Time': begin_time,
                            'End_Time': end_time,
                            'Location': location
                        }
                        
                        section = {**current_course_info, **additional_time_info}
                        sections.append(section)
            
            # Convert to DataFrame and clean
            if sections:
                df = pd.DataFrame(sections)
                # Remove duplicates and clean data
                df = df.drop_duplicates(subset=['CRN', 'Days', 'Begin_Time', 'End_Time'])
                df = df.dropna(subset=['CRN', 'Course', 'Title'])
                return df
            else:
                return pd.DataFrame()
            
        except Exception as e:
            print(f"Error extracting course details for {department}{coursenumber}: {str(e)}")
            return None
    
    def _clean_location_field(self, location):
        """Clean location field by removing extra data and formatting"""
        if not location:
            return ""
        
        # Remove newlines and extra whitespace
        location = location.replace('\n', ' ').replace('\r', ' ')
        
        # Remove extra data that gets mixed in (like CRN numbers and department codes)
        import re
        
        # Remove patterns like "13378 CS" or similar number-letter combinations
        location = re.sub(r'\s+\d+\s+[A-Z]+\s*$', '', location)
        location = re.sub(r'\s+\d+\s*$', '', location)
        
        # Clean up multiple spaces
        location = re.sub(r'\s+', ' ', location)
        
        return location.strip()
    
    def get_clean_course_data(self):
        """Get cleaned course data with proper deduplication"""
        if not self.course_timetable:
            return {}
        
        cleaned_data = {}
        for course_code, df in self.course_timetable.items():
            if df is not None and not df.empty:
                # Remove duplicates based on CRN, Days, Begin_Time, End_Time (using underscore format)
                df_cleaned = df.drop_duplicates(subset=['CRN', 'Days', 'Begin_Time', 'End_Time'])
                
                # Clean location fields
                if 'Location' in df_cleaned.columns:
                    df_cleaned['Location'] = df_cleaned['Location'].apply(self._clean_location_field)
                
                # Remove rows with empty essential fields
                df_cleaned = df_cleaned.dropna(subset=['CRN', 'Course', 'Title', 'Schedule_Type'])
                df_cleaned = df_cleaned[df_cleaned['CRN'].str.strip() != '']
                df_cleaned = df_cleaned[df_cleaned['Course'].str.strip() != '']
                df_cleaned = df_cleaned[df_cleaned['Title'].str.strip() != '']
                
                cleaned_data[course_code] = df_cleaned
        
        return cleaned_data
    
    
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
    
    