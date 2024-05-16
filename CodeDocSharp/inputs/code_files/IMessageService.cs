using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    /// <summary>
    /// Retrieve the date of the most recent message in a specific conversation, excluding messages sent by a specified user.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation under which the archival status needs to be updated.</param>
    /// <param name="userId">The unique identifier of the user whose archival status is being updated.</param>
    /// <returns>Returns the date of the latest message excluding the specified user.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Count the messages for a specified user with given filters and sorting criteria.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whom the archival status is to be updated.</param>
    /// <param name="schoolsIds">A collection of school IDs across which the conversation archival status will be updated.</param>
    /// <param name="listingSelector">The listing selector that determines which listings (or conversations) are to be considered for the archival update.</param>
    /// <returns>Returns the total number of filtered and sorted messages for a specified user.</returns>

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Count the filtered messages within a specified conversation.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which the messages will be counted.</param>
    /// <param name="listingSelector">An optional filter used to select and count specific types of messages within the conversation.</param>
    /// <returns>Returns the count of filtered messages in a specified conversation.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Get the count of unread messages for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier representing a specific user whose unread message count needs to be fetched.</param>
    /// <param name="schoolId">The unique identifier representing the school associated with the user.</param>
    /// <returns>Returns the number of unread messages for a specified user and school.</returns>

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve paginated messages for a specified conversation, ensuring the conversation exists and the user is a valid participant.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which to retrieve paginated messages.</param>
    /// <param name="userId">The ID of the user for whom to update the archival status.</param>
    /// <param name="schoolIds">A list of school IDs associated with the conversations.</param>
    /// <param name="pageNumber">The page number to retrieve in the paginated results.</param>
    /// <param name="pageSize">The number of messages per page in the paginated results.</param>
    /// <returns>Returns paginated list of messages for a given conversation and user.</returns>

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Add a message to the system, involving user verification and registration of necessary repositories.
    /// </summary>
    /// <param name="messageWAto">An instance of the IMessageWAto class containing the details of the archival status update to be performed.</param>
    /// <param name="enableNotification">A boolean flag indicating whether notifications should be enabled for this operation. Defaults to true.</param>
    /// <returns>Returns a Task representing the asynchronous operation.</returns>

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Retrieve a message by its identifier, including relevant sender and recipient details as well as any associated attachment and audio file identifiers.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message that needs to be updated.</param>
    /// <param name="currentUserId">The unique identifier of the user for whom the archival status is being updated.</param>
    /// <returns>Returns the message with sender, recipient details, and any associated attachments and audio files.</returns>

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Update an archival status for a specified user across multiple conversation IDs.
    /// </summary>
    /// <param name="conversationIds">A list of conversation IDs for which the archival status will be updated.</param>
    /// <param name="archived">A boolean flag indicating whether the conversations should be archived (true) or unarchived (false).</param>
    /// <param name="userId">The ID of the user for whom the archival status is to be updated.</param>

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}