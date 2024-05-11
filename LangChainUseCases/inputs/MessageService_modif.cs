namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public class MessageService :  IMessageService
{
	IUnitOfWork _unitOfWork;
	IMessageAttachmentService _messageAttachmentService;
	IConversationRepository _conversationRepository;
	IMessageRepository _messageRepository;
	IMessageAttachmentRepository _messageAttachmentRepository;
	IUserRepository _userRepository;
	ICorrespondantRepository _correspondantRepository;
	/// <summary>
/// Initiate a service to manage messaging features, such as attachments, database transactions, and interactions with conversations, messages, users, and correspondents.
/// </summary>
/// <param name="messageAttachmentService">Provides services related to message attachments, such as saving, retrieving, and managing attachment data.</param>
/// <param name="unitOfWork">Manages transactions and commits operations to the database, ensuring data consistency and integrity across operations.</param>
/// <param name="conversationRepository">Handles data access and operations for conversation entities, allowing querying and manipulation of conversation data.</param>
/// <param name="messageRepository">Responsible for accessing and managing message data, supporting operations like adding, deleting, and updating messages.</param>
/// <param name="messageAttachmentRepository">Deals with the persistence and retrieval of message attachment entities, facilitating operations on attachments linked to messages.</param>
/// <param name="userRepository">Manages user-related data access and operations, such as retrieving user information and updating user profiles.</param>
/// <param name="correspondantRepository">Focuses on managing data related to correspondents, who are entities or individuals involved in messaging or conversations.</param>

None MessageService(Name: 'messageAttachmentService', Name: 'unitOfWork', Name: 'conversationRepository', Name: 'messageRepository', Name: 'messageAttachmentRepository', Name: 'userRepository', Name: 'correspondantRepository')
{

        _messageAttachmentService = messageAttachmentService;
        _unitOfWork = unitOfWork;
        _conversationRepository = conversationRepository;
        _messageRepository = messageRepository;
        _messageAttachmentRepository = messageAttachmentRepository;
        _userRepository = userRepository;
        _correspondantRepository = correspondantRepository;
    
}


	/// <summary>
/// Retrieve the date of the latest message in a specific conversation that was sent by someone other than a specified user.
/// </summary>
/// <param name="conversationId">The unique identifier of the conversation for which the latest message date is being retrieved.</param>
/// <param name="userId">The identifier of the user who should be excluded from the search for the latest message.</param>
/// <returns>DateTime?</returns>

DateTime? GetLastMessageDateByConversationIdExceptUserIdAsync(Name: 'conversationId', Name: 'userId')
{

        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    
}


	/// <summary>
/// Retrieve the count of messages for a specific user and selected schools, applying designated filters and sorting criteria.
/// </summary>
/// <param name="userId">The unique identifier of the user for whom the message count is being retrieved.</param>
/// <param name="schoolsIds">A collection of school identifiers for which the message count needs to be calculated. This allows filtering the messages by specific schools associated with the user.</param>
/// <param name="listingSelector">An interface that provides methods for applying filters and sorting criteria to the message data, helping to customize the retrieval of the message count.</param>
/// <returns>int</returns>

int CountMessagesAsync(Name: 'userId', Name: 'schoolsIds', Name: 'listingSelector')
{

        return await _messageRepository.CountMessagesWithFilterAndSort(userId, schoolsIds, listingSelector);
    
}


	/// <summary>
/// Count the messages that fulfill certain conditions in a specified conversation.
/// </summary>
/// <param name="conversationId">An integer identifier for the conversation whose messages are to be counted. This ID uniquely identifies the conversation within the system.</param>
/// <param name="listingSelector">An optional parameter of type IUntypedListingSelector that allows specifying additional conditions or filters to apply when counting the messages. If null, no additional filters are applied.</param>
/// <returns>int</returns>

int CountFilteredMessagesByConversationIdAsync(Name: 'conversationId', Name: 'listingSelector')
{

        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector);
    
}


	/// <summary>
/// Retrieve the count of unread messages for a designated user at a specific school.
/// </summary>
/// <param name="userId">The unique identifier of the user for whom the unread messages count is being retrieved.</param>
/// <param name="schoolId">The unique identifier of the school where the unread messages are being counted.</param>
/// <returns>IUnreadMessageCountAto</returns>

IUnreadMessageCountAto GetUnreadMessageCountByUserIdAndSchoolIdAsync(Name: 'userId', Name: 'schoolId')
{

        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto();
    
}


	/// <summary>
