using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato.Implementation;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Message.RequestModels;

namespace Studi.Api.Lms.Messenger.Controllers.Message.Mapping
{
    internal class MappingAtoParam
    {


        public static IMessageWAto CreateMessageAtoParam(MessageRequestModel newMessageAddingToExistingConversation, int userId, int conversationId, int schoolId)
        {
            return MessageWAto.Create(
                conversationId,
                userId,
                schoolId,
                newMessageAddingToExistingConversation.MessageContent ?? string.Empty,
                newMessageAddingToExistingConversation.AudioMessageGuid,
                newMessageAddingToExistingConversation.AttachmentsUploadedFilesGuids
            );
        }
    }
}