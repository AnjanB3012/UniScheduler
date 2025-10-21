import os       
import json
from uuid import uuid4
from AIResponse import AIResponse
from AIProcessor import AIProcessor
from AIProcessorThread import AIProcessorThread

class WaitList:
    def __init__(self, server_folder, ai_config):
        if ai_config is None:
            raise ValueError("AI config is required for WaitList")
            
        self.server_folder = server_folder
        self.on_waitlist = False
        
        # Ensure server folder exists
        if not os.path.exists(self.server_folder):
            os.makedirs(self.server_folder)
        
        # Check if waitlist.json exists
        waitlist_file = os.path.join(self.server_folder, "waitlist.json")
        if os.path.exists(waitlist_file):
            self.from_dict(json.load(open(waitlist_file)))
        else:
            self.waitlist = []
            with open(waitlist_file, "w") as f:
                json.dump([], f)
        self.save()
        
        # Initialize AI Processor Thread
        self.ai_processor_thread = AIProcessorThread(self, ai_config)
        self.ai_processor_thread.start()
    
    def new_request(self, email, courses_requested, preferences, semester="202501"):
        id = uuid4()
        self.waitlist.append(AIResponse(id, courses_requested, semester, preferences, email))
        self.save()
        return id
        
    def get_status(self, id):
        for response in self.waitlist:
            if response.id == id:
                return response.stage
        return "not found"
    
    def get_response(self, id):
        for response in self.waitlist:
            if response.id == id:
                if response.stage == "done_processing":
                    return response.ai_response
                else:
                    return "processing"
            else:
                return "not found"
    
    def get_waitlist(self):
        return self.waitlist
    
    def save(self):
        with open(os.path.join(self.server_folder, "waitlist.json"), "w") as f:
            json.dump([response.to_dict() for response in self.waitlist], f)
    
    def from_dict(self, data):
        self.waitlist = [AIResponse.from_dict(response) for response in data]
        return self
    
    def get_ai_processor_status(self):
        """Get the current status of the AI processor thread"""
        return self.ai_processor_thread.get_status()
    
    def stop_ai_processor(self):
        """Stop the AI processor thread"""
        self.ai_processor_thread.stop()
    
    def restart_ai_processor(self):
        """Restart the AI processor thread"""
        self.ai_processor_thread.stop()
        self.ai_processor_thread.start()
    
    def get_queue_size(self):
        """Get the current size of the AI processing queue"""
        return self.ai_processor_thread.get_queue_size()
    
    def is_ai_processing(self):
        """Check if the AI processor is currently processing requests"""
        return self.ai_processor_thread.is_processing()