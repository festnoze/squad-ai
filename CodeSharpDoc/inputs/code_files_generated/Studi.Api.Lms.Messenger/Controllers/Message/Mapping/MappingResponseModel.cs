using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageAttachmentService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Lms.Messenger.Controllers.Conversation.Mapping;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Conversation.ResponseModels;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Message.ResponseModels;

namespace Studi.Api.Lms.Messenger.Controllers.Message.Mapping
{
    internal static class MappingResponseModel
    {
        public static UnreadMessageCountResponseModel ToResponseModel(this IUnreadMessageCountAto unreadMessageCountAto)
        {
            return new UnreadMessageCountResponseModel
            {
                TotalUnreadMessageCount = unreadMessageCountAto.TotalUnreadMessageCount,
                TotalUnreadConversationCount = unreadMessageCountAto.TotalUnreadConversationCount,
                ConversationsUnreadMessageCount = unreadMessageCountAto.ConversationsUnreadMessageCount.Select(c => new UnreadMessageCountByConversationResponseModel
                {
                    ConversationId = c.ConversationId,
                    UnreadMessageCount = c.UnreadMessageCount,
                })
            };
        }

        public static MessageResponseModel ToResponseModel(this IMessageRAto message)
        {
            return new MessageResponseModel
            {
                Id = message.Id,
                ConversationId = message.ConversationId,
                DateCreate = message.DateCreate,
                DateUpdate = message.DateUpdate,
                MessageContent = message.MessageContent,
                SenderCorrespondantId = message.SenderCorrespondantId,
                SenderCorrespondant = message.SenderCorrespondant.ToResponseModel(),
                AttachmentsUploadedFiles = message.AttachmentsUploadedFiles.Select(a => a.ToResponseModel()),
                AudioMessageUploadedFile = message.AudioMessageUploadedFile?.ToResponseModel()
            };
        }

        public static MessageFileUploadedResponseModel ToResponseModel(this IMessageAttachmentRAto uploadedFile)
        {
            return new MessageFileUploadedResponseModel
            {
                FileGuid = uploadedFile.FileGuid,
                FileName = uploadedFile.FileName,
                FileSize = uploadedFile.FileSize,
                FileUrl = uploadedFile.FileUrl,
            };
        }

        public static MessageSenderCorrespondantResponseModel ToResponseModel(this IMessageSenderCorrespondantRAto messageSenderCorrespondantRAto)
        {
            return new MessageSenderCorrespondantResponseModel
            {
                Roles = messageSenderCorrespondantRAto.Roles.Select(r => (EConversationCorrespondantRoleResponseModel)r),
                ConversationReadingDate = messageSenderCorrespondantRAto.ConversationReadingDate,
                User = messageSenderCorrespondantRAto.User.ToResponseModel()
            };
        }

        public static MessageSenderCorrespondantUserResponseModel ToResponseModel(this IMessageSenderCorrespondantUserRAto messageSenderCorrespondantUserRAto)
        {
            return new MessageSenderCorrespondantUserResponseModel
            {
                Id = messageSenderCorrespondantUserRAto.Id,
                Pseudo = messageSenderCorrespondantUserRAto.Pseudo,
                ProfilePictureUrl = messageSenderCorrespondantUserRAto.ProfilePictureUrl,
                Handicaps = messageSenderCorrespondantUserRAto.Handicaps.Select(h => h.ToResponseModel())
            };
        }
    }
}