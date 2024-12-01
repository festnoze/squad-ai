import uuid
from sqlalchemy import Column, String, DateTime, Table, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

# Association tables for many-to-many relationships, now using UUIDs
training_job_association = Table(
    'training_job',
    Base.metadata,
    Column('training_id', UUID(as_uuid=True), ForeignKey('trainings.id'), primary_key=True),
    Column('job_id', UUID(as_uuid=True), ForeignKey('jobs.id'), primary_key=True)
)

training_domain_association = Table(
    'training_domain',
    Base.metadata,
    Column('training_id', UUID(as_uuid=True), ForeignKey('trainings.id'), primary_key=True),
    Column('domain_id', UUID(as_uuid=True), ForeignKey('domains.id'), primary_key=True)
)

training_funding_association = Table(
    'training_funding',
    Base.metadata,
    Column('training_id', UUID(as_uuid=True), ForeignKey('trainings.id'), primary_key=True),
    Column('funding_id', UUID(as_uuid=True), ForeignKey('fundings.id'), primary_key=True)
)

training_diploma_association = Table(
    'training_diploma',
    Base.metadata,
    Column('training_id', UUID(as_uuid=True), ForeignKey('trainings.id'), primary_key=True),
    Column('diploma_id', UUID(as_uuid=True), ForeignKey('diplomas.id'), primary_key=True)
)

class Job(Base):
    __tablename__ = 'jobs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    changed = Column(DateTime, nullable=True)
    domain_id = Column(UUID(as_uuid=True), ForeignKey('domains.id'), nullable=True)
    
    domain = relationship("Domain", back_populates="jobs")
    trainings = relationship("Training", secondary=training_job_association, back_populates="jobs")


class Funding(Base):
    __tablename__ = 'fundings'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    changed = Column(DateTime, default=datetime.utcnow)
    paragraph = Column(String)
    
    trainings = relationship("Training", secondary=training_funding_association, back_populates="fundings")


class Training(Base):
    __tablename__ = 'trainings'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    changed = Column(DateTime)
    field_metatag = Column(String)
    
    # Foreign key column pointing to the Certification table
    certification_id = Column(UUID(as_uuid=True), ForeignKey('certifications.id'), nullable=True)
    
    # Establish the relationship with Certification (many-to-one)
    certification = relationship("Certification", back_populates="trainings")

    # Other relationships, for example, with Diploma, Funding, Domain, Job, etc.
    diplomas = relationship("Diploma", secondary=training_diploma_association, back_populates="trainings")
    fundings = relationship("Funding", secondary=training_funding_association, back_populates="trainings")
    domains = relationship("Domain", secondary=training_domain_association, back_populates="trainings")
    jobs = relationship("Job", secondary=training_job_association, back_populates="trainings")
    
    def __repr__(self):
        return f"<Training(title={self.title}, certification_id={self.certification_id})>"

class Domain(Base):
    __tablename__ = 'domains'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    changed = Column(DateTime, default=datetime.utcnow)
    
    jobs = relationship("Job", back_populates="domain")
    trainings = relationship("Training", secondary=training_domain_association, back_populates="domains")


class Diploma(Base):
    __tablename__ = 'diplomas'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    changed = Column(DateTime, default=datetime.utcnow)
    paragraph = Column(String)
    
    trainings = relationship("Training", secondary=training_diploma_association, back_populates="diplomas")


class Certification(Base):
    __tablename__ = 'certifications'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    changed = Column(DateTime)
    
    # Define the relationship to Training (one Certification can have many Trainings)
    trainings = relationship("Training", back_populates="certification", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Certification(title={self.title}, changed={self.changed})>"
