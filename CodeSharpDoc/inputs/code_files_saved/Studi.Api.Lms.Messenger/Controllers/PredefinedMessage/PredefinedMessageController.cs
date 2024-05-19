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
    /// <summary>
    /// Controller for managing predefined messages and related operations.
    /// </summary>
    [ApiController]
    [Route("v{version:apiVersion}/predefined-messages")]
    [Authorize]
    public class PredefinedMessageController : ControllerBase
    {
        private readonly IPredefinedMessageService _predefinedMessageService;

        /// <summary>
        /// Initializes a new instance of the <see cref="PredefinedMessageController"/> class.
        /// </summary>
        /// <param name="predefinedMessageService">The predefined message service to be injected.</param>
        public PredefinedMessageController(IPredefinedMessageService predefinedMessageService)
        {
            _predefinedMessageService = predefinedMessageService;
        }

        /// <summary>
        /// Retrieves predefined messages.
        /// </summary>
        /// <param name="userId">The user ID</param>
        /// <param name="schoolIds">The list of school IDs</param>
        /// <returns>A collection of predefined messages.</returns>
        [HttpGet]
        [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(List<PredefinedMessageResponseModel>))]
        [ApiVersion("1")]
        [SkipCheckParamsAgainstLmsToken]
        public async Task<IEnumerable<PredefinedMessageResponseModel>> GetPredefinedMessagesAsync([FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
        {
            var predefinedMessages = (await _predefinedMessageService.GetPredefinedMessagesAsync()).Select(pm => pm.ToPredefinedMessageResponseModel());

            return predefinedMessages;
        }

        /// <summary>
        /// Retrieves predefined message content by its ID.
        /// </summary>
        /// <param name="id">The ID of the predefined message.</param>
        /// <param name="userId">The user ID</param>
        /// <param name="schoolIds">The list of school IDs</param>
        /// <returns>The content of the predefined message.</returns>
        [HttpGet]
        [Route("{id:int}")]
        [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(string))]
        [ApiVersion("1")]
        [SkipCheckParamsAgainstLmsToken]
        public async Task<PredefinedMessageContentResponseModel> GetPredefinedMessageContentByIdAsync(int id, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
        {
            var predefinedMessageContentStr = await _predefinedMessageService.GetPredefinedMessageContentByIdAsync(id);
            var predefinedMessageContent = new PredefinedMessageContentResponseModel() { MessageContent = predefinedMessageContentStr };

            return predefinedMessageContent;
        }
    }
}
