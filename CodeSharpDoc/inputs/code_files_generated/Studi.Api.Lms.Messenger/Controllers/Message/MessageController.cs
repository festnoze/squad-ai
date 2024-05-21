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
    /// <summary>
    /// Controller for managing messages and related operations.
    /// </summary>
    [ApiController]
    [Route("v{version:apiVersion}/messages")]
    [Authorize]
    public class MessageController : ControllerBase
    {
        private readonly IMessageService _messageService;

        /// <summary>
        /// Initializes a new instance of the <see cref="MessageController"/> class.
        /// </summary>
        /// <param name="messageService">The message service to be injected.</param>
        public MessageController(IMessageService messageService)
        {
            _messageService = messageService;
        }

        /// <summary>
        /// Retrieves the count of unread messages for a user in a school.
        /// </summary>
        /// <param name="userId">The user ID for whom unread messages are counted.</param>
        /// <param name="schoolId">The school ID where the user belongs.</param>
        /// <returns>The count of unread messages.</returns>
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
        /// Send notification for messages (used to catch up on failed notifications)
        /// </summary>
        /// <param name="ids">Ids of the messages to send the notification</param>
        /// <param name="maxPerSecond">Throttle queue to limit the number of notification sent per second</param>
        /// <returns>Ok</returns>
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
        /// Count messages on function applying filters
        /// </summary>
        /// <param name="listingSelector">The listing selector for filtering and pagination.</param>
        /// <param name="userId">The user ID.</param>
        /// <param name="schoolIds">The school IDs.</param>
        /// <returns>The count of messages.</returns>
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