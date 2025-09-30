from typing import List, Optional
from pydantic import BaseModel

class ActionItem(BaseModel):
    description: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None

class Decision(BaseModel):
    text: str
    owner: Optional[str] = None

class MomContent(BaseModel):
    title: str
    date: Optional[str] = None
    time: Optional[str] = None
    attendant: List[str] = []
    project_name: Optional[str] = None
    customer: Optional[str] = None
    table_of_content: List[str] = []
    main_content: str = ""
    # Legacy fields for compatibility
    attendees: List[str] = []
    agenda: List[str] = []
    summary: str = ""
    key_points: List[str] = []
    decisions: List[Decision] = []
    action_items: List[ActionItem] = []

class ProcessResponse(BaseModel):
    mom: MomContent
    transcript: Optional[str] = None