/// Retrieve messages from a verified conversation only if the user is a participant.
/// </summary>
/// <param name="conversationId">The unique identifier of the conversation from which messages are to be retrieved. This ID ensures that the messages are fetched from the correct conversation.</param>
/// <param name="userId">The identifier of the user requesting the messages. This is used to verify that the user is a participant in the conversation.</param>
/// <param name="schoolIds">A list of school identifiers that the user is associated with. This may be used to further validate access rights to the conversation based on school affiliations.</param>
/// <param name="pageNumber">The number of the page to retrieve in a paginated query. This helps in fetching a specific subset of messages, making the data retrieval more manageable.</param>
/// <param name="pageSize">The number of messages to retrieve per page. This parameter defines the limit of messages returned in one page of the result, aiding in pagination control.</param>
/// <returns>PaginedData<IMessageRAto></returns>

PaginedData<IMessageRAto> GetPaginatedMessagesByConversationIdAsync(Name: 'conversationId', Name: 'userId', Name: 'schoolIds', Name: 'pageNumber', Name: 'pageSize')
{

        var conversation = await _conversationRepository.GetConversationByIdAsync(conversationId);

        Guard.Against.Null(conversation, ErrorCode.Api.Lms.Messenger.DataValidation.Query.Conversation.NotFoundById, paramsValues: conversationId.ToString());

        var conversationUserIds = await _conversationRepository.GetCorrespondantsUserIdsByConversationIdAsync(conversationId);

        Guard.Against.False(conversationUserIds.Contains(userId), ErrorCode.Api.Lms.Messenger.DataValidation.Query.Conversation.UserNotInCorrespondants, paramsValues: new string[] 
}


	/// <summary>
/// A new message is created in the system, linked to the current user, with all associated repositories registered to maintain transactional integrity.
/// </summary>
/// <param name="messageWAto">An instance of IMessageWAto representing the message to be added to the system. This object contains all necessary information about the message, such as content, recipient, and other metadata.</param>
/// <param name="enableNotification">A boolean flag indicating whether notifications should be sent for this message. The default value is true, meaning notifications are enabled unless specified otherwise.</param>
/// <returns>IMessageRAto</returns>

IMessageRAto AddMessageAsync(Name: 'messageWAto', Name: 'enableNotification')
{

        int messageCreatedId;
        var currentUser = await _userRepository.GetUserByIdAsync(messageWAto.UserId);

        await _unitOfWork.RegisterRepositoryAsync(_messageRepository);
        await _unitOfWork.RegisterRepositoryAsync(_messageAttachmentRepository);
        await _unitOfWork.RegisterRepositoryAsync(_correspondantRepository);

        try
        
}


	/// <summary>
/// Retrieve specific message details using its ID, including sender information and attachments.
/// </summary>
/// <param name="messageId">The unique identifier of the message to be retrieved. This ID is used to locate the specific message in the database or data store.</param>
/// <param name="currentUserId">The ID of the user who is currently logged in and requesting the message details. This can be used for authorization checks to ensure the user has the right to access the message.</param>
/// <returns>IMessageRAto</returns>

IMessageRAto GetMessageByIdAsync(Name: 'messageId', Name: 'currentUserId')
{

        var messageRIto = await _messageRepository.GetMessageByIdAsync(messageId);

        var currentUser = await _userRepository.GetUserByIdAsync(currentUserId);

        var user = await _userRepository.GetUserByIdAsync(messageRIto.SenderCorrespondant.UserId);

        var guids = messageRIto.AttachmentsUploadedFiles.Select(a => a.UploadedFileGuid).ToList();
        if (messageRIto.AudioMessageUploadedFile != null)
        
}


	/// <summary>
/// Update the archival status of conversations for a user depending on their participation in those conversations.
/// </summary>
/// <param name="conversationIds">An array of integers representing the unique identifiers of the conversations whose archival status needs to be updated.</param>
/// <param name="archived">A boolean value indicating the new archival status to be set for the specified conversations. If true, the conversations are to be marked as archived; if false, they are to be marked as unarchived.</param>
/// <param name="userId">An integer representing the unique identifier of the user for whom the archival status of the conversations is being updated. This parameter ensures that the archival status is updated only for conversations in which this user has participated.</param>
/// <returns>Task</returns>

Task UpdateIsArchivedForUserIdByConversationsIdsAsync(Name: 'conversationIds', Name: 'archived', Name: 'userId')
{

        var conversations = await _conversationRepository.GetConversationsByConversationIdsAndUserIdAsync(conversationIds, userId);
                
        List<string> conversationsIdsWhereUserIdDontBelongs = new();

        foreach (var conversation in conversations)
        
}


