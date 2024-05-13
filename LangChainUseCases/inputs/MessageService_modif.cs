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
    /// This task involves counting the number of messages that meet specific criteria for a user ID, school IDs, and listing selector.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the messages will be counted. It should be an integer value.</param>
    /// <param name="schoolsIds">A collection of school IDs for which the messages will be counted. It should be a list of integers.</param>
    /// <param name="listingSelector">The selector used to filter the messages based on specific criteria. It should be an untyped listing selector.</param>
    /// <returns>Returns the number of messages that meet specific criteria for a user ID, school IDs, and listing selector.</returns>
    /// <summary>
    /// To create an instance of the MessageService class, its dependencies need to be initialized.
    /// </summary>
    /// <param name="messageAttachmentService">An instance of the IMessageAttachmentService interface that provides methods for managing message attachments.</param>
    /// <param name="unitOfWork">An instance of the IUnitOfWork interface that represents a unit of work for database operations.</param>
    /// <param name="conversationRepository">An instance of the IConversationRepository interface that provides methods for managing conversations.</param>
    /// <param name="messageRepository">An instance of the IMessageRepository interface that provides methods for managing messages.</param>
    /// <param name="messageAttachmentRepository">An instance of the IMessageAttachmentRepository interface that provides methods for managing message attachments.</param>
    /// <param name="userRepository">An instance of the IUserRepository interface that provides methods for managing users.</param>
    /// <param name="correspondantRepository">An instance of the ICorrespondantRepository interface that provides methods for managing correspondants.</param>
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
    /// This method retrieves paginated messages for a conversation by its ID. It checks if the conversation exists and if the specified user is one of the correspondents.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which to retrieve paginated messages. It should be an integer.</param>
    /// <param name="userId">The ID of the user who is requesting the paginated messages. It should be an integer.</param>
    /// <param name="schoolIds">A list of school IDs. It should be a list of integers.</param>
    /// <param name="pageNumber">The page number of the paginated messages. It should be an integer.</param>
    /// <param name="pageSize">The number of messages per page in the paginated result. It should be an integer.</param>
    /// <returns>Returns a paginated list of messages for a conversation by its ID.</returns>
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
    /// This statement is instructing to create and add a new message asynchronously, including the user ID and any attachments or correspondents.
    /// </summary>
    /// <param name="IMessageWAto messageWAto">The message object that contains the details of the message to be added.</param>
    /// <param name="bool enableNotification">A flag indicating whether to enable notifications for the added message. Default value is true.</param>
    /// <returns>Returns void.</returns>
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
    /// This task involves retrieving a message by its ID asynchronously, obtaining information about the current user and the sender of the message, and retrieving the GUIDs of any attachments.
    /// </summary>
    /// <param name="messageId">The ID of the message to retrieve.</param>
    /// <param name="currentUserId">The ID of the current user.</param>
    /// <returns>Returns a message object with information about the user, sender, and attachments.</returns>
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
    /// This method updates the 'IsArchived' status for a specific user in conversations identified by their IDs. It retrieves the conversations and user ID, and then iterates through each conversation to update the status.
    /// </summary>
    /// <param name="conversationIds">An array of integers representing the IDs of the conversations.</param>
    /// <param name="archived">A boolean value indicating whether the conversations should be archived or not.</param>
    /// <param name="userId">An integer representing the ID of the user.</param>
    /// <returns>Returns a boolean value indicating the success of updating the 'IsArchived' status.</returns>
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