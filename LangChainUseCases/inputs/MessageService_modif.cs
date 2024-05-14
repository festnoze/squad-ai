using Hangfire;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Infrastructure.Repository.UnitOfWork;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageAttachmentService;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Mapping;
using Studi.Api.Lms.Messenger.Application.Services.NotificationService;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.ConversationRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.CorrespondantRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageAttachmentRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageRepository.Ito;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageRepository.Ito.Implementation;
using Studi.Api.Lms.Messenger.Infra.External.Data.Repositories.UserRepository;
using Studi.Api.Lms.Messenger.Localization.Error.GeneratedClasses;
using Studi.Api.Core.ListingSelector.Untyped;
using Studi.Api.Core.ListingSelector;
using System.Collections.Generic;
using System.Threading.Tasks;
using System;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

[ScopedService(typeof(IMessageService))]
public class MessageService : IMessageService
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IMessageAttachmentService _messageAttachmentService;
    private readonly IConversationRepository _conversationRepository;
    private readonly IMessageRepository _messageRepository;
    private readonly IMessageAttachmentRepository _messageAttachmentRepository;
    private readonly IUserRepository _userRepository;
    private readonly ICorrespondantRepository _correspondantRepository;

    [Obsolete("This method is deprecated, use CountMessagesAsync instead.")]
    public async Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector)
    {
        return await _messageRepository.CountMessagesWithFilterAndSort(userId, schoolsIds, listingSelector);
    }

    /// <summary>
    /// Get the count of messages for a specified user, filtering and sorting based on provided conditions.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose archived status is being updated.</param>
    /// <param name="schoolsIds">A collection of unique identifiers for the schools associated with the user's conversations.</param>
    /// <param name="listingSelector">An instance of IUntypedListingSelector used to filter or select the specific conversations that need their archived status updated.</param>
    /// <returns>Returns the count of filtered messages for a specified user.</returns>
    /// <summary>
    /// Initialize and store dependencies necessary for managing messages, user interactions, and attachments within the messaging system.
    /// </summary>
    /// <param name="messageAttachmentService">Handles the operations related to message attachments, such as adding, removing, or retrieving attachments.</param>
    /// <param name="unitOfWork">Encapsulates a single transactional session, coordinating the work of multiple repositories.</param>
    /// <param name="conversationRepository">Provides methods for accessing and manipulating conversation data in the database.</param>
    /// <param name="messageRepository">Manages the persistence and retrieval of messages from the data store.</param>
    /// <param name="messageAttachmentRepository">Deals with the storage and access of message attachment data.</param>
    /// <param name="userRepository">Responsible for operations related to user data, including getting user details and updating user information.</param>
    /// <param name="correspondantRepository">Handles the data operations for correspondents, which are the participants in a conversation.</param>
    public MessageService(
        IMessageAttachmentService messageAttachmentService,
        IUnitOfWork unitOfWork,
        IConversationRepository conversationRepository,
        IMessageRepository messageRepository,
        IMessageAttachmentRepository messageAttachmentRepository,
        IUserRepository userRepository,
        ICorrespondantRepository correspondantRepository
    )
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
    /// Retrieve the date of the last message for a specific conversation, excluding messages from a specified user.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which the last message date is to be retrieved, excluding messages sent by the specified user.</param>
    /// <param name="userId">The unique identifier of the user whose messages should be excluded when retrieving the last message date of the specified conversation.</param>
    /// <returns>Returns the date of the last message, excluding the specified user's messages.</returns>
    public async Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId)
    {
        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    }

    /// <summary>
    /// Count the filtered messages within a specified conversation based on given criteria.
    /// </summary>
    /// <param name="conversationId">An integer representing the unique identifier of the conversation for which the messages will be filtered and counted.</param>
    /// <param name="listingSelector">An optional parameter of type IUntypedListingSelector used to specify the filter criteria for selecting messages within the conversation. If not provided, all messages in the conversation will be counted.</param>
    /// <returns>Returns the number of filtered messages in a specified conversation.</returns>
    public async Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null)
    {
        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector);
    }

    /// <summary>
    /// Retrieve the count of unread messages for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose unread message count is to be fetched.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <returns>Returns the number of unread messages for a user at a school.</returns>
    public async Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId)
    {
        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto();
    }

    /// <summary>
    /// Retrieve messages in a paginated format for a specified conversation if the user is a participant.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which messages are being paginated.</param>
    /// <param name="userId">The unique identifier of the user whose archived status is to be updated.</param>
    /// <param name="schoolIds">A list containing unique identifiers of the schools associated with the user or conversation.</param>
    /// <param name="pageNumber">The page number to retrieve in the paginated set of messages.</param>
    /// <param name="pageSize">The number of messages to include in each page of the paginated results.</param>
    /// <returns>Returns a paginated list of messages for a specific conversation.</returns>
    public async Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize)
    {
        var conversation = await _conversationRepository.GetConversationByIdAsync(conversationId);

        Guard.Against.Null(conversation, ErrorCode.Api.Lms.Messenger.DataValidation.Query.Conversation.NotFoundById, paramsValues: conversationId.ToString());

        var conversationUserIds = await _conversationRepository.GetCorrespondantsUserIdsByConversationIdAsync(conversationId);

        Guard.Against.False(conversationUserIds.Contains(userId), ErrorCode.Api.Lms.Messenger.DataValidation.Query.Conversation.UserNotInCorrespondants, paramsValues: new string[] { userId.ToString(), conversationId.ToString() });

        // Get total
        var total = await CountFilteredMessagesByConversationIdAsync(conversationId);

        var take = pageSize;
        var skip = (pageNumber - 1) * take;

        IEnumerable<IMessageRIto> messages = Enumerable.Empty<IMessageRIto>();

        if (total > 0)
        {
            messages = (await _messageRepository.GetPaginatedMessagesByConversationIdAsync(conversationId, skip, take));
        }

        var usersIds = messages.Select(m => m.SenderCorrespondant.UserId).Distinct().ToList();

        var users = await _userRepository.GetUsersByIdsAsync(usersIds);

        var flattenUploadedFileGuids = messages
            .SelectMany(m =>
            {
                var guids = new List<Guid>();

                guids.AddRange(m.AttachmentsUploadedFiles.Select(a => a.UploadedFileGuid));

                if (m.AudioMessageUploadedFile != null)
                {
                    guids.Add(m.AudioMessageUploadedFile.UploadedFileGuid);
                }

                return guids;
            }).Distinct();

        var flattenMessageAttachements = await _messageAttachmentService.GetMultipleMessageAttachmentbyGuidsAsync(flattenUploadedFileGuids);

        var currentUser = await _userRepository.GetUserByIdAsync(userId);
        Guard.Against.Null(currentUser, ErrorCode.Api.Lms.Messenger.DataValidation.Query.User.NotFoundById, paramsValues: userId.ToString());

        // pagined data
        var paginedData = new PaginedData<IMessageRAto>
        {
            Data = messages.Select(m => m.ToAto(users.Single(u => u.Id == m.SenderCorrespondant.UserId), currentUser, flattenMessageAttachements)),
            PageNumber = pageNumber,
            PageSize = pageSize,
            Total = total,
        };

        return paginedData;
    }

    /// <summary>
    /// Add a new message by the specified user.
    /// </summary>
    /// <param name="messageWAto">An instance of the IMessageWAto interface, representing the message details and relevant data needed to update the archived status for the specified user.</param>
    /// <param name="enableNotification">A boolean flag indicating whether notifications should be enabled for this operation. Defaults to true.</param>
    /// <returns>Returns a Task representing the asynchronous operation status.</returns>
    public async Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true)
    {
        int messageCreatedId;
        var currentUser = await _userRepository.GetUserByIdAsync(messageWAto.UserId);

        await _unitOfWork.RegisterRepositoryAsync(_messageRepository);
        await _unitOfWork.RegisterRepositoryAsync(_messageAttachmentRepository);
        await _unitOfWork.RegisterRepositoryAsync(_correspondantRepository);

        try
        {
            var conversationCorrespondants = (await _conversationRepository.GetCorrespondantsByConversationIdAsync(messageWAto.ConversationId));

            Guard.Against.False(conversationCorrespondants.Any(corr => corr.UserId == messageWAto.UserId), ErrorCode.Api.Lms.Messenger.DataValidation.Query.Correspondant.MissingCorrespondantForMessageSender, paramsValues: messageWAto.UserId.ToString());

            var senderCorrespondantId = conversationCorrespondants.First(corr => corr.UserId == messageWAto.UserId).CorrespondantId;

            var messageWIto = MessageWIto.Create(messageWAto.ConversationId, senderCorrespondantId, messageWAto.MessageContent);

            var messageRIto = await _messageRepository.AddMessageAsync(messageWIto, currentUser.Email);

            await _messageAttachmentService.AddMessageAttachmentsAsync(messageRIto.Id, messageWAto.AttachmentsUploadedFilesGuids, messageWAto.AudioMessageGuid, currentUser.Email);

            await _correspondantRepository.UpdateIsArchivedForAllCorrespondantsByConversationsIdsAsync(new int[] { messageWAto.ConversationId }, false, currentUser.Email);

            messageCreatedId = messageRIto.Id;

            await _unitOfWork.CommitAsync();
        }
        catch (Exception)
        {
            await _unitOfWork.RollbackAsync();
            throw;
        }

        var guids = messageWAto.AttachmentsUploadedFilesGuids.ToList();
        if (messageWAto.AudioMessageGuid != null)
        {
            guids.Add((Guid)messageWAto.AudioMessageGuid);
        }

        var flattenMessageAttachements = await _messageAttachmentService.GetMultipleMessageAttachmentbyGuidsAsync(guids);

        var message = (await _messageRepository.GetMessageByIdAsync(messageCreatedId)).ToAto(currentUser, currentUser, flattenMessageAttachements);

        if (enableNotification)
        {
            BackgroundJob.Enqueue<INotificationService>(service => service.SendNewMessageWebsocketsEventAsync(message.Id));

            BackgroundJob.Enqueue<INotificationService>(service => service.SendNewMessageNotificationAsync(message.Id));
        }

        return message;
    }

    /// <summary>
    /// Retrieve a message by its identifier and gather details about relevant users and attachments.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message that needs to be retrieved. This ID corresponds to a specific message within a given conversation.</param>
    /// <param name="currentUserId">The unique identifier of the current user requesting the message. This ID is used to determine the user's permissions and access rights to the message.</param>
    /// <returns>Returns a message with user and attachment details based on the provided identifiers.</returns>
    public async Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId)
    {
        var messageRIto = await _messageRepository.GetMessageByIdAsync(messageId);

        var currentUser = await _userRepository.GetUserByIdAsync(currentUserId);

        var user = await _userRepository.GetUserByIdAsync(messageRIto.SenderCorrespondant.UserId);

        var guids = messageRIto.AttachmentsUploadedFiles.Select(a => a.UploadedFileGuid).ToList();
        if (messageRIto.AudioMessageUploadedFile != null)
        {
            guids.Add(messageRIto.AudioMessageUploadedFile.UploadedFileGuid);
        }

        var flattenMessageAttachements = await _messageAttachmentService.GetMultipleMessageAttachmentbyGuidsAsync(guids);

        return messageRIto.ToAto(user, currentUser, flattenMessageAttachements);
    }

    /// <summary>
    /// Update the archived status for a specified user by a list of conversation IDs.
    /// </summary>
    /// <param name="conversationIds">An array of integers representing the IDs of the conversations that need to be updated.</param>
    /// <param name="archived">A boolean value indicating the new archived status to be set for the specified conversations. If true, the conversations will be marked as archived; otherwise, they will be marked as unarchived.</param>
    /// <param name="userId">An integer representing the ID of the user for whom the archived status will be updated.</param>
    public async Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId)
    {
        var conversations = await _conversationRepository.GetConversationsByConversationIdsAndUserIdAsync(conversationIds, userId);
                
        List<string> conversationsIdsWhereUserIdDontBelongs = new();

        foreach (var conversation in conversations)
        {
            var correspondants = await _conversationRepository.GetCorrespondantsByConversationIdAsync(conversation.Id);
            if (!correspondants.Any(cor => cor.UserId == userId))
                conversationsIdsWhereUserIdDontBelongs.Add(conversation.Id.ToString());
        }

        // Check if the user belongs to all the conversations he want to update
        Guard.Against.NotEmpty(
            conversationsIdsWhereUserIdDontBelongs, 
            ErrorCode.Api.Lms.Messenger.DataValidation.Command.Conversation.Archive.MissingRightOnEntity, 
            paramsValues: string.Join(", ", conversationsIdsWhereUserIdDontBelongs));
 
        // Check if the number of records persisted in the database correspond to the number of conversations to update
        Guard.Against.NotEqual(conversationIds.Count(), conversations.Count(), ErrorCode.Api.Lms.Messenger.DataValidation.Command.Conversation.Archive.WrongEntityCount);

        var currentUser = await _userRepository.GetUserByIdAsync(userId);

        await _correspondantRepository.UpdateIsArchivedForUserIdByConversationsIdsAsync(conversationIds, userId, archived, currentUser.Email);
    }
}