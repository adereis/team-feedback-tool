"""
Database models for the Team Feedback Tool

This tool is for collecting peer feedback and generating performance reports.
Completely separate from the bonus/compensation system.
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import json
import re
import hashlib

Base = declarative_base()


def name_to_user_id(name):
    """Generate a derived user_id from a name.

    Used for Workday-only users who don't have an orgchart user_id.
    Returns a predictable ID based on name hash (e.g., 'wd_a1b2c3d4').

    Args:
        name: Person's display name

    Returns:
        Derived user_id string prefixed with 'wd_'
    """
    # Normalize name: lowercase and strip whitespace
    normalized = name.lower().strip()
    # Generate SHA-1 hash and take first 8 characters
    hash_hex = hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:8]
    return f'wd_{hash_hex}'


class Person(Base):
    """Person imported from orgchart export"""
    __tablename__ = 'persons'

    user_id = Column(String, primary_key=True)  # Unique identifier
    name = Column(String, nullable=False)
    job_title = Column(String)
    location = Column(String)
    email = Column(String)
    manager_uid = Column(String, ForeignKey('persons.user_id'))

    # Relationships
    manager = relationship("Person", remote_side=[user_id], backref="direct_reports")
    feedback_given = relationship("Feedback", foreign_keys="Feedback.from_user_id", backref="giver")
    feedback_received = relationship("Feedback", foreign_keys="Feedback.to_user_id", backref="receiver")

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'name': self.name,
            'job_title': self.job_title,
            'location': self.location,
            'email': self.email,
            'manager_uid': self.manager_uid
        }


class Feedback(Base):
    """Peer feedback from one person to another"""
    __tablename__ = 'feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_user_id = Column(String, ForeignKey('persons.user_id'), nullable=False)
    to_user_id = Column(String, ForeignKey('persons.user_id'), nullable=False)

    # Tenets - stored as JSON arrays of tenet IDs
    strengths = Column(Text)  # JSON array: ["tenet_id1", "tenet_id2", "tenet_id3"]
    improvements = Column(Text)  # JSON array: ["tenet_id1", "tenet_id2"]

    # Text feedback
    strengths_text = Column(Text)  # One text field for all strength explanations
    improvements_text = Column(Text)  # One text field for all improvement explanations

    def get_strengths(self):
        """Parse strengths JSON array"""
        return json.loads(self.strengths) if self.strengths else []

    def set_strengths(self, tenet_ids):
        """Set strengths as JSON array"""
        self.strengths = json.dumps(tenet_ids)

    def get_improvements(self):
        """Parse improvements JSON array"""
        return json.loads(self.improvements) if self.improvements else []

    def set_improvements(self, tenet_ids):
        """Set improvements as JSON array"""
        self.improvements = json.dumps(tenet_ids)

    def to_dict(self):
        return {
            'id': self.id,
            'from_user_id': self.from_user_id,
            'to_user_id': self.to_user_id,
            'strengths': self.get_strengths(),
            'improvements': self.get_improvements(),
            'strengths_text': self.strengths_text,
            'improvements_text': self.improvements_text
        }


class ManagerFeedback(Base):
    """Manager's own feedback for their team members.

    Note: team_member_uid may be either:
    1. A real user_id from the persons table (orgchart workflow)
    2. A derived ID from name_to_user_id() (Workday-only workflow)
    """
    __tablename__ = 'manager_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_uid = Column(String, nullable=False)  # Manager's user_id or derived ID
    team_member_uid = Column(String, nullable=False)  # Team member's user_id or derived ID

    # Manager's selected tenets (highlighted in butterfly chart)
    selected_strengths = Column(Text)  # JSON array
    selected_improvements = Column(Text)  # JSON array

    # Manager's text feedback
    feedback_text = Column(Text)

    def get_selected_strengths(self):
        return json.loads(self.selected_strengths) if self.selected_strengths else []

    def set_selected_strengths(self, tenet_ids):
        self.selected_strengths = json.dumps(tenet_ids)

    def get_selected_improvements(self):
        return json.loads(self.selected_improvements) if self.selected_improvements else []

    def set_selected_improvements(self, tenet_ids):
        self.selected_improvements = json.dumps(tenet_ids)

    def to_dict(self):
        return {
            'id': self.id,
            'manager_uid': self.manager_uid,
            'team_member_uid': self.team_member_uid,
            'selected_strengths': self.get_selected_strengths(),
            'selected_improvements': self.get_selected_improvements(),
            'feedback_text': self.feedback_text
        }


class WorkdayFeedback(Base):
    """Feedback imported from Workday XLSX export.

    Supports two types of feedback:
    1. Structured (tool-assisted): Contains [TENETS] marker with tenet selections
    2. Generic: Free-text feedback from other WD workflows
    """
    __tablename__ = 'workday_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # From XLSX columns (names only, no IDs available in WD export)
    about = Column(String, nullable=False)        # Column B: recipient name
    from_name = Column(String, nullable=False)    # Column E: provider name
    question = Column(Text)                        # Column F: feedback question
    feedback = Column(Text)                        # Column G: raw feedback text
    asked_by = Column(String)                      # Column H: who requested
    request_type = Column(String)                  # Column I: "Requested by Self" or "Requested by Others"
    date = Column(DateTime)                        # Column J: feedback date

    # Parsed structured data (null if generic feedback)
    is_structured = Column(Integer, default=0)     # 1 if contains [TENETS] marker
    strengths = Column(Text)                       # JSON array of tenet IDs (if structured)
    improvements = Column(Text)                    # JSON array of tenet IDs (if structured)
    strengths_text = Column(Text)                  # Parsed strengths text (if structured)
    improvements_text = Column(Text)               # Parsed improvements text (if structured)

    # Unique constraint for deduplication on re-import
    __table_args__ = (
        UniqueConstraint('about', 'from_name', 'question', 'date', name='unique_wd_feedback'),
    )

    # Regex pattern for parsing structured feedback
    TENET_MARKER_PATTERN = re.compile(
        r'\[TENETS\]\s*'
        r'Strengths:\s*([^\n]*)\s*'
        r'Improvements:\s*([^\n]*)\s*'
        r'\[/TENETS\]',
        re.IGNORECASE
    )

    def parse_structured_feedback(self):
        """Parse feedback text for [TENETS] marker and extract structured data.

        Returns True if structured feedback was found and parsed.
        """
        if not self.feedback:
            return False

        match = self.TENET_MARKER_PATTERN.search(self.feedback)
        if not match:
            self.is_structured = 0
            return False

        self.is_structured = 1

        # Parse tenet IDs from comma-separated list
        strengths_raw = match.group(1).strip()
        improvements_raw = match.group(2).strip()

        strength_ids = [s.strip() for s in strengths_raw.split(',') if s.strip()]
        improvement_ids = [s.strip() for s in improvements_raw.split(',') if s.strip()]

        self.strengths = json.dumps(strength_ids)
        self.improvements = json.dumps(improvement_ids)

        # Extract text sections after the marker
        after_marker = self.feedback[match.end():].strip()

        # Look for "Strengths:" and "Areas for Improvement:" sections
        strengths_match = re.search(
            r'Strengths?:\s*(.*?)(?=Areas?\s+for\s+Improvement|$)',
            after_marker,
            re.IGNORECASE | re.DOTALL
        )
        improvements_match = re.search(
            r'Areas?\s+for\s+Improvement:\s*(.*?)$',
            after_marker,
            re.IGNORECASE | re.DOTALL
        )

        if strengths_match:
            self.strengths_text = strengths_match.group(1).strip()
        if improvements_match:
            self.improvements_text = improvements_match.group(1).strip()

        return True

    def get_strengths(self):
        """Parse strengths JSON array"""
        return json.loads(self.strengths) if self.strengths else []

    def get_improvements(self):
        """Parse improvements JSON array"""
        return json.loads(self.improvements) if self.improvements else []

    def to_dict(self):
        return {
            'id': self.id,
            'about': self.about,
            'from_name': self.from_name,
            'question': self.question,
            'feedback': self.feedback,
            'asked_by': self.asked_by,
            'request_type': self.request_type,
            'date': self.date.isoformat() if self.date else None,
            'is_structured': bool(self.is_structured),
            'strengths': self.get_strengths(),
            'improvements': self.get_improvements(),
            'strengths_text': self.strengths_text,
            'improvements_text': self.improvements_text
        }


def init_db(db_path='feedback.db'):
    """Initialize database and return session"""
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
