"""
Database models for the Team Feedback Tool

This tool is for collecting peer feedback and generating performance reports.
Completely separate from the bonus/compensation system.
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import json

Base = declarative_base()


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
    """Manager's own feedback for their team members"""
    __tablename__ = 'manager_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_uid = Column(String, ForeignKey('persons.user_id'), nullable=False)
    team_member_uid = Column(String, ForeignKey('persons.user_id'), nullable=False)

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


def init_db(db_path='feedback.db'):
    """Initialize database and return session"""
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
