using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Studi.Api.Lms.Messenger.Application.Services.PredefinedMessage;
using Studi.Api.Lms.Messenger.Controllers.PredefinedMessage.Mapping;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.PredefinedMessage.ResponseModels;
using Studi.Api.Lms.Messenger.Utils.Middleware;
using Swashbuckle.AspNetCore.Annotations;
using System.Net;

namespace Studi.Api.Lms.Messenger.Controllers.PredefinedMessage
{
    [ApiController]
    [Route("v{version:apiVersion}/predefined-messages")]
    [Authorize]
    public class PredefinedMessageController : ControllerBase
    {
        private readonly IPredefinedMessageService _predefinedMessageService;


    /// <summary>
    /// Create a message with specified content, audio, and attachments for a conversation involving a user at a specific school.
    /// </summary>
    /// <param name="predefinedMessageService">The IPredefinedMessageService instance used to access predefined messages.</param>
    /// <param name="PredefinedMessageController">The constructor method for the PredefinedMessageController class.</param>
        public PredefinedMessageController(IPredefinedMessageService predefinedMessageService)
        {
            _predefinedMessageService = predefinedMessageService;
        }


    /// <summary>
    /// Initialize the predefined message service for the controller.
    /// </summary>
    /// <param name="userId">The ID of the user.</param>
    /// <param name="schoolIds">A list of IDs representing the schools.</param>
    /// <returns>Returns a list of predefined messages for the specified user and schools.</returns>
        [HttpGet]
        [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(List<PredefinedMessageResponseModel>))]
        [ApiVersion("1")]
        [SkipCheckParamsAgainstLmsToken]
        public async Task<IEnumerable<PredefinedMessageResponseModel>> GetPredefinedMessagesAsync([FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
        {
            var predefinedMessages = (await _predefinedMessageService.GetPredefinedMessagesAsync()).Select(pm => pm.ToPredefinedMessageResponseModel());

            return predefinedMessages;
        }

        [HttpGet]
        [Route("{id:int}")]
        [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(string))]
        [ApiVersion("1")]
        [SkipCheckParamsAgainstLmsToken]

    /// <summary>
    /// Retrieve predefined messages asynchronously and convert them to predefined message response models.
    /// </summary>
    /// <param name="id">The ID of the predefined message content to retrieve.</param>
    /// <param name="userId">The ID of the user for whom the predefined messages are being retrieved.</param>
    /// <param name="schoolIds">A list of IDs representing the schools for which predefined messages are requested.</param>
    /// <returns>Returns predefined message content based on ID, user ID, and school IDs.</returns>
        public async Task<PredefinedMessageContentResponseModel> GetPredefinedMessageContentByIdAsync(int id, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
        {
            var predefinedMessageContentStr = await _predefinedMessageService.GetPredefinedMessageContentByIdAsync(id);
            var predefinedMessageContent = new PredefinedMessageContentResponseModel() { MessageContent = predefinedMessageContentStr };

            return predefinedMessageContent;
        }
    }
}