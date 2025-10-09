import logging

from api_client.request_models.salesforce_request_models import (
    AddContactRoleRequest,
    CreateContactRequest,
    CreateOpportunityRequest,
    SalesforceResponse,
)
from api_client.salesforce_api_client import SalesforceApiClient
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from utils.endpoints_api_key_required_decorator import api_key_required

logger = logging.getLogger(__name__)

salesforce_router = APIRouter(prefix="/salesforce", tags=["Salesforce"])


@salesforce_router.post("/contacts", response_model=SalesforceResponse)
@api_key_required
async def create_contact(request: Request, contact_request: CreateContactRequest) -> JSONResponse:
    """
    Create a new Contact in Salesforce.

    This endpoint allows you to create a new contact record with all the standard
    and custom fields. The contact can be associated with an Account and assigned
    to a specific owner.

    **Authentication**: Requires API key via X-API-Key header or api_key query parameter.

    **Example Request**:
    ```json
    {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone": "+33123456789",
        "account_id": "001XXXXXXXXX",
        "owner_id": "005XXXXXXXXX",
        "title": "CEO",
        "additional_fields": {
            "Custom_Field__c": "Custom Value"
        }
    }
    ```
    """
    logger.info(f"Creating new contact: {contact_request.first_name} {contact_request.last_name}")

    try:
        sf_client = SalesforceApiClient()
        contact_data = contact_request.to_dict()

        # Extract additional_fields to pass as **kwargs
        additional_fields = contact_data.pop("additional_fields", {})

        contact_id = await sf_client.create_contact_async(**contact_data, **additional_fields)

        if contact_id:
            logger.info(f"Contact created successfully with ID: {contact_id}")
            return JSONResponse(
                status_code=201,
                content=SalesforceResponse.success_response(
                    record_id=contact_id,
                    message="Contact created successfully",
                    details={
                        "salesforce_url": f"https://{'test' if sf_client._is_sandbox else 'login'}.salesforce.com/lightning/r/Contact/{contact_id}/view",
                        "name": f"{contact_request.first_name} {contact_request.last_name}"
                    }
                ).dict()
            )
        else:
            logger.error("Contact creation failed")
            return JSONResponse(
                status_code=500,
                content=SalesforceResponse.error_response(
                    message="Failed to create contact"
                ).dict()
            )

    except Exception as e:
        logger.error(f"Error creating contact: {e!s}")
        return JSONResponse(
            status_code=500,
            content=SalesforceResponse.error_response(
                message=f"Internal error: {e!s}"
            ).dict()
        )


@salesforce_router.post("/opportunities", response_model=SalesforceResponse)
@api_key_required
async def create_opportunity(request: Request, opportunity_request: CreateOpportunityRequest) -> JSONResponse:
    """
    Create a new Opportunity in Salesforce with advanced prospect linking.

    This endpoint creates an opportunity and can automatically link it to:
    - An Account (via account_id)
    - A Contact directly (via contact_id) - creates OpportunityContactRole
    - Track Lead conversion (via converted_from_lead_id)

    **Authentication**: Requires API key via X-API-Key header or api_key query parameter.

    **Prospect Linking Options**:
    1. **Via Account**: Pass account_id to link indirectly through Account relationship
    2. **Via Contact**: Pass contact_id to create direct Contact-Opportunity relationship
    3. **Via Lead**: Pass converted_from_lead_id to track lead conversion
    4. **Combined**: Use multiple linking methods for comprehensive tracking

    **Example Request**:
    ```json
    {
        "name": "New Enterprise Deal",
        "stage_name": "Prospecting",
        "close_date": "2025-12-31",
        "account_id": "001XXXXXXXXX",
        "contact_id": "003XXXXXXXXX",
        "contact_role": "Decision Maker",
        "amount": 50000.0,
        "probability": 25,
        "description": "Large enterprise opportunity",
        "lead_source": "Phone Inquiry",
        "additional_fields": {
            "Custom_Field__c": "Custom Value"
        }
    }
    ```
    """
    logger.info(f"Creating new opportunity: {opportunity_request.name}")

    try:
        sf_client = SalesforceApiClient()
        opportunity_data = opportunity_request.to_dict()

        # Extract additional_fields to pass as **kwargs
        additional_fields = opportunity_data.pop("additional_fields", {})

        opportunity_id = await sf_client.create_opportunity_async(**opportunity_data, **additional_fields)

        if opportunity_id:
            logger.info(f"Opportunity created successfully with ID: {opportunity_id}")

            # Prepare response details
            details = {
                "salesforce_url": f"https://{'test' if sf_client._is_sandbox else 'login'}.salesforce.com/lightning/r/Opportunity/{opportunity_id}/view",
                "name": opportunity_request.name,
                "stage": opportunity_request.stage_name
            }

            # Add contact linking info if applicable
            if opportunity_request.contact_id:
                details["contact_linked"] = True
                details["contact_role"] = opportunity_request.contact_role

            return JSONResponse(
                status_code=201,
                content=SalesforceResponse.success_response(
                    record_id=opportunity_id,
                    message="Opportunity created successfully",
                    details=details
                ).dict()
            )
        else:
            logger.error("Opportunity creation failed")
            return JSONResponse(
                status_code=500,
                content=SalesforceResponse.error_response(
                    message="Failed to create opportunity"
                ).dict()
            )

    except Exception as e:
        logger.error(f"Error creating opportunity: {e!s}")
        return JSONResponse(
            status_code=500,
            content=SalesforceResponse.error_response(
                message=f"Internal error: {e!s}"
            ).dict()
        )


