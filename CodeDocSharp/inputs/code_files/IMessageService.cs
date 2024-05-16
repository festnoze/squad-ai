using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    /// <summary>
    /// Retrieve the date of the last message for a specified conversation, excluding messages from a specified user.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which the last message date needs to be retrieved, excluding the specified user.</param>
    /// <param name="userId">The ID of the user who is excluded when retrieving the last message date for the specified conversation.</param>
    /// <returns>Returns the last message date excluding the specified user's messages.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Count the number of messages for a specified user with filtering and sorting based on given criteria.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose conversations' archived status will be updated. Must be an integer.</param>
    /// <param name="schoolsIds">A collection of school IDs that the user is associated with. Each ID must be an integer.</param>
    /// <param name="listingSelector">An object implementing IUntypedListingSelector, used to select and filter the specific conversations to update.</param>
    /// <returns>Returns the total count of filtered, sorted messages for the specified user.</returns>

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Count the filtered messages for a specific conversation based on given criteria.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation. This ID is used to identify the specific conversation whose archived status needs to be updated.</param>
    /// <param name="listingSelector">An optional parameter that allows filtering and selection of specific messages within the conversation. If not provided, all messages within the conversation may be considered.</param>
    /// <returns>Returns the count of filtered messages in the specified conversation.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Retrieve the count of unread messages for a specified user in a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for a user. This parameter is used to specify the user whose unread message count is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for a school. This parameter is used to specify the school within which the user's unread message count is to be retrieved.</param>
    /// <returns>Returns the number of unread messages for the specified user in the specified school.</returns>

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve paginated messages for a specified conversation if the user is part of the conversation.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation.</param>
    /// <param name="userId">The ID of the user for whom the archived status is being updated.</param>
    /// <param name="schoolIds">A list of IDs representing the schools associated with the conversation.</param>
    /// <param name="pageNumber">The page number to retrieve in the paginated result set.</param>
    /// <param name="pageSize">The number of items per page in the paginated result set.</param>
    /// <returns>Returns a paginated list of messages for the specified conversation.</returns>

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Add a message with corresponding user information and register necessary repositories for further operations.
    /// </summary>
    /// <param name="messageWAto">The IMessageWAto object containing details and properties of the specific conversation to be updated.</param>
    /// <param name="enableNotification">A boolean flag indicating whether notifications should be enabled (true) or disabled (false) for the user regarding the archived status update.</param>
    /// <returns>Returns a Task tracking the asynchronous operation's completion status.</returns>

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Retrieve a message by its identifier, including its sender and attachments details.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message to be retrieved. This parameter specifies which message's archived status needs to be updated.</param>
    /// <param name="currentUserId">The unique identifier of the current user. This parameter is used to check if the user is part of the conversations whose archived status is being updated.</param>
    /// <returns>Returns a message with sender and attachments details.</returns>

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Update the archived status for specific conversations for a given user, if the user is part of those conversations.
    /// </summary>
    /// <param name="conversationIds">An array of integers representing the IDs of the conversations that need to have their archived status updated.</param>
    /// <param name="archived">A boolean value indicating whether the specified conversations should be marked as archived (true) or unarchived (false).</param>
    /// <param name="userId">An integer representing the ID of the user whose archived status for the specified conversations is being updated.</param>

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}