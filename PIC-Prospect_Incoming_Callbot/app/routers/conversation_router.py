import re
from uuid import UUID

from database.conversation_persistence_service_factory import ConversationPersistenceServiceFactory
from database.conversation_repository import ConversationRepository
from database.user_repository import UserRepository
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from utils.endpoints_api_key_required_decorator import api_key_required

conversation_router = APIRouter(prefix="/conversation")

def validate_phone_number(phone_number: str) -> bool:
    """Validate phone number format to prevent SQL injection - only allow + and digits"""
    if not phone_number:
        return False
    pattern = r'^[+\d]+$'
    return bool(re.match(pattern, phone_number))


@conversation_router.get("/{conversation_id}")
@api_key_required
async def get_conversation_by_id_async(request: Request, conversation_id: str) -> JSONResponse:
    """Get conversation history by conversation ID"""
    try:
        conversation_uuid = UUID(conversation_id)
        conversation_repository = ConversationRepository()
        conversation = await conversation_repository.get_conversation_by_id_async(conversation_uuid)

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return JSONResponse(
            {
                "conversation_id": str(conversation.id),
                "user_id": str(conversation.user.id) if conversation.user else None,
                "messages": [message.to_dict() for message in conversation.messages] if conversation.messages else [],
                "created_at": conversation.created_at.isoformat() if hasattr(conversation, "created_at") and conversation.created_at else None,
            }
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation: {str(e)}")


@conversation_router.get("/all/user/{phone_number}")
@api_key_required
async def get_all_user_conversations_by_phone_async(request: Request, phone_number: str) -> JSONResponse:
    """Get all conversations for a user by phone number"""
    try:
        if not validate_phone_number(phone_number):
            raise HTTPException(status_code=400, detail="Invalid phone number format. Only digits and + are allowed.")

        user_repository = UserRepository()
        user = await user_repository.get_user_by_ip_or_phone_async(phone_number)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        conversation_repository = ConversationRepository()
        conversations = await conversation_repository.get_all_user_conversations_async(user.id)
        return JSONResponse(
            {
                "user_id": str(user.id),
                "phone_number": phone_number,
                "conversations": [
                    {
                        "conversation_id": str(conv.id),
                        "conversation_date": conv.created_at.isoformat() if hasattr(conv, "created_at") and conv.created_at else "N.C",
                        "message_count": len(conv.messages) if conv.messages else 0,
                        "created_at": conv.created_at.isoformat() if hasattr(conv, "created_at") and conv.created_at else None,
                        "messages": [message.to_compact_dict() for message in conv.messages] if conv.messages else [],
                    }
                    for conv in conversations
                ],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving latest conversation: {str(e)}")


@conversation_router.get("/all/plain/user/{phone_number}")
@api_key_required
async def get_all_user_conversations_as_plain_text_by_phone_async(request: Request, phone_number: str) -> PlainTextResponse:
    """Get all conversations for a user by phone number"""
    try:
        if not validate_phone_number(phone_number):
            raise HTTPException(status_code=400, detail="Invalid phone number format. Only digits and + are allowed.")

        user_repository = UserRepository()
        user = await user_repository.get_user_by_ip_or_phone_async(phone_number)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        conversation_repository = ConversationRepository()
        conversations = await conversation_repository.get_all_user_conversations_async(user.id)

        if not conversations:
            return PlainTextResponse("No conversations found for this user")

        # Format all conversations as plain text
        all_conversations_text = []
        for i, conv in enumerate(conversations, 1):
            conv_date = conv.created_at.isoformat() if hasattr(conv, "created_at") and conv.created_at else "N.C"
            all_conversations_text.append(f"=== Conversation {i} ({conv_date}) ===")

            if conv.messages:
                for message in conv.messages:
                    all_conversations_text.append(message.to_compact_text())
            else:
                all_conversations_text.append("No messages in this conversation")

            all_conversations_text.append("")  # Empty line between conversations

        return PlainTextResponse('\n'.join(all_conversations_text))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user conversations: {str(e)}")


@conversation_router.get("/latest/user/{phone_number}")
@api_key_required
async def get_user_latest_conversation_by_phone_async(request: Request, phone_number: str) -> PlainTextResponse:
    """Get the latest conversation for a user by phone number"""
    try:
        if not validate_phone_number(phone_number):
            raise HTTPException(status_code=400, detail="Invalid phone number format. Only digits and + are allowed.")

        user_repository = UserRepository()
        user = await user_repository.get_user_by_ip_or_phone_async(phone_number)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        conversation_service = ConversationPersistenceServiceFactory.create_conversation_persistence_service()
        last_conversation_data = await conversation_service.get_user_last_conversation_async(user.id)

        if not last_conversation_data or not last_conversation_data.get("conversation_id"):
            return PlainTextResponse("No conversations found for this user")

        conversation_repository = ConversationRepository()
        conversation_uuid = UUID(last_conversation_data["conversation_id"])
        conversation = await conversation_repository.get_conversation_by_id_async(conversation_uuid)

        if conversation and conversation.messages:
            return PlainTextResponse('\n'.join([message.to_compact_text() for message in conversation.messages]))
        else:
            return PlainTextResponse("No messages found for this user")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving latest conversation: {str(e)}")
