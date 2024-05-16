using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    /// <summary>
    /// Get the date of the last message in a specific conversation, excluding messages from a specified user.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which the last message date is being retrieved.</param>
    /// <param name="userId">The unique identifier of the user to be excluded from the conversation when retrieving the last message date.</param>
    /// <returns>Returns the last message date in a conversation, excluding a specific user.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Count the messages that match specified user and school criteria, applying a given sorting order.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose messages are being counted.</param>
    /// <param name="schoolsIds">A collection of school identifiers for which the messages need to be counted.</param>
    /// <param name="listingSelector">An instance that determines how messages should be filtered and listed for the counting operation.</param>
    /// <returns>Returns the count of messages matching specified user and school criteria.</returns>

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Count the filtered messages for a specified conversation based on given criteria.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation. This ID is used to specify which conversation's messages need to be filtered.</param>
    /// <param name="listingSelector">An optional parameter that allows for additional filtering or selection criteria. It could be null if no further filtering is required.</param>
    /// <returns>Returns the count of filtered messages.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Retrieve the count of unread messages for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. Used to fetch the unread message count for the specified user.</param>
    /// <param name="schoolId">The unique identifier of the school. Used to fetch the unread message count for the specified school related to the user.</param>
    /// <returns>Returns the unread message count for a user in a specific school.</returns>

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve paginated messages for a specified conversation after verifying the conversation's existence and the user's inclusion in the conversation's participants.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation whose messages are to be paginated.</param>
    /// <param name="userId">The unique identifier of the user for whom the conversations need their archived status updated.</param>
    /// <param name="schoolIds">A list of school identifiers linked to the user, used to filter the conversations.</param>
    /// <param name="pageNumber">The page number to retrieve, used for paginating the results.</param>
    /// <param name="pageSize">The number of messages to display per page, defining the size of each pagination.</param>
    /// <returns>Returns a paginated list of messages for a specified conversation.</returns>

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Add a message to the system with associated user and repositories.
    /// </summary>
    /// <param name="messageWAto">The IMessageWAto instance representing the message to be updated.</param>
    /// <param name="enableNotification">A boolean flag indicating whether to enable notifications for the message update process. Default is true.</param>
    /// <returns>Returns a task that completes when the message is added with optional notification enabled.</returns>

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Retrieve a specific message by its ID, including related user details and attachment information.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message that needs to be retrieved.</param>
    /// <param name="currentUserId">The ID of the currently authenticated user requesting the message retrieval.</param>
    /// <returns>Returns the specified message with associated user details and attachments.</returns>

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Update the archived status of conversations for a specified user based on provided conversation IDs.
    /// </summary>
    /// <param name="conversationIds">An array of integer conversation IDs that need their archived status updated.</param>
    /// <param name="archived">A boolean indicating whether the conversations should be marked as archived (true) or not archived (false).</param>
    /// <param name="userId">The integer user ID for whom the archived status update should be applied.</param>

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}