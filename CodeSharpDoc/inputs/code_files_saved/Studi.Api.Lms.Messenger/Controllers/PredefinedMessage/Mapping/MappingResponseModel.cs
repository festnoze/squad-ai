using Studi.Api.Lms.Messenger.Application.Services.PredefinedMessage.Ato;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.PredefinedMessage.ResponseModels;

namespace Studi.Api.Lms.Messenger.Controllers.PredefinedMessage.Mapping
{
    internal static class MappingResponseModel
    {
        public static PredefinedMessageResponseModel ToPredefinedMessageResponseModel(this IPredefinedMessageRAto predefinedMessage)
        {
            return new PredefinedMessageResponseModel
            {
                Id = predefinedMessage.Id,
                Code = predefinedMessage.Code,
                Libelle = predefinedMessage.Libelle
            };
        }
    }
}