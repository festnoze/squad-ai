using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato.Implementation;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Conversation.RequestModels;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.Mapping;

internal class MappingAtoParam
{
    public static IConversationWAto CreateConversationAtoParam(ConversationRequestModel conversationBM)
    {
        return ConversationWAto.Create(
            conversationBM.SchoolId,
            conversationBM.SenderUserId,
            conversationBM.RecipientsUsersIds,
            conversationBM.Subject,
            conversationBM.MessageContent,
            conversationBM.AttachmentsUploadedFilesGuids,
            conversationBM.IsReadOnly ?? false,
            conversationBM.JoinLastConversation,
            conversationBM.InternalServiceCode,
            conversationBM.ConversationObjectCode,
            conversationBM.ConversationSubObjectCode
        );
    }
}