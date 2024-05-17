using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    /// <summary>
    /// Retrieve the date of the most recent message in a specified conversation, excluding messages from a specified user.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which to retrieve the most recent message date.</param>
    /// <param name="userId">The ID of the user whose messages should be excluded from the retrieval.</param>
    /// <returns>Returns the date of the latest message excluding specified user.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Count the number of messages for a specified user, applying given filters and sorting options.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the number of messages is to be counted.</param>
    /// <param name="schoolsIds">A collection of school IDs to filter the messages by the given schools.</param>
    /// <param name="listingSelector">An instance that defines the filtering and sorting options for listing the messages.</param>
    /// <returns>Returns the total count of filtered and sorted messages for a specified user.</returns>

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Count the number of filtered messages within a specific conversation.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which the filtered messages will be counted.</param>
    /// <param name="listingSelector">An optional listing selector that determines the filtering criteria for the messages. By default, it is null.</param>
    /// <returns>Returns the count of filtered messages in a specific conversation.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Get the count of unread messages for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the unread message count is being fetched.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <returns>Returns the number of unread messages for a specified user and school.</returns>

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve a paginated list of messages for a specified conversation and validate the user’s participation in that conversation.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation to retrieve messages for.</param>
    /// <param name="userId">The unique identifier of the user making the request, used to validate their participation in the conversation.</param>
    /// <param name="schoolIds">A list of school identifiers to filter the conversation messages by specific schools.</param>
    /// <param name="pageNumber">The page number to retrieve, used for pagination of the conversation messages.</param>
    /// <param name="pageSize">The number of messages to retrieve per page, used for pagination.</param>
    /// <returns>Returns a paginated list of conversation messages validated for user's participation.</returns>

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Add a message with the created ID following registration of necessary repositories and user information retrieval.
    /// </summary>
    /// <param name="messageWAto">The instance of IMessageWAto representing the message including its content and metadata details.</param>
    /// <param name="enableNotification">A boolean flag indicating whether to send a notification after adding the message. Defaults to true.</param>
    /// <returns>Returns the newly added message ID.</returns>

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Retrieve a specific message and associated user details, including attachment identifiers and audio message information.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message to retrieve.</param>
    /// <param name="currentUserId">The unique identifier of the user making the request. This is used to retrieve user-specific details, including permissions and access rights.</param>
    /// <returns>Returns the retrieved message with user details and associated identifiers.</returns>

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Update the archived status for a specified user's conversations by conversation IDs.
    /// </summary>
    /// <param name="conversationIds">An array of conversation IDs to be updated. These IDs designate which conversations will have their archived status changed.</param>
    /// <param name="archived">A boolean value indicating whether the conversations should be archived (true) or unarchived (false).</param>
    /// <param name="userId">The ID of the user for whom the archived status is being updated.</param>

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}