from datetime import timezone
from infrastructure.entities.school_entity import SchoolEntity
from models.school import School


class SchoolConverters:
    @staticmethod
    def convert_school_entity_to_model(school_entity: SchoolEntity) -> School:
        """Convert a SchoolEntity to a School model.

        Args:
            school_entity: The database entity to convert

        Returns:
            School model instance with timezone-aware datetimes
        """
        return School(
            id=school_entity.id,
            name=school_entity.name,
            address=school_entity.address,
            city=school_entity.city,
            postal_code=school_entity.postal_code,
            country=school_entity.country,
            phone=school_entity.phone,
            email=school_entity.email,
            created_at=school_entity.created_at.replace(tzinfo=timezone.utc),
            updated_at=school_entity.updated_at.replace(tzinfo=timezone.utc) if school_entity.updated_at else None,
            deleted_at=school_entity.deleted_at.replace(tzinfo=timezone.utc) if school_entity.deleted_at else None,
        )

    @staticmethod
    def convert_school_model_to_entity(school: School) -> SchoolEntity:
        """Convert a School model to a SchoolEntity.

        Args:
            school: The School model to convert

        Returns:
            SchoolEntity instance with timezone-naive datetimes (for database storage)
        """
        return SchoolEntity(
            id=school.id,
            name=school.name,
            address=school.address,
            city=school.city,
            postal_code=school.postal_code,
            country=school.country,
            phone=school.phone,
            email=school.email,
            created_at=school.created_at.replace(tzinfo=None) if school.created_at else None,
            updated_at=school.updated_at.replace(tzinfo=None) if school.updated_at else None,
            deleted_at=school.deleted_at.replace(tzinfo=None) if school.deleted_at else None,
        )
