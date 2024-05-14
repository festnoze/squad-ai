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
    /// This task involves counting and sorting messages based on a specific filter and criteria for a particular user ID, school IDs, and listing selector.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the messages will be counted and sorted.</param>
    /// <param name="schoolsIds">A collection of school IDs for which the messages will be counted and sorted.</param>
    /// <param name="listingSelector">The selector used to filter and sort the messages based on specific criteria.</param>
    /// <returns>Returns the count of messages after filtering and sorting based on specific criteria.</returns>
    /// <summary>
    /// The method initializes the MessageService class by assigning values to dependencies and repositories.
    /// </summary>
    /// <param name="messageAttachmentService">An instance of the IMessageAttachmentService interface that provides methods for managing message attachments.</param>
    /// <param name="unitOfWork">An instance of the IUnitOfWork interface that represents a unit of work for database operations.</param>
    /// <param name="conversationRepository">An instance of the IConversationRepository interface that provides methods for accessing conversation data.</param>
    /// <param name="messageRepository">An instance of the IMessageRepository interface that provides methods for accessing message data.</param>
    /// <param name="messageAttachmentRepository">An instance of the IMessageAttachmentRepository interface that provides methods for accessing message attachment data.</param>
    /// <param name="userRepository">An instance of the IUserRepository interface that provides methods for accessing user data.</param>
    /// <param name="correspondantRepository">An instance of the ICorrespondantRepository interface that provides methods for accessing correspondant data.</param>
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
    /// This task involves finding the most recent message date in a conversation, while excluding a particular user.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which to find the most recent message date.</param>
    /// <param name="userId">The ID of the user to exclude while finding the most recent message date.</param>
    /// <returns>Returns the most recent message date in a conversation, excluding a particular user.</returns>
    public async Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId)
    {
        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    }

    /// <summary>
    /// This task involves counting the number of filtered messages based on conversation ID in an asynchronous manner.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which the filtered messages will be counted. It should be of type 'int'.</param>
    /// <param name="listingSelector">An optional parameter of type 'IUntypedListingSelector'. It represents the selector used to filter the messages. If not provided, the default value is 'null'.</param>
    /// <returns>Returns the count of filtered messages based on conversation ID in an asynchronous manner.</returns>
    public async Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null)
    {
        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector);
    }

    /// <summary>
    /// This task involves retrieving the number of unread messages for a particular user and school.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the unread message count is being retrieved. It should be an integer value.</param>
    /// <param name="schoolId">The ID of the school for which the unread message count is being retrieved. It should be an integer value.</param>
    /// <returns>Returns the number of unread messages for a specific user and school.</returns>
    public async Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId)
    {
        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto();
    }

    /// <summary>
    /// This function allows users to retrieve messages for a conversation by its ID in a paginated format.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which messages will be retrieved. It should be an integer.</param>
    /// <param name="userId">The ID of the user who wants to retrieve the messages. It should be an integer.</param>
    /// <param name="schoolIds">A list of IDs representing the schools. It should be a list of integers.</param>
    /// <param name="pageNumber">The page number of the paginated results. It should be an integer.</param>
    /// <param name="pageSize">The number of messages to be displayed per page. It should be an integer.</param>
    /// <returns>Returns a paginated list of messages for a conversation.</returns>
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
    /// The task is to create and add a new message in an asynchronous manner.
    /// </summary>
    /// <param name="messageWAto">The message to be added. It should be of type IMessageWAto.</param>
    /// <param name="enableNotification">Indicates whether to enable notifications for the new message. It is optional and defaults to true.</param>
    /// <returns>Returns a task representing the asynchronous operation of creating and adding a new message.</returns>
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
    /// This task involves retrieving a message by its ID asynchronously. Additionally, it requires retrieving information about the current user and the sender of the message. The task also involves obtaining the GUIDs of any attachments and checking if there is an audio message attached.
    /// </summary>
    /// <param name="messageId">The ID of the message to retrieve.</param>
    /// <param name="currentUserId">The ID of the current user.</param>
    /// <returns>Returns a message with information about the current user and sender, attachments, and audio.</returns>
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
    /// This statement suggests retrieving conversations based on conversation IDs and user ID, and then identifying the conversation IDs where the user is not a participant.
    /// </summary>
    /// <param name="conversationIds">An array of integers representing the conversation IDs.</param>
    /// <param name="archived">A boolean value indicating whether the conversations should be archived.</param>
    /// <param name="userId">An integer representing the user ID.</param>
    /// <returns>Returns a boolean value indicating whether the update of isArchived was successful.</returns>
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