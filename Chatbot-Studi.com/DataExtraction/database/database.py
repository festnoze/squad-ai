import os
from datetime import datetime
import uuid
from dateutil import parser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Job, Funding, Training, Domain, Diploma, Certification
from common_tools.helpers import JsonHelper

class DB:
    def __init__(self):
        # Initialize the SQLite engine
        self.engine = create_engine('sqlite:///database//database.db', echo=True)
        
        # Create a session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_database(self):
        # Create all tables in the SQLite database
        Base.metadata.create_all(bind=self.engine)
        print("Database and tables created successfully!")

    def get_session(self):
        # Return a new session instance from the session factory
        return self.SessionLocal()

    def add_data(self):
        # Obtain a session
        session = self.get_session()
        
        try:
            # Add a new domain
            new_domain = Domain(title="Software Development")
            session.add(new_domain)
            session.commit()

            # Add a job related to the domain
            new_job = Job(title="Backend Developer", domain=new_domain)
            session.add(new_job)
            session.commit()

            # Query the data
            jobs = session.query(Job).all()
            for job in jobs:
                print(f"Job Title: {job.title}, Domain: {job.domain.title}")

        except Exception as e:
            session.rollback()  # Rollback the transaction in case of an error
            print(f"An error occurred: {e}")

        finally:
            # Close the session regardless of whether an error occurred
            session.close()

    def load_data(self):
        # Obtain a session
        session = self.get_session()
        
        try:
            # Fetch all jobs from the database
            jobs = session.query(Job).all()
            if not jobs:
                print("No jobs found in the database.")
                return
            
            # Display job details
            for job in jobs:
                print(f"Job ID: {job.id}, Title: {job.title}, Domain: {job.domain.title if job.domain else 'N/A'}")
                
            # Fetch all domains from the database
            domains = session.query(Domain).all()
            if domains:
                print("\nDomains:")
                for domain in domains:
                    print(f"Domain ID: {domain.id}, Title: {domain.title}, Changed: {domain.changed}")

            # Fetch all funding entries
            fundings = session.query(Funding).all()
            if fundings:
                print("\nFunding Entries:")
                for funding in fundings:
                    print(f"Funding ID: {funding.id}, Title: {funding.title}")

            # Fetch all trainings
            trainings = session.query(Training).all()
            if trainings:
                print("\nTrainings:")
                for training in trainings:
                    print(f"Training ID: {training.id}, Title: {training.title}")

        except Exception as e:
            print(f"An error occurred while loading data: {e}")

        finally:
            # Close the session
            session.close()

    def import_data_from_json(self, json_folder_path: str):
        """
        Import data from JSON files into the SQLite database.
        
        :param json_folder_path: The folder path containing the JSON files
        """
        # Create a new session
        session = self.get_session()
        
        try:
            # List of filenames and their corresponding model classes
            file_mappings = {       
                "certifications.json": Certification,
                "diplomas.json": Diploma, 
                "jobs.json": Job,
                "domains.json": Domain,
                "fundings.json": Funding,
                "trainings.json": Training,
            }
            
            for file_name, model_class in file_mappings.items():
                file_path = os.path.join(json_folder_path, file_name)
                if not os.path.exists(file_path):
                    print(f"File not found: {file_path}")
                    continue
                
                # Open the JSON file using utf-8-sig to handle BOM
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    data_list = JsonHelper.load_from_json(f)
                    for data in data_list:
                        # Handling different data structures
                        if model_class == Certification:
                            new_entry = Certification(
                                id=uuid.UUID(data.get("id")),
                                title=data.get("title") if isinstance(data.get("title"), str) else data.get("title", {}).get("value"),
                                changed=parser.parse(data.get("changed")) if data.get("changed") else None,
                            )
                        
                        elif model_class == Diploma:
                            # Extracting the field_paragraph items as a list
                            field_paragraph_items = data.get("related_infos", {}).get("field_paragraph", [])
                            # Join the items into a single string, or set to None if there are no items
                            related_info = ", ".join(field_paragraph_items) if field_paragraph_items else None

                            new_entry = Diploma(
                                id=uuid.UUID(data.get("id")),
                                title=data.get("title"),
                                changed=parser.parse(data.get("changed")) if data.get("changed") else None,
                                paragraph=related_info
                            )
                        
                        elif model_class == Funding:
                            # Similar handling as Diploma for related_infos.field_paragraph
                            field_paragraph_items = data.get("related_infos", {}).get("field_paragraph", [])
                            related_info = ", ".join(field_paragraph_items) if field_paragraph_items else None

                            new_entry = Funding(
                                id=uuid.UUID(data.get("id")),
                                title=data.get("title"),
                                changed=parser.parse(data.get("changed")) if data.get("changed") else None,
                                paragraph=related_info
                            )
                        
                        elif model_class == Job:
                            new_entry = Job(
                                id=uuid.UUID(data.get("id")),
                                title=data.get("title"),
                                changed=parser.parse(data.get("changed")) if data.get("changed") else None,
                                domain_id=data.get("related_ids", {}).get("domain", [None])[0]
                            )
                        
                        if model_class == Training:
                            # Create the Training instance
                            new_entry = Training(
                                id=uuid.UUID(data.get("id")),
                                title=data.get("title"),
                                changed=parser.parse(data.get("changed")) if data.get("changed") else None,
                                certification_id=data.get("certification"),
                                field_metatag=data.get("field_metatag", None)
                            )

                            # Establish the many-to-many relationship with Diploma if any diploma IDs are provided
                            diploma_ids = data.get("diploma", [])
                            if diploma_ids:
                                # Fetch the Diploma objects corresponding to the provided IDs
                                related_diplomas = session.query(Diploma).filter(Diploma.id.in_(diploma_ids)).all()
                                # Establish the relationship
                                new_entry.diplomas = related_diplomas

                            # Establish the many-to-many relationship with Funding if any funding IDs are provided
                            funding_ids = data.get("funding", [])
                            if funding_ids:
                                related_fundings = session.query(Funding).filter(Funding.id.in_(funding_ids)).all()
                                new_entry.fundings = related_fundings

                            # Establish the many-to-many relationship with Domain if any domain IDs are provided
                            domain_ids = data.get("domain", [])
                            if domain_ids:
                                related_domains = session.query(Domain).filter(Domain.id.in_(domain_ids)).all()
                                new_entry.domains = related_domains

                            # Establish the many-to-many relationship with Job if any job IDs are provided
                            job_ids = data.get("job", [])
                            if job_ids:
                                related_jobs = session.query(Job).filter(Job.id.in_(job_ids)).all()
                                new_entry.jobs = related_jobs

                            # Add goals if they are provided
                            goals = data.get("goal")
                            if goals:
                                new_entry.goals = goals

                        elif model_class == Domain:
                            new_entry = Domain(
                                id=uuid.UUID(data.get("id")),
                                title=data.get("title"),
                                changed=parser.parse(data.get("changed")) if data.get("changed") else None,
                                jobs=data.get("jobs")
                            )
                        
                        # Add the new entry to the session
                        session.add(new_entry)                
                        # Commit the session after adding each data type
                        session.commit()
            print("All Data imported successfully!")

        except Exception as e:
            session.rollback()
            print(f"An error occurred: {e}")

        finally:
            session.close()