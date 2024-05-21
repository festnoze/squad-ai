using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato.Implementation;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Conversation.RequestModels;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.Mapping;

internal class MappingAtoParam
{

    /// <summary>
    /// Create a message to be added to a conversation, with specified user, school, content, audio, and attachments.
    /// </summary>
    /// <param name="ConversationRequestModel">The model containing the details of the conversation request, including user, school, content, audio, and attachments.</param>
    /// <param name="conversationBM">The business model representing the conversation, containing information such as user details, school details, content, audio, and attachments.</param>
    /// <returns>Returns a conversation message with specified details.</returns>
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