@salesforce_router.post("/opportunity-contact-roles", response_model=SalesforceResponse)
@api_key_required
async def add_contact_role_to_opportunity(request: Request, role_request: AddContactRoleRequest) -> JSONResponse:
    """
    Add a Contact role to an existing Opportunity.

    This endpoint creates an OpportunityContactRole record that links a Contact
    to an Opportunity with a specific role. This is useful for adding multiple
    contacts to a single opportunity or for managing contact roles post-creation.

    **Authentication**: Requires API key via X-API-Key header or api_key query parameter.

    **Common Contact Roles**:
    - Decision Maker
    - Economic Buyer
    - Economic Decision Maker
    - Technical Buyer
    - Influencer
    - User
    - Other

    **Example Request**:
    ```json
    {
        "opportunity_id": "006XXXXXXXXX",
        "contact_id": "003XXXXXXXXX",
        "role": "Technical Buyer",
        "is_primary": false
    }
    ```
    """
    logger.info(f"Adding contact role for Opportunity: {role_request.opportunity_id}, Contact: {role_request.contact_id}")

    try:
        sf_client = SalesforceApiClient()

        role_id = await sf_client.add_contact_role_to_opportunity_async(
            opportunity_id=role_request.opportunity_id,
            contact_id=role_request.contact_id,
            role=role_request.role,
            is_primary=role_request.is_primary
        )

        if role_id:
            logger.info(f"OpportunityContactRole created successfully with ID: {role_id}")
            return JSONResponse(
                status_code=201,
                content=SalesforceResponse.success_response(
                    record_id=role_id,
                    message="Contact role added to opportunity successfully",
                    details={
                        "opportunity_id": role_request.opportunity_id,
                        "contact_id": role_request.contact_id,
                        "role": role_request.role,
                        "is_primary": role_request.is_primary
                    }
                ).dict()
            )
        else:
            logger.error("OpportunityContactRole creation failed")
            return JSONResponse(
                status_code=500,
                content=SalesforceResponse.error_response(
                    message="Failed to add contact role to opportunity"
                ).dict()
            )

    except Exception as e:
        logger.error(f"Error adding contact role to opportunity: {e!s}")
        return JSONResponse(
            status_code=500,
            content=SalesforceResponse.error_response(
                message=f"Internal error: {e!s}"
            ).dict()
        )


@salesforce_router.get("/health")
@api_key_required
async def salesforce_health_check(request: Request) -> JSONResponse:
    """
    Check Salesforce API connectivity and authentication.

    This endpoint verifies that the Salesforce API client can authenticate
    successfully and is ready to handle requests.

    **Authentication**: Requires API key via X-API-Key header or api_key query parameter.
    """
    logger.info("Performing Salesforce health check")

    try:
        sf_client = SalesforceApiClient()

        # Test authentication
        if sf_client._is_authenticated():
            return JSONResponse(
                status_code=200,
                content=SalesforceResponse.success_response(
                    record_id=None,
                    message="Salesforce API is healthy and authenticated",
                    details={
                        "authenticated": True,
                        "instance_url": sf_client._instance_url,
                        "sandbox": sf_client._is_sandbox,
                        "auth_method": sf_client._auth_method
                    }
                ).dict()
            )
        else:
            # Try to authenticate
            auth_success = sf_client.authenticate()
            if auth_success:
                return JSONResponse(
                    status_code=200,
                    content=SalesforceResponse.success_response(
                        record_id=None,
                        message="Salesforce API authentication successful",
                        details={
                            "authenticated": True,
                            "instance_url": sf_client._instance_url,
                            "sandbox": sf_client._is_sandbox,
                            "auth_method": sf_client._auth_method
                        }
                    ).dict()
                )
            else:
                return JSONResponse(
                    status_code=503,
                    content=SalesforceResponse.error_response(
                        message="Salesforce authentication failed"
                    ).dict()
                )

    except Exception as e:
        logger.error(f"Salesforce health check failed: {e!s}")
        return JSONResponse(
            status_code=503,
            content=SalesforceResponse.error_response(
                message=f"Salesforce API error: {e!s}"
            ).dict()
        )
