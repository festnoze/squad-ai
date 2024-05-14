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
    /// Count the number of messages that match specific filters and sorting criteria based on a user and related schools.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whose conversations the archival status will be updated.</param>
    /// <param name="schoolsIds">A collection of school identifiers where the user’s conversations are associated and will be considered when updating archival status.</param>
    /// <param name="listingSelector">An untyped listing selector used to specify additional criteria or filters for selecting the conversations to update.</param>
    /// <returns>Returns the count of filtered, sorted messages based on specified user and schools.</returns>
    /// <summary>
    /// Initialize resources and repositories related to messaging, user, and conversation management.
    /// </summary>
    /// <param name="messageAttachmentService">An interface providing access to operations related to message attachments, such as saving or retrieving file attachments associated with messages.</param>
    /// <param name="unitOfWork">An interface used to group together multiple operations—such as updates or deletions on different repositories—into a single transaction, to ensure all operations either complete successfully or are rolled back if an error occurs.</param>
    /// <param name="conversationRepository">An interface allowing access and manipulation of conversation-related data. It typically includes methods to query, update, delete, or add new conversation records in the database.</param>
    /// <param name="messageRepository">An interface used for managing message data access. This repository would especially handle CRUD operations—creating, reading, updating, and deleting messages.</param>
    /// <param name="messageAttachmentRepository">An interface designed to handle the specific needs related to accessing and manipulating message attachments stored in the database.</param>
    /// <param name="userRepository">An interface concerned with database operations on user data. It typically provides methods for fetching, updating, and managing user-related information.</param>
    /// <param name="correspondantRepository">An interface focused on managing data access and manipulations related to correspondents of the messages, supporting operations like adding, removing, or updating the records of individuals who correspond within conversations.</param>
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
    /// Retrieve the most recent message's date from a specific conversation, excluding messages from a particular user.
    /// </summary>
    /// <param name="conversationId">A unique identifier for the conversation whose archival status needs to be updated.</param>
    /// <param name="userId">The identifier of the user for whom the conversation's archival status should not be updated.</param>
    /// <returns>Returns the date of the latest message in a conversation, excluding those from a specified user.</returns>
    public async Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId)
    {
        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    }

    /// <summary>
    /// Count the number of messages in a specific conversation that meet certain criteria.
    /// </summary>
    /// <param name="conversationId">An integer that uniquely identifies a conversation. This ID is used to specify which conversation the method should focus on when updating archival status.</param>
    /// <param name="listingSelector">An optional parameter of type IUntypedListingSelector that allows the method to filter which messages within the specified conversation should be considered for archival status update. If null, all messages in the conversation may be considered.</param>
    /// <returns>Returns the count of specified filtered messages within a given conversation.</returns>
    public async Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null)
    {
        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector);
    }

    /// <summary>
    /// Count unread messages for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This ID is used to locate and differentiate the particular user whose archival status of conversations needs to be updated.</param>
    /// <param name="schoolId">The unique identifier for the school. This ID is used to ensure that the archival update of conversations is specific to conversations associated with this school, connected to the user identified by userId.</param>
    /// <returns>Returns the count of unread messages for a specific user at a specified school.</returns>
    public async Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId)
    {
        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto();
    }

    /// <summary>
    /// Retrieve messages in a conversation for a specific user, verifying first that the conversation exists and that the user is a participant in it.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation whose messages are to be paginated and fetched.</param>
    /// <param name="userId">The identifier of the user for whom the archival status of conversations is being updated.</param>
    /// <param name="schoolIds">A list of school identifiers which may be used to filter or determine the conversations relevant to those schools.</param>
    /// <param name="pageNumber">The number of the page in the paginated result set that is being requested.</param>
    /// <param name="pageSize">The number of items per page in the paginated result set.</param>
    /// <returns>Returns paginated messages from a verified, specific conversation and user.</returns>
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
    /// Add a new message to the database for a specified user and ensure associated repositories such as message, message attachment, and correspondent are registered beforehand.
    /// </summary>
    /// <param name="messageWAto">An instance of IMessageWAto representing the message to be archived, containing details about the message and its associated conversation specific to a user.</param>
    /// <param name="enableNotification">A boolean flag indicating whether to enable notifications when the archival status is updated. Defaults to true, enabling notifications unless specified otherwise.</param>
    /// <returns>Returns a Task representing the asynchronous operation of adding a message to the database.</returns>
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
    /// Retrieve a specific message using its identifier, including the details of the sender and any associated audio or file attachments.
    /// </summary>
    /// <param name="messageId">An integer representing the unique identifier of the message whose archival status needs to be updated. This ID ensures that the specific message is correctly located and processed within the method.</param>
    /// <param name="currentUserId">An integer that identifies the current user making the request to update the archival status. This parameter is necessary to verify that the user has the appropriate permissions to modify the archival status and to ensure that the changes are attributed to the correct user account.</param>
    /// <returns>Returns the detailed message data including sender and attachments, identified by a unique ID.</returns>
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
    /// Update the archival status of conversations specific to a user, based on a list of conversation IDs.
    /// </summary>
    /// <param name="conversationIds">An array of integers representing the unique identifiers of the conversations that are to be updated for their archival status.</param>
    /// <param name="archived">A boolean value indicating whether the conversations should be marked as archived (true) or unarchived (false).</param>
    /// <param name="userId">An integer representing the unique identifier of the user for whom the archival status of the conversations is being updated.</param>
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