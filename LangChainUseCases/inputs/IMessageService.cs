using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{
    /// <summary>
    /// Gets the date of the last message in a conversation excluding messages from a specific user.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation.</param>
    /// <param name="userId">The ID of the user to exclude messages from.</param>
    /// <returns>The date of the last message or null if no message found.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Counts the messages, optionally applying filters.
    /// </summary>
    /// <param name="filtersCompositions">Optional filters to apply.</param>
    /// <returns>The count of messages.</returns>
    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Counts the messages in a conversation, optionally applying filters.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation.</param>
    /// <param name="listingSelector">Optional filters to apply.</param>
    /// <returns>The count of messages.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Retrieves the count of unread messages for a user within a school.
    /// </summary>
    /// <param name="userId">The ID of the user.</param>
    /// <param name="schoolId">The ID of the school.</param>
    /// <returns>An object representing the count of unread messages.</returns>
    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieves paginated messages in a conversation.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation.</param>
    /// <param name="userId">The ID of the user requesting the messages.</param>
    /// <param name="schoolIds">A list of school IDs.</param>
    /// <param name="pageNumber">The page number.</param>
    /// <param name="pageSize">The size of each page.</param>
    /// <returns>A paginated list of messages.</returns>
    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Adds a new message to an existing conversation.
    /// </summary>
    /// <param name="messageWAto">The message details to add.</param>
    /// <returns>The newly added message.</returns>
    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Asynchronously retrieves a message based on the provided message ID, along with additional related data like the sender's user information and associated attachments.
    /// </summary>
    /// <param name="messageId">The unique identifier for the desired message.</param>
    /// <param name="currentUserId">The current user id</param>
    /// <returns>
    /// An asynchronous task that represents the operation to get the message as an <see cref="IMessageRAto"/> type which includes the message details, sender information, and associated attachments.
    /// </returns>
    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Archive multiple conversations
    /// (this service is defined here as it's needed both in message and conversation services)
    /// </summary>
    /// <param name="conversationIds">Conversations ids</param>
    /// <param name="archived">Archived new value</param>
    /// <param name="userId">User id</param>
    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}