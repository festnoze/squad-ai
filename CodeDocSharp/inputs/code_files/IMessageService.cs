using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IM
    /// <summary>
    /// Retrieve the date of the last message in a specified conversation, excluding messages sent by a particular user.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which the last message date is being fetched.</param>
    /// <param name="userId">The unique identifier of the user for whom the archived status is to be ignored.</param>
    /// <returns>Returns the last message date in the conversation, excluding specified user's messages.</returns>
essageService
{
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationI
    /// <summary>
    /// Analyze and return the total number of messages present in a specified collection.
    /// </summary>
    /// <param name="userId">The unique identifier for the specified user whose archived status is being updated.</param>
    /// <param name="schoolsIds">A collection of unique identifiers representing the schools in scope for the update operation.</param>
    /// <param name="listingSelector">An object that defines criteria for selecting which listings or conversations to update for the specified user.</param>
    /// <returns>Returns the total number of messages in the specified collection.</returns>
d, int userId);

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector li
    /// <summary>
    /// Count messages that meet specified filter criteria within a particular conversation.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation.</param>
    /// <param name="listingSelector">An optional parameter used to select listings; can be null.</param>
    /// <returns>Returns the count of filtered messages within the specified conversation.</returns>
stingSelector);
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSe
    /// <summary>
    /// Get the count of unread messages for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose unread message count is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns the number of unread messages for a specific user and school.</returns>
lector = null);

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId,
    /// <summary>
    /// Retrieve messages for a specified conversation, segmented into pages.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation to retrieve messages from.</param>
    /// <param name="userId">The unique identifier for the user whose messages' archived status is being updated.</param>
    /// <param name="schoolIds">A list of unique identifiers for the schools related to the conversations.</param>
    /// <param name="pageNumber">The number representing the page of results to retrieve, used for pagination.</param>
    /// <param name="pageSize">The number of items per page, used for pagination.</param>
    /// <returns>Returns paginated messages for a specified conversation.</returns>
 int schoolId);

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber,
    /// <summary>
    /// Add a new message to a designated storage medium with necessary details.
    /// </summary>
    /// <param name="messageWAto">The IMessageWAto object containing the message information that needs to be updated for the specified user.</param>
    /// <param name="enableNotification">A boolean flag indicating whether or not to enable notifications for the update operation. Defaults to true.</param>
    /// <returns>Returns a boolean indicating the success of adding the message.</returns>
 int pageSize);

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotifi
    /// <summary>
    /// Get a message by its unique identifier, allowing access to specific message data.
    /// </summary>
    /// <param name="messageId">The unique identifier for the message that needs to be updated.</param>
    /// <param name="currentUserId">The unique identifier for the user whose archived status is being updated.</param>
    /// <returns>Returns a message object identified by a unique identifier.</returns>
cation = true);

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int 
    /// <summary>
    /// Update the archived status for a specified user across multiple conversations.
    /// </summary>
    /// <param name="conversationIds">A list of conversation IDs for which the archived status needs to be updated.</param>
    /// <param name="archived">A boolean value indicating whether to archive (true) or unarchive (false) the specified conversations for the user.</param>
    /// <param name="userId">The unique identifier of the user whose archived status is being updated across multiple conversations.</param>
currentUserId);

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}