using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    /// <summary>
    /// Retrieve the date of the last message in a specific conversation, excluding a specified user's messages.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation from which to retrieve the last message date.</param>
    /// <param name="userId">The unique identifier of the user whose messages should be excluded from the retrieval.</param>
    /// <returns>Returns the date of the last message excluding specified user's messages.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Count the number of messages associated with a specific user, filtered and sorted based on the user's school IDs and a given listing criteria.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the message count is being retrieved.</param>
    /// <param name="schoolsIds">A collection of school IDs associated with the user, used for filtering messages.</param>
    /// <param name="listingSelector">An instance of IUntypedListingSelector representing the criteria for listing and sorting messages.</param>
    /// <returns>Returns the total count of messages for the specified user.</returns>

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Count the number of filtered messages associated with a specified conversation ID.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which the number of filtered messages is to be counted.</param>
    /// <param name="listingSelector">An optional parameter used to specify the criteria for filtering messages. If null, no filtering is applied.</param>
    /// <returns>Returns the count of filtered messages by conversation ID.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Retrieve the count of unread messages for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier representing the user whose unread messages count is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier representing the school in which the user's unread messages count is to be retrieved.</param>
    /// <returns>Returns the number of unread messages for the specified user and school.</returns>

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve paginated messages for a specified conversation and user by verifying the existence of the conversation and ensuring that the specified user is a participant.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation to retrieve messages for. It helps to locate the specific conversation within which messages are paginated.</param>
    /// <param name="userId">The unique identifier of the user. This parameter is used to verify that the user is a participant in the conversation.</param>
    /// <param name="schoolIds">A list of school identifiers associated with the user or the conversation. This parameter is utilized to filter or verify pertinent school-related contexts.</param>
    /// <param name="pageNumber">The specific page number of the paginated messages to retrieve. This is used to determine which subset or segment of messages is being requested.</param>
    /// <param name="pageSize">The number of messages to include in each page. This controls how many messages are displayed or processed per page.</param>
    /// <returns>Returns paginated messages for a specified conversation and user.</returns>

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Add a message to a user's repository and register associated repositories.
    /// </summary>
    /// <param name="messageWAto">A message object to be added to the user's repository. This object includes all necessary properties and data required for storing and processing the message.</param>
    /// <param name="enableNotification">A boolean flag that indicates whether notifications should be enabled. If set to true, notifications will be sent out upon adding the message; otherwise, no notifications will be sent.</param>
    /// <returns>Returns a task representing the asynchronous operation.</returns>

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Retrieve the message details by ID, including sender information, user details, and attachment files.
    /// </summary>
    /// <param name="messageId">The unique identifier for the message to retrieve.</param>
    /// <param name="currentUserId">The unique identifier for the current user requesting the message details.</param>
    /// <returns>Returns the message details, sender info, user info, and attachment files.</returns>

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Update the archival status for a specified user's conversations.
    /// </summary>
    /// <param name="conversationIds">An array of integer IDs representing the conversations to update.</param>
    /// <param name="archived">A boolean flag indicating whether to archive (true) or unarchive (false) the conversations.</param>
    /// <param name="userId">The unique integer ID of the user for whom the archival status is being updated.</param>

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}