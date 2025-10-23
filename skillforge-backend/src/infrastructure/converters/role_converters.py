from infrastructure.entities.role_entity import RoleEntity
from models.role import Role


class RoleConverters:
    @staticmethod
    def convert_role_entity_to_model(role_entity: RoleEntity) -> Role:
        """Convert a RoleEntity to a Role model.

        Args:
            role_entity: The database entity to convert

        Returns:
            Role model instance
        """
        return Role(
            id=role_entity.id,
            name=role_entity.name,
        )

    @staticmethod
    def convert_role_model_to_entity(role: Role) -> RoleEntity:
        """Convert a Role model to a RoleEntity.

        Args:
            role: The Role model to convert

        Returns:
            RoleEntity instance
        """
        return RoleEntity(
            id=role.id,
            name=role.name,
        )
