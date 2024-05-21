using Hangfire;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.ListingSelector;
using Studi.Api.Core.Security.Authentication;
using Studi.Api.Lms.Messenger.Application.Services.MessageService;
using Studi.Api.Lms.Messenger.Application.Services.NotificationService;
using Studi.Api.Lms.Messenger.Controllers.Message.Mapping;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Message.ResponseModels;
using Studi.Api.Lms.Messenger.Shared.MessageListing;
using Studi.Api.Lms.Messenger.Utils.Middleware;
using Swashbuckle.AspNetCore.Annotations;
using System.Net;

namespace Studi.Api.Lms.Messenger.Controllers.Message
{
    [ApiController]
    [Route("v{version:apiVersion}/messages")]
    [Authorize]
    public class MessageController : ControllerBase
    {
        private readonly IMessageService _messageService;


    /// <summary>
    /// Initialize the message service for the MessageController.
    /// </summary>
    /// <param name="messageService">The message service used by the MessageController to handle messages.</param>
    /// <param name="MessageController">The constructor method for the containing class, used to initialize the message service.</param>
        public MessageController(IMessageService messageService)
        {
            _messageService = messageService;
        }


    /// <summary>
    /// Retrieve the unread message count for a specified user and school.
    /// </summary>
    /// <param name="userId">The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <param name="schoolId">The generated description for the parameter</param>
    /// <returns>Returns the unread message count for a specified user and school.</returns>
        [HttpGet]
        [Route("unread-infos")]
        [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(UnreadMessageCountResponseModel))]
        [ApiVersion("1")]
        public async Task<UnreadMessageCountResponseModel> GetMessageUnreadCountAsync([FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] int schoolId)
        {
            var unreadMessageCount = await _messageService.GetUnreadMessageCountByUserIdAndSchoolIdAsync(userId, schoolId);

            return unreadMessageCount.ToResponseModel();
        }


    /// <summary>
    /// Check if the user is an intranet user and guard against negative or zero values, then iterate through a list of IDs.
    /// </summary>
    /// <param name="ids">Collection of integers representing the IDs to be processed. It is recommended to provide a non-empty collection.</param>
    /// <param name="maxPerSecond">An integer representing the maximum number of operations allowed per second. The default value is 10.</param>
    /// <returns>Returns boolean indicating if notification was successfully sent.</returns>
        [HttpPost]
        [Route("notifications")]
        [ApiVersion("1")]
        [SkipCheckParamsAgainstLmsToken]
        public IActionResult PostSendNotification([FromBody] ICollection<int> ids, [FromQuery(Name = "max-per-second")] int maxPerSecond = 10)
        {
            Guard.Against.False(User.StudiIdentity().IsIntranetUser);
            Guard.Against.NegativeOrZero(maxPerSecond);

            foreach (var id in ids)
            {
                BackgroundJob.Enqueue<INotificationService>(service => service.SendNewMessageNotificationThrottledAsync(id, new ThrottleJobsPerSecondParams() { JobsPerSecond = maxPerSecond }));
            }

            return Ok();
        }


    /// <summary>
    /// Retrieve the count of messages for a specified user and school, based on a given listing selector.
    /// </summary>
    /// <param name="listingSelector">The listing selector used to filter and specify the type of message listing to retrieve.</param>
    /// <param name="userId">The unique identifier of the user for whom the message count is being retrieved.</param>
    /// <param name="schoolIds">The list of unique identifiers representing the schools for which the message count is being retrieved.</param>
    /// <returns>Returns the count of messages for a specified user and school.</returns>
        [HttpPost]
        [Route("count")]
        [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(int))]
        [ApiVersion("1")]
        public async Task<int> CountMessageAsync([FromBody] IListingSelector<IMessageListing> listingSelector, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-ids")] List<int> schoolIds)
        {
            var untypedListingSelector = listingSelector.ConvertToUntypedListingSelector();

            var countMessages = await _messageService.CountMessagesAsync(userId, schoolIds, untypedListingSelector);

            return countMessages;
        }
    }
}