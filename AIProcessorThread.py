import threading
import time
import queue
import os
import json
from datetime import datetime, timezone
from AIProcessor import AIProcessor
from AIResponse import AIResponse

class AIProcessorThread:
    def __init__(self, waitlist, ai_config=None):
        """
        Initialize the AI Processor Thread with queue management
        
        Args:
            waitlist: WaitList instance to monitor for status changes
            ai_config: Configuration for AIProcessor (required)
        """
        if ai_config is None:
            raise ValueError("AI config is required for AIProcessorThread")
            
        self.waitlist = waitlist
        self.ai_processor = AIProcessor(ai_config)
        self.processing_queue = queue.Queue()
        self.thread = None
        self.running = False
        self.monitor_interval = 2  # Check for status changes every 2 seconds
        self.server_folder = waitlist.server_folder
    
    def log_event(self, event, data=None):
        """Log events to waitlist logs"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data": data or {}
        }
        
        log_file = os.path.join(self.server_folder, "waitlist_logs.json")
        
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
        
        print(f"Waitlist event logged: {event}")
        
    def start(self):
        """Start the AI processor thread"""
        if self.thread is None or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            print("AI Processor Thread started")
    
    def stop(self):
        """Stop the AI processor thread"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            print("AI Processor Thread stopped")
    
    def _run(self):
        """Main thread loop that monitors status changes and processes requests"""
        while self.running:
            try:
                # Check for status changes in the waitlist
                self._check_status_changes()
                
                # Process items in the queue
                self._process_queue()
                
                # Sleep before next iteration
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                print(f"Error in AI Processor Thread: {e}")
                time.sleep(self.monitor_interval)
    
    def _check_status_changes(self):
        """Check for requests that have changed status to courses_collected"""
        try:
            for response in self.waitlist.waitlist:
                if response.stage == "courses_collected" and not self._is_in_queue(response.id):
                    # Add to processing queue
                    self.processing_queue.put(response)
                    self.log_event("ai_processing_queued", {
                        "request_id": str(response.id),
                        "email": response.email
                    })
                    print(f"Added request {response.id} to AI processing queue")
                    
        except Exception as e:
            print(f"Error checking status changes: {e}")
            self.log_event("status_check_error", {"error": str(e)})
    
    def _is_in_queue(self, request_id):
        """Check if a request is already in the processing queue"""
        try:
            # Convert queue to list to check contents
            queue_items = list(self.processing_queue.queue)
            return any(item.id == request_id for item in queue_items)
        except:
            return False
    
    def _process_queue(self):
        """Process items in the queue one by one"""
        try:
            while not self.processing_queue.empty() and self.running:
                # Check if AI processor is on cooldown
                if self._is_on_cooldown():
                    self.waitlist.on_waitlist = True
                    print("AI Processor on cooldown - setting on_waitlist to True")
                    break
                else:
                    self.waitlist.on_waitlist = False
                
                # Get next item from queue
                try:
                    response = self.processing_queue.get_nowait()
                except queue.Empty:
                    break
                
                # Process the request
                self._process_single_request(response)
                
        except Exception as e:
            print(f"Error processing queue: {e}")
    
    def _is_on_cooldown(self):
        """Check if the AI processor is currently on cooldown"""
        try:
            # Check if we should wait for cooldown
            if self.ai_processor._should_wait_for_cooldown():
                return True
            
            # Check if all API keys are exhausted
            if (self.ai_processor.quota_error_count > 0 and 
                self.ai_processor.last_quota_exhausted is not None):
                return True
                
            return False
        except:
            return False
    
    def _process_single_request(self, response):
        """Process a single request through the AI processor"""
        try:
            print(f"Processing request {response.id} with AI")
            
            # Update stage to processing
            response.update_stage("ai_processing")
            self.waitlist.save()
            
            self.log_event("ai_processing_started", {
                "request_id": str(response.id),
                "email": response.email
            })
            
            # Prepare the AI prompt with courses and preferences
            ai_prompt = self._build_ai_prompt(response)
            
            # Process with AI
            ai_result = self.ai_processor.process_ai_request(ai_prompt, response.courses_requested)
            
            # Store the AI response
            response.set_ai_response(ai_result)
            
            # Save the updated response
            self.waitlist.save()
            
            self.log_event("ai_processing_completed", {
                "request_id": str(response.id),
                "email": response.email,
                "classes_count": len(ai_result.get('classes', [])) if isinstance(ai_result, dict) else 0
            })
            
            print(f"Completed processing request {response.id}")
            
        except Exception as e:
            print(f"Error processing request {response.id}: {e}")
            # Update stage to processing_failed
            response.set_ai_error(str(e))
            self.waitlist.save()
            
            self.log_event("ai_processing_failed", {
                "request_id": str(response.id),
                "email": response.email,
                "error": str(e)
            })
    
    def _build_ai_prompt(self, response):
        """Build the AI prompt using course data and preferences"""
        try:
            prompt_parts = []
            
            # Add course information
            prompt_parts.append("Required Courses:")
            for course in response.courses_requested:
                department = course.get('department', '')
                number = course.get('number', '')
                prompt_parts.append(f"- {department}{number}")
            
            # Add available course sections
            if response.course_timetable:
                prompt_parts.append("\nAvailable Course Sections:")
                for course_code, course_data in response.course_timetable.items():
                    if not course_data.empty:
                        prompt_parts.append(f"\n{course_code}:")
                        # Filter out comment-heavy or malformed rows
                        cleaned_data = self._clean_course_data(course_data)
                        for _, section in cleaned_data.iterrows():
                            prompt_parts.append(
                                f"  CRN: {section['CRN']}, "
                                f"Course: {section['Course']}, "
                                f"Title: {section['Title']}, "
                                f"Type: {section['Schedule Type']}, "
                                f"Instructor: {section['Instructor']}, "
                                f"Days: {section['Days']}, "
                                f"Time: {section['Begin Time']} - {section['End Time']}, "
                                f"Location: {section['Location']}"
                            )
            
            # Add preferences
            if response.preferences:
                prompt_parts.append("\nPreferences:")
                # Handle both string and dictionary preferences
                if isinstance(response.preferences, dict):
                    for key, value in response.preferences.items():
                        prompt_parts.append(f"- {key}: {value}")
                elif isinstance(response.preferences, str) and response.preferences.strip():
                    prompt_parts.append(f"- {response.preferences}")
            
            return "\n".join(prompt_parts)
            
        except Exception as e:
            print(f"Error building AI prompt: {e}")
            return "Generate a schedule for the requested courses."
    
    def _clean_course_data(self, course_data):
        """Clean course data by removing comment-heavy and malformed rows"""
        import pandas as pd
        import re
        
        if course_data.empty:
            return course_data
        
        # Create a copy to avoid modifying the original
        cleaned_data = course_data.copy()
        
        # Filter out rows that are likely comments or malformed data
        def is_valid_row(row):
            # Get all field values as strings
            crn = str(row.get('CRN', '')).strip()
            course = str(row.get('Course', '')).strip()
            title = str(row.get('Title', '')).strip()
            schedule_type = str(row.get('Schedule Type', '')).strip()
            instructor = str(row.get('Instructor', '')).strip()
            days = str(row.get('Days', '')).strip()
            begin_time = str(row.get('Begin Time', '')).strip()
            end_time = str(row.get('End Time', '')).strip()
            location = str(row.get('Location', '')).strip()
            exam_code = str(row.get('Exam Code', '')).strip()
            
            # Skip rows with exam code information (not needed for scheduling)
            if exam_code and exam_code != '':
                return False
            
            # Check if this is an "* Additional Times *" entry - these should be preserved
            if ('* Additional Times *' in title or '* Additional Time *' in title or
                '* Additional Times *' in schedule_type or '* Additional Time *' in schedule_type):
                return True
            
            # Skip rows that are clearly malformed or contain comments
            comment_indicators = [
                'Comments for CRN', 'Each CRN is a combined', 'Students outside',
                'Graduate students looking', 'To force/add', 'vtmit@vt.edu',
                'Show All Types', 'Course Number', 'Course Request Number',
                'Display', 'ALL Sections', 'ONLY OPEN Sections', 'Course Modality',
                'ALL Modalities', 'Face-to-Face Instruction', 'Hybrid',
                'Online with Synchronous', 'Online: Asynchronous'
            ]
            
            # Check if any field contains comment indicators
            all_fields = [crn, course, title, schedule_type, instructor, days, begin_time, end_time, location]
            for field in all_fields:
                for indicator in comment_indicators:
                    if indicator in field:
                        return False
            
            # Check if CRN is a valid number (not empty, not '?', not a comment)
            if not crn or crn == '?' or not crn.isdigit():
                return False
            
            # Check if Course field contains valid course info (not comments)
            if not course or course == '' or len(course) > 20:
                return False
            
            # Check if Title is not a comment and not too long
            if not title or len(title) > 100:
                return False
            
            # Check if Schedule Type is valid (not empty, not comments)
            if not schedule_type or len(schedule_type) > 20:
                return False
            
            # Check if Instructor field is not a long comment
            if len(instructor) > 50:
                return False
            
            # Check if Days field contains valid day codes
            if not days or len(days) > 10:
                return False
            
            # Check if times are valid
            if not begin_time or not end_time or len(begin_time) > 10 or len(end_time) > 10:
                return False
            
            # Check if location is reasonable
            if not location or len(location) > 50:
                return False
            
            return True
        
        # Apply the filter
        valid_mask = cleaned_data.apply(is_valid_row, axis=1)
        cleaned_data = cleaned_data[valid_mask]
        
        # Remove exam code column if it exists
        if 'Exam Code' in cleaned_data.columns:
            cleaned_data = cleaned_data.drop('Exam Code', axis=1)
        
        return cleaned_data
    
    def get_queue_size(self):
        """Get the current size of the processing queue"""
        return self.processing_queue.qsize()
    
    def is_processing(self):
        """Check if the thread is currently processing requests"""
        return self.running and (not self.processing_queue.empty() or self._is_on_cooldown())
    
    def get_status(self):
        """Get the current status of the AI processor thread"""
        return {
            "running": self.running,
            "queue_size": self.get_queue_size(),
            "on_cooldown": self._is_on_cooldown(),
            "on_waitlist": self.waitlist.on_waitlist
        }
