using Studi.Api.Lms.Messenger.Application.Services.ConversationObjectService.Ato;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.ConversationObject.ResponseModels;

namespace Studi.Api.Lms.Messenger.Controllers.ConversationObject.Mapping
{
    internal static class ToResponseModelMapper
    {
        public static InternalServiceResponseModel ToResponseModel(this IInternalServiceAto ato)
        {
            return new InternalServiceResponseModel { Id = ato.Id, Code = ato.Code, Name = ato.Name };
                
        }

        public static ConversationObjectResponseModel ToResponseModel(this IConversationObjectAto ato)
        {
            return new ConversationObjectResponseModel { Id = ato.Id, Code = ato.Code, Libelle = ato.Libelle, InternalServiceCode = ato.InternalServiceCode };
        }

        public static ConversationSubObjectResponseModel ToResponseModel(this IConversationSubObjectAto ato)
        {
            return new ConversationSubObjectResponseModel { Id = ato.Id, Code = ato.Code, Libelle = ato.Libelle, ConversationObjectCode = ato.ConversationObjectCode };
        }
    }
}