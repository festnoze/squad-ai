using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IM
    /// <summary>
    /// Retrieve the last message date in a conversation, excluding a specific user ID.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation.</param>
    /// <param name="userId">The ID of the user.</param>
    /// <returns>Returns the last message date of a conversation, excluding a specific user.</returns>
essageService
{
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationI
    /// <summary>
    /// Count the number of messages.
    /// </summary>
    /// <param name="userId">The ID of the user.</param>
    /// <param name="schoolsIds">A list of school IDs.</param>
    /// <param name="listingSelector">A selector for the type of listing.</param>
    /// <returns>Returns the number of messages as an asynchronous task.</returns>
d, int userId);

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector li
    /// <summary>
    /// Count the number of messages that match a specific conversation ID, taking into account any applied filters.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation.</param>
    /// <param name="listingSelector">The selector for filtering the listings. It is an optional parameter and can be null.</param>
    /// <returns>Returns the count of filtered messages for a specific conversation ID.</returns>
stingSelector);
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSe
    /// <summary>
    /// Get the count of unread messages for a specified user ID and school ID in an asynchronous manner.
    /// </summary>
    /// <param name="userId">The identifier of the user.</param>
    /// <param name="schoolId">The identifier of the school.</param>
    /// <returns>Returns the count of unread messages for a specified user ID and school ID.</returns>
lector = null);

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId,
    /// <summary>
    /// Retrieve paginated messages by conversation ID. The method retrieves a specific set of messages belonging to a conversation, based on the provided conversation ID. It returns the messages in a paginated format, allowing for efficient retrieval of a large number of messages.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which to retrieve the paginated messages. It should be an integer.</param>
    /// <param name="userId">The ID of the user whose 'IsArchived' status will be updated. It should be an integer.</param>
    /// <param name="schoolIds">A list of integer values representing the IDs of the schools associated with the user. Can be an empty list.</param>
    /// <param name="pageNumber">The number of the page to retrieve. It should be an integer.</param>
    /// <param name="pageSize">The maximum number of messages to retrieve per page. It should be an integer.</param>
    /// <returns>Returns paginated messages belonging to a conversation based on the provided conversation ID.</returns>
 int schoolId);

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber,
    /// <summary>
    /// Add a message to the system asynchronously.
    /// </summary>
    /// <param name="IMessageWAto">The message object being sent to WA</param>
    /// <param name="enableNotification">Indicates whether to enable or disable notifications for the message. Default value is true.</param>
    /// <returns>Returns a task representing the asynchronous operation of adding a message to the system.</returns>
 int pageSize);

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotifi
    /// <summary>
    /// Retrieve a message by its unique ID.
    /// </summary>
    /// <param name="messageId">The ID of the message to retrieve.</param>
    /// <param name="currentUserId">The ID of the current user.</param>
    /// <returns>Returns the message identified by the unique ID.</returns>
cation = true);

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int 
    /// <summary>
    /// Update the 'IsArchived' status for a specific user, based on a given list of conversation IDs.
    /// </summary>
    /// <param name="conversationIds">An array of integer values representing the IDs of conversations. This parameter is used to identify the specific conversations for which the 'IsArchived' status will be updated.</param>
    /// <param name="archived">A boolean value indicating whether the conversations should be archived or unarchived. 'True' represents archived status and 'False' represents unarchived status.</param>
    /// <param name="userId">An integer value representing the ID of the user. This parameter is used to identify the specific user for whom the 'IsArchived' status will be updated.</param>
currentUserId);

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}