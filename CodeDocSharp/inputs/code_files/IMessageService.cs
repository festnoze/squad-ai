using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    /// <summary>
    /// Retrieve the date of the last message in a specified conversation, excluding messages from a specified user.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation from which to retrieve the last message date.</param>
    /// <param name="userId">The unique identifier of the user whose messages should be excluded when retrieving the last message date.</param>
    /// <returns>Returns the last message date excluding specified user's messages in a conversation.</returns>
    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    /// <summary>
    /// Count the number of messages for a specified user with given schools and a specific listing selector.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user.</param>
    /// <param name="schoolsIds">A collection of integer IDs representing the schools associated with the user.</param>
    /// <param name="listingSelector">An instance of IUntypedListingSelector used to define the criteria for selecting specific listings.</param>
    /// <returns>Returns the total message count for the specified user and criteria.</returns>

    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    /// <summary>
    /// Count the filtered messages for a given conversation based on specific criteria.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation. It is used to specify which conversation's messages are to be counted.</param>
    /// <param name="listingSelector">An optional parameter that defines the criteria for filtering the messages. It can be used to apply various filters such as date range, sender, or message type.</param>
    /// <returns>Returns the count of filtered messages for a specified conversation.</returns>
    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    /// <summary>
    /// Get the number of unread messages for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the unread messages count is being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user whose unread messages count is being retrieved.</param>
    /// <returns>Returns the count of unread messages for the specified user and school.</returns>

    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve paginated messages for a specified conversation and user, ensuring that the conversation exists and the user is a participant.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which paginated messages are being retrieved. Ensures the conversation exists.</param>
    /// <param name="userId">The unique identifier of the user requesting the messages. Ensures the user is a participant in the conversation.</param>
    /// <param name="schoolIds">A list of school identifiers relevant to the user or conversation. Provides context or filtering for retrieving messages.</param>
    /// <param name="pageNumber">The current page number of the paginated messages being requested. Helps in navigating through the message pages.</param>
    /// <param name="pageSize">The number of messages to include on each page. Controls the size of each page in the pagination.</param>
    /// <returns>Returns a paginated list of messages for the specified conversation and user.</returns>

    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    /// <summary>
    /// Add a new message with its associated attachments and correspondent information for a specified user.
    /// </summary>
    /// <param name="messageWAto">The message object containing information about the message's text, attachments, and recipient.</param>
    /// <param name="enableNotification">Indicates whether notifications should be enabled for the message. Defaults to true.</param>
    /// <returns>Returns a task indicating the completion of adding the message.</returns>

    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    /// <summary>
    /// Retrieve a specific message's details using its unique identifier, along with associated user information and any attached files, including audio messages if present.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message to retrieve. This ID is used to fetch the specific details of the message, including any attached files and audio messages if present.</param>
    /// <param name="currentUserId">The ID of the current user requesting the message details. This is used to fetch user-specific information associated with the message.</param>
    /// <returns>Returns the message details, user information, and attached files for the given message ID.</returns>

    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    /// <summary>
    /// Update the archived status for specified conversations belonging to a user.
    /// </summary>
    /// <param name="conversationIds">A list of conversation IDs for which the archived status will be updated. These IDs are represented as integers.</param>
    /// <param name="archived">A boolean value indicating whether the specified conversations should be marked as archived (true) or unarchived (false).</param>
    /// <param name="userId">The ID of the user for whom the archived status of the conversations is being updated. This ID is represented as an integer.</param>

    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}